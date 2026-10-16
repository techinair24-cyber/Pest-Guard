import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
from fastapi import HTTPException

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
    def test_model_output_dimension_matches_class_labels(self):
        self.assertEqual(main.ai_model.output_shape[-1], len(main.class_names))

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

    def test_valid_json_pcm_preserves_prediction_response_contract(self):
        audio = np.tile(
            np.array([-800, 800], dtype=np.int16),
            40000,
        )
        request = FakeRequest(
            "application/json",
            payload={"audio": audio.tolist()},
        )

        response = asyncio.run(main.ai_predict(request))

        self.assertEqual(
            set(response),
            {"status", "pest", "confidence", "risk"},
        )
        self.assertEqual(response["status"], "UNKNOWN")
        self.assertIn(response["pest"], main.class_names)
        self.assertGreaterEqual(response["confidence"], 0)
        self.assertLessEqual(response["confidence"], 1)

    def test_model_class_index_maps_to_cicada_label(self):
        audio = np.tile(
            np.array([-800, 800], dtype=np.int16),
            40000,
        )
        scores = np.zeros(len(main.class_names), dtype=np.float32)
        scores[0] = 0.983

        with patch.object(main.ai_model, "predict", return_value=[scores]):
            result = main.predict_pest(audio)

        self.assertEqual(main.class_names[0], "Cicada")
        self.assertEqual(result["pest"], "Cicada")
        self.assertAlmostEqual(result["confidence"], 0.983, places=5)

    def test_low_level_background_noise_stays_unverified(self):
        audio = np.random.default_rng(1).integers(
            -4, 5, size=80000, dtype=np.int16
        )
        request = FakeRequest(
            "application/octet-stream",
            body=audio.tobytes(),
        )

        response = asyncio.run(main.ai_predict(request))

        self.assertEqual(response["status"], "UNKNOWN")
        self.assertEqual(response["risk"], "UNKNOWN")
        self.assertIn(response["pest"], main.class_names)

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
            "pest": "Cicada",
            "confidence": 0.99,
        }

        with patch.object(main, "predict_pest", return_value=candidate_result):
            response = asyncio.run(main.ai_predict(request))

        self.assertEqual(response["status"], "UNKNOWN")
        self.assertEqual(response["pest"], "Cicada")
        self.assertEqual(response["confidence"], 0.99)
        self.assertEqual(response["risk"], "UNKNOWN")

    def test_unvalidated_device_score_is_not_stored_as_a_pest(self):
        database = Mock()
        database.query.return_value.filter.return_value.first.return_value = None
        payload = main.DetectionCreate(
            device_id="FIELD-UNIT-01",
            status="HARMFUL_PEST",
            pest="Cicada",
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
        self.assertEqual(detection.pest, "Cicada")
        self.assertEqual(detection.risk, "UNKNOWN")
        event = broadcast.await_args.args[0]
        self.assertEqual(event["status"], "UNKNOWN")
        self.assertEqual(event["pest"], "Cicada")
        self.assertEqual(event["risk"], "UNKNOWN")
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


if __name__ == "__main__":
    unittest.main()
