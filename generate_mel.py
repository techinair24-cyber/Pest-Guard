import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Select one actual audio recording from the dataset
dataset = Path("Pest Guard Dataset")

audio_files = []
for ext in ("*.wav", "*.mp3", "*.flac", "*.ogg"):
    audio_files.extend(dataset.rglob(ext))

if not audio_files:
    raise FileNotFoundError("No audio recordings found. Check the dataset folder name.")

audio_path = audio_files[0]
print("Original audio:", audio_path.name)

y, sr = librosa.load(audio_path, sr=16000, mono=True, duration=5)

mel = librosa.feature.melspectrogram(
    y=y,
    sr=sr,
    n_fft=1024,
    hop_length=512,
    n_mels=128,
    fmin=50,
    fmax=8000
)

log_mel = librosa.power_to_db(mel, ref=np.max)

plt.figure(figsize=(12, 5))
librosa.display.specshow(
    log_mel,
    sr=sr,
    hop_length=512,
    x_axis="time",
    y_axis="mel",
    cmap="magma"
)
plt.colorbar(format="%+2.0f dB")
plt.title("Pest Guard - Original Dataset Mel Spectrogram")
plt.xlabel("Time (seconds)")
plt.ylabel("Frequency (Hz)")
plt.tight_layout()

output = Path("Pest_Guard_Original_Mel_Spectrogram.png")
plt.savefig(output, dpi=300, bbox_inches="tight")
plt.show()

print("Saved image:", output.resolve())
