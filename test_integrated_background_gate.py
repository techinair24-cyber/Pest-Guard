#!/usr/bin/env python3
"""Smoke-test the integrated Pest Guard gate via backend.main.predict_pest.

Run from the project root after connect_background_gate.py has been applied:
    python .\\test_integrated_background_gate.py

This calls predict_pest directly, not the API endpoint, so it does not write to
SQLite or broadcast WebSocket messages. It does load the CNN and YAMNet locally.
"""
from __future__ import annotations

import sys
from pathlib import Path

import librosa
import numpy as np
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

try:
    import main as pest_main
except Exception as exc:
    print(f"FAIL: backend import failed: {type(exc).__name__}: {exc}")
    raise SystemExit(2)

THRESHOLD = float(getattr(pest_main, "_PEST_BACKGROUND_GATE_THRESHOLD", 0.30))
INSECT_FILES = [ROOT / "backend" / "pest_test.wav", ROOT / "backend" / "roeselii_test.wav"]
BACKGROUND_DIR = Path.home() / "Desktop" / "InsectSound1000_Training" / "ESC50_background_pilot"
BACKGROUND_NAMES = [
    "1-115521-A-19.wav",
    "1-118206-A-31.wav",
    "1-12654-B-15.wav",
    "1-137-A-32.wav",
    "1-155858-D-25.wav",
]


def load_pcm16(path: Path) -> np.ndarray:
    audio, _ = librosa.load(str(path), sr=16000, mono=True)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size < 16000:
        raise ValueError(f"Recording shorter than one second: {path}")
    audio = audio[:80000]
    # decode_audio_samples accepts PCM int16 or float samples in [-1, 1].
    return np.clip(np.rint(audio * 32767.0), -32768, 32767).astype(np.int16)


def run_one(path: Path, expected: str) -> bool:
    print(f"\nFile: {path}")
    if not path.is_file():
        print("  FAIL: file not found")
        return False
    try:
        samples = load_pcm16(path)
        score = pest_main._pest_background_gate_score(pest_main.decode_audio_samples(samples))
        decision = "INSECT-LIKE" if score >= THRESHOLD else "BACKGROUND-LIKE"
        print(f"  Integrated gate score: {score:.4f} (threshold {THRESHOLD:.2f})")
        print(f"  Gate decision: {decision}")
        try:
            prediction = pest_main.predict_pest(samples)
            rejected = False
            print(f"  Classifier result: {prediction['pest']} ({prediction['confidence']:.4f}; unverified class candidate)")
        except HTTPException as exc:
            rejected = exc.status_code == 422 and "background" in str(exc.detail).lower()
            print(f"  Prediction stopped: HTTP {exc.status_code}: {exc.detail}")
            if not rejected:
                print("  FAIL: prediction stopped for an unexpected reason")
                return False
        if expected == "insect":
            ok = score >= THRESHOLD and not rejected
        else:
            ok = score < THRESHOLD and rejected
        print(f"  {'PASS' if ok else 'FAIL'}: expected {expected} audio behavior")
        return ok
    except Exception as exc:
        print(f"  FAIL: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    if not hasattr(pest_main, "_pest_background_gate_score"):
        print("FAIL: backend/main.py does not contain the background gate integration.")
        return 2
    print("PEST GUARD INTEGRATED GATE SMOKE TEST")
    print("No database endpoint or WebSocket broadcast is called by this script.")
    print(f"Threshold: {THRESHOLD:.2f}")

    passed = 0
    total = 0
    for path in INSECT_FILES:
        total += 1
        passed += int(run_one(path, "insect"))
    for name in BACKGROUND_NAMES:
        total += 1
        passed += int(run_one(BACKGROUND_DIR / name, "background"))

    print(f"\nSUMMARY: {passed}/{total} expected gate decisions passed")
    if passed != total:
        print("Do not deploy yet. Share this output for review.")
        return 1
    print("Local integration smoke test passed. This is not a full field validation.")
    print("Keep ESP32 diagnostic-only until backend deployment is verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
