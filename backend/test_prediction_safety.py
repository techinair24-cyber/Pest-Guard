import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main

ACTIVE_LABELS = [
    label
    for label in main.MODEL_COMMON_NAMES.values()
    if main._is_active_species_label(label)
]
ACTIVE_COMMON_NAMES = ACTIVE_LABELS


def catalog_records(risk="LOW"):
    return [
        main.Pest(
            pest_id=main._normalize_pest_label(label).replace(" ", "-"),
            name=label,
            scientific_name=f"Test species {index}",
            risk=risk,
            description="Catalog description.",
            symptoms="Catalog symptoms.",
        )
        for index, label in enumerate(ACTIVE_LABELS)
    ]


def real_active_catalog_item():
    return next(
        item
        for item in main.PEST_DATA
        if main._is_active_species_label(item.get("name"))
        and item.get("risk") in {"HIGH", "MEDIUM", "LOW", "NO_RISK"}
    )

def real_high_risk_catalog_item():
    return next(
        item
        for item in main.PEST_DATA
        if main._is_active_species_label(item.get("name"))
        and item.get("risk") == "HIGH"
    )


class _FakeTensor:
    def __init__(self, value):
        self.value = np.asarray(value, dtype=np.float32)

    def numpy(self):
        return self.value


class _FakeModel:
    def __init__(self, probabilities):
        self.probabilities = np.asarray(probabilities, dtype=np.float32)

    def __call__(self, _features, training=False):
        return _FakeTensor(self.probabilities[None, :])


