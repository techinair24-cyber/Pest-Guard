"""Score WAV clips through the lightweight background gate already in backend/main.py.

Run from the project root (the folder containing backend):
    backend\\.venv311\\Scripts\\python.exe score_gate_clips.py

Folder layout:
    test_clips/insect/*.wav       real ESP32 insect recordings
    test_clips/background/*.wav   silence + ordinary noise recorded by the ESP32

It does not import backend/main.py (so TensorFlow and the 47-class model are NOT
loaded). It extracts the gate code block from main.py and runs that exact code,
so the features always match what the backend uses.
"""
import logging
import os
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

ROOT = Path.cwd()
MAIN = ROOT / "backend" / "main.py"
CLIPS = ROOT / "test_clips"
SAMPLE_RATE = 16000
START = "# --- Pest Guard lightweight insect/background gate ---"
END = "# --- End Pest Guard lightweight background gate ---"


class HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(f"{status_code}: {detail}")


def load_gate_namespace():
    src = MAIN.read_text(encoding="utf-8-sig")
    if START not in src or END not in src:
        sys.exit("Gate block markers not found in backend/main.py")
    block = src.split(START, 1)[1].split(END, 1)[0]
    ns = {
        "os": os, "np": np, "logging": logging, "HTTPException": HTTPException,
        "logger": logging.getLogger("gate"), "SAMPLE_RATE": SAMPLE_RATE,
        "__file__": str(MAIN),
    }
    exec(compile(START + block, "main_gate_block", "exec"), ns)
    return ns


def read_wav(path):
    rate, data = wavfile.read(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if data.dtype == np.int16:
        x = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        x = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        x = (data.astype(np.float32) - 128.0) / 128.0
    else:
        x = data.astype(np.float32)
    if rate != SAMPLE_RATE:
        x = resample_poly(x, SAMPLE_RATE, rate).astype(np.float32)
    return x


def main():
    ns = load_gate_namespace()
    ns["_load_pest_light_gate"]()
    threshold = ns["_PEST_LIGHT_GATE_THRESHOLD"]
    print(f"\nEffective threshold: {threshold}\n")
    results = {"insect": [], "background": []}
    for label in results:
        folder = CLIPS / label
        files = sorted(folder.glob("*.wav"))
        if not files:
            print(f"(no WAV files in {folder})")
        for f in files:
            x = read_wav(f)
            rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
            score = ns["_pest_light_gate_score"](x)
            results[label].append(score)
            verdict = "ACCEPT" if score >= threshold else "REJECT"
            print(f"{label:11s} {f.name:35s} rms={rms:.4f} score={score:.4f} {verdict}")

    ins, bg = results["insect"], results["background"]
    print("\n--- Summary ---")
    if ins:
        print(f"insect:     min={min(ins):.3f} max={max(ins):.3f} accepted={sum(s >= threshold for s in ins)}/{len(ins)}")
    if bg:
        print(f"background: min={min(bg):.3f} max={max(bg):.3f} accepted={sum(s >= threshold for s in bg)}/{len(bg)}")
    if ins and bg:
        print("\nThreshold sweep (insect accepted / background wrongly accepted):")
        for t in [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]:
            print(f"  {t:.2f}: {sum(s >= t for s in ins)}/{len(ins)}  |  {sum(s >= t for s in bg)}/{len(bg)}")


if __name__ == "__main__":
    main()
