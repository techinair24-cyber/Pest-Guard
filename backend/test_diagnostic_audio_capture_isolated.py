import ast
import json
import logging
import os
import tempfile
import unittest
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path


def load_capture_helper():
    source_path = Path(__file__).with_name("main.py")
    syntax_tree = ast.parse(source_path.read_text(encoding="utf-8-sig"))
    function = next(
        node
        for node in syntax_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_save_diagnostic_capture"
    )
    namespace = {
        "__file__": str(source_path),
        "Path": Path,
        "datetime": datetime,
        "timezone": timezone,
        "json": json,
        "logging": logging,
        "logger": logging.getLogger(__name__),
        "os": os,
        "uuid": uuid,
        "wave": wave,
        "SAMPLE_RATE": 16000,
        "_PEST_LIGHT_GATE_THRESHOLD": 0.10,
        "_DIAGNOSTIC_CAPTURE_SAMPLE_COUNT": 80_000,
        "_DIAGNOSTIC_CAPTURE_MAX_FILES": 100,
    }
    isolated_module = ast.Module(body=[function], type_ignores=[])
    exec(
        compile(
            ast.fix_missing_locations(isolated_module),
            str(source_path),
            "exec",
        ),
        namespace,
    )
    return namespace


class DiagnosticAudioCaptureIsolatedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = load_capture_helper()
        cls.save_capture = staticmethod(
            cls.namespace["_save_diagnostic_capture"]
        )

    def setUp(self):
        self.previous_max_files = self.namespace[
            "_DIAGNOSTIC_CAPTURE_MAX_FILES"
        ]
        self.namespace["_DIAGNOSTIC_CAPTURE_MAX_FILES"] = 100
        self.previous_capture_dir = os.environ.get(
            "PEST_DIAGNOSTIC_CAPTURE_DIR"
        )
        self.temp_root = tempfile.TemporaryDirectory(dir=str(Path.home()))
        self.capture_dir = Path(self.temp_root.name) / "captures"
        os.environ["PEST_DIAGNOSTIC_CAPTURE_DIR"] = str(self.capture_dir)
        self.raw_audio = b"\x00\x01" * 80_000

    def tearDown(self):
        if self.previous_capture_dir is None:
            os.environ.pop("PEST_DIAGNOSTIC_CAPTURE_DIR", None)
        else:
            os.environ["PEST_DIAGNOSTIC_CAPTURE_DIR"] = (
                self.previous_capture_dir
            )
        self.namespace["_DIAGNOSTIC_CAPTURE_MAX_FILES"] = (
            self.previous_max_files
        )
        self.temp_root.cleanup()

    def test_saves_exact_five_second_wav_and_gate_metadata(self):
        result = {
            "background_gate_score": 0.15,
            "background_gate_threshold": 0.10,
            "background_gate_passed": True,
            "background_gate_bypassed": False,
        }

        self.assertTrue(self.save_capture(self.raw_audio, result))

        wav_files = list(self.capture_dir.glob("pest-guard-*.wav"))
        self.assertEqual(len(wav_files), 1)
        wav_path = wav_files[0]
        with wave.open(str(wav_path), "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertEqual(wav_file.getsampwidth(), 2)
            self.assertEqual(wav_file.getframerate(), 16000)
            self.assertEqual(wav_file.getnframes(), 80_000)
            self.assertEqual(wav_file.readframes(80_000), self.raw_audio)

        metadata_path = wav_path.with_suffix(".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["sample_count"], 80_000)
        self.assertEqual(metadata["background_gate_score"], 0.15)
        self.assertEqual(metadata["background_gate_threshold"], 0.10)
        self.assertEqual(metadata["background_gate_decision"], "accepted")
        self.assertIs(metadata["background_gate_passed"], True)
        self.assertIsNotNone(datetime.fromisoformat(metadata["timestamp_utc"]))

    def test_saves_gate_rejected_audio_and_records_rejection(self):
        result = {
            "background_gate_score": 0.05,
            "background_gate_threshold": 0.10,
            "background_gate_passed": False,
            "background_gate_bypassed": False,
        }

        self.assertTrue(self.save_capture(self.raw_audio, result))

        metadata_path = next(self.capture_dir.glob("*.json"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["background_gate_decision"], "rejected")
        self.assertIs(metadata["background_gate_passed"], False)
        self.assertTrue(metadata_path.with_suffix(".wav").is_file())

    def test_saves_valid_length_audio_rejected_before_gate_scoring(self):
        self.assertTrue(
            self.save_capture(
                self.raw_audio,
                None,
                "rejected",
                422,
            )
        )

        metadata_path = next(self.capture_dir.glob("*.json"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["background_gate_decision"], "not_scored")
        self.assertEqual(metadata["background_gate_threshold"], 0.10)
        self.assertEqual(metadata["prediction_outcome"], "rejected")
        self.assertEqual(metadata["prediction_rejection_status_code"], 422)

    def test_capture_is_disabled_without_environment_setting(self):
        os.environ.pop("PEST_DIAGNOSTIC_CAPTURE_DIR", None)

        self.assertFalse(self.save_capture(self.raw_audio, {}))
        self.assertFalse(self.capture_dir.exists())

    def test_skips_non_five_second_pcm_and_repository_paths(self):
        self.assertFalse(self.save_capture(self.raw_audio[:-2], {}))
        self.assertFalse(self.capture_dir.exists())

        repository_capture_dir = (
            Path(__file__).resolve().parents[1]
            / f"diagnostic-captures-test-{uuid.uuid4().hex}"
        )
        os.environ["PEST_DIAGNOSTIC_CAPTURE_DIR"] = str(
            repository_capture_dir
        )
        self.assertFalse(self.save_capture(self.raw_audio, {}))
        self.assertFalse(repository_capture_dir.exists())

    def test_retains_only_the_most_recent_configured_count(self):
        self.namespace["_DIAGNOSTIC_CAPTURE_MAX_FILES"] = 2
        for _ in range(3):
            self.assertTrue(self.save_capture(self.raw_audio, {}))

        wav_files = list(self.capture_dir.glob("pest-guard-*.wav"))
        self.assertEqual(len(wav_files), 2)
        self.assertTrue(
            all(path.with_suffix(".json").is_file() for path in wav_files)
        )


if __name__ == "__main__":
    unittest.main()
