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

    def test_solution_inventory_requires_verified_crop_specific_records(self):
        from crop_data import CROP_DATA
        from solution_data import PEST_COVERAGE_DATA, SOLUTION_RECORDS

        self.assertEqual(len(CROP_DATA), 60)
        self.assertEqual(
            {item["pest_id"] for item in PEST_COVERAGE_DATA},
            {item["pest_id"] for item in main.PEST_DATA},
        )
        self.assertTrue(SOLUTION_RECORDS)
        self.assertTrue(
            all(item["status"] == "NEEDS_REVIEW" for item in SOLUTION_RECORDS)
        )
        self.assertTrue(
            all(not item.get("recommended_action") for item in SOLUTION_RECORDS)
        )

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
            crops = main.get_crops(search="paddy", db=session)
            self.assertEqual(len(crops), 1)
            self.assertEqual(crops[0]["crop_id"], "rice")

            crop = session.query(main.Crop).first()
            response = main.get_solutions(crop_id=crop.crop_id, pest_id=None, db=session)
            main.PestCropSolutionListResponse.model_validate(response)
            self.assertEqual(response["solutions"], [])
        finally:
            session.close()
            engine.dispose()

    def test_solution_api_excludes_low_risk_records(self):
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
                {item["risk"] for item in response["solutions"]},
                set(),
            )
            self.assertEqual(
                {item["solution_id"] for item in response["solutions"]},
                set(),
            )
        finally:
            session.close()
            engine.dispose()

    def test_solution_seed_rejects_low_risk_records(self):
        from copy import deepcopy
        from database import Base
        from solution_data import SOLUTION_RECORDS

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        pest = next(item for item in main.PEST_DATA if item["risk"] == "LOW")
        record = deepcopy(SOLUTION_RECORDS[0])
        record.update(
            solution_id="unsupported_low",
            pest_id=pest["pest_id"],
            risk_level="LOW",
        )

        try:
            with patch.object(main, "SOLUTION_RECORDS", [record]):
                with self.assertRaisesRegex(ValueError, "Unsupported solution risk"):
                    main.seed_pest_data(session)
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