def _prediction_harness(
    *,
    group,
    subtype_label,
    subtype_confidence,
    group_confidence=0.99,
    group_threshold=0.50,
    subtype_threshold=0.50,
    other_label=None,
    verified_labels=None,
):
    source = main._PEST_GUARD_HIERARCHY
    hierarchy = object.__new__(type(source))
    hierarchy.groups = list(source.groups)
    group_probabilities = np.full(
        len(hierarchy.groups),
        (1.0 - group_confidence) / (len(hierarchy.groups) - 1),
        dtype=np.float32,
    )
    group_probabilities[hierarchy.groups.index(group)] = group_confidence
    hierarchy.group_model = _FakeModel(group_probabilities)
    hierarchy.manifest = {
        "group_model": {
            "threshold": {"minimum_confidence": group_threshold},
        },
    }
    hierarchy._features = lambda _waveform: np.zeros((155, 128, 1), dtype=np.float32)
    hierarchy.subtype_manifest = {}
    hierarchy.experts = {}
    hierarchy.verified_subtype_labels = {}
    if subtype_label is not None:
        labels = list(source.subtype_manifest[group]["labels"])
        if subtype_label not in labels:
            labels[0] = subtype_label
        if other_label is not None and other_label not in labels:
            labels[1] = other_label
        subtype_probabilities = np.zeros(len(labels), dtype=np.float32)
        subtype_probabilities[labels.index(subtype_label)] = subtype_confidence
        if other_label is not None:
            subtype_probabilities[labels.index(other_label)] = 1.0 - subtype_confidence
        else:
            remainder = 1.0 - subtype_confidence
            other_indices = [i for i in range(len(labels)) if labels[i] != subtype_label]
            subtype_probabilities[other_indices] = remainder / len(other_indices)
        hierarchy.subtype_manifest[group] = {
            "labels": labels,
            "threshold": {"minimum_confidence": subtype_threshold},
        }
        hierarchy.experts[group] = _FakeModel(subtype_probabilities)
        hierarchy.verified_subtype_labels[group] = (
            set(verified_labels)
            if verified_labels is not None
            else set(source.verified_subtype_labels.get(group, set()))
        )
    return hierarchy


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
        self.database.query.return_value.all.return_value = catalog_records()
        self.database.refresh.side_effect = (
            lambda detection: setattr(detection, "id", 1)
        )

    def test_model_output_dimension_matches_class_labels(self):
        self.assertEqual(
            main._PEST_GUARD_HIERARCHY.groups,
            main._PEST_GUARD_HIERARCHY.manifest["group_labels"],
        )
        self.assertEqual(
            main._PEST_GUARD_HIERARCHY.group_model.output_shape[-1],
            len(main._PEST_GUARD_HIERARCHY.groups),
        )

    def test_only_dataset_mapped_subtypes_are_active_api_labels(self):
        hierarchy = main._PEST_GUARD_HIERARCHY
        mapped = {
            label
            for labels in hierarchy.verified_subtype_labels.values()
            for label in labels
        }
        unmapped = {
            label
            for item in hierarchy.subtype_manifest.values()
            for label in item.get("labels", [])
        } - mapped

        self.assertEqual(len(mapped), 113)
        self.assertEqual(unmapped, {"Mountain Cricket"})
        self.assertTrue(all(
            main._normalize_pest_label(label) not in main._ACTIVE_HIERARCHICAL_LABELS
            for label in unmapped
        ))

    def test_subtype_allowlist_maps_to_actual_dataset_folders(self):
        manifest = main._PEST_GUARD_HIERARCHY.manifest
        dataset_root = Path(manifest["dataset_root"])
        mappings = manifest["dataset_provenance"]["subclass_label_mappings"]
        verified_count = 0
        for group, model_to_dataset in mappings.items():
            folder_names = {
                "".join(character for character in folder.name.casefold() if character.isalnum())
                for folder in (dataset_root / group).iterdir()
                if folder.is_dir()
            }
            for model_label, dataset_label in model_to_dataset.items():
                with self.subTest(group=group, label=model_label):
                    normalize = lambda value: "".join(
                        character for character in value.casefold() if character.isalnum()
                    )
                    self.assertEqual(normalize(model_label), normalize(dataset_label))
                    self.assertIn(normalize(dataset_label), folder_names)
                    verified_count += 1
        self.assertEqual(verified_count, 113)

    def test_verified_subtype_prediction_preserves_subclass_result(self):
        hierarchy = _prediction_harness(
            group="Crickets",
            subtype_label="European tree cricket",
            subtype_confidence=0.99,
        )

        result = hierarchy.predict(np.zeros(80000, dtype=np.float32))

        self.assertEqual(result["pest"], "European tree cricket")
        self.assertEqual(result["identification_label"], "Possible match")
        self.assertAlmostEqual(result["top_predictions"][0]["subtype_confidence"], 0.99)

    def test_unverified_top_subtype_falls_back_to_group(self):
        hierarchy = _prediction_harness(
            group="Cicada",
            subtype_label="Graptopsaltria_nigrofuscata",
            subtype_confidence=0.99,
            verified_labels=set(),
        )

        result = hierarchy.predict(np.zeros(80000, dtype=np.float32))

        self.assertEqual(result["pest"], "Cicada")
        self.assertEqual(result["identification_label"], "Possible group match; subtype label unverified")
        self.assertEqual(result["top_predictions"], [])

    def test_subtype_confidence_rejection_keeps_group_and_only_verified_candidates(self):
        hierarchy = _prediction_harness(
            group="Crickets",
            subtype_label="European tree cricket",
            subtype_confidence=0.60,
            subtype_threshold=0.80,
            other_label="Mediterranean field cricket",
        )

        result = hierarchy.predict(np.zeros(80000, dtype=np.float32))

        self.assertEqual(result["pest"], "Crickets")
        self.assertEqual(result["identification_label"], "Possible group match")
        self.assertIn(
            "European tree cricket",
            [candidate["pest"] for candidate in result["top_predictions"]],
        )
        self.assertTrue(all(
            candidate["pest"] in hierarchy.verified_subtype_labels["Crickets"]
            for candidate in result["top_predictions"]
        ))

    def test_group_confidence_rejection_and_group_only_candidates_are_not_species(self):
        low_group = _prediction_harness(
            group="Crickets",
            subtype_label="European tree cricket",
            subtype_confidence=0.99,
            group_confidence=0.40,
            group_threshold=0.50,
        )
        rejected = low_group.predict(np.zeros(80000, dtype=np.float32))
        self.assertEqual(rejected["pest"], "Crickets")
        self.assertIsNone(rejected["top_predictions"][0]["subtype_confidence"])

        group_only = _prediction_harness(
            group="Beetles",
            subtype_label=None,
            subtype_confidence=1.0,
        )
        fallback = group_only.predict(np.zeros(80000, dtype=np.float32))
        self.assertEqual(fallback["pest"], "Beetles")
        self.assertIsNone(fallback["top_predictions"][0]["subtype_confidence"])

    def test_every_hierarchy_label_maps_to_its_group(self):
        hierarchy = main._PEST_GUARD_HIERARCHY
        self.assertEqual(len(hierarchy.groups), 8)
        self.assertEqual(
            len(ACTIVE_LABELS) + len(hierarchy.groups),
            len(main._ACTIVE_HIERARCHICAL_LABELS),
        )
        for label in ACTIVE_LABELS:
            with self.subTest(label=label):
                self.assertIn(label, [
                    subtype
                    for item in hierarchy.subtype_manifest.values()
                    for subtype in item.get("labels", [])
                ])
                self.assertTrue(main._active_group_for_label(label))

    def test_scientific_name_matching_normalizes_class_formatting(self):
        pest_record = SimpleNamespace(
            name="Common Field Grasshopper",
            scientific_name="Chorthippus brunneus",
            risk="INVALID",
        )
        with patch.object(
            main,
            "_find_pest_record_normalized",
            return_value=pest_record,
        ):
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
        self.assertEqual(resolved["risk"], "LOW")

    def test_unverified_model_label_does_not_supply_catalog_risk(self):
        model_label = ACTIVE_LABELS[0]
        with patch.object(
            main,
            "_find_pest_record_normalized",
            return_value=Mock(risk="  "),
        ):
            resolved = main._resolve_species_metadata(model_label, self.database)
        self.assertEqual(resolved["risk"], "LOW")

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

    def test_valid_pcm_uses_hierarchy_feature_shape(self):
        audio = np.tile(
            np.array([-800, 800], dtype=np.int16),
            40000,
        )
        waveform = main.decode_audio_samples(audio)
        features = main.PestGuardHierarchy._features(waveform)
        self.assertEqual(features.shape, (155, 128, 1))
        self.assertTrue(np.all(np.isfinite(features)))

    def test_prediction_inference_is_dispatched_off_the_async_event_loop(self):
        audio = [1, -1]
        request = FakeRequest(
            "application/json",
            payload={"audio": audio},
        )
        result = {"pest": ACTIVE_LABELS[0], "confidence": 0.8}

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
        self.assertEqual(response["pest"], ACTIVE_LABELS[0])
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
                "insect_group",
                "group_score",
                "top_predictions",
                "broad_group_prediction",
                "broad_group_confidence",
                "broad_group_top_predictions",
                "risk",
                "risk_rationale",
                "affected_crops",
                "metadata_source_name",
                "metadata_source_url",
                "pest_id",
                "pest_verified",
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
        if response["status"] == "HARMFUL_PEST":
            self.assertEqual(
                response["identification_status"], "MODEL_PREDICTED"
            )
            self.assertIn(response["pest"], ACTIVE_LABELS)
            self.assertEqual(
                response["identification_label"], response["common_name"]
            )
            self.assertTrue(response["pest_verified"])
        else:
            self.assertEqual(response["status"], "UNKNOWN")
            self.assertEqual(
                response["identification_status"], "UNCONFIRMED"
            )
        self.assertGreaterEqual(response["confidence"], 0)
        self.assertLessEqual(response["confidence"], 1)

    def test_ai_prediction_is_persisted_before_broadcast(self):
        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )
        candidate_result = {
            "pest": ACTIVE_LABELS[0],
            "confidence": 0.8,
            "insect_group": main.MODEL_SPECIES_GROUPS[
                main._normalize_pest_label(ACTIVE_LABELS[0])
            ],
        }

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
        self.assertEqual(detection.status, "HARMFUL_PEST")
        self.assertEqual(detection.pest, ACTIVE_LABELS[0])
        self.assertEqual(detection.risk, main._resolve_species_metadata(ACTIVE_LABELS[0])["risk"])
        self.assertEqual(response["common_name"], detection.common_name)
        self.assertEqual(response["risk"], detection.risk)
        self.assertEqual(detection.message, "Model-predicted harmful pest")
        self.database.commit.assert_called_once()
        self.database.refresh.assert_called_once_with(detection)
        broadcast.assert_awaited_once_with(response)
        self.assertEqual(response["id"], detection.id)

    def test_ai_prediction_uses_catalog_risk_without_verifying_identity(self):
        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )
        candidate_result = {
            "pest": ACTIVE_LABELS[0],
            "confidence": 0.8,
            "insect_group": main.MODEL_SPECIES_GROUPS[
                main._normalize_pest_label(ACTIVE_LABELS[0])
            ],
        }
        pest_record = SimpleNamespace(
            risk=" high ",
            name=ACTIVE_LABELS[0],
            scientific_name="Test species 0",
            pest_id=main._normalize_pest_label(ACTIVE_LABELS[0]).replace(" ", "-"),
        )

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
        find_pest.assert_any_call(self.database, ACTIVE_LABELS[0])
        self.assertEqual(response["identification_status"], "MODEL_PREDICTED")
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
                return_value={
                    "pest": ACTIVE_LABELS[0],
                    "confidence": 0.81,
                    "insect_group": main.MODEL_SPECIES_GROUPS[
                        main._normalize_pest_label(ACTIVE_LABELS[0])
                    ],
                    "group_score": 0.44,
                    "top_predictions": [
                        {
                            "pest": ACTIVE_LABELS[0],
                            "score": 0.81,
                            "common_name": ACTIVE_COMMON_NAMES[0],
                        }
                    ],
                },
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


    def test_prediction_uses_only_the_loaded_hierarchy(self):
        audio = np.tile(
            np.array([-800, 800], dtype=np.int16),
            40000,
        )
        expected = {"pest": ACTIVE_LABELS[0], "confidence": 0.8}

        with (
            patch.object(main, "_pest_light_gate_score", return_value=1.0),
            patch.object(
                main._PEST_GUARD_HIERARCHY,
                "predict",
                return_value=expected,
            ) as hierarchy_predict,
        ):
            result = main.predict_pest(audio)

        hierarchy_predict.assert_called_once()
        self.assertIn("background_gate_score", result)
        self.assertEqual(result["pest"], expected["pest"])

    def test_low_level_background_noise_uses_hierarchy_acceptance_status(self):
        audio = np.random.default_rng(1).integers(
            -4, 5, size=80000, dtype=np.int16
        )
        request = FakeRequest(
            "application/octet-stream",
            body=audio.tobytes(),
        )

        response = asyncio.run(main.ai_predict(request, db=self.database))

        self.assertEqual(response["status"], "HARMFUL_PEST")
        self.assertEqual(response["identification_status"], "MODEL_PREDICTED")
        self.assertIn(response["pest"], ACTIVE_LABELS)
        self.assertEqual(
            response["identification_label"], response["common_name"]
        )
        self.assertEqual(
            response["message"], "Model-predicted harmful pest"
        )

    def test_low_score_prediction_is_kept_as_an_unverified_possible_match(self):
        request = FakeRequest("application/json", payload={"audio": []})
        candidate_result = {
            "pest": ACTIVE_LABELS[17],
            "confidence": 0.2,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        self.assertEqual(response["pest"], ACTIVE_LABELS[17])
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
            "pest": ACTIVE_LABELS[0],
            "confidence": 0.99,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        self.assertEqual(response["status"], "UNKNOWN")
        self.assertEqual(response["pest"], ACTIVE_LABELS[0])
        self.assertEqual(response["confidence"], 0.99)
        self.assertEqual(response["risk"], main._resolve_species_metadata(ACTIVE_LABELS[0])["risk"])

    def test_accepted_hierarchy_prediction_status_is_persisted_and_returned(self):
        pest = ACTIVE_LABELS[0]
        request = FakeRequest("application/json", payload={"audio": []})
        candidate_result = {
            "pest": pest,
            "confidence": 0.99,
            "insect_group": main.MODEL_SPECIES_GROUPS[
                main._normalize_pest_label(pest)
            ],
            "rejection_reason": None,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        detection = self.database.add.call_args.args[0]
        self.assertEqual(detection.status, "HARMFUL_PEST")
        self.assertEqual(response["status"], "HARMFUL_PEST")
        self.assertEqual(response["identification_status"], "MODEL_PREDICTED")
        self.database.commit.assert_called_once()

    def test_hierarchy_acceptance_does_not_add_an_overall_score_threshold(self):
        pest = ACTIVE_LABELS[0]
        request = FakeRequest("application/json", payload={"audio": []})
        candidate_result = {
            "pest": pest,
            "confidence": 0.2,
            "insect_group": main.MODEL_SPECIES_GROUPS[
                main._normalize_pest_label(pest)
            ],
            "rejection_reason": None,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        self.assertEqual(response["status"], "HARMFUL_PEST")
        self.assertEqual(response["identification_status"], "MODEL_PREDICTED")
        self.assertEqual(response["confidence"], 0.2)

    def test_rejected_hierarchy_prediction_remains_unknown(self):
        pest = ACTIVE_LABELS[0]
        request = FakeRequest("application/json", payload={"audio": []})
        candidate_result = {
            "pest": pest,
            "confidence": 0.99,
            "insect_group": main.MODEL_SPECIES_GROUPS[
                main._normalize_pest_label(pest)
            ],
            "rejection_reason": "subtype_confidence_below_validation_threshold",
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        detection = self.database.add.call_args.args[0]
        self.assertEqual(detection.status, "UNKNOWN")
        self.assertEqual(response["status"], "UNKNOWN")
        self.assertEqual(response["identification_status"], "UNCONFIRMED")

    def test_group_only_hierarchy_fallback_is_not_an_accepted_species(self):
        group = main._PEST_GUARD_HIERARCHY.groups[0]
        request = FakeRequest("application/json", payload={"audio": []})
        candidate_result = {
            "pest": group,
            "confidence": 0.99,
            "insect_group": group,
            "rejection_reason": None,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        detection = self.database.add.call_args.args[0]
        self.assertEqual(detection.status, "UNKNOWN")
        self.assertIsNone(detection.pest)
        self.assertEqual(response["status"], "UNKNOWN")
        self.assertEqual(response["identification_status"], "UNCONFIRMED")
        self.assertEqual(response["identification_label"], "Possible group match")

    def test_subtype_with_mismatched_group_is_not_accepted(self):
        pest = ACTIVE_LABELS[0]
        expected_group = main.MODEL_SPECIES_GROUPS[
            main._normalize_pest_label(pest)
        ]
        mismatched_group = next(
            group
            for group in main._PEST_GUARD_HIERARCHY.groups
            if group != expected_group
        )
        request = FakeRequest("application/json", payload={"audio": []})
        candidate_result = {
            "pest": pest,
            "confidence": 0.99,
            "insect_group": mismatched_group,
            "rejection_reason": None,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        self.assertEqual(response["status"], "UNKNOWN")
        self.assertEqual(response["identification_status"], "UNCONFIRMED")

    def test_every_model_class_is_retained_as_unverified_at_low_and_high_scores(self):
        request = FakeRequest("application/json", payload={"audio": []})

        for pest in ACTIVE_LABELS:
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
                    self.assertEqual(response["risk"], "LOW")

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
        self.assertEqual(response["risk"], "LOW")

    def test_serialized_low_confidence_record_is_explicitly_unconfirmed(self):
        detection = Mock(
            id=4,
            device_id="FIELD-UNIT-01",
            status="UNKNOWN",
            pest=None,
            scientific_name=None,
            common_name=None,
            confidence=0.632,
            top_predictions=None,
            risk="LOW",
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
            top_predictions=None,
            risk="LOW",
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

    def test_latest_detection_serialization_preserves_known_common_name_and_scores(self):
        pest = main.Pest(
            pest_id="european_field_cricket",
            name="European Field Cricket",
            scientific_name=None,
            risk="LOW",
            description="",
            symptoms="",
        )
        detection = Mock(
            id=42,
            device_id="FIELD-UNIT-01",
            status="HARMFUL_PEST",
            pest="European Field Cricket",
            scientific_name=None,
            common_name="European Field Cricket",
            confidence=0.677,
            top_predictions=json.dumps({
                "species": [{
                    "pest": "European Field Cricket",
                    "score": 0.677,
                    "subtype_confidence": 0.677,
                }],
            }),
            insect_group="Crickets",
            group_score=0.728,
            risk="LOW",
            risk_rationale="Catalogue risk.",
            affected_crops="[]",
            metadata_source_name=None,
            metadata_source_url=None,
            temperature=None,
            humidity=None,
            audio_file=None,
            message="Model-predicted harmful pest",
            detected_at=datetime(2026, 11, 11, 12, 0),
        )
        latest_query = Mock()
        latest_query.order_by.return_value = latest_query
        latest_query.first.return_value = detection
        pest_query = Mock()
        pest_query.all.return_value = [pest]
        database = Mock()
        database.query.side_effect = lambda model: (
            latest_query if model is main.Detection else pest_query
        )

        response = main.get_latest_detection(db=database)["detection"]
        api_response = main.DetectionResponse.model_validate(response)

        self.assertEqual(response["common_name"], "European Field Cricket")
        self.assertIsNone(response["scientific_name"])
        self.assertEqual(response["pest_id"], "european_field_cricket")
        self.assertTrue(response["pest_verified"])
        self.assertEqual(response["risk"], "LOW")
        self.assertEqual(response["confidence"], 0.677)
        self.assertEqual(response["group_score"], 0.728)
        self.assertEqual(api_response.common_name, "European Field Cricket")
        self.assertIsNone(api_response.scientific_name)

    def test_solution_inventory_requires_verified_crop_specific_records(self):
        import csv

        from crop_data import CROP_DATA
        from solution_data import (
            ALLARDS_GROUND_CRICKET_ADVISORY_DATA,
            ASH_CICADA_ADVISORY_DATA,
            BLACK_CICADA_ADVISORY_DATA,
            BLACK_PRINCE_CICADA_ADVISORY_DATA,
            BLADDER_CICADA_ADVISORY_DATA,
            BROWN_BUNYIP_CICADA_ADVISORY_DATA,
            CAROLINA_GROUND_CRICKET_ADVISORY_DATA,
            CHORUS_CICADA_KIWIFRUIT_ADVISORY_DATA,
            COMMON_CICADA_ADVISORY_DATA,
            DARK_BUSH_CRICKET_ADVISORY_DATA,
            DESERT_FIELD_CRICKET_ADVISORY_DATA,
            DOUBLE_DRUMMER_CICADA_ADVISORY_DATA,
            FALL_FIELD_CRICKET_ADVISORY_DATA,
            FIELD_CRICKET_ADVISORY_DATA,
            FLOURY_BAKER_CICADA_ADVISORY_DATA,
            GIANT_CICADA_ADVISORY_DATA,
            JAPANESE_BURROWING_CRICKET_ADVISORY_DATA,
            LARGE_DARK_BUSH_CRICKET_ADVISORY_DATA,
            EUROPEAN_FIELD_CRICKET_ADVISORY_DATA,
            EUROPEAN_TREE_CRICKET_ADVISORY_DATA,
            PEST_COVERAGE_DATA,
            SOLUTION_RECORDS,
            SPRING_FIELD_CRICKET_ADVISORY_DATA,
            TWO_SPOTTED_CRICKET_ADVISORY_DATA,
            validate_solution_records,
        )

        self.assertEqual(len(CROP_DATA), 68)
        self.assertEqual(
            {item["pest_id"] for item in PEST_COVERAGE_DATA},
            {item["pest_id"] for item in main.PEST_DATA},
        )
        self.assertEqual(len(PEST_COVERAGE_DATA), 132)
        self.assertEqual(
            {
                risk: sum(item["risk"] == risk for item in main.PEST_DATA)
                for risk in ("HIGH", "MEDIUM", "LOW")
            },
            {"HIGH": 17, "MEDIUM": 59, "LOW": 56},
        )
        catalogue = {item["pest_id"]: item for item in main.PEST_DATA}
        spring_cricket = catalogue["spring_field_cricket"]
        self.assertEqual(spring_cricket["name"], "Spring Field Cricket")
        self.assertEqual(spring_cricket["risk"], "LOW")
        self.assertEqual(spring_cricket["scientific_name"], "Gryllus veletis")
        self.assertEqual(spring_cricket["crop_ids"], [])
        self.assertEqual(
            spring_cricket.get("database_reference"),
            "PG-FC-003",
        )
        self.assertEqual(
            sum(item["pest_id"] == "spring_field_cricket" for item in main.PEST_DATA),
            1,
        )
        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            spring_cricket_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "spring_field_cricket"
            )
        self.assertEqual(spring_cricket_row["risk_level"], "LOW")
        self.assertEqual(spring_cricket_row["scientific_name"], "Gryllus veletis")
        self.assertEqual(spring_cricket_row["candidate_scientific_name"], "")
        self.assertEqual(
            spring_cricket_row["taxonomy_status"],
            "TAXON_MATCH_CONFIRMED",
        )
        self.assertEqual(
            spring_cricket_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(
            spring_cricket_row["relationship_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(spring_cricket_row["crop_id"], "")
        self.assertEqual(spring_cricket_row["crop_name"], "")
        self.assertEqual(spring_cricket_row["verified_host_crops"], "")
        self.assertIn("north america", spring_cricket_row["damage_evidence"].casefold())
        self.assertIn("collectively", spring_cricket_row["damage_evidence"].casefold())
        self.assertEqual(spring_cricket_row["damage_status"], "NOT_ESTABLISHED")
        self.assertEqual(
            spring_cricket_row["affected_plant_parts_status"],
            "NOT_ESTABLISHED",
        )
        for field in (
            "cultural_management_status",
            "biological_management_status",
            "chemical_management_status",
            "prevention_status",
        ):
            self.assertEqual(spring_cricket_row[field], "NOT_ESTABLISHED")
        field_cricket = catalogue["field_cricket"]
        self.assertEqual(field_cricket["name"], "Field Cricket")
        self.assertEqual(field_cricket["risk"], "MEDIUM")
        self.assertIsNone(field_cricket["scientific_name"])
        spring_record = SimpleNamespace(
            pest_id="spring_field_cricket",
            name="Spring Field Cricket",
            scientific_name="Gryllus veletis",
            risk="LOW",
        )
        fall_record = SimpleNamespace(
            pest_id="fall_field_cricket",
            name="Fall Field Cricket",
            scientific_name="Gryllus pennsylvanicus",
            risk="MEDIUM",
        )
        generic_field_record = SimpleNamespace(
            pest_id="field_cricket",
            name="Field Cricket",
            scientific_name=None,
            risk="MEDIUM",
        )
        cricket_database = Mock()
        cricket_database.query.return_value.all.return_value = [
            spring_record,
            fall_record,
            generic_field_record,
        ]
        self.assertIs(
            main._find_pest_record_normalized(
                cricket_database,
                "Gryllus veletis",
            ),
            spring_record,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                cricket_database,
                "Fall Field Cricket",
            ),
            fall_record,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                cricket_database,
                "Field Cricket",
            ),
            generic_field_record,
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            field_cricket_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "field_cricket"
            )
        self.assertEqual(field_cricket_row["risk_level"], "MEDIUM")
        self.assertEqual(field_cricket_row["scientific_name"], "")
        self.assertEqual(
            field_cricket_row["candidate_scientific_name"],
            "Gryllus spp. (species undetermined)",
        )
        self.assertEqual(
            field_cricket_row["taxonomy_status"],
            "TAXON_AMBIGUOUS",
        )
        self.assertEqual(field_cricket_row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(field_cricket_row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(field_cricket_row["crop_id"], "")
        self.assertEqual(field_cricket_row["crop_name"], "")
        self.assertEqual(field_cricket_row["verified_host_crops"], "")
        self.assertEqual(field_cricket_row["damage_status"], "NOT_ESTABLISHED")
        for field in (
            "cultural_management_status",
            "biological_management_status",
            "chemical_management_status",
            "prevention_status",
        ):
            self.assertEqual(field_cricket_row[field], "NOT_ESTABLISHED")
        desert_cricket = catalogue["desert_field_cricket"]
        self.assertEqual(desert_cricket["risk"], "MEDIUM")
        self.assertEqual(desert_cricket["insect_group"], "Crickets")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            desert_cricket_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "desert_field_cricket"
            )
        self.assertEqual(desert_cricket_row["risk_level"], "MEDIUM")
        self.assertEqual(desert_cricket_row["scientific_name"], "")
        self.assertEqual(
            desert_cricket_row["candidate_scientific_name"],
            "Melanogryllus desertus",
        )
        self.assertEqual(
            desert_cricket_row["accepted_synonyms"],
            "Gryllus desertus",
        )
        self.assertEqual(
            desert_cricket_row["taxonomy_status"],
            "TAXON_AMBIGUOUS",
        )
        self.assertEqual(desert_cricket_row["crop_id"], "")
        self.assertEqual(desert_cricket_row["crop_name"], "")
        self.assertEqual(
            desert_cricket_row["relationship_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            desert_cricket_row["indian_occurrence_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            desert_cricket_row["damage_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(
            desert_cricket_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        japanese_cricket = catalogue["japanese_burrowing_cricket"]
        self.assertEqual(japanese_cricket["name"], "Japanese Burrowing Cricket")
        self.assertEqual(japanese_cricket["scientific_name"], "Velarifictorus micado")
        self.assertEqual(japanese_cricket["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            japanese_cricket_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "japanese_burrowing_cricket"
            )
        self.assertEqual(
            japanese_cricket_row["taxonomy_status"],
            "TAXON_MATCH_CONFIRMED",
        )
        self.assertEqual(
            japanese_cricket_row["scientific_name"],
            "Velarifictorus micado",
        )
        self.assertEqual(
            japanese_cricket_row["candidate_scientific_name"],
            "Velarifictorus mikado",
        )
        self.assertEqual(japanese_cricket_row["accepted_synonyms"], "")
        self.assertEqual(
            japanese_cricket_row["indian_occurrence_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(japanese_cricket_row["crop_id"], "")
        self.assertEqual(japanese_cricket_row["crop_name"], "")
        self.assertIn("red clover and orchard grass", japanese_cricket_row["damage_evidence"])
        self.assertEqual(
            japanese_cricket_row["damage_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(
            japanese_cricket_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        allards_catalogue_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "allards_ground_cricket"
        ]
        self.assertEqual(len(allards_catalogue_entries), 1)
        allards_cricket = allards_catalogue_entries[0]
        self.assertEqual(allards_cricket["name"], "Allard's Ground Cricket")
        self.assertEqual(allards_cricket["scientific_name"], "Allonemobius allardi")
        self.assertEqual(allards_cricket["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            allards_cricket_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "allards_ground_cricket"
            )
        self.assertEqual(allards_cricket_row["risk_level"], "LOW")
        self.assertEqual(
            allards_cricket_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            allards_cricket_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(allards_cricket_row["crop_id"], "")
        self.assertEqual(allards_cricket_row["crop_name"], "")
        self.assertEqual(allards_cricket_row["verified_host_crops"], "")
        self.assertNotEqual(
            allards_cricket_row["relationship_status"],
            "CONFIRMED_HOST",
        )
        self.assertIn(
            "Alfalfa is listed as a food plant",
            allards_cricket_row["damage_evidence"],
        )
        self.assertEqual(
            allards_cricket_row["crop_damage"],
            "Not established.",
        )
        self.assertEqual(
            allards_cricket_row["damage_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(
            allards_cricket_row["affected_plant_parts_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(
            allards_cricket_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        self.assertIn(
            "economic_threshold",
            allards_cricket_row["missing_evidence_fields"],
        )
        ash_cicada_entries = [
            item for item in main.PEST_DATA if item["pest_id"] == "ash_cicada"
        ]
        self.assertEqual(len(ash_cicada_entries), 1)
        ash_cicada = ash_cicada_entries[0]
        self.assertEqual(ash_cicada["name"], "Ash Cicada")
        self.assertEqual(ash_cicada["scientific_name"], "Cicada orni")
        self.assertEqual(ash_cicada["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            ash_cicada_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "ash_cicada"
            )
        self.assertEqual(ash_cicada_row["risk_level"], "LOW")
        self.assertEqual(ash_cicada_row["taxonomy_status"], "NEEDS_REVIEW")
        self.assertEqual(
            ash_cicada_row["indian_occurrence_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(ash_cicada_row["crop_id"], "")
        self.assertEqual(ash_cicada_row["crop_name"], "")
        self.assertEqual(ash_cicada_row["verified_host_crops"], "")
        self.assertNotEqual(
            ash_cicada_row["relationship_status"],
            "CONFIRMED_HOST",
        )
        self.assertIn(
            "Fraxinus ornus (manna ash)",
            ash_cicada_row["damage_evidence"],
        )
        self.assertNotIn("Fraxinus ornus", ash_cicada_row["verified_host_crops"])
        self.assertEqual(
            ash_cicada_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        self.assertIn(
            "economic_threshold",
            ash_cicada_row["missing_evidence_fields"],
        )
        black_cicada_entries = [
            item for item in main.PEST_DATA if item["pest_id"] == "black_cicada"
        ]
        self.assertEqual(len(black_cicada_entries), 1)
        self.assertEqual(
            [
                item["pest_id"]
                for item in main.PEST_DATA
                if item["name"]
                in {"Black Cicada", "Black and Scarlet Cicada"}
            ],
            ["black_cicada"],
        )
        black_cicada = black_cicada_entries[0]
        self.assertEqual(black_cicada["name"], "Black Cicada")
        self.assertEqual(black_cicada["scientific_name"], "Huechys sanguinea")
        self.assertEqual(black_cicada["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            black_cicada_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "black_cicada"
            )
        self.assertEqual(black_cicada_row["risk_level"], "LOW")
        self.assertEqual(
            black_cicada_row["scientific_name"],
            "Huechys sanguinea",
        )
        self.assertEqual(
            black_cicada_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            black_cicada_row["indian_occurrence_status"],
            "INDIA_OCCURRENCE_CONFIRMED",
        )
        self.assertEqual(black_cicada_row["crop_id"], "rose_apple")
        self.assertEqual(black_cicada_row["crop_name"], "Rose Apple")
        self.assertEqual(
            black_cicada_row["relationship_status"],
            "CONFIRMED_HOST",
        )
        self.assertEqual(black_cicada_row["verified_host_crops"], "Rose Apple")
        self.assertEqual(black_cicada_row["accepted_synonyms"], "")
        self.assertNotIn(
            "Cryptotympana atrata",
            black_cicada_row["accepted_synonyms"],
        )
        self.assertNotIn(
            "Cryptotympana aquila",
            black_cicada_row["accepted_synonyms"],
        )
        self.assertEqual(black_cicada_row["crop_damage"], "Not quantified.")
        self.assertEqual(black_cicada_row["damage_status"], "NOT_ESTABLISHED")
        self.assertEqual(black_cicada_row["affected_plant_parts"], "")
        self.assertEqual(
            black_cicada_row["affected_plant_parts_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(
            black_cicada_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        black_prince_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "black_prince_cicada"
        ]
        self.assertEqual(len(black_prince_entries), 1)
        black_prince = black_prince_entries[0]
        self.assertEqual(black_prince["name"], "Black Prince Cicada")
        self.assertEqual(black_prince["scientific_name"], "Psaltoda plaga")
        self.assertEqual(black_prince["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            black_prince_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "black_prince_cicada"
            )
        self.assertEqual(black_prince_row["risk_level"], "LOW")
        self.assertEqual(
            black_prince_row["scientific_name"],
            "Psaltoda plaga",
        )
        self.assertEqual(
            black_prince_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            black_prince_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(black_prince_row["crop_id"], "")
        self.assertEqual(black_prince_row["crop_name"], "")
        self.assertEqual(black_prince_row["verified_host_crops"], "")
        self.assertNotEqual(
            black_prince_row["relationship_status"],
            "CONFIRMED_HOST",
        )
        self.assertEqual(
            black_prince_row["ecological_host_plants"].split("; "),
            [
                "Eucalyptus",
                "Casuarina cunninghamiana",
                "Salix babylonica",
                "Angophora floribunda",
            ],
        )
        self.assertEqual(black_prince_row["accepted_synonyms"], "")
        self.assertNotIn(
            "Huechys sanguinea",
            black_prince_row["accepted_synonyms"],
        )
        self.assertNotIn(
            "Cryptotympana atrata",
            black_prince_row["accepted_synonyms"],
        )
        self.assertEqual(
            black_prince_row["crop_damage"],
            "No substantial commercial crop damage established.",
        )
        self.assertEqual(
            black_prince_row["affected_plant_parts"],
            "Roots, stems, branches, young twigs",
        )
        self.assertEqual(
            black_prince_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        bladder_cicada_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "bladder_cicada"
        ]
        self.assertEqual(len(bladder_cicada_entries), 1)
        bladder_cicada = bladder_cicada_entries[0]
        self.assertEqual(bladder_cicada["name"], "Bladder Cicada")
        self.assertEqual(
            bladder_cicada["scientific_name"],
            "Cystosoma saundersii",
        )
        self.assertEqual(bladder_cicada["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            bladder_cicada_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "bladder_cicada"
            )
        self.assertEqual(bladder_cicada_row["risk_level"], "LOW")
        self.assertEqual(
            bladder_cicada_row["scientific_name"],
            "Cystosoma saundersii",
        )
        self.assertEqual(
            bladder_cicada_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            bladder_cicada_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(bladder_cicada_row["crop_id"], "")
        self.assertEqual(bladder_cicada_row["crop_name"], "")
        self.assertEqual(bladder_cicada_row["verified_host_crops"], "")
        self.assertNotEqual(
            bladder_cicada_row["relationship_status"],
            "CONFIRMED_HOST",
        )
        bladder_host_plants = bladder_cicada_row[
            "ecological_host_plants"
        ].split("; ")
        self.assertEqual(
            bladder_host_plants,
            [
                "Eucalyptus",
                "grasses",
                "mango",
                "loquat",
                "privet",
                "jacaranda",
                "weeping willow",
            ],
        )
        crop_names = {item["name"].casefold() for item in CROP_DATA}
        self.assertEqual(
            {
                host.casefold()
                for host in bladder_host_plants
                if host.casefold() in crop_names
            },
            {"mango"},
        )
        self.assertEqual(bladder_cicada_row["accepted_synonyms"], "")
        self.assertNotIn(
            "Cystosoma schmeltzi",
            bladder_cicada_row["accepted_synonyms"],
        )
        self.assertEqual(
            bladder_cicada_row["crop_damage"],
            "Not established.",
        )
        self.assertEqual(
            bladder_cicada_row["damage_evidence"],
            "Possible localised twig injury from egg-laying.",
        )
        self.assertEqual(
            bladder_cicada_row["affected_plant_parts"],
            "Roots, stems, branches, young twigs",
        )
        self.assertEqual(
            bladder_cicada_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        carolina_cricket_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "carolina_ground_cricket"
        ]
        self.assertEqual(len(carolina_cricket_entries), 1)
        carolina_cricket = carolina_cricket_entries[0]
        self.assertEqual(carolina_cricket["name"], "Carolina Ground Cricket")
        self.assertEqual(
            carolina_cricket["scientific_name"],
            "Eunemobius carolinus",
        )
        self.assertEqual(carolina_cricket["insect_group"], "Ground Cricket")
        self.assertEqual(carolina_cricket["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            carolina_cricket_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "carolina_ground_cricket"
            )
        self.assertEqual(carolina_cricket_row["risk_level"], "LOW")
        self.assertEqual(
            carolina_cricket_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            carolina_cricket_row["scientific_name"],
            "",
        )
        self.assertEqual(
            carolina_cricket_row["candidate_scientific_name"],
            "Eunemobius carolinus",
        )
        self.assertEqual(
            carolina_cricket_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(carolina_cricket_row["crop_id"], "")
        self.assertEqual(carolina_cricket_row["crop_name"], "")
        self.assertEqual(carolina_cricket_row["verified_host_crops"], "")
        self.assertEqual(carolina_cricket_row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(carolina_cricket_row["accepted_synonyms"], "")
        for related_species in (
            "Eunemobius confusus",
            "Eunemobius melodius",
            "Allonemobius",
        ):
            self.assertNotIn(
                related_species,
                carolina_cricket_row["accepted_synonyms"],
            )
        self.assertEqual(
            carolina_cricket_row["ecological_host_plants"],
            "",
        )
        self.assertEqual(
            carolina_cricket_row["ecological_habitat"],
            "Moist meadows; damp woodland; stream margins; decaying logs; stones; ground cover",
        )
        self.assertEqual(
            carolina_cricket_row["crop_damage"],
            "Not established.",
        )
        self.assertEqual(
            carolina_cricket_row["affected_plant_parts"],
            "",
        )
        self.assertEqual(
            carolina_cricket_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        chorus_cicada_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "chorus_cicada"
        ]
        self.assertEqual(len(chorus_cicada_entries), 1)
        chorus_cicada = chorus_cicada_entries[0]
        self.assertEqual(chorus_cicada["name"], "Chorus Cicada")
        self.assertEqual(
            chorus_cicada["scientific_name"],
            "Amphipsalta zelandica",
        )
        self.assertEqual(chorus_cicada["risk"], "HIGH")
        kiwifruit_crops = [
            item for item in CROP_DATA if item["crop_id"] == "kiwifruit"
        ]
        self.assertEqual(len(kiwifruit_crops), 1)
        self.assertEqual(
            kiwifruit_crops[0]["name"],
            "Kiwifruit (Actinidia spp.)",
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            chorus_cicada_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "chorus_cicada"
            )
        self.assertEqual(chorus_cicada_row["risk_level"], "HIGH")
        self.assertEqual(chorus_cicada_row["taxonomy_status"], "NEEDS_REVIEW")
        self.assertEqual(
            chorus_cicada_row["candidate_scientific_name"],
            "Amphipsalta zelandica",
        )
        self.assertEqual(
            chorus_cicada_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(chorus_cicada_row["crop_id"], "kiwifruit")
        self.assertEqual(
            chorus_cicada_row["crop_name"],
            "Kiwifruit (Actinidia spp.)",
        )
        self.assertEqual(
            chorus_cicada_row["relationship_status"],
            "CONFIRMED_HOST",
        )
        self.assertEqual(
            chorus_cicada_row["verified_host_crops"],
            "Kiwifruit (New Zealand)",
        )
        self.assertIn("New Zealand", chorus_cicada_row["damage_evidence"])
        self.assertIn(
            "herringbone wounds",
            chorus_cicada_row["damage_evidence"],
        )
        self.assertEqual(
            chorus_cicada_row["ecological_host_plants"],
            "Eucalyptus spp.; other recorded trees/shrubs",
        )
        self.assertEqual(chorus_cicada_row["ecological_habitat"], "")
        self.assertEqual(
            chorus_cicada_row["affected_plant_parts"],
            "Current-season canes, shoots and woody branches",
        )
        self.assertEqual(
            chorus_cicada_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        brown_bunyip_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "brown_bunyip_cicada"
        ]
        self.assertEqual(len(brown_bunyip_entries), 1)
        self.assertNotIn(
            "brown_bunyip",
            {item["pest_id"] for item in main.PEST_DATA},
        )
        brown_bunyip = brown_bunyip_entries[0]
        self.assertEqual(brown_bunyip["name"], "Brown Bunyip Cicada")
        self.assertEqual(brown_bunyip["scientific_name"], "Tamasa tristigma")
        self.assertEqual(brown_bunyip["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            brown_bunyip_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "brown_bunyip_cicada"
            )
        self.assertEqual(brown_bunyip_row["risk_level"], "LOW")
        self.assertEqual(
            brown_bunyip_row["scientific_name"],
            "Tamasa tristigma",
        )
        self.assertEqual(
            brown_bunyip_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            brown_bunyip_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(brown_bunyip_row["crop_id"], "")
        self.assertEqual(brown_bunyip_row["crop_name"], "")
        self.assertEqual(brown_bunyip_row["verified_host_crops"], "")
        self.assertNotEqual(
            brown_bunyip_row["relationship_status"],
            "CONFIRMED_HOST",
        )
        brown_bunyip_host_plants = brown_bunyip_row[
            "ecological_host_plants"
        ].split("; ")
        self.assertEqual(
            brown_bunyip_host_plants,
            [
                "Liquidambar styraciflua",
                "Casuarina spp.",
                "Acacia spp.",
                "Jacaranda spp.",
                "Eucalyptus spp.",
            ],
        )
        crop_names = {item["name"].casefold() for item in CROP_DATA}
        self.assertTrue(
            all(
                host.casefold() not in crop_names
                for host in brown_bunyip_host_plants
            )
        )
        self.assertEqual(brown_bunyip_row["accepted_synonyms"], "")
        self.assertNotIn("Tamasa", brown_bunyip_row["accepted_synonyms"])
        self.assertEqual(
            brown_bunyip_row["crop_damage"],
            "No significant commercial crop damage established.",
        )
        self.assertEqual(
            brown_bunyip_row["damage_evidence"],
            "Potential twig injury from egg-laying; not confirmed as species-specific crop damage.",
        )
        self.assertEqual(
            brown_bunyip_row["affected_plant_parts"],
            "Roots and woody twigs",
        )
        self.assertEqual(
            brown_bunyip_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        two_spotted_cricket = catalogue["two_spotted_cricket"]
        self.assertEqual(two_spotted_cricket["risk"], "MEDIUM")
        self.assertEqual(
            two_spotted_cricket["scientific_name"],
            "Gryllus bimaculatus",
        )
        self.assertEqual(
            two_spotted_cricket["database_reference"],
            "PG-FC-006",
        )
        self.assertEqual(
            two_spotted_cricket["aliases"],
            ["Liogryllus bimaculatus"],
        )
        self.assertEqual(
            sum(
                item["pest_id"] == "two_spotted_cricket"
                for item in main.PEST_DATA
            ),
            1,
        )
        two_spotted_record = SimpleNamespace(
            pest_id="two_spotted_cricket",
            name="Two-spotted Cricket",
            scientific_name="Gryllus bimaculatus",
            risk="MEDIUM",
        )
        generic_field_record = SimpleNamespace(
            pest_id="field_cricket",
            name="Field Cricket",
            scientific_name=None,
            risk="MEDIUM",
        )
        fall_field_record = SimpleNamespace(
            pest_id="fall_field_cricket",
            name="Fall Field Cricket",
            scientific_name="Gryllus pennsylvanicus",
            risk="MEDIUM",
        )
        cricket_database = Mock()
        cricket_database.query.return_value.all.return_value = [
            two_spotted_record,
            generic_field_record,
            fall_field_record,
        ]
        self.assertIs(
            main._find_pest_record_normalized(
                cricket_database,
                "Liogryllus bimaculatus",
            ),
            two_spotted_record,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                cricket_database,
                "Field Cricket",
            ),
            generic_field_record,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                cricket_database,
                "Gryllus pennsylvanicus",
            ),
            fall_field_record,
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            two_spotted_cricket_row = next(
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "two_spotted_cricket"
            )
        self.assertEqual(
            two_spotted_cricket_row["taxonomy_status"],
            "TAXON_MATCH_CONFIRMED",
        )
        self.assertEqual(
            two_spotted_cricket_row["scientific_name"],
            "Gryllus bimaculatus",
        )
        self.assertEqual(
            two_spotted_cricket_row["accepted_synonyms"],
            "Liogryllus bimaculatus",
        )
        self.assertEqual(
            two_spotted_cricket_row["indian_occurrence_status"],
            "INDIA_OCCURRENCE_CONFIRMED",
        )
        self.assertIn(
            "Karnataka",
            two_spotted_cricket_row["indian_occurrence_evidence"],
        )
        self.assertEqual(
            two_spotted_cricket_row["relationship_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(two_spotted_cricket_row["verified_host_crops"], "")
        self.assertEqual(two_spotted_cricket_row["damage_status"], "VERIFIED")
        self.assertIn(
            "chickpea pods and seeds",
            two_spotted_cricket_row["crop_damage"],
        )
        self.assertIn(
            "potato plant damage",
            two_spotted_cricket_row["crop_damage"],
        )
        self.assertIn(
            "Potato: affected plant part not specified",
            two_spotted_cricket_row["affected_plant_parts"],
        )
        self.assertEqual(
            two_spotted_cricket_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        self.assertIn(
            "Pakistan field study",
            two_spotted_cricket_row["damage_evidence"],
        )
        for pakistan_crop in ("wheat", "rice", "sugarcane", "jungle rice"):
            self.assertIn(
                pakistan_crop,
                two_spotted_cricket_row["damage_evidence"].casefold(),
            )
        self.assertIn(
            "economic importance",
            two_spotted_cricket_row["crop_damage"].casefold(),
        )
        self.assertIn(
            "not established",
            two_spotted_cricket_row["crop_damage"].casefold(),
        )
        self.assertTrue(
            all(
                item["research_data"]["common_name"]
                and item["research_data"]["insect_group"]
                and item["research_data"]["risk_level"]
                == catalogue[item["pest_id"]]["risk"]
                and item["research_data"]["missing_evidence_fields"] is not None
                for item in PEST_COVERAGE_DATA
            )
        )
        pine_weevil_coverage = next(
            item
            for item in PEST_COVERAGE_DATA
            if item["pest_id"] == "pine_weevil"
        )["research_data"]
        self.assertEqual(
            pine_weevil_coverage["taxonomy_status"],
            "TAXON_AMBIGUOUS",
        )
        self.assertEqual(
            pine_weevil_coverage["relationship_status"],
            "NEEDS_REVIEW",
        )
        pine_host_ids = [
            host["crop_id"]
            for host in pine_weevil_coverage["potential_host_crops"]
        ]
        self.assertEqual(
            pine_host_ids,
            ["pine", "spruce", "fir", "douglas_fir", "hemlock"],
        )
        self.assertEqual(len(SOLUTION_RECORDS), 11)
        self.assertEqual(len(EUROPEAN_FIELD_CRICKET_ADVISORY_DATA), 1)
        cricket_advisory = EUROPEAN_FIELD_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(cricket_advisory["pest_id"], "european_field_cricket")
        self.assertEqual(cricket_advisory["scientific_name"], "Gryllus campestris")
        self.assertEqual(cricket_advisory["risk_level"], "LOW")
        self.assertEqual(cricket_advisory["status"], "ADVISORY")
        self.assertIsNone(cricket_advisory["crop_id"])
        self.assertIsNone(cricket_advisory["crop_name"])
        self.assertEqual(
            cricket_advisory["habitat"],
            [
                "Sunny grasslands",
                "Short vegetation",
                "Patches of bare ground",
                "Individual soil burrows",
            ],
        )
        self.assertEqual(
            cricket_advisory["crop_damage"],
            "Serious crop damage is not well documented. Occasional vegetation feeding does not establish economically significant crop injury.",
        )
        self.assertEqual(cricket_advisory["affected_plant_parts"], [])
        self.assertIsNone(cricket_advisory["chemical_control_options"])
        self.assertNotIn(cricket_advisory, SOLUTION_RECORDS)
        european_cricket_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "european_field_cricket"
        ]
        self.assertEqual(len(european_cricket_entries), 1)
        european_cricket = european_cricket_entries[0]
        self.assertEqual(european_cricket["risk"], "LOW")
        self.assertEqual(
            european_cricket["scientific_name"],
            "Gryllus campestris",
        )
        self.assertEqual(european_cricket["insect_group"], "Cricket")
        self.assertIn("field_cricket", {item["pest_id"] for item in main.PEST_DATA})
        self.assertEqual(
            FALL_FIELD_CRICKET_ADVISORY_DATA[0]["scientific_name"],
            "Gryllus pennsylvanicus",
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            european_cricket_rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "european_field_cricket"
            ]
        self.assertEqual(len(european_cricket_rows), 1)
        european_cricket_row = european_cricket_rows[0]
        self.assertEqual(european_cricket_row["risk_level"], "LOW")
        self.assertEqual(
            european_cricket_row["scientific_name"],
            "Gryllus campestris",
        )
        self.assertEqual(
            european_cricket_row["taxonomy_status"],
            "TAXON_MATCH_CONFIRMED",
        )
        self.assertEqual(
            european_cricket_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(european_cricket_row["crop_id"], "")
        self.assertEqual(european_cricket_row["crop_name"], "")
        self.assertEqual(european_cricket_row["verified_host_crops"], "")
        self.assertEqual(
            european_cricket_row["ecological_habitat"],
            "Sunny grasslands; short vegetation; bare-ground patches; individual soil burrows",
        )
        self.assertEqual(
            european_cricket_row["crop_damage"],
            "No significant crop damage established.",
        )
        european_tree_cricket_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "european_tree_cricket"
        ]
        self.assertEqual(len(european_tree_cricket_entries), 1)
        european_tree_cricket = european_tree_cricket_entries[0]
        self.assertEqual(
            european_tree_cricket["name"],
            "European Tree Cricket",
        )
        self.assertEqual(
            european_tree_cricket["scientific_name"],
            "Oecanthus pellucens",
        )
        self.assertEqual(european_tree_cricket["insect_group"], "Tree Cricket")
        self.assertEqual(european_tree_cricket["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            european_tree_cricket_rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "european_tree_cricket"
            ]
        self.assertEqual(len(european_tree_cricket_rows), 1)
        european_tree_cricket_row = european_tree_cricket_rows[0]
        self.assertEqual(european_tree_cricket_row["risk_level"], "LOW")
        self.assertEqual(european_tree_cricket_row["scientific_name"], "")
        self.assertEqual(
            european_tree_cricket_row["candidate_scientific_name"],
            "Oecanthus pellucens",
        )
        self.assertEqual(european_tree_cricket_row["accepted_synonyms"], "")
        self.assertEqual(
            european_tree_cricket_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            european_tree_cricket_row["indian_occurrence_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(european_tree_cricket_row["crop_id"], "")
        self.assertEqual(european_tree_cricket_row["crop_name"], "")
        self.assertEqual(european_tree_cricket_row["verified_host_crops"], "")
        self.assertEqual(
            european_tree_cricket_row["ecological_host_plants"],
            "Mint; chicory; agrimony",
        )
        self.assertEqual(
            european_tree_cricket_row["ecological_habitat"],
            "Tall grasses; herbs; shrubs and vegetation",
        )
        self.assertIn(
            "European grapevines",
            european_tree_cricket_row["damage_evidence"],
        )
        self.assertIn(
            "not Indian crop damage",
            european_tree_cricket_row["damage_evidence"],
        )
        self.assertIn(
            "not established",
            european_tree_cricket_row["crop_damage"].lower(),
        )
        self.assertEqual(
            european_tree_cricket_row["affected_plant_parts"],
            "Grapevine stems and shoots (reported in European vineyards); herbaceous stems used for egg deposition",
        )
        self.assertEqual(
            european_tree_cricket_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        self.assertTrue(
            all(
                item["pest_id"] != "european_tree_cricket"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(EUROPEAN_TREE_CRICKET_ADVISORY_DATA), 1)
        european_tree_cricket_advisory = EUROPEAN_TREE_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(
            european_tree_cricket_advisory["solution_id"],
            "european_tree_cricket_general_advisory",
        )
        self.assertEqual(
            european_tree_cricket_advisory["pest_id"],
            "european_tree_cricket",
        )
        self.assertEqual(european_tree_cricket_advisory["risk_level"], "LOW")
        self.assertEqual(
            european_tree_cricket_advisory["status"],
            "ADVISORY",
        )
        self.assertIsNone(european_tree_cricket_advisory["crop_id"])
        self.assertIsNone(
            european_tree_cricket_advisory["chemical_control_options"]
        )
        self.assertEqual(
            european_tree_cricket_advisory["source_references"],
            [],
        )
        self.assertIn(
            "European vineyards",
            european_tree_cricket_advisory["geographic_limitation"],
        )
        self.assertIn(
            "Oecanthus indicus",
            european_tree_cricket_advisory["expert_advice"],
        )
        self.assertEqual(len(FALL_FIELD_CRICKET_ADVISORY_DATA), 1)
        fall_cricket_advisory = FALL_FIELD_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(fall_cricket_advisory["pest_id"], "fall_field_cricket")
        self.assertEqual(
            fall_cricket_advisory["scientific_name"],
            "Gryllus pennsylvanicus",
        )
        self.assertEqual(fall_cricket_advisory["risk_level"], "MEDIUM")
        self.assertEqual(fall_cricket_advisory["status"], "ADVISORY")
        self.assertIsNone(fall_cricket_advisory["crop_id"])
        self.assertIsNone(fall_cricket_advisory["crop_name"])
        self.assertIsNone(fall_cricket_advisory["chemical_control_options"])
        self.assertNotIn(fall_cricket_advisory, SOLUTION_RECORDS)
        self.assertEqual(len(SPRING_FIELD_CRICKET_ADVISORY_DATA), 1)
        spring_cricket_advisory = SPRING_FIELD_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(
            spring_cricket_advisory["pest_id"],
            "spring_field_cricket",
        )
        self.assertEqual(
            spring_cricket_advisory["scientific_name"],
            "Gryllus veletis",
        )
        self.assertEqual(spring_cricket_advisory["risk_level"], "LOW")
        self.assertEqual(spring_cricket_advisory["status"], "ADVISORY")
        self.assertIsNone(spring_cricket_advisory["crop_id"])
        self.assertIsNone(spring_cricket_advisory["crop_name"])
        self.assertIsNone(spring_cricket_advisory["chemical_control_options"])
        self.assertNotIn(spring_cricket_advisory, SOLUTION_RECORDS)
        self.assertEqual(
            spring_cricket_advisory["life_cycle_notes"],
            "Generally one generation per year; Gryllus veletis primarily "
            "overwinters as a nymph. This is not a Fall Field Cricket "
            "life-cycle claim.",
        )
        self.assertIn(
            "Canadian guidance",
            spring_cricket_advisory["crop_damage"],
        )
        self.assertIn(
            "collectively",
            spring_cricket_advisory["crop_damage"],
        )
        self.assertIn(
            "15-25 mm",
            " ".join(spring_cricket_advisory["identification_signs"]),
        )
        self.assertIn(
            "not a definitive",
            " ".join(spring_cricket_advisory["identification_signs"]),
        )
        self.assertNotIn(
            "nymph",
            fall_cricket_advisory.get("life_cycle_notes", "").casefold(),
        )
        self.assertEqual(len(FIELD_CRICKET_ADVISORY_DATA), 1)
        field_cricket_advisory = FIELD_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(field_cricket_advisory["pest_id"], "field_cricket")
        self.assertEqual(
            field_cricket_advisory["scientific_name"],
            "Gryllus spp. (species undetermined)",
        )
        self.assertEqual(field_cricket_advisory["risk_level"], "MEDIUM")
        self.assertEqual(field_cricket_advisory["status"], "ADVISORY")
        self.assertIsNone(field_cricket_advisory["crop_id"])
        self.assertIsNone(field_cricket_advisory["crop_name"])
        self.assertIsNone(field_cricket_advisory["chemical_control_options"])
        self.assertNotIn(field_cricket_advisory, SOLUTION_RECORDS)
        self.assertTrue(
            all(
                item["pest_id"] != "desert_field_cricket"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(DESERT_FIELD_CRICKET_ADVISORY_DATA), 1)
        desert_cricket_advisory = DESERT_FIELD_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(desert_cricket_advisory["status"], "ADVISORY")
        self.assertEqual(desert_cricket_advisory["risk_level"], "MEDIUM")
        self.assertIsNone(desert_cricket_advisory["crop_id"])
        self.assertIsNone(desert_cricket_advisory["crop_name"])
        self.assertIsNone(desert_cricket_advisory["chemical_control_options"])
        self.assertTrue(
            all(
                item["pest_id"] != "two_spotted_cricket"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(TWO_SPOTTED_CRICKET_ADVISORY_DATA), 2)
        self.assertEqual(
            [item["crop_id"] for item in TWO_SPOTTED_CRICKET_ADVISORY_DATA],
            ["chickpea", "potato"],
        )
        for advisory in TWO_SPOTTED_CRICKET_ADVISORY_DATA:
            self.assertEqual(advisory["status"], "ADVISORY")
            self.assertEqual(advisory["risk_level"], "MEDIUM")
            self.assertEqual(advisory["pest_id"], "two_spotted_cricket")
            self.assertIsNone(advisory["chemical_control_options"])
        chickpea_advisory = next(
            item
            for item in TWO_SPOTTED_CRICKET_ADVISORY_DATA
            if item["crop_id"] == "chickpea"
        )
        self.assertEqual(chickpea_advisory["pest_id"], "two_spotted_cricket")
        self.assertIn(
            "developing chickpea pods",
            " ".join(chickpea_advisory["immediate_control_measures"]).casefold(),
        )
        self.assertIn(
            "damaged or partially eaten seeds",
            " ".join(chickpea_advisory["immediate_control_measures"]).casefold(),
        )
        self.assertIn(
            "evening and night",
            " ".join(chickpea_advisory["monitoring"]).casefold(),
        )
        self.assertIn(
            "presence alone",
            " ".join(chickpea_advisory["prevention"]).casefold(),
        )
        potato_advisory = next(
            item
            for item in TWO_SPOTTED_CRICKET_ADVISORY_DATA
            if item["crop_id"] == "potato"
        )
        self.assertEqual(potato_advisory["pest_id"], "two_spotted_cricket")
        self.assertIn("Chopard (1969)", potato_advisory["crop_damage"])
        self.assertIn("2021 review", potato_advisory["crop_damage"])
        self.assertIsNone(potato_advisory["chemical_control_options"])
        self.assertFalse(
            any(
                item["pest_id"] == "two_spotted_cricket"
                and item["crop_id"] in {"wheat", "rice", "sugarcane", "jungle_rice"}
                for item in SOLUTION_RECORDS
            )
        )
        self.assertTrue(
            all(
                item["pest_id"] != "japanese_burrowing_cricket"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(JAPANESE_BURROWING_CRICKET_ADVISORY_DATA), 1)
        japanese_cricket_advisory = JAPANESE_BURROWING_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(
            japanese_cricket_advisory["status"],
            "ADVISORY",
        )
        self.assertEqual(japanese_cricket_advisory["risk_level"], "LOW")
        self.assertIsNone(japanese_cricket_advisory["crop_id"])
        self.assertIsNone(japanese_cricket_advisory["chemical_control_options"])
        self.assertTrue(
            all(
                item["pest_id"] != "allards_ground_cricket"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(ALLARDS_GROUND_CRICKET_ADVISORY_DATA), 1)
        allards_cricket_advisory = ALLARDS_GROUND_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(
            allards_cricket_advisory["solution_id"],
            "allards_ground_cricket_general_advisory",
        )
        self.assertEqual(
            allards_cricket_advisory["status"],
            "ADVISORY",
        )
        self.assertEqual(allards_cricket_advisory["risk_level"], "LOW")
        self.assertIsNone(allards_cricket_advisory["crop_id"])
        self.assertIsNone(
            allards_cricket_advisory["chemical_control_options"]
        )
        self.assertEqual(allards_cricket_advisory["source_references"], [])
        self.assertTrue(
            all(
                item["pest_id"] != "ash_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(ASH_CICADA_ADVISORY_DATA), 1)
        ash_cicada_advisory = ASH_CICADA_ADVISORY_DATA[0]
        self.assertEqual(
            ash_cicada_advisory["status"],
            "ADVISORY",
        )
        self.assertIsNone(ash_cicada_advisory["crop_id"])
        self.assertIsNone(
            ash_cicada_advisory["chemical_control_options"]
        )
        self.assertEqual(ash_cicada_advisory["source_references"], [])
        rose_apple_crop_ids = [
            item["crop_id"]
            for item in CROP_DATA
            if item["name"] == "Rose Apple"
        ]
        self.assertEqual(rose_apple_crop_ids, ["rose_apple"])
        self.assertTrue(
            all(
                item["pest_id"] != "black_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(BLACK_CICADA_ADVISORY_DATA), 1)
        black_cicada_advisory = BLACK_CICADA_ADVISORY_DATA[0]
        self.assertEqual(
            [item["crop_id"] for item in BLACK_CICADA_ADVISORY_DATA],
            rose_apple_crop_ids,
        )
        self.assertEqual(
            black_cicada_advisory["solution_id"],
            "black_cicada_rose_apple_advisory",
        )
        self.assertEqual(black_cicada_advisory["pest_id"], "black_cicada")
        self.assertEqual(black_cicada_advisory["crop_id"], rose_apple_crop_ids[0])
        self.assertEqual(black_cicada_advisory["status"], "ADVISORY")
        self.assertEqual(black_cicada_advisory["risk_level"], "LOW")
        self.assertEqual(
            black_cicada_advisory["scientific_name"],
            "Huechys sanguinea",
        )
        self.assertEqual(
            black_cicada_advisory["affected_plant_parts"],
            [],
        )
        self.assertIsNone(
            black_cicada_advisory["chemical_control_options"]
        )
        self.assertEqual(black_cicada_advisory["source_references"], [])
        self.assertTrue(
            all(
                item["pest_id"] != "black_prince_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(BLACK_PRINCE_CICADA_ADVISORY_DATA), 1)
        black_prince_advisory = BLACK_PRINCE_CICADA_ADVISORY_DATA[0]
        self.assertEqual(
            black_prince_advisory["solution_id"],
            "black_prince_cicada_general_advisory",
        )
        self.assertEqual(black_prince_advisory["pest_id"], "black_prince_cicada")
        self.assertEqual(black_prince_advisory["status"], "ADVISORY")
        self.assertEqual(black_prince_advisory["risk_level"], "LOW")
        self.assertIsNone(black_prince_advisory["crop_id"])
        self.assertIsNone(
            black_prince_advisory["chemical_control_options"]
        )
        self.assertEqual(black_prince_advisory["source_references"], [])
        self.assertTrue(
            all(
                item["pest_id"] != "bladder_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(BLADDER_CICADA_ADVISORY_DATA), 1)
        bladder_cicada_advisory = BLADDER_CICADA_ADVISORY_DATA[0]
        self.assertEqual(
            bladder_cicada_advisory["solution_id"],
            "bladder_cicada_general_advisory",
        )
        self.assertEqual(bladder_cicada_advisory["pest_id"], "bladder_cicada")
        self.assertEqual(bladder_cicada_advisory["status"], "ADVISORY")
        self.assertEqual(bladder_cicada_advisory["risk_level"], "LOW")
        self.assertIsNone(bladder_cicada_advisory["crop_id"])
        self.assertIsNone(
            bladder_cicada_advisory["chemical_control_options"]
        )
        self.assertEqual(bladder_cicada_advisory["source_references"], [])
        self.assertTrue(
            all(
                item["pest_id"] != "brown_bunyip_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(BROWN_BUNYIP_CICADA_ADVISORY_DATA), 1)
        brown_bunyip_advisory = BROWN_BUNYIP_CICADA_ADVISORY_DATA[0]
        self.assertEqual(
            brown_bunyip_advisory["solution_id"],
            "brown_bunyip_cicada_general_advisory",
        )
        self.assertEqual(
            brown_bunyip_advisory["pest_id"],
            "brown_bunyip_cicada",
        )
        self.assertEqual(brown_bunyip_advisory["status"], "ADVISORY")
        self.assertEqual(brown_bunyip_advisory["risk_level"], "LOW")
        self.assertIsNone(brown_bunyip_advisory["crop_id"])
        self.assertIsNone(
            brown_bunyip_advisory["chemical_control_options"]
        )
        self.assertEqual(brown_bunyip_advisory["source_references"], [])
        self.assertTrue(
            all(
                item["pest_id"] != "carolina_ground_cricket"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(CAROLINA_GROUND_CRICKET_ADVISORY_DATA), 1)
        carolina_cricket_advisory = CAROLINA_GROUND_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(
            carolina_cricket_advisory["solution_id"],
            "carolina_ground_cricket_general_advisory",
        )
        self.assertEqual(
            carolina_cricket_advisory["pest_id"],
            "carolina_ground_cricket",
        )
        self.assertEqual(carolina_cricket_advisory["status"], "ADVISORY")
        self.assertEqual(carolina_cricket_advisory["risk_level"], "LOW")
        self.assertIsNone(carolina_cricket_advisory["crop_id"])
        self.assertIsNone(
            carolina_cricket_advisory["chemical_control_options"]
        )
        self.assertEqual(carolina_cricket_advisory["source_references"], [])
        self.assertTrue(
            all(
                item["pest_id"] != "chorus_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(CHORUS_CICADA_KIWIFRUIT_ADVISORY_DATA), 1)
        chorus_cicada_advisory = CHORUS_CICADA_KIWIFRUIT_ADVISORY_DATA[0]
        self.assertEqual(
            chorus_cicada_advisory["solution_id"],
            "chorus_cicada_kiwifruit_advisory",
        )
        self.assertEqual(chorus_cicada_advisory["pest_id"], "chorus_cicada")
        self.assertEqual(chorus_cicada_advisory["crop_id"], "kiwifruit")
        self.assertEqual(chorus_cicada_advisory["status"], "ADVISORY")
        self.assertEqual(chorus_cicada_advisory["risk_level"], "HIGH")
        self.assertIsNone(
            chorus_cicada_advisory["chemical_control_options"]
        )
        self.assertEqual(chorus_cicada_advisory["source_references"], [])
        self.assertIn(
            "New Zealand",
            chorus_cicada_advisory["geographic_limitation"],
        )
        self.assertIn(
            "not the main documented injury",
            chorus_cicada_advisory["crop_damage"],
        )
        self.assertIn(
            "not guaranteed commercial treatments",
            chorus_cicada_advisory["biological_control_options"][-1],
        )
        self.assertIn(
            "25-44 month",
            chorus_cicada_advisory["expert_advice"],
        )
        self.assertIn(
            "three-to-four-year",
            chorus_cicada_advisory["expert_advice"],
        )
        common_cicada_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "common_cicada"
        ]
        self.assertEqual(len(common_cicada_entries), 1)
        common_cicada = common_cicada_entries[0]
        self.assertEqual(common_cicada["name"], "Common Cicada")
        self.assertEqual(common_cicada["scientific_name"], "Cicadidae spp.")
        self.assertEqual(common_cicada["insect_group"], "Cicada")
        self.assertEqual(common_cicada["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            common_cicada_rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "common_cicada"
            ]
        self.assertEqual(len(common_cicada_rows), 1)
        common_cicada_row = common_cicada_rows[0]
        self.assertEqual(common_cicada_row["risk_level"], "LOW")
        self.assertEqual(
            common_cicada_row["scientific_name"],
            "Cicadidae spp.",
        )
        self.assertEqual(
            common_cicada_row["taxonomy_status"],
            "TAXON_AMBIGUOUS",
        )
        self.assertEqual(common_cicada_row["candidate_scientific_name"], "")
        self.assertEqual(common_cicada_row["accepted_synonyms"], "")
        self.assertEqual(
            common_cicada_row["indian_occurrence_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(common_cicada_row["crop_id"], "")
        self.assertEqual(common_cicada_row["crop_name"], "")
        self.assertEqual(common_cicada_row["verified_host_crops"], "")
        self.assertEqual(common_cicada_row["ecological_host_plants"], "")
        self.assertEqual(
            common_cicada_row["damage_evidence"],
            "General family-level cicada biology only; no species-specific crop damage is established.",
        )
        self.assertEqual(
            common_cicada_row["damage_status"],
            "NOT_ESTABLISHED",
        )
        self.assertIn(
            "not established as species-specific crop damage",
            common_cicada_row["crop_damage"],
        )
        self.assertEqual(
            common_cicada_row["affected_plant_parts"],
            "Roots, young woody branches and twigs (general cicada biology only)",
        )
        self.assertTrue(
            all(item["pest_id"] != "common_cicada" for item in SOLUTION_RECORDS)
        )
        self.assertEqual(len(COMMON_CICADA_ADVISORY_DATA), 1)
        common_cicada_advisory = COMMON_CICADA_ADVISORY_DATA[0]
        self.assertEqual(
            common_cicada_advisory["solution_id"],
            "common_cicada_general_advisory",
        )
        self.assertEqual(common_cicada_advisory["pest_id"], "common_cicada")
        self.assertEqual(common_cicada_advisory["scientific_name"], "Cicadidae spp.")
        self.assertEqual(common_cicada_advisory["risk_level"], "LOW")
        self.assertEqual(common_cicada_advisory["status"], "ADVISORY")
        self.assertIsNone(common_cicada_advisory["crop_id"])
        self.assertIsNone(
            common_cicada_advisory["chemical_control_options"]
        )
        self.assertEqual(common_cicada_advisory["source_references"], [])
        self.assertIn(
            "No species-specific crop damage is established",
            common_cicada_advisory["crop_damage"],
        )
        dark_bush_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "dark_bush_cricket"
        ]
        self.assertEqual(len(dark_bush_entries), 1)
        dark_bush = dark_bush_entries[0]
        self.assertEqual(dark_bush["name"], "Dark Bush-cricket")
        self.assertEqual(
            dark_bush["scientific_name"],
            "Pholidoptera griseoaptera",
        )
        self.assertEqual(
            dark_bush["insect_group"],
            "Bush-cricket / Katydid",
        )
        self.assertEqual(dark_bush["risk"], "LOW")
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            dark_bush_rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "dark_bush_cricket"
            ]
        self.assertEqual(len(dark_bush_rows), 1)
        dark_bush_row = dark_bush_rows[0]
        self.assertEqual(dark_bush_row["risk_level"], "LOW")
        self.assertEqual(dark_bush_row["scientific_name"], "")
        self.assertEqual(
            dark_bush_row["candidate_scientific_name"],
            "Pholidoptera griseoaptera",
        )
        self.assertEqual(
            dark_bush_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            dark_bush_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(dark_bush_row["crop_id"], "")
        self.assertEqual(dark_bush_row["crop_name"], "")
        self.assertEqual(dark_bush_row["verified_host_crops"], "")
        self.assertEqual(
            dark_bush_row["ecological_host_plants"],
            "Rubus fruticosus aggregate; Taraxacum officinale; Urtica dioica",
        )
        self.assertEqual(
            dark_bush_row["ecological_habitat"],
            "Woodland edges; hedgerows; bramble patches; gardens; scrubland",
        )
        self.assertIn(
            "omnivorous",
            dark_bush_row["damage_evidence"].lower(),
        )
        self.assertIn(
            "small-insect predation",
            dark_bush_row["damage_evidence"],
        )
        self.assertEqual(
            dark_bush_row["crop_damage"],
            "No significant commercial crop damage established.",
        )
        self.assertEqual(dark_bush_row["affected_plant_parts"], "")
        self.assertEqual(
            dark_bush_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        self.assertTrue(
            all(item["pest_id"] != "dark_bush_cricket" for item in SOLUTION_RECORDS)
        )
        self.assertEqual(len(DARK_BUSH_CRICKET_ADVISORY_DATA), 1)
        dark_bush_advisory = DARK_BUSH_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(
            dark_bush_advisory["solution_id"],
            "dark_bush_cricket_general_advisory",
        )
        self.assertEqual(dark_bush_advisory["pest_id"], "dark_bush_cricket")
        self.assertEqual(dark_bush_advisory["risk_level"], "LOW")
        self.assertEqual(dark_bush_advisory["status"], "ADVISORY")
        self.assertIsNone(dark_bush_advisory["crop_id"])
        self.assertEqual(dark_bush_advisory["affected_plant_parts"], [])
        self.assertIsNone(dark_bush_advisory["chemical_control_options"])
        self.assertEqual(dark_bush_advisory["source_references"], [])
        self.assertIn(
            "small insects",
            dark_bush_advisory["description"],
        )
        large_dark_bush_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "large_dark_bush_cricket"
        ]
        self.assertEqual(len(large_dark_bush_entries), 1)
        large_dark_bush = large_dark_bush_entries[0]
        self.assertEqual(large_dark_bush["name"], "Large Dark Bush-cricket")
        self.assertEqual(
            large_dark_bush["scientific_name"],
            "Pholidoptera femorata",
        )
        self.assertEqual(large_dark_bush["insect_group"], "Bush-cricket")
        self.assertEqual(large_dark_bush["risk"], "LOW")
        self.assertEqual(large_dark_bush["crop_ids"], [])
        self.assertEqual(
            large_dark_bush["aliases"],
            ["greater_dark_bush_cricket"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "greater_dark_bush_cricket"
                for item in main.PEST_DATA
            )
        )
        self.assertTrue(
            any(
                item["pest_id"] == "dark_bush_cricket"
                for item in main.PEST_DATA
            )
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            large_dark_bush_rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "large_dark_bush_cricket"
            ]
        self.assertEqual(len(large_dark_bush_rows), 1)
        large_dark_bush_row = large_dark_bush_rows[0]
        self.assertEqual(
            large_dark_bush_row["scientific_name"],
            "Pholidoptera femorata",
        )
        self.assertEqual(large_dark_bush_row["risk_level"], "LOW")
        self.assertEqual(
            large_dark_bush_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(large_dark_bush_row["crop_id"], "")
        self.assertEqual(large_dark_bush_row["crop_name"], "")
        self.assertEqual(large_dark_bush_row["verified_host_crops"], "")
        self.assertEqual(
            large_dark_bush_row["ecological_habitat"],
            "Grasslands; shrub-rich vegetation",
        )
        self.assertIn("omnivorous", large_dark_bush_row["damage_evidence"].lower())
        self.assertEqual(
            large_dark_bush_row["crop_damage"],
            "No significant commercial crop damage established.",
        )
        self.assertEqual(
            large_dark_bush_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        self.assertTrue(
            all(
                item["pest_id"] != "large_dark_bush_cricket"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(LARGE_DARK_BUSH_CRICKET_ADVISORY_DATA), 1)
        large_dark_bush_advisory = LARGE_DARK_BUSH_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(
            large_dark_bush_advisory["pest_id"],
            "large_dark_bush_cricket",
        )
        self.assertEqual(large_dark_bush_advisory["status"], "ADVISORY")
        self.assertEqual(large_dark_bush_advisory["risk_level"], "LOW")
        self.assertIsNone(large_dark_bush_advisory["crop_id"])
        self.assertIsNone(
            large_dark_bush_advisory["chemical_control_options"]
        )
        self.assertIsNone(large_dark_bush_advisory["economic_threshold"])
        self.assertIn(
            "European distribution",
            large_dark_bush_advisory["geographic_qualification"],
        )
        self.assertIn(
            "unconfirmed",
            large_dark_bush_advisory["geographic_qualification"],
        )
        self.assertEqual(
            large_dark_bush_advisory["source_refs"],
            [
                "https://www.gbif.org/taxon/4GLSR",
                "https://doi.org/10.3390/insects13070572",
                "https://www.tandfonline.com/doi/full/10.1080/00379271.2018.1521706",
            ],
        )
        double_drummer_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "double_drummer_cicada"
        ]
        self.assertEqual(len(double_drummer_entries), 1)
        double_drummer = double_drummer_entries[0]
        self.assertEqual(
            double_drummer["name"],
            "Double Drummer Cicada",
        )
        self.assertEqual(
            double_drummer["scientific_name"],
            "Thopha saccata",
        )
        self.assertEqual(double_drummer["insect_group"], "Cicada")
        self.assertEqual(double_drummer["risk"], "LOW")
        self.assertFalse(
            any(
                item.get("scientific_name") == "Thopha sessiliba"
                for item in main.PEST_DATA
            )
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            double_drummer_rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "double_drummer_cicada"
            ]
        self.assertEqual(len(double_drummer_rows), 1)
        double_drummer_row = double_drummer_rows[0]
        self.assertEqual(double_drummer_row["risk_level"], "LOW")
        self.assertEqual(double_drummer_row["scientific_name"], "")
        self.assertEqual(
            double_drummer_row["candidate_scientific_name"],
            "Thopha saccata",
        )
        self.assertEqual(
            double_drummer_row["taxonomy_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(double_drummer_row["accepted_synonyms"], "")
        self.assertEqual(
            double_drummer_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(double_drummer_row["crop_id"], "")
        self.assertEqual(double_drummer_row["crop_name"], "")
        self.assertEqual(double_drummer_row["verified_host_crops"], "")
        self.assertEqual(
            double_drummer_row["ecological_host_plants"],
            "Eucalyptus spp.; Angophora spp.; Allocasuarina spp.",
        )
        self.assertEqual(
            double_drummer_row["ecological_habitat"],
            "Eastern Australian forests, woodlands and urban areas",
        )
        self.assertEqual(
            double_drummer_row["crop_damage"],
            "No significant commercial crop damage established.",
        )
        self.assertIn(
            "general cicada root sap feeding and potential twig egg-laying",
            double_drummer_row["damage_evidence"].lower(),
        )
        self.assertEqual(double_drummer_row["affected_plant_parts"], "")
        self.assertEqual(
            double_drummer_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        self.assertTrue(
            all(
                item["pest_id"] != "double_drummer_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(DOUBLE_DRUMMER_CICADA_ADVISORY_DATA), 1)
        double_drummer_advisory = DOUBLE_DRUMMER_CICADA_ADVISORY_DATA[0]
        self.assertEqual(
            double_drummer_advisory["solution_id"],
            "double_drummer_cicada_general_advisory",
        )
        self.assertEqual(
            double_drummer_advisory["pest_id"],
            "double_drummer_cicada",
        )
        self.assertEqual(double_drummer_advisory["risk_level"], "LOW")
        self.assertEqual(double_drummer_advisory["status"], "ADVISORY")
        self.assertIsNone(double_drummer_advisory["crop_id"])
        self.assertEqual(double_drummer_advisory["affected_plant_parts"], [])
        self.assertIsNone(
            double_drummer_advisory["chemical_control_options"]
        )
        self.assertEqual(double_drummer_advisory["source_references"], [])
        self.assertIn(
            "No significant commercial crop damage is established",
            double_drummer_advisory["crop_damage"],
        )
        giant_cicada_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "giant_cicada"
        ]
        self.assertEqual(len(giant_cicada_entries), 1)
        giant_cicada = giant_cicada_entries[0]
        self.assertEqual(giant_cicada["name"], "Giant Cicada")
        self.assertEqual(giant_cicada["scientific_name"], "Quesada gigas")
        self.assertEqual(giant_cicada["risk"], "HIGH")
        self.assertEqual(giant_cicada["crop_ids"], [])
        self.assertIn("Brazilian coffee plantations", giant_cicada["description"])
        self.assertIn("unconfirmed", giant_cicada["description"])
        self.assertTrue(
            all(
                item["pest_id"] != "giant_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(GIANT_CICADA_ADVISORY_DATA), 1)
        giant_cicada_advisory = GIANT_CICADA_ADVISORY_DATA[0]
        self.assertEqual(giant_cicada_advisory["status"], "ADVISORY")
        self.assertEqual(giant_cicada_advisory["risk_level"], "HIGH")
        self.assertIsNone(giant_cicada_advisory["crop_id"])
        self.assertIsNone(
            giant_cicada_advisory["chemical_control_options"]
        )
        self.assertIsNone(giant_cicada_advisory["economic_threshold"])
        self.assertTrue(
            any(
                "adult detection alone" in measure.lower()
                for measure in giant_cicada_advisory["management"]
            )
        )
        self.assertIn(
            "Brazilian coffee plantations",
            giant_cicada_advisory["damage_notes"],
        )
        self.assertIn(
            "Indian plantations",
            giant_cicada_advisory["damage_notes"],
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            giant_cicada_rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "giant_cicada"
            ]
        self.assertEqual(len(giant_cicada_rows), 1)
        giant_cicada_row = giant_cicada_rows[0]
        self.assertEqual(giant_cicada_row["risk_level"], "HIGH")
        self.assertEqual(giant_cicada_row["scientific_name"], "Quesada gigas")
        self.assertEqual(giant_cicada_row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(giant_cicada_row["crop_id"], "")
        self.assertEqual(giant_cicada_row["crop_name"], "")
        self.assertEqual(giant_cicada_row["verified_host_crops"], "")
        self.assertIn("Brazil", giant_cicada_row["crop_damage"])
        self.assertIn(
            "does not establish",
            giant_cicada_row["indian_occurrence_evidence"],
        )
        self.assertIn("coffee", giant_cicada_row["crop_damage"].lower())
        self.assertEqual(
            giant_cicada_row["chemical_management"],
            "No Indian crop-specific chemical treatment established.",
        )
        self.assertIn(
            "root infestation",
            giant_cicada_row["damage_evidence"],
        )
        floury_baker_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "floury_baker_cicada"
        ]
        self.assertEqual(len(floury_baker_entries), 1)
        floury_baker = floury_baker_entries[0]
        self.assertEqual(floury_baker["name"], "Floury Baker Cicada")
        self.assertEqual(floury_baker["scientific_name"], "Aleeta curvicosta")
        self.assertEqual(floury_baker["insect_group"], "Cicada")
        self.assertEqual(floury_baker["risk"], "LOW")
        self.assertEqual(floury_baker["aliases"], ["Floury Baker"])
        self.assertFalse(
            any(
                item["pest_id"] == "abricta_curvicosta"
                for item in main.PEST_DATA
            )
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            floury_baker_rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "floury_baker_cicada"
            ]
        self.assertEqual(len(floury_baker_rows), 1)
        floury_baker_row = floury_baker_rows[0]
        self.assertEqual(
            floury_baker_row["scientific_name"],
            "Aleeta curvicosta",
        )
        self.assertEqual(floury_baker_row["risk_level"], "LOW")
        self.assertEqual(
            floury_baker_row["taxonomy_status"],
            "TAXON_MATCH_CONFIRMED",
        )
        self.assertEqual(
            floury_baker_row["accepted_synonyms"],
            "Abricta curvicosta (historical combination; not a separate pest)",
        )
        self.assertEqual(
            floury_baker_row["indian_occurrence_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(floury_baker_row["crop_id"], "")
        self.assertEqual(floury_baker_row["crop_name"], "")
        self.assertEqual(floury_baker_row["verified_host_crops"], "")
        self.assertIn(
            "Australian orchard",
            floury_baker_row["damage_evidence"],
        )
        self.assertIn(
            "not evidence of Indian crop damage",
            floury_baker_row["damage_evidence"],
        )
        self.assertIn(
            "fruit and nut trees",
            floury_baker_row["crop_damage"],
        )
        self.assertTrue(
            all(
                item["pest_id"] != "floury_baker_cicada"
                for item in SOLUTION_RECORDS
            )
        )
        self.assertEqual(len(FLOURY_BAKER_CICADA_ADVISORY_DATA), 1)
        floury_baker_advisory = FLOURY_BAKER_CICADA_ADVISORY_DATA[0]
        self.assertEqual(
            floury_baker_advisory["pest_id"],
            "floury_baker_cicada",
        )
        self.assertEqual(floury_baker_advisory["status"], "ADVISORY")
        self.assertEqual(floury_baker_advisory["risk_level"], "LOW")
        self.assertIsNone(floury_baker_advisory["crop_id"])
        self.assertIsNone(
            floury_baker_advisory["chemical_control_options"]
        )
        self.assertIsNone(floury_baker_advisory["economic_threshold"])
        self.assertEqual(
            floury_baker_advisory["source_refs"],
            [
                "https://journals.australian.museum/media/Uploads/Journals/17962/1386_complete.pdf"
            ],
        )
        verified_records = [
            item for item in SOLUTION_RECORDS if item["status"] == "VERIFIED"
        ]
        self.assertEqual(len(verified_records), 1)
        self.assertEqual(
            verified_records[0]["solution_id"],
            "rhinoceros_beetle_coconut_high_2026_11_11",
        )
        self.assertEqual(verified_records[0]["pest_id"], "rhinoceros_beetle")
        self.assertEqual(verified_records[0]["crop_id"], "coconut")
        self.assertEqual(verified_records[0]["risk_level"], "HIGH")
        self.assertEqual(verified_records[0]["status"], "VERIFIED")
        self.assertTrue(main._has_verified_solution_evidence(verified_records[0]))
        self.assertIsNone(verified_records[0]["chemical_control_options"])
        self.assertIn(
            "mechanical_control_methods",
            verified_records[0]["source_references"][0]["supports"],
        )
        self.assertIn(
            "Rhinolure pheromone traps",
            verified_records[0]["mechanical_control_methods"],
        )
        pine_weevil = next(
            item
            for item in SOLUTION_RECORDS
            if item["solution_id"] == "pine_weevil_multi_host_high_2026_11_12"
        )
        self.assertIsNone(pine_weevil["crop_id"])
        self.assertEqual(pine_weevil["status"], "NEEDS_REVIEW")
        self.assertEqual(
            [host["crop_id"] for host in pine_weevil["potential_host_crops"]],
            ["pine", "spruce", "fir", "douglas_fir", "hemlock"],
        )
        self.assertTrue(validate_solution_records(SOLUTION_RECORDS))
        with self.assertRaisesRegex(ValueError, "Duplicate pest-crop solution"):
            validate_solution_records(SOLUTION_RECORDS * 2)

    def test_floury_baker_model_label_resolves_to_canonical_catalogue_entry(self):
        pest = SimpleNamespace(
            pest_id="floury_baker_cicada",
            name="Floury Baker Cicada",
            scientific_name="Aleeta curvicosta",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [pest]
        database.query.return_value.filter.return_value.first.return_value = pest

        self.assertIs(
            main._find_pest_record_normalized(database, "Floury Baker"),
            pest,
        )
        self.assertIs(
            main._find_verified_pest_record(
                database,
                "Floury Baker",
                pest_id="floury_baker_cicada",
            ),
            pest,
        )

    def test_kaempfer_cicada_advisory_keeps_hosts_out_of_crop_damage(self):
        import csv

        from solution_data import (
            KAEMPFER_CICADA_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "kaempfer_cicada"
        ]
        self.assertEqual(len(entries), 1)
        kaempfer_cicada = entries[0]
        self.assertEqual(
            kaempfer_cicada["scientific_name"],
            "Planopleura kaempferi",
        )
        self.assertEqual(kaempfer_cicada["risk"], "LOW")
        self.assertEqual(kaempfer_cicada["insect_group"], "Cicada")
        self.assertEqual(kaempfer_cicada["crop_ids"], [])
        self.assertEqual(
            kaempfer_cicada["aliases"],
            ["Platypleura kaempferi"],
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Planopleura kaempferi"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item["scientific_name"] == "Platypleura kaempferi"
                for item in main.PEST_DATA
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "kaempfer_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Planopleura kaempferi")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertIn("Platypleura kaempferi", row["accepted_synonyms"])
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("Walnut", row["ecological_host_plants"])
        self.assertIn("loquat", row["ecological_host_plants"])
        self.assertIn("not proven economic damage", row["ecological_host_plants"])
        self.assertIn(
            "No significant commercial crop damage is established",
            row["crop_damage"],
        )
        self.assertEqual(
            row["chemical_management"],
            "No chemical recommendation established.",
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(KAEMPFER_CICADA_ADVISORY_DATA), 1)
        advisory = KAEMPFER_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "kaempfer_cicada")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIsNone(advisory["economic_threshold"])
        self.assertFalse(
            any(
                item["pest_id"] == "kaempfer_cicada"
                and item["status"] == "VERIFIED"
                for item in SOLUTION_RECORDS
            )
        )

    def test_historical_kaempfer_cicada_name_resolves_to_canonical_record(self):
        kaempfer_cicada = SimpleNamespace(
            pest_id="kaempfer_cicada",
            name="Kaempfer Cicada",
            scientific_name="Planopleura kaempferi",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [kaempfer_cicada]
        database.query.return_value.filter.return_value.first.return_value = (
            kaempfer_cicada
        )

        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Platypleura kaempferi",
            ),
            kaempfer_cicada,
        )
        self.assertIs(
            main._find_verified_pest_record(
                database,
                "Platypleura kaempferi",
                pest_id="kaempfer_cicada",
            ),
            kaempfer_cicada,
        )

    def test_large_brown_cicada_advisory_keeps_geography_and_crop_evidence_separate(self):
        import csv

        from solution_data import (
            LARGE_BROWN_CICADA_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "large_brown_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(
            cicada["scientific_name"],
            "Graptopsaltria nigrofuscata",
        )
        self.assertEqual(cicada["risk"], "MEDIUM")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(
            sum(
                item["scientific_name"] == "Graptopsaltria nigrofuscata"
                for item in main.PEST_DATA
            ),
            1,
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "large_brown_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Graptopsaltria nigrofuscata")
        self.assertEqual(row["risk_level"], "MEDIUM")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertIn("apple", row["crop_damage"].casefold())
        self.assertIn("Japan", row["crop_damage"])
        self.assertIn("localized", row["crop_damage"].casefold())
        self.assertNotIn("White pine", row["crop_damage"])
        self.assertIn("White pine", row["ecological_host_plants"])
        self.assertIn("introduction pathway", row["ecological_host_plants"])
        self.assertEqual(
            row["chemical_management"],
            "No Indian chemical recommendation established.",
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(LARGE_BROWN_CICADA_ADVISORY_DATA), 1)
        advisory = LARGE_BROWN_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "large_brown_cicada")
        self.assertEqual(advisory["risk_level"], "MEDIUM")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIsNone(advisory["economic_threshold"])
        self.assertIn("Japan", advisory["geographic_qualification"])
        self.assertIn("Slovakia", advisory["geographic_qualification"])
        self.assertFalse(
            any(
                item["pest_id"] == "large_brown_cicada"
                and item["status"] == "VERIFIED"
                for item in SOLUTION_RECORDS
            )
        )

    def test_northern_dusk_singing_cicada_advisory_keeps_trees_out_of_crop_associations(self):
        import csv

        from solution_data import (
            NORTHERN_DUSK_SINGING_CICADA_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "northern_dusk_singing_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(cicada["scientific_name"], "Megatibicen grossus")
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(
            cicada["aliases"],
            ["Megatibicen auletes", "Tibicen auletes", "Neotibicen auletes"],
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Megatibicen grossus"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item is not cicada
                and (
                    item.get("name") in cicada["aliases"]
                    or item.get("scientific_name") in cicada["aliases"]
                )
                for item in main.PEST_DATA
            )
        )

        database_cicada = SimpleNamespace(
            pest_id="northern_dusk_singing_cicada",
            name="Northern Dusk-singing Cicada",
            scientific_name="Megatibicen grossus",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_cicada]
        for alias in cicada["aliases"]:
            with self.subTest(alias=alias):
                self.assertIs(
                    main._find_pest_record_normalized(database, alias),
                    database_cicada,
                )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "northern_dusk_singing_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Megatibicen grossus")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        for alias in cicada["aliases"]:
            self.assertIn(alias, row["accepted_synonyms"])
        self.assertIn("oak", row["ecological_host_plants"].casefold())
        self.assertIn("willow", row["ecological_host_plants"].casefold())
        self.assertIn("not crop associations", row["ecological_host_plants"])
        self.assertIn("general cicada biology", row["damage_evidence"])
        self.assertIn("not confirmed economically significant damage", row["damage_evidence"])

        self.assertEqual(len(NORTHERN_DUSK_SINGING_CICADA_ADVISORY_DATA), 1)
        advisory = NORTHERN_DUSK_SINGING_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "northern_dusk_singing_cicada")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("oak", advisory["notes"].casefold())
        self.assertFalse(
            any(
                item["pest_id"] == "northern_dusk_singing_cicada"
                for item in SOLUTION_RECORDS
            )
        )

    def test_periodical_cicada_stays_genus_level_and_regional(self):
        import csv

        from solution_data import (
            PERIODICAL_CICADA_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-014"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(database_references[0]["pest_id"], "periodical_cicada")

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "periodical_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(cicada["scientific_name"], "Magicicada spp.")
        self.assertEqual(cicada["risk"], "MEDIUM")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        species_references = cicada["taxonomic_metadata"]["species_references"]
        self.assertEqual(
            species_references,
            [
                "Magicicada septendecim",
                "Magicicada cassini",
                "Magicicada septendecula",
                "Magicicada tredecim",
                "Magicicada tredecassini",
                "Magicicada tredecula",
                "Magicicada neotredecim",
            ],
        )
        self.assertIn(
            "vary by species and brood",
            cicada["taxonomic_metadata"]["emergence_cycle_note"],
        )
        for species_name in species_references:
            self.assertFalse(
                any(
                    item["name"] == species_name
                    or item["scientific_name"] == species_name
                    for item in main.PEST_DATA
                )
            )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "periodical_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Magicicada spp.")
        self.assertEqual(row["risk_level"], "MEDIUM")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("egg-laying injury", row["damage_evidence"].casefold())
        self.assertIn("twig flagging", row["damage_evidence"].casefold())
        self.assertIn("branch splitting", row["damage_evidence"].casefold())
        self.assertIn("young fruit-tree vulnerability", row["damage_evidence"].casefold())
        self.assertIn("root-fluid feeding is biological behaviour", row["damage_evidence"].casefold())
        self.assertIn("apple", row["ecological_host_plants"].casefold())
        self.assertIn("oak", row["ecological_host_plants"].casefold())
        self.assertIn("not establish Indian crop associations", row["ecological_host_plants"])

        self.assertEqual(len(PERIODICAL_CICADA_ADVISORY_DATA), 1)
        advisory = PERIODICAL_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "periodical_cicada")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "MEDIUM")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("depending on species and brood", advisory["notes"])
        self.assertFalse(
            any(
                item["pest_id"] == "periodical_cicada"
                for item in SOLUTION_RECORDS
            )
        )

    def test_red_squeaker_cicada_resolves_its_historical_name_without_crop_risk(self):
        import csv

        from solution_data import (
            RED_SQUEAKER_CICADA_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-017"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "red_squeaker_cicada",
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "red_squeaker_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(cicada["scientific_name"], "Haemopsalta rubea")
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(
            cicada["aliases"],
            ["Red Squeaker", "Melampsalta rubea"],
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Haemopsalta rubea"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item.get("name") == "Melampsalta rubea"
                or item.get("scientific_name") == "Melampsalta rubea"
                for item in main.PEST_DATA
            )
        )
        self.assertIn("Australian endemic", cicada["description"])
        self.assertIn("Red coloration alone is not sufficient", cicada["description"])

        database_cicada = SimpleNamespace(
            pest_id="red_squeaker_cicada",
            name="Red Squeaker Cicada",
            scientific_name="Haemopsalta rubea",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_cicada]
        self.assertIs(
            main._find_pest_record_normalized(database, "Melampsalta rubea"),
            database_cicada,
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "red_squeaker_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Haemopsalta rubea")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("australian endemic", row["damage_evidence"].casefold())
        self.assertIn(
            "root-fluid feeding is general cicada biology",
            row["damage_evidence"].casefold(),
        )
        self.assertIn(
            "egg laying is general cicada behaviour",
            row["damage_evidence"].casefold(),
        )
        self.assertIn(
            "do not establish commercial crop damage",
            row["damage_evidence"].casefold(),
        )

        self.assertEqual(len(RED_SQUEAKER_CICADA_ADVISORY_DATA), 1)
        advisory = RED_SQUEAKER_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "red_squeaker_cicada")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertFalse(
            any(
                item["pest_id"] == "red_squeaker_cicada"
                for item in SOLUTION_RECORDS
            )
        )

    def test_short_winged_conehead_keeps_regional_food_plants_out_of_crop_records(self):
        import csv

        from solution_data import (
            SHORT_WINGED_CONEHEAD_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-KT-005"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "short_winged_conehead",
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "short_winged_conehead"
        ]
        self.assertEqual(len(entries), 1)
        conehead = entries[0]
        self.assertEqual(
            conehead["scientific_name"],
            "Conocephalus dorsalis",
        )
        self.assertEqual(conehead["risk"], "LOW")
        self.assertEqual(conehead["insect_group"], "Katydid")
        self.assertEqual(conehead["crop_ids"], [])
        self.assertIn("11–18 mm", conehead["description"])
        self.assertIn("occasional long-winged forms", conehead["description"])
        self.assertIn("upward-curving female ovipositor", conehead["description"])
        self.assertIn(
            "British seasonal observations, not Karnataka",
            conehead["description"],
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Conocephalus dorsalis"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item.get("name") == "Conocephalus fuscus"
                or item.get("scientific_name") == "Conocephalus fuscus"
                or "Conocephalus fuscus" in item.get("aliases", [])
                for item in main.PEST_DATA
                if item["pest_id"] == "short_winged_conehead"
            )
        )

        database_conehead = SimpleNamespace(
            pest_id="short_winged_conehead",
            name="Short-winged Conehead",
            scientific_name="Conocephalus dorsalis",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_conehead]
        self.assertIsNone(
            main._find_pest_record_normalized(database, "Conocephalus fuscus")
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "short_winged_conehead"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Conocephalus dorsalis")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("grasses", row["ecological_host_plants"].casefold())
        self.assertIn("rushes", row["ecological_host_plants"].casefold())
        self.assertIn("sedges", row["ecological_host_plants"].casefold())
        self.assertIn("wetland", row["ecological_habitat"].casefold())
        self.assertIn("british seasonal observations", row["ecological_habitat"].casefold())
        self.assertIn("not indian seasonal data", row["ecological_habitat"].casefold())
        self.assertIn("not be applied to karnataka", row["ecological_habitat"].casefold())
        self.assertIn(
            "do not establish commercial crop damage",
            row["damage_evidence"].casefold(),
        )
        self.assertIn("not evidence of cereal crop loss", row["damage_evidence"].casefold())

        self.assertEqual(len(SHORT_WINGED_CONEHEAD_ADVISORY_DATA), 1)
        advisory = SHORT_WINGED_CONEHEAD_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "short_winged_conehead")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertFalse(
            any(
                item["pest_id"] == "short_winged_conehead"
                for item in SOLUTION_RECORDS
            )
        )

    def test_silver_cicada_identity_and_advisory_do_not_create_crop_treatment(self):
        import csv

        from solution_data import SILVER_CICADA_ADVISORY_DATA, SOLUTION_RECORDS

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-018"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(database_references[0]["pest_id"], "silver_cicada")

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "silver_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(cicada["name"], "Silver Cicada")
        self.assertEqual(cicada["scientific_name"], "Tettigettalna argentata")
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertIn(
            "Tettigettalna argentata argentata",
            cicada["aliases"],
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Tettigettalna argentata"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item.get("pest_id") != "silver_cicada"
                and (
                    item.get("name") == "Tettigettalna argentata argentata"
                    or item.get("scientific_name")
                    == "Tettigettalna argentata argentata"
                )
                for item in main.PEST_DATA
            )
        )

        database_cicada = SimpleNamespace(
            pest_id="silver_cicada",
            name="Silver Cicada",
            scientific_name="Tettigettalna argentata",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_cicada]
        self.assertIsNone(
            main._find_pest_record_normalized(database, "Neotibicen pruinosus")
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Tettigettalna argentata argentata",
            ),
            database_cicada,
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "silver_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Tettigettalna argentata")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertIn("grassland", row["ecological_habitat"].casefold())
        self.assertIn("scrub", row["ecological_habitat"].casefold())
        self.assertIn("garrigue", row["ecological_habitat"].casefold())
        self.assertIn("open woodland", row["ecological_habitat"].casefold())
        self.assertIn(
            "crop damage are not established",
            row["crop_damage"].casefold(),
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(SILVER_CICADA_ADVISORY_DATA), 1)
        advisory = SILVER_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "silver_cicada")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn(
            "No Indian pesticide recommendation",
            advisory["notes"],
        )
        self.assertFalse(
            any(item["pest_id"] == "silver_cicada" for item in SOLUTION_RECORDS)
        )

    def test_silver_princess_cicada_remains_separate_and_advisory_only(self):
        import csv

        from solution_data import (
            SILVER_PRINCESS_CICADA_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-019"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "silver_princess_cicada",
        )

        princess_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "silver_princess_cicada"
        ]
        silver_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "silver_cicada"
        ]
        self.assertEqual(len(princess_entries), 1)
        self.assertEqual(len(silver_entries), 1)
        princess = princess_entries[0]
        silver = silver_entries[0]
        self.assertEqual(princess["scientific_name"], "Yoyetta celis")
        self.assertEqual(princess["risk"], "LOW")
        self.assertEqual(princess["insect_group"], "Cicada")
        self.assertEqual(princess["crop_ids"], [])
        self.assertNotIn("silver_cicada", princess.get("aliases", []))
        self.assertNotIn(
            "silver_princess_cicada",
            silver.get("aliases", []),
        )
        self.assertNotEqual(princess["pest_id"], silver["pest_id"])

        princess_record = SimpleNamespace(
            pest_id="silver_princess_cicada",
            name="Silver Princess Cicada",
            scientific_name="Yoyetta celis",
            risk="LOW",
        )
        silver_record = SimpleNamespace(
            pest_id="silver_cicada",
            name="Silver Cicada",
            scientific_name="Tettigettalna argentata",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [
            princess_record,
            silver_record,
        ]
        self.assertIs(
            main._find_pest_record_normalized(database, "Silver Princess Cicada"),
            princess_record,
        )
        self.assertIs(
            main._find_pest_record_normalized(database, "Silver Cicada"),
            silver_record,
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "silver_princess_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Yoyetta celis")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("leptospermum spp.", row["ecological_host_plants"].casefold())
        self.assertIn("melaleuca spp.", row["ecological_host_plants"].casefold())
        self.assertIn("southeastern australia", row["ecological_habitat"].casefold())
        self.assertIn(
            "crop damage are not established",
            row["crop_damage"].casefold(),
        )
        self.assertIn(
            "affected crop parts are not established",
            row["affected_plant_parts"].casefold(),
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(SILVER_PRINCESS_CICADA_ADVISORY_DATA), 1)
        advisory = SILVER_PRINCESS_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "silver_princess_cicada")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("No Indian chemical recommendation", advisory["notes"])
        self.assertFalse(
            any(
                item["pest_id"] == "silver_princess_cicada"
                for item in SOLUTION_RECORDS
            )
        )

    def test_zipping_ambertail_keeps_yoyetta_identity_and_ecology_non_crop_specific(self):
        import csv

        from solution_data import (
            SOLUTION_RECORDS,
            ZIPPING_AMBERTAIL_ADVISORY_DATA,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-025"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "zipping_ambertail",
        )
        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "zipping_ambertail"
        ]
        self.assertEqual(len(entries), 1)
        zipping = entries[0]
        self.assertEqual(zipping["scientific_name"], "Yoyetta repetens")
        self.assertEqual(zipping["risk"], "LOW")
        self.assertEqual(zipping["insect_group"], "Cicada")
        self.assertEqual(zipping["crop_ids"], [])
        self.assertEqual(zipping.get("aliases", []), [])

        zipping_record = SimpleNamespace(
            pest_id="zipping_ambertail",
            name="Zipping Ambertail",
            scientific_name="Yoyetta repetens",
            risk="LOW",
        )
        silver_princess_record = SimpleNamespace(
            pest_id="silver_princess_cicada",
            name="Silver Princess Cicada",
            scientific_name="Yoyetta celis",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [
            zipping_record,
            silver_princess_record,
        ]
        self.assertIs(
            main._find_pest_record_normalized(database, "Yoyetta repetens"),
            zipping_record,
        )
        self.assertIs(
            main._find_pest_record_normalized(database, "Yoyetta celis"),
            silver_princess_record,
        )
        self.assertIsNone(
            main._find_pest_record_normalized(
                database,
                "Western Sydney Ambertail",
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "zipping_ambertail"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Yoyetta repetens")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertEqual(row["accepted_synonyms"], "")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("grey box", row["ecological_host_plants"].casefold())
        self.assertIn("eucalyptus", row["ecological_host_plants"].casefold())
        self.assertIn("not commercial crop hosts", row["ecological_host_plants"])
        self.assertIn(
            "general cicada root feeding and twig egg-laying",
            row["damage_evidence"].casefold(),
        )
        self.assertIn(
            "not confirmed economic damage by yoyetta repetens",
            row["damage_evidence"].casefold(),
        )
        self.assertEqual(row["chemical_management_status"], "NOT_ESTABLISHED")

        self.assertEqual(len(ZIPPING_AMBERTAIL_ADVISORY_DATA), 1)
        advisory = ZIPPING_AMBERTAIL_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "zipping_ambertail")
        self.assertEqual(advisory["scientific_name"], "Yoyetta repetens")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertNotIn("pesticide_dose", advisory)
        self.assertIn(
            "Do not interpret adult presence or calling activity as crop damage.",
            advisory["management"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "zipping_ambertail"
                for item in SOLUTION_RECORDS
            )
        )

    def test_southern_bark_squeaker_preserves_identity_and_avoids_ambiguous_aliases(self):
        import csv

        from solution_data import (
            SOLUTION_RECORDS,
            SOUTHERN_BARK_SQUEAKER_ADVISORY_DATA,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-020"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "southern_bark_squeaker",
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "southern_bark_squeaker"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(cicada["scientific_name"], "Atrapsalta corticina")
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(cicada["aliases"], ["Pauropsalta corticinus"])
        self.assertNotIn("Bark Squeaker", cicada["aliases"])
        self.assertIn(
            "Bark Squeaker",
            cicada["taxonomic_metadata"]["common_name_caution"],
        )
        self.assertIn(
            "Atrapsalta sp. near Atrapsalta corticina",
            cicada["taxonomic_metadata"]["identification_caution"],
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Atrapsalta corticina"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item.get("scientific_name") == "Atrapsalta sp."
                or item.get("name") == "Bark Squeaker"
                for item in main.PEST_DATA
            )
        )

        database_cicada = SimpleNamespace(
            pest_id="southern_bark_squeaker",
            name="Southern Bark Squeaker",
            scientific_name="Atrapsalta corticina",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_cicada]
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Pauropsalta corticinus",
            ),
            database_cicada,
        )
        self.assertIsNone(
            main._find_pest_record_normalized(database, "Atrapsalta sp.")
        )
        self.assertIsNone(
            main._find_pest_record_normalized(database, "Bark Squeaker")
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "southern_bark_squeaker"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Atrapsalta corticina")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("pauropsalta corticinus", row["accepted_synonyms"].casefold())
        self.assertIn("bark squeaker", row["verification_reason"].casefold())
        self.assertIn("atrapsalta sp.", row["verification_reason"].casefold())
        self.assertIn("australia", row["ecological_habitat"].casefold())
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(SOUTHERN_BARK_SQUEAKER_ADVISORY_DATA), 1)
        advisory = SOUTHERN_BARK_SQUEAKER_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "southern_bark_squeaker")
        self.assertEqual(advisory["scientific_name"], "Atrapsalta corticina")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn(
            "No Indian chemical recommendation",
            advisory["notes"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "southern_bark_squeaker"
                for item in SOLUTION_RECORDS
            )
        )

    def test_southern_red_eyed_squeaker_keeps_subspecies_identity_separate(self):
        import csv

        from solution_data import (
            SOLUTION_RECORDS,
            SOUTHERN_RED_EYED_SQUEAKER_ADVISORY_DATA,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-021"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "southern_red_eyed_squeaker",
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "southern_red_eyed_squeaker"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(
            cicada["scientific_name"],
            "Popplepsalta notialis notialis",
        )
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(cicada["aliases"], ["Pauropsalta notialis notialis"])
        metadata = cicada["taxonomic_metadata"]
        self.assertEqual(metadata["parent_species"], "Popplepsalta notialis")
        self.assertEqual(
            metadata["other_subspecies"],
            ["Popplepsalta notialis incitata"],
        )
        self.assertNotIn(
            "Popplepsalta notialis",
            cicada["aliases"],
        )
        self.assertNotIn(
            "Popplepsalta notialis incitata",
            cicada["aliases"],
        )
        self.assertIn(
            "Popplepsalta granitica",
            metadata["identification_note"],
        )

        database_cicada = SimpleNamespace(
            pest_id="southern_red_eyed_squeaker",
            name="Southern Red-eyed Squeaker",
            scientific_name="Popplepsalta notialis notialis",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_cicada]
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Pauropsalta notialis notialis",
            ),
            database_cicada,
        )
        for separate_identity in (
            "Popplepsalta notialis",
            "Popplepsalta notialis incitata",
            "Northern Red-eyed Squeaker",
            "Popplepsalta granitica",
        ):
            self.assertIsNone(
                main._find_pest_record_normalized(database, separate_identity),
                separate_identity,
            )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "southern_red_eyed_squeaker"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            row["scientific_name"],
            "Popplepsalta notialis notialis",
        )
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn(
            "pauropsalta notialis notialis",
            row["accepted_synonyms"].casefold(),
        )
        self.assertIn(
            "popplepsalta notialis incitata",
            row["verification_reason"].casefold(),
        )
        self.assertIn("australia", row["ecological_habitat"].casefold())
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(SOUTHERN_RED_EYED_SQUEAKER_ADVISORY_DATA), 1)
        advisory = SOUTHERN_RED_EYED_SQUEAKER_ADVISORY_DATA[0]
        self.assertEqual(
            advisory["pest_id"],
            "southern_red_eyed_squeaker",
        )
        self.assertEqual(
            advisory["scientific_name"],
            "Popplepsalta notialis notialis",
        )
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn(
            "No Indian chemical recommendation",
            advisory["notes"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "southern_red_eyed_squeaker"
                for item in SOLUTION_RECORDS
            )
        )

    def test_swamp_cicada_keeps_subspecies_taxonomy_and_advisory_separate(self):
        import csv

        from solution_data import SOLUTION_RECORDS, SWAMP_CICADA_ADVISORY_DATA

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-022"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(database_references[0]["pest_id"], "swamp_cicada")

        entries = [
            item for item in main.PEST_DATA if item["pest_id"] == "swamp_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(cicada["scientific_name"], "Neotibicen tibicen")
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(cicada["aliases"], ["Tibicen chloromerus"])
        metadata = cicada["taxonomic_metadata"]
        self.assertEqual(metadata["rank"], "Species")
        self.assertEqual(
            metadata["recognized_subspecies"],
            [
                "Neotibicen tibicen tibicen",
                "Neotibicen tibicen australis",
            ],
        )
        self.assertEqual(
            metadata["subspecies_common_names"]["Southern Swamp Cicada"],
            "Neotibicen tibicen australis",
        )
        self.assertNotIn("Neotibicen tibicen tibicen", cicada["aliases"])
        self.assertNotIn("Neotibicen tibicen australis", cicada["aliases"])
        self.assertFalse(
            any(
                item.get("name") == "Southern Swamp Cicada"
                or item.get("scientific_name")
                in {
                    "Neotibicen tibicen tibicen",
                    "Neotibicen tibicen australis",
                }
                for item in main.PEST_DATA
            )
        )

        database_cicada = SimpleNamespace(
            pest_id="swamp_cicada",
            name="Swamp Cicada",
            scientific_name="Neotibicen tibicen",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_cicada]
        self.assertIs(
            main._find_pest_record_normalized(database, "Tibicen chloromerus"),
            database_cicada,
        )
        self.assertIsNone(
            main._find_pest_record_normalized(
                database,
                "Neotibicen tibicen australis",
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "swamp_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Neotibicen tibicen")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("tibicen chloromerus", row["accepted_synonyms"].casefold())
        self.assertIn("n. t. tibicen", row["verification_reason"].casefold())
        self.assertIn("n. t. australis", row["verification_reason"].casefold())
        self.assertIn("southern swamp cicada", row["verification_reason"].casefold())
        for habitat in ("wetlands", "marshes", "meadows", "overgrown fields"):
            self.assertIn(habitat, row["ecological_habitat"].casefold())
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(SWAMP_CICADA_ADVISORY_DATA), 1)
        advisory = SWAMP_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "swamp_cicada")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("No Indian pesticide recommendation", advisory["notes"])
        self.assertFalse(
            any(item["pest_id"] == "swamp_cicada" for item in SOLUTION_RECORDS)
        )

    def test_razor_grinder_cicada_preserves_identity_and_regional_evidence(self):
        import csv

        from solution_data import (
            RAZOR_GRINDER_CICADA_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-016"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "razor_grinder_cicada",
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "razor_grinder_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(
            cicada["scientific_name"],
            "Henicopsaltria eydouxii",
        )
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(
            sum(
                item["scientific_name"] == "Henicopsaltria eydouxii"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertIn("Psaltoda harrisii", cicada["taxonomic_metadata"]["historical_common_name_note"])
        self.assertFalse(
            any(
                "Psaltoda harrisii" in item.get("aliases", [])
                for item in main.PEST_DATA
            )
        )

        database_cicada = SimpleNamespace(
            pest_id="razor_grinder_cicada",
            name="Razor Grinder Cicada",
            scientific_name="Henicopsaltria eydouxii",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_cicada]
        self.assertIs(
            main._find_pest_record_normalized(database, "Razor Grinder"),
            database_cicada,
        )
        self.assertIsNone(
            main._find_pest_record_normalized(database, "Psaltoda harrisii")
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "razor_grinder_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Henicopsaltria eydouxii")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("zigzag forewing markings", row["damage_evidence"].casefold())
        self.assertIn("loud calling", row["damage_evidence"].casefold())
        self.assertIn("general cicada biology", row["damage_evidence"].casefold())
        self.assertIn("not confirmed economic damage", row["damage_evidence"].casefold())
        self.assertIn("eastern australian", row["ecological_habitat"].casefold())

        self.assertEqual(len(RAZOR_GRINDER_CICADA_ADVISORY_DATA), 1)
        advisory = RAZOR_GRINDER_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "razor_grinder_cicada")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertFalse(
            any(
                item["pest_id"] == "razor_grinder_cicada"
                for item in SOLUTION_RECORDS
            )
        )

    def test_plains_cicada_advisory_keeps_twig_injury_non_crop_specific(self):
        import csv

        from solution_data import (
            PLAINS_CICADA_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "plains_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(
            cicada["scientific_name"],
            "Megatibicen dealbatus",
        )
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(
            sum(
                item["scientific_name"] == "Megatibicen dealbatus"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertIn("body colour varies", cicada["description"])
        self.assertIn("calling sound alone is not sufficient", cicada["description"])
        self.assertIn(
            "not firmly established",
            cicada["description"],
        )
        self.assertIn("Karnataka", cicada["description"])
        self.assertIn("taxonomic confirmation", cicada["description"])

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "plains_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Megatibicen dealbatus")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("localized egg-laying wounds", row["damage_evidence"].casefold())
        self.assertIn(
            "not established as major crop damage",
            row["damage_evidence"].casefold(),
        )
        self.assertIn(
            "not confirmed serious root damage",
            row["damage_evidence"].casefold(),
        )
        self.assertIn("trees and woody vegetation", row["ecological_host_plants"].casefold())

        self.assertEqual(len(PLAINS_CICADA_ADVISORY_DATA), 1)
        advisory = PLAINS_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "plains_cicada")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertFalse(
            any(
                item["pest_id"] == "plains_cicada"
                for item in SOLUTION_RECORDS
            )
        )

    def test_walkers_cicada_keeps_proposed_subspecies_unresolved_and_non_crop(self):
        import csv

        from solution_data import SOLUTION_RECORDS, WALKERS_CICADA_ADVISORY_DATA

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-023"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(database_references[0]["pest_id"], "walkers_cicada")

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "walkers_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(
            cicada["scientific_name"],
            "Megatibicen pronotalis",
        )
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertIn("Tibicen pronotalis", cicada["aliases"])
        self.assertNotIn("Tibicen walkeri", cicada["aliases"])
        self.assertNotIn("Tibicen pronotalis walkeri", cicada["aliases"])
        self.assertEqual(
            cicada["taxonomic_metadata"]["proposed_subspecies_status"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Megatibicen pronotalis"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item["pest_id"] == "tibicen_pronotalis_walkeri"
                or item["scientific_name"] == "Tibicen pronotalis walkeri"
                for item in main.PEST_DATA
            )
        )

        walkers = SimpleNamespace(
            pest_id="walkers_cicada",
            name="Walker's Cicada",
            scientific_name="Megatibicen pronotalis",
            risk="LOW",
        )
        plains = SimpleNamespace(
            pest_id="plains_cicada",
            name="Plains Cicada",
            scientific_name="Megatibicen dealbatus",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [walkers, plains]
        for label in (
            "Megatibicen pronotalis",
            "Tibicen pronotalis",
            "Walker's Annual Cicada",
            "Great Harvestfly",
        ):
            with self.subTest(label=label):
                self.assertIs(
                    main._find_pest_record_normalized(database, label),
                    walkers,
                )
        for unconfirmed_name in (
            "Tibicen walkeri",
            "Tibicen pronotalis walkeri",
        ):
            with self.subTest(unconfirmed_name=unconfirmed_name):
                self.assertIsNone(
                    main._find_pest_record_normalized(database, unconfirmed_name)
                )
        self.assertIs(
            main._find_pest_record_normalized(database, "Megatibicen dealbatus"),
            plains,
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "walkers_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Megatibicen pronotalis")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertEqual(row["candidate_scientific_name"], "Tibicen pronotalis walkeri")
        self.assertIn("NEEDS_REVIEW", row["verification_reason"])
        self.assertIn("not an alias", row["verification_reason"])
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertEqual(row["damage_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["affected_plant_parts"], "None confirmed.")
        self.assertEqual(row["chemical_management_status"], "NOT_ESTABLISHED")
        tree_associations = row["ecological_host_plants"].casefold()
        for tree in ("cottonwood", "willow", "sycamore", "maple"):
            self.assertIn(tree, tree_associations)
        self.assertIn("not commercial crop hosts", tree_associations)

        self.assertEqual(len(WALKERS_CICADA_ADVISORY_DATA), 1)
        advisory = WALKERS_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "walkers_cicada")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("No routine pest treatment is recommended", advisory["notes"])
        self.assertFalse(
            any(
                item["pest_id"] == "walkers_cicada"
                for item in SOLUTION_RECORDS
            )
        )

    def test_white_drummer_cicada_keeps_australian_ecology_non_crop_specific(self):
        import csv

        from solution_data import (
            SOLUTION_RECORDS,
            WHITE_DRUMMER_CICADA_ADVISORY_DATA,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-CI-024"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "white_drummer_cicada",
        )
        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "white_drummer_cicada"
        ]
        self.assertEqual(len(entries), 1)
        cicada = entries[0]
        self.assertEqual(cicada["name"], "White Drummer Cicada")
        self.assertEqual(cicada["scientific_name"], "Arunta perulata")
        self.assertEqual(cicada["risk"], "LOW")
        self.assertEqual(cicada["insect_group"], "Cicada")
        self.assertEqual(cicada["crop_ids"], [])
        self.assertEqual(
            cicada["taxonomic_metadata"],
            {
                "family": "Cicadidae",
                "order": "Hemiptera",
            },
        )
        self.assertIn("Cooktown", cicada["description"])
        self.assertIn("far northern Cape York", cicada["description"])
        self.assertIn("Narooma", cicada["description"])
        self.assertIn("white, sac-like tymbal covers", cicada["description"])
        self.assertIn("females lack", cicada["description"])
        self.assertIn("40 mm", cicada["description"])
        self.assertIn(
            "no species-specific underground development duration",
            cicada["description"],
        )
        self.assertIn(
            "not confirmed economic damage by this species",
            cicada["description"],
        )
        self.assertFalse(
            any(item["pest_id"] == "white_drummer" for item in main.PEST_DATA)
        )

        white_drummer = SimpleNamespace(
            pest_id="white_drummer_cicada",
            name="White Drummer Cicada",
            scientific_name="Arunta perulata",
            risk="LOW",
        )
        double_drummer = SimpleNamespace(
            pest_id="double_drummer_cicada",
            name="Double Drummer Cicada",
            scientific_name="Thopha saccata",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [
            white_drummer,
            double_drummer,
        ]
        self.assertIs(
            main._find_pest_record_normalized(database, "Arunta perulata"),
            white_drummer,
        )
        self.assertIs(
            main._find_pest_record_normalized(database, "White Drummer"),
            white_drummer,
        )
        self.assertIs(
            main._find_pest_record_normalized(database, "Thopha saccata"),
            double_drummer,
        )
        self.assertIsNone(
            main._find_pest_record_normalized(database, "Orange Drummer")
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "white_drummer_cicada"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Arunta perulata")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertEqual(row["damage_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["affected_plant_parts_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["chemical_management_status"], "NOT_ESTABLISHED")
        self.assertIn(
            "general cicada root feeding and twig egg-laying",
            row["damage_evidence"].casefold(),
        )
        self.assertIn(
            "not confirmed economic damage by arunta perulata",
            row["damage_evidence"].casefold(),
        )
        ecological_hosts = row["ecological_host_plants"].casefold()
        for vegetation in (
            "she-oak",
            "swamp oak",
            "banksia",
            "coast wattle",
        ):
            self.assertIn(vegetation, ecological_hosts)
        self.assertIn("not commercial crop hosts", ecological_hosts)
        self.assertIn("Cooktown", row["ecological_habitat"])
        self.assertIn("Narooma", row["ecological_habitat"])
        self.assertIn("far northern Cape York", row["ecological_habitat"])

        self.assertEqual(len(WHITE_DRUMMER_CICADA_ADVISORY_DATA), 1)
        advisory = WHITE_DRUMMER_CICADA_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "white_drummer_cicada")
        self.assertEqual(advisory["scientific_name"], "Arunta perulata")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn(
            "No routine pest treatment is recommended",
            advisory["recommended_treatment"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "white_drummer_cicada"
                for item in SOLUTION_RECORDS
            )
        )

    def test_northern_mole_cricket_advisory_keeps_tunnels_and_habitats_non_crop(self):
        import csv

        from solution_data import (
            NORTHERN_MOLE_CRICKET_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "northern_mole_cricket"
        ]
        self.assertEqual(len(entries), 1)
        mole_cricket = entries[0]
        self.assertEqual(
            mole_cricket["scientific_name"],
            "Neocurtilla hexadactyla",
        )
        self.assertEqual(mole_cricket["risk"], "LOW")
        self.assertEqual(mole_cricket["insect_group"], "Mole Cricket")
        self.assertEqual(mole_cricket["crop_ids"], [])
        self.assertIn("fore-tibial", mole_cricket["description"])
        self.assertIn(
            "conspicuous long external ovipositor",
            mole_cricket["description"],
        )
        self.assertIn("do not prove crop injury", mole_cricket["description"])

        european_mole_cricket = next(
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "european_mole_cricket"
        )
        self.assertNotEqual(
            european_mole_cricket["pest_id"],
            mole_cricket["pest_id"],
        )
        self.assertNotIn(
            "Gryllotalpa gryllotalpa",
            mole_cricket.get("aliases", []),
        )
        self.assertNotIn(
            "Neoscapteriscus borellii",
            mole_cricket.get("aliases", []),
        )

        database_mole_cricket = SimpleNamespace(
            pest_id="northern_mole_cricket",
            name="Northern Mole Cricket",
            scientific_name="Neocurtilla hexadactyla",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_mole_cricket]
        for unrelated_name in (
            "Gryllotalpa gryllotalpa",
            "Neoscapteriscus borellii",
            "Neoscapteriscus vicinus",
        ):
            with self.subTest(unrelated_name=unrelated_name):
                self.assertIsNone(
                    main._find_pest_record_normalized(
                        database,
                        unrelated_name,
                    )
                )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "northern_mole_cricket"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Neocurtilla hexadactyla")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("root feeding", row["damage_evidence"].casefold())
        self.assertIn("soil tunnelling", row["damage_evidence"].casefold())
        self.assertIn("seedling disturbance", row["damage_evidence"].casefold())
        self.assertIn(
            "do not by themselves establish feeding injury",
            row["damage_evidence"].casefold(),
        )
        self.assertIn("moist grasslands", row["ecological_habitat"].casefold())
        self.assertIn("marshes", row["ecological_habitat"].casefold())
        self.assertIn("lawns", row["ecological_habitat"].casefold())

        self.assertEqual(len(NORTHERN_MOLE_CRICKET_ADVISORY_DATA), 1)
        advisory = NORTHERN_MOLE_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "northern_mole_cricket")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("Tunnelling alone does not prove crop damage", advisory["notes"])
        self.assertFalse(
            any(
                item["pest_id"] == "northern_mole_cricket"
                for item in SOLUTION_RECORDS
            )
        )

    def test_northern_katydid_advisory_keeps_hardwood_hosts_out_of_crops(self):
        import csv

        from solution_data import (
            NORTHERN_KATYDID_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "northern_katydid"
        ]
        self.assertEqual(len(entries), 1)
        katydid = entries[0]
        self.assertEqual(
            katydid["scientific_name"],
            "Pterophylla camellifolia",
        )
        self.assertEqual(katydid["risk"], "LOW")
        self.assertEqual(katydid["insect_group"], "Katydid")
        self.assertEqual(katydid["crop_ids"], [])
        self.assertEqual(katydid["aliases"], ["Common True Katydid"])
        self.assertEqual(
            sum(
                item["pest_id"] == "northern_katydid"
                for item in main.PEST_DATA
            ),
            1,
        )

        database_katydid = SimpleNamespace(
            pest_id="northern_katydid",
            name="Northern Katydid",
            scientific_name="Pterophylla camellifolia",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_katydid]
        self.assertIs(
            main._find_pest_record_normalized(database, "Common True Katydid"),
            database_katydid,
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "northern_katydid"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Pterophylla camellifolia")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("tree foliage feeding", row["damage_evidence"].casefold())
        self.assertIn("localized defoliation", row["damage_evidence"].casefold())
        self.assertIn(
            "commercial crop damage is not established",
            row["damage_evidence"].casefold(),
        )
        self.assertIn("oak", row["ecological_host_plants"].casefold())
        self.assertIn("hardwood", row["ecological_host_plants"].casefold())
        self.assertIn(
            "not crop associations",
            row["ecological_host_plants"].casefold(),
        )

        self.assertEqual(len(NORTHERN_KATYDID_ADVISORY_DATA), 1)
        advisory = NORTHERN_KATYDID_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "northern_katydid")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("oak", advisory["notes"].casefold())
        self.assertFalse(
            any(
                item["pest_id"] == "northern_katydid"
                for item in SOLUTION_RECORDS
            )
        )

    def test_large_tree_cricket_advisory_has_no_crop_or_chemical_solution(self):
        import csv

        from solution_data import (
            LARGE_TREE_CRICKET_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "large_tree_cricket"
        ]
        self.assertEqual(len(entries), 1)
        cricket = entries[0]
        self.assertEqual(
            cricket["scientific_name"],
            "Oecanthus dulcisonans",
        )
        self.assertEqual(cricket["risk"], "LOW")
        self.assertEqual(cricket["insect_group"], "Cricket")
        self.assertEqual(cricket["crop_ids"], [])
        self.assertEqual(
            sum(
                item["scientific_name"] == "Oecanthus dulcisonans"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item["scientific_name"] == "Oecanthus pellucens"
                and item["pest_id"] == "large_tree_cricket"
                for item in main.PEST_DATA
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "large_tree_cricket"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Oecanthus dulcisonans")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertIn("Gryllidae", row["verification_reason"])
        self.assertIn("Oecanthinae", row["verification_reason"])
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("Grapevine", row["ecological_host_plants"])
        self.assertIn("calling observation only", row["ecological_host_plants"])
        self.assertIn("not a confirmed feeding host", row["ecological_host_plants"])
        self.assertIn(
            "No significant commercial crop damage is established",
            row["crop_damage"],
        )
        self.assertEqual(
            row["chemical_management"],
            "No chemical recommendation established.",
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(LARGE_TREE_CRICKET_ADVISORY_DATA), 1)
        advisory = LARGE_TREE_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "large_tree_cricket")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIsNone(advisory["economic_threshold"])
        self.assertFalse(
            any(
                item["pest_id"] == "large_tree_cricket"
                and item["status"] == "VERIFIED"
                for item in SOLUTION_RECORDS
            )
        )

    def test_mediterranean_wart_biter_keeps_turkish_crop_evidence_regional(self):
        import csv

        from solution_data import (
            MEDITERRANEAN_WART_BITER_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "mediterranean_wart_biter"
        ]
        self.assertEqual(len(entries), 1)
        pest = entries[0]
        self.assertEqual(pest["scientific_name"], "Decticus albifrons")
        self.assertEqual(pest["risk"], "MEDIUM")
        self.assertEqual(pest["insect_group"], "Katydid")
        self.assertEqual(pest["crop_ids"], [])
        self.assertIn("Turkey", pest["description"])
        self.assertIn("does not confirm an established Indian", pest["description"])
        self.assertIn("individual specimen", pest["description"])
        self.assertIn("not diagnostic", pest["symptoms"])
        self.assertEqual(
            sum(
                item["scientific_name"] == "Decticus albifrons"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item["scientific_name"] == "Decticus verrucivorus"
                and item["pest_id"] == "mediterranean_wart_biter"
                for item in main.PEST_DATA
            )
        )

        database_pest = SimpleNamespace(
            pest_id="mediterranean_wart_biter",
            name="Mediterranean Wart-biter",
            scientific_name="Decticus albifrons",
            risk="MEDIUM",
        )
        database = Mock()
        database.query.return_value.all.return_value = [database_pest]
        self.assertIs(
            main._find_pest_record_normalized(database, "Decticus albifrons"),
            database_pest,
        )
        self.assertIsNone(
            main._find_pest_record_normalized(database, "Decticus verrucivorus")
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "mediterranean_wart_biter"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Decticus albifrons")
        self.assertEqual(row["risk_level"], "MEDIUM")
        self.assertEqual(row["relationship_status"], "NEEDS_REVIEW")
        self.assertEqual(row["indian_occurrence_status"], "NEEDS_REVIEW")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        for crop in ("wheat", "barley", "maize", "cotton", "melon", "forage crops"):
            self.assertIn(crop, row["damage_evidence"].casefold())
        self.assertIn("Turkey", row["damage_evidence"])
        self.assertIn("cereal ears", row["damage_evidence"])
        self.assertIn("omnivorous", row["damage_evidence"])
        self.assertIn("not confirmed Indian host records", row["damage_evidence"])

        self.assertEqual(len(MEDITERRANEAN_WART_BITER_ADVISORY_DATA), 1)
        advisory = MEDITERRANEAN_WART_BITER_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "mediterranean_wart_biter")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "MEDIUM")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("Turkey", advisory["notes"])
        self.assertFalse(
            any(
                item["pest_id"] == "mediterranean_wart_biter"
                and item["status"] == "VERIFIED"
                for item in SOLUTION_RECORDS
            )
        )

    def test_snowy_tree_cricket_keeps_identity_and_regional_damage_separate(self):
        import csv

        from solution_data import (
            SNOWY_TREE_CRICKET_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-FC-015"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(
            database_references[0]["pest_id"],
            "snowy_tree_cricket",
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "snowy_tree_cricket"
        ]
        self.assertEqual(len(entries), 1)
        snowy = entries[0]
        self.assertEqual(snowy["scientific_name"], "Oecanthus fultoni")
        self.assertEqual(snowy["risk"], "MEDIUM")
        self.assertEqual(snowy["insect_group"], "Crickets")
        self.assertEqual(snowy["crop_ids"], [])
        self.assertEqual(snowy.get("aliases", []), [])
        self.assertEqual(
            snowy["taxonomic_metadata"]["family_classification"],
            "Oecanthidae (newer classification)",
        )
        self.assertEqual(
            snowy["taxonomic_metadata"]["older_family_classification"],
            "Gryllidae",
        )
        misidentification = snowy["taxonomic_metadata"][
            "historical_misidentification_note"
        ]
        self.assertIn("Oecanthus niveus", misidentification)
        self.assertNotIn("Oecanthus niveus", snowy.get("aliases", []))
        self.assertIn("minor and localised", snowy["description"])
        self.assertIn("North American reports", snowy["description"])

        tree_crickets = {
            "snowy_tree_cricket": SimpleNamespace(
                pest_id="snowy_tree_cricket",
                name="Snowy Tree Cricket",
                scientific_name="Oecanthus fultoni",
                risk="MEDIUM",
            ),
            "european_tree_cricket": SimpleNamespace(
                pest_id="european_tree_cricket",
                name="European Tree Cricket",
                scientific_name="Oecanthus pellucens",
                risk="LOW",
            ),
            "large_tree_cricket": SimpleNamespace(
                pest_id="large_tree_cricket",
                name="Large Tree Cricket",
                scientific_name="Oecanthus dulcisonans",
                risk="LOW",
            ),
        }
        database = Mock()
        database.query.return_value.all.return_value = list(tree_crickets.values())
        for pest_id, record in tree_crickets.items():
            self.assertIs(
                main._find_pest_record_normalized(database, pest_id),
                record,
            )
        self.assertIsNone(
            main._find_pest_record_normalized(database, "Oecanthus niveus")
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "snowy_tree_cricket"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Oecanthus fultoni")
        self.assertEqual(row["risk_level"], "MEDIUM")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        for crop in ("apple", "peach", "cherry", "hazelnut", "raspberry", "blackberry"):
            self.assertIn(crop, row["damage_evidence"].casefold())
        self.assertIn("north american", row["damage_evidence"].casefold())
        self.assertIn("minor and localised", row["crop_damage"].casefold())
        self.assertIn("oecanthidae", row["verification_reason"].casefold())
        self.assertIn("gryllidae", row["verification_reason"].casefold())
        self.assertIn("oecanthus niveus", row["verification_reason"].casefold())
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(SNOWY_TREE_CRICKET_ADVISORY_DATA), 1)
        advisory = SNOWY_TREE_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "snowy_tree_cricket")
        self.assertEqual(advisory["scientific_name"], "Oecanthus fultoni")
        self.assertEqual(advisory["risk_level"], "MEDIUM")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn(
            "No verified Indian chemical treatment",
            advisory["notes"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "snowy_tree_cricket"
                for item in SOLUTION_RECORDS
            )
        )

    def test_tree_cricket_scientific_names_resolve_to_distinct_records(self):
        large_tree_cricket = SimpleNamespace(
            pest_id="large_tree_cricket",
            name="Large Tree Cricket",
            scientific_name="Oecanthus dulcisonans",
            risk="LOW",
        )
        european_tree_cricket = SimpleNamespace(
            pest_id="european_tree_cricket",
            name="European Tree Cricket",
            scientific_name="Oecanthus pellucens",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [
            large_tree_cricket,
            european_tree_cricket,
        ]

        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Oecanthus dulcisonans",
            ),
            large_tree_cricket,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Oecanthus pellucens",
            ),
            european_tree_cricket,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Large Tree Cricket",
            ),
            large_tree_cricket,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "European Tree Cricket",
            ),
            european_tree_cricket,
        )

    def test_lesser_field_grasshopper_advisory_has_no_crop_or_chemical_solution(self):
        import csv

        from solution_data import (
            LESSER_FIELD_GRASSHOPPER_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "lesser_field_grasshopper"
        ]
        self.assertEqual(len(entries), 1)
        grasshopper = entries[0]
        self.assertEqual(grasshopper["scientific_name"], "Chorthippus mollis")
        self.assertEqual(grasshopper["risk"], "LOW")
        self.assertEqual(grasshopper["insect_group"], "Grasshopper")
        self.assertEqual(grasshopper["crop_ids"], [])
        self.assertEqual(
            grasshopper["nominate_subspecies"],
            "Chorthippus mollis mollis",
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Chorthippus mollis"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item["pest_id"] == "chorthippus_mollis_mollis"
                or item["scientific_name"] == "Chorthippus mollis mollis"
                for item in main.PEST_DATA
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "lesser_field_grasshopper"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Chorthippus mollis")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertIn("Chorthippus mollis mollis", row["verification_reason"])
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        habitat = row["ecological_habitat"].casefold()
        self.assertIn("dry grasslands", habitat)
        self.assertIn("sandy", habitat)
        self.assertIn("fallow", habitat)
        self.assertEqual(
            row["crop_damage"],
            "No significant species-specific commercial crop damage is established.",
        )
        self.assertEqual(
            row["chemical_management"],
            "No chemical recommendation established.",
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(LESSER_FIELD_GRASSHOPPER_ADVISORY_DATA), 1)
        advisory = LESSER_FIELD_GRASSHOPPER_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "lesser_field_grasshopper")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIsNone(advisory["economic_threshold"])
        self.assertFalse(
            any(
                item["pest_id"] == "lesser_field_grasshopper"
                and item["status"] == "VERIFIED"
                for item in SOLUTION_RECORDS
            )
        )

    def test_lesser_field_grasshopper_lookup_does_not_match_other_chorthippus(self):
        grasshopper = SimpleNamespace(
            pest_id="lesser_field_grasshopper",
            name="Lesser Field Grasshopper",
            scientific_name="Chorthippus mollis",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [grasshopper]

        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Chorthippus mollis",
            ),
            grasshopper,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Lesser Field Grasshopper",
            ),
            grasshopper,
        )
        self.assertIsNone(
            main._find_pest_record_normalized(
                database,
                "Chorthippus brunneus",
            )
        )

    def test_meadow_grasshopper_advisory_has_no_crop_or_chemical_solution(self):
        import csv

        from solution_data import (
            MEADOW_GRASSHOPPER_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "meadow_grasshopper"
        ]
        self.assertEqual(len(entries), 1)
        grasshopper = entries[0]
        self.assertEqual(
            grasshopper["scientific_name"],
            "Pseudochorthippus parallelus",
        )
        self.assertEqual(grasshopper["risk"], "LOW")
        self.assertEqual(grasshopper["insect_group"], "Grasshopper")
        self.assertEqual(grasshopper["crop_ids"], [])
        self.assertEqual(
            grasshopper["aliases"],
            ["Chorthippus parallelus"],
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Pseudochorthippus parallelus"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item["pest_id"] == "chorthippus_parallelus"
                or item["scientific_name"] == "Chorthippus parallelus"
                for item in main.PEST_DATA
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "meadow_grasshopper"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Pseudochorthippus parallelus")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertIn("Chorthippus parallelus", row["verification_reason"])
        self.assertIn("historical scientific-name alias", row["verification_reason"])
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        habitat = row["ecological_habitat"].casefold()
        for habitat_name in ("meadows", "pastures", "wetlands", "field margins"):
            self.assertIn(habitat_name, habitat)
        self.assertEqual(
            row["crop_damage"],
            "Significant species-specific commercial crop damage is not established.",
        )
        self.assertEqual(
            row["chemical_management"],
            "No chemical recommendation established.",
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(MEADOW_GRASSHOPPER_ADVISORY_DATA), 1)
        advisory = MEADOW_GRASSHOPPER_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "meadow_grasshopper")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIsNone(advisory["economic_threshold"])
        self.assertFalse(
            any(
                item["pest_id"] == "meadow_grasshopper"
                and item["status"] == "VERIFIED"
                for item in SOLUTION_RECORDS
            )
        )

    def test_meadow_grasshopper_historical_name_does_not_match_lesser_field(self):
        meadow_grasshopper = SimpleNamespace(
            pest_id="meadow_grasshopper",
            name="Meadow Grasshopper",
            scientific_name="Pseudochorthippus parallelus",
            risk="LOW",
        )
        lesser_field_grasshopper = SimpleNamespace(
            pest_id="lesser_field_grasshopper",
            name="Lesser Field Grasshopper",
            scientific_name="Chorthippus mollis",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [
            meadow_grasshopper,
            lesser_field_grasshopper,
        ]

        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Pseudochorthippus parallelus",
            ),
            meadow_grasshopper,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Chorthippus parallelus",
            ),
            meadow_grasshopper,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Chorthippus mollis",
            ),
            lesser_field_grasshopper,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Lesser Field Grasshopper",
            ),
            lesser_field_grasshopper,
        )

    def test_marsh_cricket_advisory_preserves_subspecies_and_indian_record(self):
        import csv

        from solution_data import MARSH_CRICKET_ADVISORY_DATA, SOLUTION_RECORDS

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "marsh_cricket"
        ]
        self.assertEqual(len(entries), 1)
        marsh_cricket = entries[0]
        self.assertEqual(
            marsh_cricket["scientific_name"],
            "Pteronemobius heydenii",
        )
        self.assertEqual(marsh_cricket["risk"], "LOW")
        self.assertEqual(marsh_cricket["insect_group"], "Cricket")
        self.assertEqual(marsh_cricket["crop_ids"], [])
        self.assertEqual(
            marsh_cricket["taxonomic_metadata"],
            {
                "family": "Trigonidiidae",
                "subfamily": "Nemobiinae",
                "nominate_subspecies": "Pteronemobius heydenii heydenii",
                "other_subspecies": ["Pteronemobius heydenii concolor"],
                "identification_note": (
                    "Do not assume Indian records of the species complex "
                    "represent the nominate subspecies."
                ),
            },
        )
        self.assertFalse(
            any(
                item["pest_id"] == "pteronemobius_heydenii_concolor"
                or item["scientific_name"] == "Pteronemobius heydenii concolor"
                for item in main.PEST_DATA
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "marsh_cricket"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Pteronemobius heydenii")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertIn("Trigonidiidae", row["verification_reason"])
        self.assertIn("Nemobiinae", row["verification_reason"])
        self.assertIn("P. h. heydenii", row["verification_reason"])
        self.assertIn("P. h. concolor", row["verification_reason"])
        self.assertEqual(
            row["indian_occurrence_status"],
            "INDIA_OCCURRENCE_CONFIRMED",
        )
        self.assertIn("Mumbai", row["indian_occurrence_evidence"])
        self.assertIn("concolor", row["indian_occurrence_evidence"])
        self.assertIn(
            "not for the European nominate subspecies",
            row["indian_occurrence_evidence"],
        )
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        habitat = row["ecological_habitat"].casefold()
        self.assertIn("humid vegetation", habitat)
        self.assertIn("wet grassland", habitat)
        self.assertEqual(
            row["crop_damage"],
            "No significant species-specific commercial crop damage is established. "
            "Occurrence in damp agricultural habitats does not establish crop injury.",
        )
        self.assertEqual(
            row["chemical_management"],
            "No chemical recommendation established.",
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(MARSH_CRICKET_ADVISORY_DATA), 1)
        advisory = MARSH_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "marsh_cricket")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIsNone(advisory["economic_threshold"])
        self.assertIn(
            "Indian-associated subspecies",
            advisory["geographic_qualification"],
        )
        self.assertIn(
            "Indian crop damage is not established",
            advisory["geographic_qualification"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "marsh_cricket"
                and item["status"] == "VERIFIED"
                for item in SOLUTION_RECORDS
            )
        )

    def test_wood_cricket_keeps_woodland_ecology_and_regional_life_cycle_qualified(self):
        import csv

        from solution_data import SOLUTION_RECORDS, WOOD_CRICKET_ADVISORY_DATA

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-FC-017"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(database_references[0]["pest_id"], "wood_cricket")

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "wood_cricket"
        ]
        self.assertEqual(len(entries), 1)
        wood_cricket = entries[0]
        self.assertEqual(wood_cricket["name"], "Wood Cricket")
        self.assertEqual(
            wood_cricket["scientific_name"],
            "Nemobius sylvestris",
        )
        self.assertEqual(wood_cricket["risk"], "LOW")
        self.assertNotEqual(wood_cricket["risk"], "VERY_LOW")
        self.assertEqual(wood_cricket["insect_group"], "Crickets")
        self.assertEqual(wood_cricket["crop_ids"], [])
        self.assertIn("leaf litter", wood_cricket["description"])
        self.assertIn("fungi", wood_cricket["description"])
        self.assertIn(
            "not crop hosts",
            wood_cricket["description"],
        )
        life_cycle_note = wood_cricket["taxonomic_metadata"]["life_cycle_note"]
        self.assertIn("Britain", life_cycle_note)
        self.assertIn("not be treated as universal", life_cycle_note)
        self.assertNotIn(
            "Pteronemobius",
            wood_cricket.get("aliases", []),
        )

        wood = SimpleNamespace(
            pest_id="wood_cricket",
            name="Wood Cricket",
            scientific_name="Nemobius sylvestris",
            risk="LOW",
        )
        marsh = SimpleNamespace(
            pest_id="marsh_cricket",
            name="Marsh Cricket",
            scientific_name="Pteronemobius heydenii",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [wood, marsh]
        self.assertIs(
            main._find_pest_record_normalized(database, "Nemobius sylvestris"),
            wood,
        )
        self.assertIs(
            main._find_pest_record_normalized(database, "Pteronemobius heydenii"),
            marsh,
        )
        self.assertIsNot(
            main._find_pest_record_normalized(database, "Pteronemobius heydenii"),
            wood,
        )
        self.assertIsNone(
            main._find_pest_record_normalized(
                database,
                "Pteronemobius heydenii concolor",
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "wood_cricket"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Nemobius sylvestris")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["taxonomy_status"], "TAXON_MATCH_CONFIRMED")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertEqual(row["ecological_host_plants"], "")
        self.assertIn("leaf litter", row["damage_evidence"])
        self.assertIn("fungi", row["damage_evidence"])
        self.assertIn("not crop hosts", row["damage_evidence"])
        self.assertIn("Britain", row["verification_reason"])
        self.assertIn(
            "do not treat that duration as universal",
            row["verification_reason"],
        )
        self.assertEqual(row["damage_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["chemical_management_status"], "NOT_ESTABLISHED")

        self.assertEqual(len(WOOD_CRICKET_ADVISORY_DATA), 1)
        advisory = WOOD_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "wood_cricket")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("No agricultural pest treatment is required.", advisory["management"])
        self.assertIn(
            "Distinguish this species from other small ground crickets, including Pteronemobius species.",
            advisory["management"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "wood_cricket"
                for item in SOLUTION_RECORDS
            )
        )

    def test_verge_cricket_keeps_identity_low_risk_and_regional_evidence_separate(self):
        import csv

        from solution_data import SOLUTION_RECORDS, VERGE_CRICKET_ADVISORY_DATA

        database_references = [
            item
            for item in main.PEST_DATA
            if item.get("database_reference") == "PG-FC-016"
        ]
        self.assertEqual(len(database_references), 1)
        self.assertEqual(database_references[0]["pest_id"], "verge_cricket")

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "verge_cricket"
        ]
        self.assertEqual(len(entries), 1)
        verge_cricket = entries[0]
        self.assertEqual(
            verge_cricket["scientific_name"],
            "Eumodicogryllus bordigalensis",
        )
        self.assertEqual(verge_cricket["risk"], "LOW")
        self.assertEqual(verge_cricket["insect_group"], "Crickets")
        self.assertEqual(verge_cricket["crop_ids"], [])
        self.assertEqual(
            verge_cricket["aliases"],
            [
                "Modicogryllus bordigalensis",
                "Southern Cricket",
                "Bordeaux Cricket",
            ],
        )
        self.assertEqual(
            verge_cricket["taxonomic_metadata"]["authority"],
            "(Latreille, 1804)",
        )
        self.assertEqual(
            verge_cricket["taxonomic_metadata"]["family"],
            "Gryllidae",
        )
        self.assertEqual(
            verge_cricket["taxonomic_metadata"]["order"],
            "Orthoptera",
        )
        self.assertEqual(
            verge_cricket["taxonomic_metadata"]["former_combination"],
            "Modicogryllus bordigalensis",
        )

        resolved_records = {
            "verge_cricket": SimpleNamespace(
                pest_id="verge_cricket",
                name="Verge Cricket",
                scientific_name="Eumodicogryllus bordigalensis",
            ),
            "house_cricket": SimpleNamespace(
                pest_id="house_cricket",
                name="House Cricket",
                scientific_name="Acheta domesticus",
            ),
            "field_cricket": SimpleNamespace(
                pest_id="field_cricket",
                name="Field Cricket",
                scientific_name=None,
            ),
            "desert_field_cricket": SimpleNamespace(
                pest_id="desert_field_cricket",
                name="Desert Field Cricket",
                scientific_name="Melanogryllus desertus",
            ),
        }
        database = Mock()
        database.query.return_value.all.return_value = list(
            resolved_records.values()
        )
        for label in (
            "Eumodicogryllus bordigalensis",
            "Modicogryllus bordigalensis",
            "Southern Cricket",
            "Bordeaux Cricket",
        ):
            with self.subTest(label=label):
                self.assertIs(
                    main._find_pest_record_normalized(database, label),
                    resolved_records["verge_cricket"],
                )
        for label, pest_id in (
            ("Acheta domesticus", "house_cricket"),
            ("Field Cricket", "field_cricket"),
            ("Melanogryllus desertus", "desert_field_cricket"),
        ):
            with self.subTest(label=label):
                self.assertIs(
                    main._find_pest_record_normalized(database, label),
                    resolved_records[pest_id],
                )
        self.assertIsNone(
            main._find_pest_record_normalized(
                database,
                "Gryllus spp. (species undetermined)",
            )
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "verge_cricket"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            row["scientific_name"],
            "Eumodicogryllus bordigalensis",
        )
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["indian_occurrence_status"], "REPORTED_NEEDS_LOCAL_CONFIRMATION")
        self.assertIn("Modicogryllus bordigalensis", row["accepted_synonyms"])
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertEqual(row["damage_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["affected_plant_parts_status"], "NOT_ESTABLISHED")
        self.assertIn("Iraqi", row["damage_evidence"])
        self.assertIn("not establish", row["damage_evidence"])
        self.assertIn("India", row["damage_evidence"])
        self.assertEqual(row["chemical_management_status"], "NOT_ESTABLISHED")
        habitat = row["ecological_habitat"].casefold()
        for habitat_term in (
            "agricultural fields",
            "dry grassland",
            "field margins",
            "gardens",
        ):
            self.assertIn(habitat_term, habitat)

        self.assertEqual(len(VERGE_CRICKET_ADVISORY_DATA), 1)
        advisory = VERGE_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "verge_cricket")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIn("Iraqi survey", advisory["damage_notes"])
        self.assertIn(
            "needs local confirmation",
            advisory["geographic_qualification"],
        )
        self.assertFalse(
            any(
                item["pest_id"] == "verge_cricket"
                for item in SOLUTION_RECORDS
            )
        )

    def test_greater_dark_bush_cricket_label_resolves_to_large_dark_entry(self):
        large_dark_bush = SimpleNamespace(
            pest_id="large_dark_bush_cricket",
            name="Large Dark Bush-cricket",
            scientific_name="Pholidoptera femorata",
            risk="LOW",
        )
        dark_bush = SimpleNamespace(
            pest_id="dark_bush_cricket",
            name="Dark Bush-cricket",
            scientific_name="Pholidoptera griseoaptera",
            risk="LOW",
        )
        database = Mock()
        database.query.return_value.all.return_value = [
            large_dark_bush,
            dark_bush,
        ]
        database.query.return_value.filter.return_value.first.return_value = (
            large_dark_bush
        )

        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Greater Dark Bush-cricket",
            ),
            large_dark_bush,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "greater_dark_bush_cricket",
            ),
            large_dark_bush,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Dark Bush-cricket",
            ),
            dark_bush,
        )
        self.assertIs(
            main._find_verified_pest_record(
                database,
                "Greater Dark Bush-cricket",
                pest_id="large_dark_bush_cricket",
            ),
            large_dark_bush,
        )

    def test_house_cricket_profile_has_no_confirmed_crop_or_treatment(self):
        import csv

        from solution_data import HOUSE_CRICKET_ADVISORY_DATA, SOLUTION_RECORDS

        house_cricket_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "house_cricket"
        ]
        self.assertEqual(len(house_cricket_entries), 1)
        house_cricket = house_cricket_entries[0]
        self.assertEqual(house_cricket["scientific_name"], "Acheta domesticus")
        self.assertEqual(house_cricket["risk"], "MEDIUM")
        self.assertEqual(house_cricket["crop_ids"], [])
        self.assertEqual(house_cricket["insect_group"], "Cricket")
        self.assertIn(
            "serious widespread crop losses are not established",
            house_cricket["description"],
        )
        tropical_entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "tropical_house_cricket"
        ]
        self.assertEqual(len(tropical_entries), 1)
        self.assertEqual(
            tropical_entries[0]["scientific_name"],
            "Gryllodes sigillatus",
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Gryllodes sigillatus"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertEqual(len(HOUSE_CRICKET_ADVISORY_DATA), 1)
        advisory = HOUSE_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "house_cricket")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertEqual(advisory["risk_level"], "MEDIUM")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIsNone(advisory["economic_threshold"])
        self.assertNotIn(advisory, SOLUTION_RECORDS)
        self.assertEqual(
            advisory["source_refs"],
            [
                "https://epubs.icar.org.in/index.php/AAZ/article/view/65126",
                "https://ask.ifas.ufl.edu/publication/IN220",
                "https://ddugu.ac.in/ePathshala_Attachments/E_PS155267%40d7832c66i.pdf",
            ],
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = list(csv.DictReader(matrix_file))
        house_rows = [row for row in rows if row["pest_id"] == "house_cricket"]
        tropical_rows = [
            row for row in rows if row["pest_id"] == "tropical_house_cricket"
        ]
        self.assertEqual(len(house_rows), 1)
        self.assertEqual(len(tropical_rows), 1)
        house_row = house_rows[0]
        self.assertEqual(house_row["scientific_name"], "Acheta domesticus")
        self.assertEqual(house_row["risk_level"], "MEDIUM")
        self.assertEqual(house_row["crop_id"], "")
        self.assertEqual(house_row["crop_name"], "")
        self.assertEqual(house_row["verified_host_crops"], "")
        self.assertEqual(
            house_row["indian_occurrence_status"],
            "NEEDS_REVIEW",
        )
        self.assertIn(
            "report",
            house_row["indian_occurrence_evidence"].lower(),
        )
        self.assertIn("report", house_row["damage_evidence"].lower())
        self.assertIn("not established", house_row["crop_damage"].lower())
        self.assertEqual(
            house_row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(
            tropical_rows[0]["scientific_name"],
            "Gryllodes sigillatus",
        )
        self.assertNotEqual(
            house_row["scientific_name"],
            tropical_rows[0]["scientific_name"],
        )

    def test_house_cricket_common_label_stays_uncertain_and_species_stays_separate(self):
        house_cricket = SimpleNamespace(
            pest_id="house_cricket",
            name="House Cricket",
            scientific_name="Acheta domesticus",
            risk="MEDIUM",
        )
        tropical_house_cricket = SimpleNamespace(
            pest_id="tropical_house_cricket",
            name="Tropical House Cricket",
            scientific_name="Gryllodes sigillatus",
            risk="MEDIUM",
        )
        database = Mock()
        database.query.return_value.all.return_value = [
            house_cricket,
            tropical_house_cricket,
        ]
        database.query.return_value.filter.return_value.first.side_effect = [
            house_cricket,
            tropical_house_cricket,
        ]

        self.assertIsNone(
            main._find_pest_record_normalized(database, "House Cricket")
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Acheta domesticus",
            ),
            house_cricket,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Gryllodes sigillatus",
            ),
            tropical_house_cricket,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Indian House Cricket",
            ),
            tropical_house_cricket,
        )
        self.assertIsNone(
            main._find_verified_pest_record(
                database,
                "Gryllodes sigillatus",
                pest_id="house_cricket",
            )
        )
        self.assertIs(
            main._find_verified_pest_record(
                database,
                "Gryllodes sigillatus",
                pest_id="tropical_house_cricket",
            ),
            tropical_house_cricket,
        )

        request = FakeRequest("application/json", payload={"audio": []})
        model_result = {
            "pest": "House Cricket",
            "confidence": 0.95,
            "insect_group": "Crickets",
        }
        with (
            patch.object(
                main,
                "_is_active_species_label",
                side_effect=lambda label: label == "House Cricket",
            ),
            patch.object(
                main,
                "_active_group_for_label",
                return_value="Crickets",
            ),
            patch.object(main, "predict_pest", return_value=model_result),
            patch.object(main.manager, "broadcast", new_callable=AsyncMock),
        ):
            response = asyncio.run(
                main.ai_predict(request, db=self.database)
            )

        self.assertEqual(response["status"], "UNKNOWN")
        self.assertEqual(
            response["common_name"],
            "Cricket (species uncertain)",
        )
        self.assertIsNone(response["scientific_name"])
        self.assertIsNone(response["pest_id"])

    def test_jumping_bush_cricket_advisory_has_no_crop_or_chemical_solution(self):
        import csv

        from solution_data import (
            JUMPING_BUSH_CRICKET_ADVISORY_DATA,
            SOLUTION_RECORDS,
        )

        entries = [
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "jumping_bush_cricket"
        ]
        self.assertEqual(len(entries), 1)
        jumping_cricket = entries[0]
        self.assertEqual(
            jumping_cricket["scientific_name"],
            "Orocharis saltator",
        )
        self.assertEqual(jumping_cricket["risk"], "LOW")
        self.assertEqual(jumping_cricket["insect_group"], "Cricket")
        self.assertEqual(jumping_cricket["crop_ids"], [])
        self.assertEqual(
            jumping_cricket["aliases"],
            ["Hapithus saltator"],
        )
        self.assertEqual(
            sum(
                item["scientific_name"] == "Orocharis saltator"
                for item in main.PEST_DATA
            ),
            1,
        )
        self.assertFalse(
            any(
                item["pest_id"] == "hapithus_saltator"
                for item in main.PEST_DATA
            )
        )
        dark_bush_cricket = next(
            item
            for item in main.PEST_DATA
            if item["pest_id"] == "dark_bush_cricket"
        )
        self.assertNotEqual(
            dark_bush_cricket["scientific_name"],
            jumping_cricket["scientific_name"],
        )

        matrix_path = (
            Path(__file__).resolve().parents[1]
            / "pest_crop_evidence_matrix.csv"
        )
        with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
            rows = [
                row
                for row in csv.DictReader(matrix_file)
                if row["pest_id"] == "jumping_bush_cricket"
            ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scientific_name"], "Orocharis saltator")
        self.assertEqual(row["risk_level"], "LOW")
        self.assertEqual(row["indian_occurrence_status"], "NOT_ESTABLISHED")
        self.assertEqual(row["crop_id"], "")
        self.assertEqual(row["crop_name"], "")
        self.assertEqual(row["verified_host_crops"], "")
        self.assertIn("Gryllidae", row["verification_reason"])
        self.assertIn("Podoscirtidae", row["verification_reason"])
        self.assertEqual(
            row["ecological_habitat"],
            "Trees; shrubs; herbaceous vegetation",
        )
        self.assertIn(
            "No species-specific commercial crop damage",
            row["crop_damage"],
        )
        self.assertEqual(
            row["chemical_management_status"],
            "NOT_ESTABLISHED",
        )

        self.assertEqual(len(JUMPING_BUSH_CRICKET_ADVISORY_DATA), 1)
        advisory = JUMPING_BUSH_CRICKET_ADVISORY_DATA[0]
        self.assertEqual(advisory["pest_id"], "jumping_bush_cricket")
        self.assertEqual(advisory["risk_level"], "LOW")
        self.assertEqual(advisory["status"], "ADVISORY")
        self.assertIsNone(advisory["crop_id"])
        self.assertIsNone(advisory["chemical_control_options"])
        self.assertIsNone(advisory["economic_threshold"])
        self.assertNotIn(advisory, SOLUTION_RECORDS)
        self.assertEqual(
            advisory["source_refs"],
            [
                "https://www.fws.gov/species/jumping-bush-cricket-orocharis-saltator",
                "https://www.orthsoc.org/sina/686a.htm",
                "https://www.itis.gov/servlet/SingleRpt/SingleRpt?search_topic=TSN&search_value=102354",
            ],
        )

    def test_historical_name_resolves_to_jumping_cricket_not_bush_crickets(self):
        jumping_cricket = SimpleNamespace(
            pest_id="jumping_bush_cricket",
            name="Jumping Bush Cricket",
            scientific_name="Orocharis saltator",
            risk="LOW",
            insect_group="Cricket",
        )
        dark_bush_cricket = SimpleNamespace(
            pest_id="dark_bush_cricket",
            name="Dark Bush-cricket",
            scientific_name="Pholidoptera griseoaptera",
            risk="LOW",
            insect_group="Bush-cricket / Katydid",
        )
        large_dark_bush_cricket = SimpleNamespace(
            pest_id="large_dark_bush_cricket",
            name="Large Dark Bush-cricket",
            scientific_name="Pholidoptera femorata",
            risk="LOW",
            insect_group="Bush-cricket",
        )
        database = Mock()
        database.query.return_value.all.return_value = [
            jumping_cricket,
            dark_bush_cricket,
            large_dark_bush_cricket,
        ]
        database.query.return_value.filter.return_value.first.return_value = (
            jumping_cricket
        )

        self.assertIs(
            main._find_pest_record_normalized(database, "Hapithus saltator"),
            jumping_cricket,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Jumping Bush Cricket",
            ),
            jumping_cricket,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Dark Bush-cricket",
            ),
            dark_bush_cricket,
        )
        self.assertIs(
            main._find_pest_record_normalized(
                database,
                "Large Dark Bush-cricket",
            ),
            large_dark_bush_cricket,
        )
        self.assertIs(
            main._find_verified_pest_record(
                database,
                "Hapithus saltator",
                pest_id="jumping_bush_cricket",
            ),
            jumping_cricket,
        )
        self.assertEqual(jumping_cricket.insect_group, "Cricket")

    def test_pine_weevil_potential_hosts_api_keeps_candidate_separate(self):
        from database import Base

        self.assertIn(
            "/api/pests/{pest_id}/solutions",
            {route.path for route in main.app.routes},
        )
        self.assertNotIn(
            "/api/pests/{pest_id}/potential-hosts",
            {route.path for route in main.app.routes},
        )

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        try:
            main.seed_pest_data(session)
            response = main.get_pest_solutions("pine_weevil", db=session)
            validated = main.PestSolutionsResponse.model_validate(response)

            self.assertEqual(validated.pest.pest_id, "pine_weevil")
            self.assertEqual(validated.solutions, [])
            self.assertEqual(validated.total_solutions, 0)
            self.assertIsNotNone(validated.potential_host_profile)
            self.assertEqual(
                validated.potential_host_profile.status,
                "NEEDS_REVIEW",
            )
            self.assertEqual(
                validated.potential_host_profile.scientific_name,
                "Hylobius abietis",
            )
            self.assertEqual(
                [
                    (
                        host.crop_id,
                        host.crop_name,
                        host.review_status,
                    )
                    for host in validated.potential_host_profile.potential_host_crops
                ],
                [
                    ("pine", "Pine", "NEEDS_REVIEW"),
                    ("spruce", "Spruce", "NEEDS_REVIEW"),
                    ("fir", "Fir", "NEEDS_REVIEW"),
                    ("douglas_fir", "Douglas Fir", "NEEDS_REVIEW"),
                    ("hemlock", "Hemlock", "NEEDS_REVIEW"),
                ],
            )
            self.assertIn(
                "cambial region",
                validated.potential_host_profile.crop_damage,
            )
        finally:
            session.close()
            engine.dispose()

    def test_pine_weevil_candidate_is_not_in_verified_solutions_api(self):
        from database import Base

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        try:
            main.seed_pest_data(session)
            response = main.get_pest_solutions("pine_weevil", db=session)
            self.assertEqual(response["solutions"], [])
            self.assertEqual(response["total_crops"], 0)
            self.assertEqual(
                session.query(main.PestCropSolution)
                .filter_by(pest_id="pine_weevil")
                .count(),
                0,
            )
        finally:
            session.close()
            engine.dispose()

    def test_unverified_solution_records_are_not_returned_by_api(self):
        from database import Base

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        try:
            main.seed_pest_data(session)
            crops = main.get_crops(pest_id=None, db=session)
            rice_crop = next(
                item for item in crops if item["crop_id"] == "rice"
            )
            crop = (
                session.query(main.Crop)
                .filter_by(crop_id=rice_crop["crop_id"])
                .first()
            )
            response = main.get_solutions(crop_id=crop.crop_id, pest_id=None, db=session)
            main.PestCropSolutionListResponse.model_validate(response)
            self.assertEqual(response["solutions"], [])
        finally:
            session.close()
            engine.dispose()

    def test_solution_response_omits_scientific_name_and_allows_missing_fields(self):
        response = main.PestCropSolutionResponse.model_validate(
            {
                "solution_id": "response-shape-check",
                "pest_id": "rhinoceros_beetle",
                "pest_name": "Rhinoceros Beetle",
                "insect_group": "Beetles",
                "risk": "HIGH",
                "crop_id": "coconut",
                "crop_name": "Coconut",
                "source_references": [],
            }
        )

        self.assertFalse(hasattr(response, "scientific_name"))
        self.assertIsNone(response.crop_damage)
        self.assertIsNone(response.cultural_control_methods)
        self.assertIsNone(response.chemical_control_options)

    def test_solution_api_returns_supported_record_but_hides_incomplete_record(self):
        from database import Base

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        try:
            main.seed_pest_data(session)
            crop = session.query(main.Crop).filter_by(crop_id="coconut").one()
            low_risk_pest = next(
                item
                for item in main.PEST_DATA
                if item["risk"] == "LOW"
                and main._is_active_species_label(item["name"])
            )
            unsupported_record = main.PestCropSolution(
                solution_id="unsupported_low",
                pest_id=low_risk_pest["pest_id"],
                crop_id=crop.crop_id,
                risk_level="LOW",
                status="VERIFIED",
            )

            session.add(unsupported_record)
            session.commit()

            response = main.get_solutions(
                crop_id=crop.crop_id,
                pest_id=None,
                db=session,
            )
            main.PestCropSolutionListResponse.model_validate(response)
            self.assertEqual(
                {item["solution_id"] for item in response["solutions"]},
                {"rhinoceros_beetle_coconut_high_2026_11_11"},
            )
            self.assertNotIn("scientific_name", response["solutions"][0])
            self.assertNotIn(
                "unsupported_low",
                {item["solution_id"] for item in response["solutions"]},
            )
        finally:
            session.close()
            engine.dispose()

    def test_solution_api_filters_crop_and_pest_and_supports_multiple_crops(self):
        from database import Base

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        try:
            main.seed_pest_data(session)
            rice = session.query(main.Crop).filter_by(crop_id="rice").one()
            synthetic_record = main.PestCropSolution(
                solution_id="test_only_rhinoceros_beetle_rice",
                pest_id="rhinoceros_beetle",
                crop_id=rice.crop_id,
                risk_level="HIGH",
                status="VERIFIED",
                scientific_name="Test-only fixture identity",
                crop_damage="Test-only fixture damage evidence.",
                mechanical_control_methods="Test-only fixture mechanical control.",
                reviewed_on="2026-11-11",
                source_references=[
                    {
                        "title": "Synthetic API test fixture",
                        "organization": "Automated test",
                        "url": "https://example.test/fixture",
                        "reviewed_on": "2026-11-11",
                        "supports": [
                            "scientific_name",
                            "crop_id",
                            "crop_damage",
                            "mechanical_control_methods",
                        ],
                    }
                ],
            )
            session.add(synthetic_record)
            session.commit()

            rice_response = main.get_solutions(
                crop_id="rice",
                pest_id="rhinoceros_beetle",
                db=session,
            )
            main.PestCropSolutionListResponse.model_validate(rice_response)
            self.assertEqual(
                [item["solution_id"] for item in rice_response["solutions"]],
                ["test_only_rhinoceros_beetle_rice"],
            )

            unmatched_pest_response = main.get_solutions(
                crop_id="rice",
                pest_id="green_grasshopper",
                db=session,
            )
            self.assertEqual(unmatched_pest_response["solutions"], [])

            coconut_response = main.get_solutions(
                crop_id="coconut",
                pest_id="rhinoceros_beetle",
                db=session,
            )
            self.assertEqual(
                [item["solution_id"] for item in coconut_response["solutions"]],
                ["rhinoceros_beetle_coconut_high_2026_11_11"],
            )
        finally:
            session.close()
            engine.dispose()

    def test_solution_seed_creates_low_risk_coverage_records(self):
        from database import Base

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()

        try:
            with patch.object(main, "SOLUTION_RECORDS", []):
                main.seed_pest_data(session)
            self.assertEqual(
                session.query(main.PestSolutionCoverage).count(),
                132,
            )
            pest = next(item for item in main.PEST_DATA if item["risk"] == "LOW")
            stored = (
                session.query(main.PestSolutionCoverage)
                .filter_by(pest_id=pest["pest_id"])
                .one()
            )
            self.assertEqual(stored.research_data["risk_level"], "LOW")
            self.assertEqual(stored.research_data["common_name"], pest["name"])
            self.assertEqual(stored.review_status, "NEEDS_REVIEW")

            rhinoceros = (
                session.query(main.PestSolutionCoverage)
                .filter_by(pest_id="rhinoceros_beetle")
                .one()
            )
            self.assertEqual(
                rhinoceros.research_data["verified_host_crops"][0]["crop_id"],
                "coconut",
            )
            self.assertEqual(
                rhinoceros.research_data["field_status"]["chemical_management"],
                "NOT_ESTABLISHED",
            )
        finally:
            session.close()
            engine.dispose()

    def test_untracked_history_guidance_is_not_served(self):
        catalog_item = real_active_catalog_item()
        pest_record = SimpleNamespace(**catalog_item)
        database = Mock()
        item = SimpleNamespace(
            id=1,
            detection_id=1,
            device_id="FIELD-UNIT-01",
            pest_id=pest_record.pest_id,
            pest=pest_record.name,
            common_name=pest_record.name,
            image_url=None,
            risk=catalog_item["risk"],
            confidence=None,
            temperature=None,
            humidity=None,
            solution_title=None,
            solution_source=None,
            solution_description="Legacy guidance",
            recommended_action="Legacy guidance",
            prevention="Legacy guidance",
            detected_at=None,
            created_at=None,
        )

        with patch.object(
            main,
            "_find_verified_pest_record",
            return_value=pest_record,
        ):
            response = main._high_risk_solution_history_response(item, database)

        self.assertEqual(response["risk"], catalog_item["risk"])
        self.assertIsNone(response["solution_title"])
        self.assertIsNone(response["solution_source"])
        self.assertIsNone(response["solution_description"])
        self.assertIsNone(response["recommended_action"])
        self.assertIsNone(response["prevention"])

    def test_high_risk_history_preserves_identity_and_risk(self):
        catalog_item = real_high_risk_catalog_item()
        pest_record = SimpleNamespace(**catalog_item)
        item = SimpleNamespace(
            id=7,
            detection_id=11,
            device_id="FIELD-UNIT-01",
            pest_id=catalog_item["pest_id"],
            pest=catalog_item["name"],
            common_name=catalog_item["name"],
            image_url=None,
            risk=catalog_item["risk"],
            confidence=None,
            temperature=None,
            humidity=None,
            solution_title="Legacy title",
            solution_source="CATALOG",
            solution_description="Legacy guidance",
            recommended_action="Legacy guidance",
            prevention="Legacy guidance",
            detected_at=None,
            created_at=None,
        )

        database = Mock()
        with patch.object(
            main,
            "_find_verified_pest_record",
            return_value=pest_record,
        ):
            response = main._high_risk_solution_history_response(item, database)

        self.assertTrue(response["pest_verified"])
        self.assertEqual(response["risk"], catalog_item["risk"])
        self.assertEqual(response["pest"], catalog_item["name"])
        self.assertEqual(response["common_name"], catalog_item["name"])
        self.assertEqual(
            response["solution_title"],
            None,
        )
        self.assertIsNone(response["solution_source"])
        self.assertIsNone(response["solution_description"])
        self.assertIsNone(response["recommended_action"])
        self.assertIsNone(response["prevention"])

    def test_harmful_device_detection_status_is_preserved(self):
        database = Mock()
        database.query.return_value.all.return_value = catalog_records()
        database.refresh.side_effect = lambda detection: setattr(
            detection, "id", 1
        )
        payload = main.DetectionCreate(
            device_id="FIELD-UNIT-01",
            status="HARMFUL_PEST",
            pest=ACTIVE_LABELS[0],
            confidence=0.99,
            risk="HIGH",
            temperature=26.2,
            humidity=65.0,
        )

        with patch.object(
            main.manager, "broadcast", new_callable=AsyncMock
        ) as broadcast:
            detection = asyncio.run(main.create_detection(payload, database))

        self.assertEqual(detection["status"], "HARMFUL_PEST")
        self.assertEqual(detection["identification_status"], "MODEL_PREDICTED")
        self.assertEqual(detection["pest"], ACTIVE_LABELS[0])
        self.assertEqual(detection["risk"], "LOW")
        event = broadcast.await_args.args[0]
        self.assertEqual(event["status"], "HARMFUL_PEST")
        self.assertEqual(event["pest"], ACTIVE_LABELS[0])
        self.assertEqual(event["risk"], "LOW")
        self.assertEqual(event["temperature"], 26.2)
        self.assertEqual(event["humidity"], 65.0)
        api_response = main.DetectionResponse.model_validate(detection)
        self.assertEqual(api_response.status, "HARMFUL_PEST")
        self.assertEqual(api_response.identification_status, "MODEL_PREDICTED")
        self.assertTrue(api_response.pest_verified)

    def test_device_harmful_status_without_catalog_match_is_unconfirmed(self):
        database = Mock()
        database.query.return_value.all.return_value = []
        database.query.return_value.filter.return_value.first.return_value = None
        payload = main.DetectionCreate(
            device_id="FIELD-UNIT-01",
            status="HARMFUL_PEST",
            pest=ACTIVE_LABELS[0],
            confidence=0.99,
            risk="HIGH",
        )

        with patch.object(
            main.manager, "broadcast", new_callable=AsyncMock
        ) as broadcast:
            detection = asyncio.run(main.create_detection(payload, database))

        self.assertEqual(detection["status"], "UNKNOWN")
        self.assertEqual(detection["pest"], ACTIVE_LABELS[0])
        self.assertFalse(detection["pest_verified"])
        self.assertEqual(detection["risk"], "LOW")
        broadcast.assert_awaited_once_with(detection)

    def test_device_low_confidence_harmful_status_is_unconfirmed(self):
        database = Mock()
        database.query.return_value.all.return_value = catalog_records("HIGH")
        database.query.return_value.filter.return_value.first.return_value = None
        payload = main.DetectionCreate(
            device_id="FIELD-UNIT-01",
            status="HARMFUL_PEST",
            pest=ACTIVE_LABELS[0],
            confidence=0.69,
            risk="HIGH",
        )

        with (
            patch.object(main.manager, "broadcast", new_callable=AsyncMock),
            patch.object(main, "Client") as twilio_client,
        ):
            detection = asyncio.run(main.create_detection(payload, database))

        self.assertEqual(detection["status"], "UNKNOWN")
        self.assertEqual(detection["identification_status"], "UNCONFIRMED")
        self.assertEqual(detection["risk"], "HIGH")
        self.assertFalse(detection["pest_verified"])
        twilio_client.assert_not_called()

    def test_device_high_risk_uses_catalog_risk_not_submitted_risk(self):
        database = Mock()
        database.query.return_value.all.return_value = catalog_records("HIGH")
        database.query.return_value.filter.return_value.first.return_value = None
        payload = main.DetectionCreate(
            device_id="FIELD-UNIT-01",
            status="HARMFUL_PEST",
            pest=ACTIVE_LABELS[0],
            confidence=0.99,
            risk="LOW",
        )

        with (
            patch.object(
                main.manager, "broadcast", new_callable=AsyncMock
            ) as broadcast,
            patch.object(main, "send_high_risk_sms"),
        ):
            detection = asyncio.run(main.create_detection(payload, database))

        self.assertEqual(detection["status"], "HARMFUL_PEST")
        self.assertEqual(detection["risk"], "HIGH")
        self.assertEqual(detection["identification_status"], "MODEL_PREDICTED")
        history_record = next(
            record
            for record in (
                call.args[0] for call in database.add.call_args_list
            )
            if isinstance(record, main.HighRiskSolutionHistory)
        )
        self.assertEqual(history_record.pest, ACTIVE_LABELS[0])
        self.assertEqual(history_record.risk, "HIGH")
        broadcast.assert_awaited_once_with(detection)

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

        self.assertEqual(detection["status"], "UNKNOWN")
        self.assertIsNone(detection["pest"])
        self.assertEqual(detection["risk"], "LOW")
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

        self.assertEqual(detection["status"], "NON_PEST")
        self.assertIsNone(detection["pest"])
        self.assertEqual(detection["risk"], "LOW")
        self.assertEqual(
            detection["insect_group"],
            main.UNKNOWN_INSECT_GROUP,
        )
        response = main.DetectionResponse.model_validate(
            {**detection, "id": detection["id"] or 1}
        )
        self.assertEqual(
            response.insect_group,
            main.UNKNOWN_INSECT_GROUP,
        )
        self.assertIsNone(response.group_score)


class DetectionHistoryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        main.Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add_all(catalog_records())
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_legacy_detection_without_group_fields_remains_serializable(self):
        pest = ACTIVE_LABELS[0]
        detection = SimpleNamespace(
            id=1,
            device_id="LEGACY-UNIT",
            status="UNKNOWN",
            pest=pest,
            scientific_name=pest,
            common_name=ACTIVE_COMMON_NAMES[0],
            confidence=0.277,
            top_predictions=json.dumps([{"pest": pest, "score": 0.277}]),
            risk="LOW",
            risk_rationale=None,
            affected_crops="[]",
            metadata_source_name=None,
            metadata_source_url=None,
            temperature=None,
            humidity=None,
            audio_file=None,
            message="Unverified model prediction",
            detected_at=datetime(2026, 1, 1),
        )

        response = main._serialize_detection(detection, None)

        self.assertEqual(
            response["insect_group"],
            main.MODEL_SPECIES_GROUPS[
                main._normalize_pest_label(pest)
            ],
        )
        self.assertIsNone(response["group_score"])
        self.assertEqual(response["top_predictions"][0]["score"], 0.277)
        self.assertEqual(
            response["top_predictions"][0]["common_name"],
            ACTIVE_COMMON_NAMES[0],
        )

    def test_one_device_event_is_committed_and_returned_once_by_history(self):
        payload = main.DetectionCreate(
            device_id="TEST-FIELD-UNIT",
            status="UNKNOWN",
            pest=ACTIVE_LABELS[0],
            confidence=0.8,
            risk="LOW",
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
        self.assertEqual(history["detections"][0]["id"], saved["id"])
        self.assertEqual(history["detections"][0]["pest"], ACTIVE_LABELS[0])
        self.assertEqual(history["detections"][0]["common_name"], ACTIVE_COMMON_NAMES[0])
        self.assertEqual(history["detections"][0]["risk"], main._resolve_species_metadata(ACTIVE_LABELS[0])["risk"])
        self.assertEqual(broadcast.await_count, 1)

    def test_ai_metadata_matches_saved_row_latest_history_and_websocket(self):
        pest_record = (
            self.db.query(main.Pest)
            .filter_by(name=ACTIVE_LABELS[0])
            .first()
        )
        pest_record.risk = "HIGH"
        self.db.commit()
        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )

        with (
            patch.object(
                main,
                "predict_pest",
                return_value={
                    "pest": ACTIVE_LABELS[0],
                    "confidence": 0.81,
                    "insect_group": main.MODEL_SPECIES_GROUPS[
                        main._normalize_pest_label(ACTIVE_LABELS[0])
                    ],
                    "group_score": 0.44,
                    "top_predictions": [
                        {
                            "pest": ACTIVE_LABELS[0],
                            "score": 0.81,
                            "common_name": ACTIVE_COMMON_NAMES[0],
                        }
                    ],
                },
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
                record.insect_group if hasattr(record, "insect_group") else record["insect_group"],
                response["insect_group"],
            )
            self.assertEqual(
                record.group_score if hasattr(record, "group_score") else record["group_score"],
                response["group_score"],
            )
            if isinstance(record, dict):
                self.assertEqual(
                    record["identification_status"],
                    "MODEL_PREDICTED",
                )
                self.assertEqual(
                    record["identification_label"],
                    response["common_name"],
                )
                self.assertTrue(record["pest_verified"])
                self.assertEqual(record["pest_id"], response["pest_id"])
                self.assertEqual(record["status"], "HARMFUL_PEST")
        self.assertEqual(response["identification_status"], "MODEL_PREDICTED")
        self.assertEqual(response["risk"], "HIGH")
        self.assertEqual(
            json.loads(saved.affected_crops),
            response["affected_crops"],
        )
        broadcast.assert_awaited_once_with(response)

    def test_catalogue_risk_survives_detection_history_and_websocket_for_all_levels(self):
        pest_name = ACTIVE_LABELS[0]
        pest_record = (
            self.db.query(main.Pest)
            .filter_by(name=pest_name)
            .first()
        )

        for risk in ("HIGH", "MEDIUM", "LOW", "NO_RISK"):
            with self.subTest(risk=risk):
                pest_record.risk = risk
                self.db.commit()
                payload = main.DetectionCreate(
                    device_id="RISK-CATEGORY-UNIT",
                    status="HARMFUL_PEST",
                    pest=pest_name,
                    confidence=0.99,
                    risk="LOW" if risk != "HIGH" else "MEDIUM",
                )

                with (
                    patch.object(
                        main.manager,
                        "broadcast",
                        new_callable=AsyncMock,
                    ) as broadcast,
                    patch.object(main, "send_high_risk_sms"),
                ):
                    response = asyncio.run(
                        main.create_detection(payload, self.db)
                    )

                saved = self.db.query(main.Detection).filter_by(
                    id=response["id"]
                ).first()
                history = main.get_detection_history(
                    device_id="RISK-CATEGORY-UNIT",
                    status=None,
                    limit=500,
                    db=self.db,
                )["detections"]
                history_response = next(
                    item for item in history if item["id"] == response["id"]
                )
                websocket_event = broadcast.await_args.args[0]

                self.assertEqual(response["risk"], risk)
                self.assertEqual(saved.risk, risk)
                self.assertEqual(history_response["risk"], risk)
                self.assertEqual(websocket_event["risk"], risk)
                self.assertEqual(response["identification_status"], "MODEL_PREDICTED")
                if risk == "HIGH":
                    solution_history = (
                        self.db.query(main.HighRiskSolutionHistory)
                        .filter_by(detection_id=response["id"])
                        .first()
                    )
                    self.assertEqual(solution_history.risk, risk)
                    self.assertIsNone(solution_history.solution_title)
                    for field in (
                        "solution_description",
                        "recommended_action",
                        "prevention",
                    ):
                        self.assertIsNone(getattr(solution_history, field), field)

    def test_prediction_prefers_canonical_catalogue_id_over_stale_name_match(self):
        pest_name = "Field Cricket"
        source_record = next(
            item for item in main.PEST_DATA if item["name"] == pest_name
        )
        self.assertEqual(source_record["pest_id"], "field_cricket")
        self.assertEqual(source_record["risk"], "MEDIUM")
        stale_record = main.Pest(
            pest_id="field_crickt",
            name=pest_name,
            scientific_name="Gryllus campestris",
            risk="LOW",
        )
        canonical_record = main.Pest(
            pest_id=source_record["pest_id"],
            name=pest_name,
            scientific_name=source_record["scientific_name"],
            description=source_record["description"],
            risk=source_record["risk"],
            symptoms=source_record["symptoms"],
        )
        self.db.add_all([stale_record, canonical_record])
        self.db.commit()

        self.assertEqual(
            main._find_pest_record_normalized(self.db, pest_name).pest_id,
            source_record["pest_id"],
        )

        request = FakeRequest(
            "application/json",
            payload={"audio": [0.1, -0.1]},
        )
        for risk in ("HIGH", "MEDIUM", "LOW", "NO_RISK"):
            with self.subTest(risk=risk):
                canonical_record.risk = risk
                self.db.commit()
                with (
                    patch.object(
                        main,
                        "predict_pest",
                        return_value={
                            "pest": pest_name,
                            "confidence": 0.9,
                            "insect_group": "Crickets",
                        },
                    ),
                    patch.object(
                        main.manager,
                        "broadcast",
                        new_callable=AsyncMock,
                    ) as broadcast,
                ):
                    response = asyncio.run(
                        main.ai_predict(request, db=self.db)
                    )

                saved = self.db.query(main.Detection).filter_by(
                    id=response["id"]
                ).first()
                history = main.get_detection_history(
                    device_id=None,
                    status=None,
                    limit=500,
                    db=self.db,
                )["detections"]
                history_response = next(
                    item for item in history if item["id"] == response["id"]
                )

                self.assertEqual(response["risk"], risk)
                self.assertEqual(saved.risk, risk)
                self.assertEqual(history_response["risk"], risk)
                self.assertEqual(broadcast.await_args.args[0]["risk"], risk)
                self.assertTrue(response["pest_verified"])

    def test_high_risk_solution_history_does_not_store_fallback_guidance(self):
        catalog_item = real_high_risk_catalog_item()
        pest_name = catalog_item["name"]
        pest_record = (
            self.db.query(main.Pest)
            .filter_by(name=pest_name)
            .first()
        )
        pest_record.pest_id = catalog_item["pest_id"]
        pest_record.scientific_name = catalog_item.get("scientific_name")
        pest_record.risk = catalog_item["risk"]
        self.db.commit()

        payload = main.DetectionCreate(
            device_id="HIGH-RISK-NO-GUIDANCE",
            status="HARMFUL_PEST",
            pest=pest_name,
            confidence=0.99,
        )
        with (
            patch.object(main.manager, "broadcast", new_callable=AsyncMock),
            patch.object(main, "send_high_risk_sms"),
        ):
            response = asyncio.run(main.create_detection(payload, self.db))

        history = (
            self.db.query(main.HighRiskSolutionHistory)
            .filter_by(detection_id=response["id"])
            .first()
        )
        self.assertEqual(history.risk, "HIGH")
        self.assertIsNone(history.solution_source)
        for field in (
            "solution_description",
            "recommended_action",
            "prevention",
        ):
            self.assertIsNone(getattr(history, field), field)


class DeviceHeartbeatAndControlTests(unittest.TestCase):
    def setUp(self):
        self.device_id = "TEST-CONTROL-UNIT"
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        main.Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.db = self.session_factory()
        self.device = main.Device(
            device_id=self.device_id,
            name="Test field unit",
            status="ONLINE",
            connection="CONNECTED",
            last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
            temperature=0.0,
            humidity=0.0,
        )
        self.db.add(self.device)
        self.db.commit()
        main.DEVICE_SENSOR_REPORTS.pop(self.device_id, None)

    def tearDown(self):
        main.DEVICE_SENSOR_REPORTS.pop(self.device_id, None)
        self.db.close()
        self.engine.dispose()

    def get_control(self):
        return main.get_detection_control(self.device_id, self.db)

    def send_command(self, enabled):
        return main.set_detection_control(
            self.device_id,
            {"enabled": enabled},
            self.db,
        )

    def test_heartbeat_clears_unreported_sensor_values(self):
        response = main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(),
            self.db,
        )

        self.assertIsNone(self.device.temperature)
        self.assertIsNone(self.device.humidity)
        self.assertIsNone(response["device"]["temperature"])
        self.assertIsNone(response["device"]["humidity"])

    def test_stored_sensor_values_without_a_fresh_device_report_are_unavailable(self):
        main.DEVICE_SENSOR_REPORTS.pop(self.device_id, None)

        response = main._device_response(self.device)

        self.assertIsNone(response["temperature"])
        self.assertIsNone(response["humidity"])

    def test_invalid_sensor_values_are_unavailable_and_valid_zero_is_preserved(self):
        response = main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(temperature=float("nan"), humidity=101),
            self.db,
        )
        self.assertIsNone(response["device"]["temperature"])
        self.assertIsNone(response["device"]["humidity"])

        response = main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(temperature=0, humidity=0),
            self.db,
        )
        self.assertEqual(response["device"]["temperature"], 0)
        self.assertEqual(response["device"]["humidity"], 0)

    def test_control_state_waits_for_real_heartbeat_acknowledgement(self):
        unknown = self.get_control()
        self.assertEqual(unknown["status"], "UNKNOWN")
        self.assertFalse(unknown["command_received"])

        requested = self.send_command(True)
        self.assertEqual(requested["status"], "REQUESTED")
        self.assertTrue(requested["command_received"])
        self.assertTrue(requested["device_online"])
        self.assertIsNone(requested["device_enabled"])
        command_id = requested["command_id"]

        main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(
                detection_enabled=False,
            ),
            self.db,
        )
        self.assertEqual(self.get_control()["status"], "REQUESTED")

        main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(
                detection_enabled=False,
                control_command_id="stale-command-id",
            ),
            self.db,
        )
        self.assertEqual(
            self.get_control()["status"],
            "REQUESTED",
        )

        main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(
                detection_enabled=False,
                control_command_id=command_id,
            ),
            self.db,
        )
        self.assertEqual(self.get_control()["status"], "REQUESTED")

        main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(
                detection_enabled=True,
                control_command_id=command_id,
            ),
            self.db,
        )
        acknowledged = self.get_control()
        self.assertEqual(acknowledged["status"], "RUNNING")
        self.assertTrue(acknowledged["device_enabled"])
        self.assertTrue(acknowledged["command_received"])
        other_session = self.session_factory()
        try:
            self.assertEqual(
                main.get_detection_control(self.device_id, other_session)["status"],
                "RUNNING",
            )
        finally:
            other_session.close()

        stopped = self.send_command(False)
        self.assertEqual(stopped["status"], "REQUESTED")
        self.assertNotEqual(stopped["command_id"], command_id)
        self.assertIsNone(stopped["device_enabled"])

        main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(
                detection_enabled=False,
                control_command_id=command_id,
            ),
            self.db,
        )
        self.assertEqual(
            self.get_control()["status"],
            "REQUESTED",
        )
        main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(
                detection_enabled=False,
                control_command_id=stopped["command_id"],
            ),
            self.db,
        )
        self.assertEqual(
            self.get_control()["status"],
            "STOPPED",
        )

    def test_invalid_control_command_is_rejected_without_changing_state(self):
        with self.assertRaises(main.HTTPException) as error:
            self.send_command("true")

        self.assertEqual(error.exception.status_code, 422)
        response = self.get_control()
        self.assertEqual(response["status"], "UNKNOWN")
        self.assertFalse(response["command_received"])

    def test_command_is_delivered_from_persistent_storage_to_another_session(self):
        created = self.send_command(True)
        other_session = self.session_factory()
        try:
            delivered = main.get_detection_control(self.device_id, other_session)
        finally:
            other_session.close()

        self.assertEqual(delivered["command_id"], created["command_id"])
        self.assertTrue(delivered["enabled"])
        self.assertEqual(delivered["status"], "REQUESTED")

    def test_matching_but_stale_acknowledgement_times_out(self):
        command = self.send_command(True)
        main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(
                detection_enabled=True,
                control_command_id=command["command_id"],
            ),
            self.db,
        )
        saved_command = (
            self.db.query(main.DetectionControlCommand)
            .filter_by(device_id=self.device_id)
            .first()
        )
        saved_command.created_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(seconds=main.CONTROL_COMMAND_TIMEOUT_SECONDS + 1)
        saved_command.acknowledged_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(seconds=main.DEVICE_STALE_SECONDS + 1)
        self.db.commit()

        response = self.get_control()
        self.assertEqual(response["status"], "TIMEOUT")
        self.assertIsNone(response["device_enabled"])

    def test_matching_command_id_with_wrong_device_state_never_confirms(self):
        command = self.send_command(True)
        main.device_heartbeat(
            self.device_id,
            main.DeviceHeartbeat(
                detection_enabled=False,
                control_command_id=command["command_id"],
            ),
            self.db,
        )

        response = self.get_control()
        self.assertEqual(response["status"], "REQUESTED")
        self.assertFalse(response["device_enabled"])

    def test_pending_command_times_out_while_device_remains_online(self):
        self.send_command(False)
        command = (
            self.db.query(main.DetectionControlCommand)
            .filter_by(device_id=self.device_id)
            .first()
        )
        command.created_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(seconds=main.CONTROL_COMMAND_TIMEOUT_SECONDS + 1)
        self.db.commit()

        response = self.get_control()
        self.assertTrue(response["device_online"])
        self.assertEqual(response["status"], "TIMEOUT")
        self.assertIsNone(response["device_enabled"])

    def test_command_for_an_offline_device_is_not_reported_as_acknowledged(self):
        self.send_command(False)
        self.device.last_seen = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(seconds=main.DEVICE_STALE_SECONDS + 1)
        self.db.commit()

        response = self.get_control()
        self.assertEqual(response["status"], "DEVICE_OFFLINE")
        self.assertFalse(response["device_online"])
        self.assertIsNone(response["device_enabled"])
        self.assertTrue(response["command_received"])
        self.assertIsNone(response["device_enabled"])


if __name__ == "__main__":
    unittest.main()
