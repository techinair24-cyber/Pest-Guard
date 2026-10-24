"""Send one known 5-second insect WAV to Pest Guard's deployed prediction API.
This is diagnostic only: it does not change local files or model weights, but a successful
prediction is saved by the backend to detection history.
Run from any Python environment with librosa, numpy, and requests installed.
"""
from pathlib import Path
import json
import sys

try:
    import librosa
    import numpy as np
    import requests
except Exception as exc:
    print(f"Missing Python dependency: {exc}")
    print("Use Pest Guard's active .venv, where librosa, numpy, and requests are installed.")
    sys.exit(1)

API_URL = "https://pest-guard-1q36.onrender.com/api/ai/predict"
SAMPLE_RATE = 16000
SAMPLES = 5 * SAMPLE_RATE

path_text = input("Paste the full path of the same known insect .wav file: ").strip().strip('"')
path = Path(path_text)
if not path.is_file():
    print(f"Audio file not found: {path}")
    sys.exit(2)
expected = input("Expected pest name (for comparison only): ").strip()

print("Loading WAV as mono 16 kHz, matching the backend's 5-second input...")
audio, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
if len(audio) > SAMPLES:
    audio = audio[:SAMPLES]
elif len(audio) < SAMPLES:
    audio = np.pad(audio, (0, SAMPLES - len(audio)))
# ESP32 transport is signed 16-bit little-endian PCM. Avoid peak normalization here;
# backend preprocessing normalizes for the CNN, while the sound gate sees input level.
pcm = np.clip(np.rint(audio * 32767.0), -32768, 32767).astype("<i2")
print(f"Sending {len(pcm)} samples ({len(pcm) / SAMPLE_RATE:.1f} sec) to Render.")
print("Note: a successful API prediction will add one detection-history record.")
try:
    response = requests.post(
        API_URL,
        data=pcm.tobytes(),
        headers={"Content-Type": "application/octet-stream"},
        timeout=90,
    )
except requests.RequestException as exc:
    print(f"Request failed: {exc}")
    sys.exit(3)

print(f"HTTP status: {response.status_code}")
try:
    result = response.json()
    print("Response:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    detail = result.get("detail") if isinstance(result, dict) else None
    if detail:
        print(f"Diagnostic detail: {detail}")
    elif isinstance(result, dict):
        pest = result.get("pest")
        common = result.get("common_name")
        confidence = result.get("confidence")
        print("\n--- COMPARISON ---")
        print(f"Expected: {expected or '(not entered)'}")
        print(f"Render predicted: {pest or '(not present in response)'}")
        if isinstance(confidence, (int, float)):
            print(f"Render score: {confidence * 100:.2f}%")
        if common:
            print(f"Common name: {common}")
except ValueError:
    print(response.text[:5000])
