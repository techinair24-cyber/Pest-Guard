"""Read-only diagnostic for Pest Guard's active 47-class candidate model.
Run from the Pest guard project root with: python diagnose_pest_prediction.py
This file does not modify the project, model, or deployed service.
"""
from pathlib import Path
import json
import sys

try:
    import librosa
    import numpy as np
    import tensorflow as tf
except Exception as exc:
    print(f"Missing Python dependency: {exc}")
    print("Run this using the same Python environment used for Pest Guard training.")
    sys.exit(1)

ROOT = Path.cwd()
MODEL_DIR = ROOT / "backend" / "ai_model" / "pest_new_dataset_candidate"
MODEL_PATH = MODEL_DIR / "best_candidate.keras"
LABELS_PATH = MODEL_DIR / "class_names.json"

if not MODEL_PATH.is_file() or not LABELS_PATH.is_file():
    print("ERROR: Run this script from the Pest guard project root (the folder containing backend\\).")
    print(f"Model expected at: {MODEL_PATH}")
    sys.exit(2)

wav_path_text = input("Paste the full path of ONE known insect .wav file: ").strip().strip('"')
if not wav_path_text:
    print("No audio path provided.")
    sys.exit(2)
wav_path = Path(wav_path_text)
if not wav_path.is_file():
    print(f"Audio file not found: {wav_path}")
    sys.exit(2)

expected = input("Expected pest name from the dataset filename (or press Enter): ").strip()

print("Loading active 47-class model...")
model = tf.keras.models.load_model(MODEL_PATH, compile=False)
class_names = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
if len(class_names) != 47 or model.output_shape[-1] != len(class_names):
    print(f"ERROR: model outputs={model.output_shape[-1]}, labels={len(class_names)}")
    sys.exit(3)

# Match training/inference sampling and model feature shape.
audio, _ = librosa.load(str(wav_path), sr=16000, mono=True)
target_length = 80000
if len(audio) > target_length:
    audio = audio[:target_length]
else:
    audio = np.pad(audio, (0, target_length - len(audio)))
audio = np.asarray(audio, dtype=np.float32)
peak = float(np.max(np.abs(audio))) if audio.size else 0.0
if peak > 0:
    audio = audio / peak

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    num_mel_bins=128,
    num_spectrogram_bins=513,
    sample_rate=16000,
    lower_edge_hertz=50.0,
    upper_edge_hertz=8000.0,
)
stft = tf.signal.stft(audio, frame_length=1024, frame_step=512, fft_length=1024)
power_spectrogram = tf.square(tf.abs(stft))
mel = tf.matmul(power_spectrogram, mel_matrix)
mel = tf.math.log(mel + 1e-6)
mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
features = mel[..., tf.newaxis]

scores = np.asarray(model(tf.expand_dims(features, 0), training=False).numpy()[0], dtype=float)
indices = np.argsort(scores)[::-1][:5]
print("\n--- READ-ONLY RESULT ---")
print(f"Audio: {wav_path.name}")
print(f"Audio duration: {len(librosa.load(str(wav_path), sr=16000, mono=True)[0]) / 16000:.2f} seconds")
print("Top 5 model predictions:")
for rank, idx in enumerate(indices, start=1):
    print(f"{rank}. {class_names[int(idx)]}: {scores[int(idx)] * 100:.2f}%")
if expected:
    norm = lambda s: ''.join(ch.lower() for ch in s if ch.isalnum())
    target_idx = next((i for i, label in enumerate(class_names) if norm(label) == norm(expected)), None)
    if target_idx is None:
        print(f"Expected label '{expected}' does not exactly match a model class name.")
        print("Use the scientific class name from class_names.json for an exact comparison.")
    else:
        print(f"Expected class score: {scores[target_idx] * 100:.2f}% ({class_names[target_idx]})")
print("\nDo not change the confidence threshold based on this result; send the output for diagnosis.")
