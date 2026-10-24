import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import main

audio_path = input("Enter path to the original insect WAV: ").strip().strip('"')

waveform, sample_rate = sf.read(
    audio_path, dtype="float32", always_2d=True
)
waveform = waveform.mean(axis=1, dtype=np.float32)

if waveform.size == 0:
    raise ValueError("The audio file is empty.")

if sample_rate != 16000:
    divisor = gcd(int(sample_rate), 16000)
    waveform = resample_poly(
        waveform,
        16000 // divisor,
        int(sample_rate) // divisor,
    ).astype(np.float32)

waveform = waveform[:80000]

if waveform.size < 80000:
    waveform = np.pad(waveform, (0, 80000 - waveform.size))

peak = float(np.max(np.abs(waveform)))
if peak > 1e-8:
    waveform = waveform / peak

print("Model input rate: 16000 Hz")
print("Model input duration: 5 seconds")
print("RMS:", float(np.sqrt(np.mean(waveform ** 2))))

result = main.predict_pest(waveform)

print("\nPredicted species:", result.get("pest"))
print("Species score:", result.get("confidence"))
print("Predicted group:", result.get("insect_group"))
print("Group score:", result.get("group_score"))
print("Top predictions:")
for item in result.get("top_predictions", []):
    print(item)
