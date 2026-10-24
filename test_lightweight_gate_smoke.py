#!/usr/bin/env python3
"""Local smoke test for Pest Guard's integrated lightweight gate.

Run from the Pest guard project root:
    python .\\test_lightweight_gate_smoke.py

Uses the actual backend gate and predict_pest() path, but never calls the API
handler, database, or WebSocket broadcaster.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Use the better-performing threshold observed in this project's pilot sweep:
# 59/60 background clips rejected and 90/92 insect clips accepted.
os.environ["PEST_BACKGROUND_GATE_THRESHOLD"] = "0.45"

ROOT = Path.cwd().resolve()
BACKEND = ROOT / "backend"
if not (BACKEND / "main.py").is_file():
    raise SystemExit("Run this script from the Pest guard project root.")
sys.path.insert(0, str(BACKEND))

import librosa  # noqa: E402
import numpy as np  # noqa: E402
from fastapi import HTTPException  # noqa: E402
import main  # noqa: E402

THRESHOLD = 0.45
INSECT_FILES = [BACKEND / "pest_test.wav", BACKEND / "roeselii_test.wav"]
BACKGROUND_DIR = Path.home() / "Desktop" / "InsectSound1000_Training" / "ESC50_background_pilot"
BACKGROUND_FILES = sorted(BACKGROUND_DIR.glob("*.wav"))[:5]


def pcm16(path: Path) -> np.ndarray:
    if not path.is_file():
        raise FileNotFoundError(f"Test recording missing: {path}")
    audio, _ = librosa.load(str(path), sr=main.SAMPLE_RATE, mono=True)
    if audio.size < main.SAMPLE_RATE:
        raise ValueError(f"Recording shorter than one second: {path}")
    pcm = np.clip(np.rint(audio * 32767.0), -32768, 32767).astype(np.int16)
    return pcm


def test_one(path: Path, expect_insect: bool) -> bool:
    pcm = pcm16(path)
    waveform = main.decode_audio_samples(pcm)
    score = main._pest_light_gate_score(waveform)
    decision_insect = score >= THRESHOLD
    expected = "INSECT-LIKE" if expect_insect else "BACKGROUND-LIKE"
    actual = "INSECT-LIKE" if decision_insect else "BACKGROUND-LIKE"
    print(f"\nFile: {path.name}\n  Gate score: {score:.4f} (threshold {THRESHOLD:.2f})\n  Gate decision: {actual}")

    try:
        result = main.predict_pest(pcm)
        if not expect_insect:
            print(f"  FAIL: background reached classifier as {result.get('pest')}")
            return False
        print(f"  Classifier candidate: {result.get('pest')} ({float(result.get('confidence', 0)):.4f}; unverified)")
        ok = decision_insect
    except HTTPException as exc:
        if expect_insect:
            print(f"  FAIL: insect audio rejected: HTTP {exc.status_code}: {exc.detail}")
            return False
        ok = exc.status_code == 422 and "background" in str(exc.detail).lower()
        print(f"  {'PASS' if ok else 'FAIL'}: API prediction path stopped with HTTP {exc.status_code}: {exc.detail}")
    if expect_insect:
        print(f"  {'PASS' if ok else 'FAIL'}: expected insect audio behavior")
    return ok


def main_test() -> int:
    print("PEST GUARD LIGHTWEIGHT GATE SMOKE TEST")
    print("This calls predict_pest only; no database or WebSocket endpoint is invoked.")
    print(f"Threshold override for this test: {THRESHOLD:.2f}")
    if not BACKGROUND_FILES:
        print(f"FAIL: no background WAVs found at {BACKGROUND_DIR}")
        return 2
    cases = [(p, True) for p in INSECT_FILES] + [(p, False) for p in BACKGROUND_FILES]
    passed = 0
    for path, expected in cases:
        try:
            passed += bool(test_one(path, expected))
        except Exception as exc:
            print(f"\nFAIL: {path}: {type(exc).__name__}: {exc}")
    print(f"\nSUMMARY: {passed}/{len(cases)} expected decisions passed")
    print("Local smoke test only; it does not establish field performance or verify species identity.")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main_test())
