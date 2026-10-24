from pathlib import Path
import urllib.request
import urllib.error
import json

import librosa
import numpy as np

DATA_ROOT = (
    Path.home()
    / "Desktop"
    / "Pest_Guard_New_Datasets"
)

API_URL = "http://127.0.0.1:8000/api/ai/predict"
SAMPLE_RATE = 16000

# Find one WAV recording from the new dataset.
audio_files = sorted(DATA_ROOT.rglob("*.wav"))

if not audio_files:
    raise RuntimeError("No WAV files found in the new dataset.")

audio_path = audio_files[0]
print("Testing audio:", audio_path.name)

# Load audio in the format expected by the model.
audio, _ = librosa.load(
    str(audio_path),
    sr=SAMPLE_RATE,
    mono=True,
    duration=5,
)

if len(audio) < SAMPLE_RATE:
    raise RuntimeError(
        "Selected audio is shorter than one second."
    )

# Normalize before converting to signed 16-bit PCM.
peak = np.max(np.abs(audio))

if peak > 0:
    audio = audio / peak * 0.8

pcm = (
    np.clip(audio, -1.0, 1.0) * 32767
).astype("<i2")

request = urllib.request.Request(
    API_URL,
    data=pcm.tobytes(),
    headers={
        "Content-Type": "application/octet-stream",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(
        request,
        timeout=60,
    ) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    print("\nCANDIDATE MODEL RESPONSE")
    print(json.dumps(result, indent=2))

except urllib.error.HTTPError as error:
    print("API returned HTTP error:", error.code)
    print(error.read().decode("utf-8", errors="replace"))

except Exception as error:
    print("Test failed:", repr(error))