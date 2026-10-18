import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main


class FakeRequest:
    def __init__(self, content_type, body=b"", payload=None):
        self.headers = {"content-type": content_type}
        self._body = body
        self._payload = payload

    async def body(self):
        return self._body

    async def json(self):
        return self._payload


class AudioPredictionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.database = Mock()
        self.database.query.return_value.all.return_value = []
        self.database.refresh.side_effect = (
            lambda detection: setattr(detection, "id", 1)
        )

    def test_model_output_dimension_matches_class_labels(self):
        self.assertEqual(main.ai_model.output_shape[-1], len(main.class_names))

    def test_every_model_class_has_complete_metadata(self):
        self.assertEqual(len(main.class_names), 47)
        self.assertEqual(len(main.common_names), 47)
        self.assertEqual(len(main.MODEL_SPECIES_METADATA), 47)

        for model_class, common_name in zip(main.class_names, main.common_names):
            with self.subTest(model_class=model_class):
                key = main._normalize_pest_label(model_class)
                metadata = main.MODEL_SPECIES_METADATA[key]
                self.assertEqual(metadata["model_class"], model_class)
                self.assertEqual(metadata["common_name"], common_name)
                self.assertIn(metadata["risk"], {"LOW", "MEDIUM", "HIGH", "UNKNOWN"})
                self.assertTrue(metadata["risk_rationale"].strip())
                self.assertTrue(metadata["source_url"].startswith("https://"))
                self.assertIsInstance(metadata["affected_crops"], list)

    def test_scientific_name_matching_normalizes_class_formatting(self):
        resolved = main._resolve_species_metadata(
            " COMMON_field__grasshopper ",
            self.database,
        )

        self.assertEqual(resolved["common_name"], "Common Field Grasshopper")
        self.assertEqual(
            resolved["scientific_name"],
            "Chorthippus brunneus",
        )

    def test_unrated_prediction_is_safe_for_unknown_species(self):
        resolved = main._resolve_species_metadata(
            "unrecognized insect",
            self.database,
        )

        self.assertEqual(resolved["common_name"], "unrecognized insect")
        self.assertIsNone(resolved["scientific_name"])
        self.assertEqual(resolved["risk"], "UNKNOWN")

    def test_valid_model_risk_wins_over_blank_catalog_risk(self):
        model_class = main.class_names[0]
        key = main._normalize_pest_label(model_class)
        metadata = main.MODEL_SPECIES_METADATA_BY_NAME[key]
        original_risk = metadata["risk"]
        metadata["risk"] = "HIGH"
        try:
            with patch.object(
                main,
                "_find_pest_record_normalized",
                return_value=Mock(risk="  "),
            ):
                resolved = main._resolve_species_metadata(model_class, self.database)
            self.assertEqual(resolved["risk"], "HIGH")
        finally:
            metadata["risk"] = original_risk

    def test_signed_pcm16_is_decoded_to_the_training_float_range(self):
        samples = np.array([-32768, 32767] * 8000, dtype="<i2")

        decoded = main.decode_audio_samples(samples)

        self.assertEqual(decoded.dtype, np.float32)
        self.assertEqual(decoded[0], -1.0)
        self.assertAlmostEqual(decoded[1], 32767 / 32768)

    def test_silence_and_quantization_floor_are_rejected(self):
        silence = np.zeros(16000, dtype=np.int16)
        dc_offset = np.full(16000, 2, dtype=np.int16)
        below_floor = np.full(
            16000, main.PCM16_RMS_FLOOR / 2, dtype=np.float32
        )

        for audio in (silence, dc_offset, below_floor):
            with self.subTest(audio=audio.dtype):
                with self.assertRaises(HTTPException) as raised:
                    main.decode_audio_samples(audio)
                self.assertEqual(raised.exception.status_code, 422)

    def test_silent_pcm_is_rejected_by_the_prediction_endpoint(self):
        audio = np.zeros(80000, dtype="<i2")
        request = FakeRequest(
            "application/octet-stream",
            body=audio.tobytes(),
        )

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.ai_predict(request))

        self.assertEqual(raised.exception.status_code, 422)

    def test_valid_pcm_uses_training_cnn_shape(self):
        audio = np.tile(
            np.array([-800, 800], dtype=np.int16),
            40000,
        )
        scores = np.full(len(main.class_names), 1 / len(main.class_names))

        with patch.object(main.ai_model, "predict", return_value=[scores]) as predict:
            main.predict_pest(audio)

        features = predict.call_args.args[0].numpy()
        self.assertEqual(features.shape, (1, 155, 128, 1))

    def test_prediction_inference_is_dispatched_off_the_async_event_loop(self):
        audio = [1, -1]
        request = FakeRequest(
            "application/json",
            payload={"audio": audio},
        )
        result = {"pest": main.class_names[0], "confidence": 0.8}

        with patch.object(
            main.asyncio,
            "to_thread",
            new_callable=AsyncMock,
            return_value=result,
        ) as to_thread:
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        to_thread.assert_awaited_once_with(main.predict_pest, audio)
        self.assertEqual(response["pest"], main.class_names[0])
        self.assertEqual(response["status"], "UNKNOWN")

    def test_valid_json_pcm_preserves_prediction_response_contract(self):
        audio = np.tile(
            np.array([-800, 800], dtype=np.int16),
            40000,
        )
        request = FakeRequest(
            "application/json",
            payload={"audio": audio.tolist()},
        )

        response = asyncio.run(main.ai_predict(request, db=self.database))

        self.assertEqual(
            {
                "status",
                "identification_status",
                "identification_label",
                "pest",
                "common_name",
                "scientific_name",
                "confidence",
                "risk",
                "risk_rationale",
                "affected_crops",
                "metadata_source_name",
                "metadata_source_url",
                "message",
                "source",
                "id",
                "device_id",
                "temperature",
                "humidity",
                "audio_file",
                "detected_at",
            },
            set(response),
        )
        self.assertEqual(response["status"], "UNKNOWN")
        self.assertIn(response["pest"], main.class_names)
        self.assertEqual(
            response["identification_label"], "Possible match"
        )
        self.assertEqual(
            response["message"], "Unverified model prediction"
        )
        self.assertGreaterEqual(response["confidence"], 0)
        self.assertLessEqual(response["confidence"], 1)

    def test_ai_prediction_is_persisted_before_broadcast(self):
        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )
        candidate_result = {"pest": main.class_names[0], "confidence": 0.8}

        with (
            patch.object(
                main,
                "predict_pest",
                return_value=candidate_result,
            ),
            patch.object(
                main.manager,
                "broadcast",
                new_callable=AsyncMock,
            ) as broadcast,
        ):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        detection = self.database.add.call_args.args[0]
        self.assertEqual(detection.status, "UNKNOWN")
        self.assertEqual(detection.pest, main.class_names[0])
        self.assertEqual(detection.risk, main._resolve_species_metadata(main.class_names[0])["risk"])
        self.assertEqual(response["common_name"], detection.common_name)
        self.assertEqual(response["risk"], detection.risk)
        self.assertEqual(detection.message, "Unverified model prediction")
        self.database.commit.assert_called_once()
        self.database.refresh.assert_called_once_with(detection)
        broadcast.assert_awaited_once_with(response)
        self.assertEqual(response["id"], detection.id)

    def test_ai_prediction_uses_catalog_risk_without_verifying_identity(self):
        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )
        candidate_result = {"pest": main.class_names[0], "confidence": 0.8}
        pest_record = Mock(risk=" high ")

        with (
            patch.object(
                main,
                "predict_pest",
                return_value=candidate_result,
            ),
            patch.object(
                main,
                "_find_pest_record_normalized",
                return_value=pest_record,
            ) as find_pest,
            patch.object(
                main.manager,
                "broadcast",
                new_callable=AsyncMock,
            ) as broadcast,
        ):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        detection = self.database.add.call_args.args[0]
        find_pest.assert_called_once_with(self.database, main.class_names[0])
        self.assertEqual(response["identification_status"], "UNCONFIRMED")
        self.assertEqual(response["risk"], "HIGH")
        self.assertEqual(detection.risk, "HIGH")
        broadcast.assert_awaited_once_with(response)

    def test_prediction_metadata_is_identical_in_database_and_websocket(self):
        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )
        with (
            patch.object(
                main,
                "predict_pest",
                return_value={"pest": main.class_names[0], "confidence": 0.81},
            ),
            patch.object(
                main.manager,
                "broadcast",
                new_callable=AsyncMock,
            ) as broadcast,
        ):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        detection = self.database.add.call_args.args[0]
        self.assertEqual(response["common_name"], detection.common_name)
        self.assertEqual(response["scientific_name"], detection.scientific_name)
        self.assertEqual(response["risk"], detection.risk)
        self.assertEqual(response["risk_rationale"], detection.risk_rationale)
        self.assertEqual(
            response["affected_crops"],
            json.loads(detection.affected_crops),
        )
        broadcast.assert_awaited_once_with(response)


    def test_model_class_index_maps_to_candidate_label(self):
        audio = np.tile(
            np.array([-800, 800], dtype=np.int16),
            40000,
        )
        scores = np.zeros(len(main.class_names), dtype=np.float32)
        selected_index = 17
        expected_label = main.class_names[selected_index]
        scores[selected_index] = 0.983

        with patch.object(main.ai_model, "predict", return_value=[scores]):
            result = main.predict_pest(audio)

        self.assertEqual(result["pest"], expected_label)
        self.assertAlmostEqual(result["confidence"], 0.983, places=5)

    def test_model_output_with_wrong_class_count_is_rejected(self):
        audio = np.tile(
            np.array([-800, 800], dtype=np.int16),
            40000,
        )
        wrong_output = np.zeros(len(main.class_names) - 1, dtype=np.float32)

        with (
            patch.object(main.ai_model, "predict", return_value=[wrong_output]),
            self.assertRaisesRegex(
                RuntimeError,
                "Model output does not match the class labels",
            ),
        ):
            main.predict_pest(audio)

    def test_low_level_background_noise_is_rejected(self):
        audio = np.random.default_rng(1).integers(
            -4, 5, size=80000, dtype=np.int16
        )
        request = FakeRequest(
            "application/octet-stream",
            body=audio.tobytes(),
        )

        with self.assertRaises(main.HTTPException) as context:
            asyncio.run(main.ai_predict(request, db=self.database))

        self.assertEqual(context.exception.status_code, 422)
    def test_low_score_prediction_is_kept_as_an_unverified_possible_match(self):
        request = FakeRequest("application/json", payload={"audio": []})
        candidate_result = {
            "pest": main.class_names[17],
            "confidence": 0.2,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        self.assertEqual(response["pest"], main.class_names[17])
        self.assertEqual(response["identification_label"], "Possible match")
        self.assertEqual(response["message"], "Unverified model prediction")
        self.assertEqual(response["confidence"], 0.2)

    def test_malformed_pcm_and_json_audio_are_rejected(self):
        malformed_pcm = FakeRequest("application/octet-stream", b"\x00")
        malformed_json = FakeRequest(
            "application/json",
            payload={"audio": [[0.1, 0.2]]},
        )

        for request in (malformed_pcm, malformed_json):
            with self.subTest(content_type=request.headers["content-type"]):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(main.ai_predict(request))
                self.assertEqual(raised.exception.status_code, 400)

    def test_high_model_score_keeps_class_as_unverified_suggestion(self):
        request = FakeRequest("application/json", payload={"audio": []})
        candidate_result = {
            "pest": main.class_names[0],
            "confidence": 0.99,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        self.assertEqual(response["status"], "UNKNOWN")
        self.assertEqual(response["pest"], main.class_names[0])
        self.assertEqual(response["confidence"], 0.99)
        self.assertEqual(response["risk"], main._resolve_species_metadata(main.class_names[0])["risk"])

    def test_every_model_class_is_retained_as_unverified_at_low_and_high_scores(self):
        request = FakeRequest("application/json", payload={"audio": []})

        for pest in main.class_names:
            for confidence in (0.2, 0.99):
                candidate_result = {
                    "pest": pest,
                    "confidence": confidence,
                }
                with self.subTest(pest=pest, confidence=confidence):
                    with patch.object(
                        main,
                        "predict_pest",
                        return_value=candidate_result,
                    ):
                        response = asyncio.run(
                            main.ai_predict(request, db=self.database)
                        )

                    self.assertEqual(response["status"], "UNKNOWN")
                    self.assertEqual(response["pest"], pest)
                    self.assertEqual(
                        response["identification_label"], "Possible match"
                    )
                    self.assertEqual(
                        response["message"], "Unverified model prediction"
                    )
                    self.assertEqual(response["confidence"], confidence)
                    metadata = main.MODEL_SPECIES_METADATA[
                        main._normalize_pest_label(pest)
                    ]
                    self.assertEqual(response["risk"], metadata["risk"])

    def test_unrecognized_model_label_does_not_crash_prediction_endpoint(self):
        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )
        with patch.object(
            main,
            "predict_pest",
            return_value={"pest": "not-a-model-class", "confidence": 0.4},
        ):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        self.assertIsNone(response["pest"])
        self.assertEqual(response["risk"], "UNKNOWN")

    def test_serialized_low_confidence_record_is_explicitly_unconfirmed(self):
        detection = Mock(
            id=4,
            device_id="FIELD-UNIT-01",
            status="UNKNOWN",
            pest=None,
            scientific_name=None,
            common_name=None,
            confidence=0.632,
            risk="UNKNOWN",
            risk_rationale=None,
            affected_crops="[]",
            metadata_source_name=None,
            metadata_source_url=None,
            temperature=None,
            humidity=None,
            audio_file=None,
            message="Low-confidence model prediction rejected",
            detected_at=None,
        )

        serialized = main._serialize_detection(detection, None)

        self.assertEqual(serialized["identification_status"], "UNCONFIRMED")
        self.assertEqual(serialized["identification_label"], "Unidentified sound")
        self.assertEqual(serialized["source"], "AI_MODEL_PREDICTION")

    def test_serialized_device_inference_error_is_not_a_detection(self):
        detection = Mock(
            id=5,
            device_id="FIELD-UNIT-01",
            status="UNKNOWN",
            pest=None,
            scientific_name=None,
            common_name=None,
            confidence=0.0,
            risk="UNKNOWN",
            risk_rationale=None,
            affected_crops="[]",
            metadata_source_name=None,
            metadata_source_url=None,
            temperature=None,
            humidity=None,
            audio_file=None,
            message="INFERENCE_ERROR: AI API HTTP 500",
            detected_at=None,
        )

        serialized = main._serialize_detection(detection, None)

        self.assertEqual(serialized["identification_status"], "ERROR")
        self.assertEqual(serialized["identification_label"], "Inference error")

    def test_latest_detection_can_be_scoped_to_a_device(self):
        query = Mock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.first.return_value = None
        database = Mock()
        database.query.return_value = query

        response = main.get_latest_detection(
            device_id="FIELD-UNIT-02",
            db=database,
        )

        self.assertIsNone(response["detection"])
        query.filter.assert_called_once()
        device_filter = query.filter.call_args.args[0]
        self.assertEqual(device_filter.left, main.Detection.device_id)
        self.assertEqual(device_filter.right.value, "FIELD-UNIT-02")

    def test_uncertain_solution_keeps_risk_unknown_even_for_high_score(self):
        payload = main.AISolutionRequest(
            pest="Cicada",
            common_name="Unconfirmed insect",
            risk="HIGH",
            confidence=0.99,
        )

        response = main._fallback_uncertain_solution(payload)

        self.assertEqual(response["risk"], "UNKNOWN")
        self.assertIn(
            "Do not choose or apply a pest-specific pesticide",
            response["pesticide_recommendation"],
        )

    def test_unknown_risk_does_not_allow_specific_solution_with_a_record(self):
        payload = main.AISolutionRequest(
            pest="Cicada",
            common_name="Unconfirmed insect",
            risk="UNKNOWN",
            confidence=0.99,
        )
        verified_record = Mock(
            pest_id="cicada",
            name="Cicada",
            scientific_name="Cicadidae",
            description="",
            symptoms="",
        )

        with patch.object(
            main,
            "_find_verified_pest_record",
            return_value=verified_record,
        ):
            response = asyncio.run(
                main.generate_ai_solution(payload, Mock())
            )

        self.assertEqual(response["risk"], "UNKNOWN")
        self.assertEqual(response["pest"], "Unconfirmed insect")
        self.assertIn(
            "Do not choose or apply a pest-specific pesticide",
            response["pesticide_recommendation"],
        )
        self.assertEqual(
            main.AISolutionResponse(**response).risk,
            "UNKNOWN",
        )

    def test_high_score_and_catalog_match_do_not_verify_a_prediction(self):
        payload = main.AISolutionRequest(
            pest="Cicada",
            common_name="Cicada",
            risk="HIGH",
            confidence=0.99,
            pest_id="cicada",
        )
        catalog_record = Mock(
            pest_id="cicada",
            name="Cicada",
            scientific_name="Cicadidae",
        )

        with patch.object(
            main,
            "_find_verified_pest_record",
            return_value=catalog_record,
        ):
            response = asyncio.run(
                main.generate_ai_solution(payload, Mock())
            )

        self.assertEqual(response["risk"], "UNKNOWN")
        self.assertEqual(response["pest"], "Unconfirmed insect")
        self.assertIn(
            "Do not choose or apply a pest-specific pesticide",
            response["pesticide_recommendation"],
        )

    def test_high_risk_history_is_still_unverified_and_general(self):
        item = Mock(
            id=7,
            detection_id=11,
            device_id="FIELD-UNIT-01",
            pest_id="cicada",
            pest="Cicada",
            image_url=None,
            risk="HIGH",
            confidence=0.99,
            temperature=None,
            humidity=None,
            solution_title="Legacy species-specific title",
            detected_at=None,
            created_at=None,
        )

        response = main._high_risk_solution_history_response(item, Mock())

        self.assertFalse(response["pest_verified"])
        self.assertEqual(response["risk"], "UNKNOWN")
        self.assertEqual(
            response["solution_title"],
            "General Integrated Pest Management Guidance",
        )
        self.assertEqual(response["pest_description"], "")
        self.assertIn(
            "before choosing any species-specific treatment",
            response["recommended_action"],
        )

    def test_supported_classes_without_catalog_records_get_general_guidance(self):
        for pest in (
            "Grasshopper",
            "Migratory locust",
            "termite",
            "Cicada",
        ):
            payload = main.AISolutionRequest(
                pest=pest,
                common_name="Unconfirmed insect",
                risk="HIGH",
                confidence=0.99,
            )

            with self.subTest(pest=pest):
                with patch.object(
                    main,
                    "_find_verified_pest_record",
                    return_value=None,
                ):
                    response = asyncio.run(
                        main.generate_ai_solution(payload, Mock())
                    )

                self.assertEqual(response["risk"], "UNKNOWN")
                self.assertEqual(response["pest"], "Unconfirmed insect")
                self.assertIn(
                    "Do not choose or apply a pest-specific pesticide",
                    response["pesticide_recommendation"],
                )

    def test_unvalidated_device_score_is_not_stored_as_a_pest(self):
        database = Mock()
        database.query.return_value.filter.return_value.first.return_value = None
        payload = main.DetectionCreate(
            device_id="FIELD-UNIT-01",
            status="HARMFUL_PEST",
            pest=main.class_names[0],
            confidence=0.99,
            risk="HIGH",
            temperature=26.2,
            humidity=65.0,
        )

        with patch.object(
            main.manager, "broadcast", new_callable=AsyncMock
        ) as broadcast:
            detection = asyncio.run(main.create_detection(payload, database))

        self.assertEqual(detection.status, "UNKNOWN")
        self.assertEqual(detection.pest, main.class_names[0])
        self.assertEqual(detection.risk, main._resolve_species_metadata(main.class_names[0])["risk"])
        event = broadcast.await_args.args[0]
        self.assertEqual(event["status"], "UNKNOWN")
        self.assertEqual(event["pest"], main.class_names[0])
        self.assertEqual(event["risk"], main._resolve_species_metadata(main.class_names[0])["risk"])
        self.assertEqual(event["temperature"], 26.2)
        self.assertEqual(event["humidity"], 65.0)

    def test_untrained_device_label_is_not_forwarded(self):
        database = Mock()
        database.query.return_value.filter.return_value.first.return_value = None
        payload = main.DetectionCreate(
            device_id="FIELD-UNIT-01",
            status="UNKNOWN",
            pest="Not a trained class",
            confidence=0.99,
            risk="HIGH",
        )

        with patch.object(
            main.manager, "broadcast", new_callable=AsyncMock
        ) as broadcast:
            detection = asyncio.run(main.create_detection(payload, database))

        self.assertEqual(detection.status, "UNKNOWN")
        self.assertIsNone(detection.pest)
        self.assertEqual(detection.risk, "UNKNOWN")
        event = broadcast.await_args.args[0]
        self.assertIsNone(event["pest"])
        self.assertEqual(event["status"], "UNKNOWN")

    def test_non_pest_detection_cannot_trigger_high_risk_alerts(self):
        database = Mock()
        database.query.return_value.filter.return_value.first.return_value = None
        payload = main.DetectionCreate(
            device_id="FIELD-UNIT-01",
            status="NON_PEST",
            pest="Cicada",
            confidence=0.99,
            risk="HIGH",
        )

        with patch.object(main.manager, "broadcast", new_callable=AsyncMock):
            detection = asyncio.run(main.create_detection(payload, database))

        self.assertEqual(detection.status, "NON_PEST")
        self.assertIsNone(detection.pest)
        self.assertEqual(detection.risk, "LOW")


class DetectionHistoryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        main.Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_one_device_event_is_committed_and_returned_once_by_history(self):
        payload = main.DetectionCreate(
            device_id="TEST-FIELD-UNIT",
            status="UNKNOWN",
            pest=main.class_names[0],
            confidence=0.8,
            risk="UNKNOWN",
        )

        with (
            patch.object(
                main.manager, "broadcast", new_callable=AsyncMock
            ) as broadcast,
            patch.object(main, "send_high_risk_sms"),
        ):
            saved = asyncio.run(main.create_detection(payload, self.db))

        history = main.get_detection_history(
            device_id=None,
            status=None,
            limit=50,
            db=self.db,
        )

        self.assertEqual(self.db.query(main.Detection).count(), 1)
        self.assertEqual(len(history["detections"]), 1)
        self.assertEqual(history["detections"][0]["id"], saved.id)
        self.assertEqual(history["detections"][0]["pest"], main.class_names[0])
        self.assertEqual(history["detections"][0]["common_name"], main.common_names[0])
        self.assertEqual(history["detections"][0]["risk"], main._resolve_species_metadata(main.class_names[0])["risk"])
        self.assertEqual(broadcast.await_count, 1)

    def test_ai_metadata_matches_saved_row_latest_history_and_websocket(self):
        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )

        with (
            patch.object(
                main,
                "predict_pest",
                return_value={"pest": main.class_names[0], "confidence": 0.81},
            ),
            patch.object(
                main.manager,
                "broadcast",
                new_callable=AsyncMock,
            ) as broadcast,
        ):
            response = asyncio.run(main.ai_predict(request, db=self.db))

        saved = self.db.query(main.Detection).first()
        latest = main.get_latest_detection(db=self.db)["detection"]
        history = main.get_detection_history(
            device_id=None,
            status=None,
            limit=50,
            db=self.db,
        )["detections"][0]

        for record in (saved, latest, history):
            self.assertEqual(record.common_name if hasattr(record, "common_name") else record["common_name"], response["common_name"])
            self.assertEqual(record.risk if hasattr(record, "risk") else record["risk"], response["risk"])
            self.assertEqual(
                record.scientific_name if hasattr(record, "scientific_name") else record["scientific_name"],
                response["scientific_name"],
            )
        self.assertEqual(
            json.loads(saved.affected_crops),
            response["affected_crops"],
        )
        broadcast.assert_awaited_once_with(response)


if __name__ == "__main__":
    unittest.main()
