#!/usr/bin/env python3
"""Offline evaluation helper for the experimental Pest Guard background gate.

This only scores audio files; it does not edit the backend, gate, or insect model.
Usage from the Pest guard project root:
    python .\\evaluate_background_gate_audio.py path\\to\\sample.wav [another.wav ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import librosa
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub

ROOT = Path(__file__).resolve().parent
GATE_PATH = ROOT / "backend" / "ai_model" / "yamnet_background_gate_pilot" / "background_gate.joblib"
YAMNET_URL = "https://tfhub.dev/google/yamnet/1"
SAMPLE_RATE = 16000
CLIP_SAMPLES = SAMPLE_RATE * 5
THRESHOLD = 0.30  # provisional: selected from this pilot's validation sweep only


def load_fixed_waveform(path: Path) -> np.ndarray:
    audio, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size < SAMPLE_RATE:
        raise ValueError("audio is shorter than 1 second")
    if audio.size > CLIP_SAMPLES:
        audio = audio[:CLIP_SAMPLES]
    elif audio.size < CLIP_SAMPLES:
        audio = np.pad(audio, (0, CLIP_SAMPLES - audio.size))
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak
    return audio.astype(np.float32)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python .\\evaluate_background_gate_audio.py <audio-file> [<audio-file> ...]")
        return 2
    if not GATE_PATH.is_file():
        print(f"ERROR: trained gate not found: {GATE_PATH}")
        return 2

    gate = joblib.load(GATE_PATH)
    print("Loading YAMNet for offline scoring...")
    yamnet = hub.load(YAMNET_URL)
    print(f"Provisional threshold: {THRESHOLD:.2f}")
    print("Reminder: scores are experimental; passing the gate does not verify an insect or its species.\n")

    errors = 0
    for raw_path in sys.argv[1:]:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        print(f"File: {path}")
        if not path.is_file():
            print("  ERROR: file not found\n")
            errors += 1
            continue
        try:
            waveform = load_fixed_waveform(path)
            _, embeddings, _ = yamnet(waveform)
            vector = tf.reduce_mean(embeddings, axis=0).numpy().reshape(1, -1)
            insect_score = float(gate.predict_proba(vector)[0, 1])
            decision = "INSECT-LIKE (candidate for classifier)" if insect_score >= THRESHOLD else "BACKGROUND-LIKE (reject candidate)"
            print(f"  Insect-like score: {insect_score:.4f}")
            print(f"  Gate decision: {decision}\n")
        except Exception as exc:  # show file-specific decode/model errors without aborting other files
            print(f"  ERROR: {type(exc).__name__}: {exc}\n")
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
