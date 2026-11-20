import ast
import logging
import os
import unittest
from pathlib import Path


def load_predict_pest():
    source_path = Path(__file__).with_name("main.py")
    syntax_tree = ast.parse(source_path.read_text(encoding="utf-8-sig"))
    function = next(
        node
        for node in syntax_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "predict_pest"
    )
    namespace = {
        "UNKNOWN_INSECT_GROUP": "Unknown insect group",
        "logger": logging.getLogger(__name__),
        "os": os,
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


class FakeHierarchy:
    def __init__(self):
        self.calls = 0

    def predict(self, _waveform):
        self.calls += 1
        return {
            "pest": "Test insect",
            "confidence": 0.9,
            "top_predictions": [{"pest": "Test insect", "score": 0.9}],
        }


class BackgroundGateIsolatedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = load_predict_pest()

    def run_prediction(self, score, threshold):
        hierarchy = FakeHierarchy()
        self.namespace.update({
            "decode_audio_samples": lambda audio: audio,
            "_pest_light_gate_score": lambda _waveform: score,
            "_PEST_LIGHT_GATE_THRESHOLD": threshold,
            "_PEST_GUARD_HIERARCHY": hierarchy,
        })

        previous_bypass = os.environ.get("PEST_BACKGROUND_GATE_BYPASS")
        os.environ["PEST_BACKGROUND_GATE_BYPASS"] = "false"
        try:
            result = self.namespace["predict_pest"]([1.0, -1.0])
        finally:
            if previous_bypass is None:
                os.environ.pop("PEST_BACKGROUND_GATE_BYPASS", None)
            else:
                os.environ["PEST_BACKGROUND_GATE_BYPASS"] = previous_bypass

        return result, hierarchy

    def test_score_below_threshold_rejects_without_hierarchy_inference(self):
        result, hierarchy = self.run_prediction(score=0.05, threshold=0.10)

        self.assertEqual(hierarchy.calls, 0)
        self.assertIsNone(result["pest"])
        self.assertEqual(result["top_predictions"], [])
        self.assertEqual(result["confidence"], 0.0)
        self.assertIs(result["background_gate_passed"], False)

    def test_score_above_threshold_runs_hierarchy_inference(self):
        result, hierarchy = self.run_prediction(score=0.15, threshold=0.10)

        self.assertEqual(hierarchy.calls, 1)
        self.assertEqual(result["pest"], "Test insect")
        self.assertEqual(
            result["top_predictions"],
            [{"pest": "Test insect", "score": 0.9}],
        )
        self.assertIs(result["background_gate_passed"], True)

    def test_score_equal_to_threshold_runs_hierarchy_inference(self):
        result, hierarchy = self.run_prediction(score=0.10, threshold=0.10)

        self.assertEqual(hierarchy.calls, 1)
        self.assertEqual(result["pest"], "Test insect")
        self.assertIs(result["background_gate_passed"], True)


if __name__ == "__main__":
    unittest.main()
