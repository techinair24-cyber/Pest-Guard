
import json
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import tensorflow as tf


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

wav_path = Path(
    r"C:\Users\Deepthi MG\Desktop\InsectSound1000_Training"
    r"\InsectSet459_Overlap_Train\Train"
    r"\Roeseliana_roeselii_XC751670.wav"
)

segment_path = Path(
    r"C:\Users\Deepthi MG\Desktop\InsectSound1000_Training"
    r"\InsectSet459_Processed\Roeselianaroeselii"
    r"\Roeseliana_roeselii_XC751670_seg000.npy"
)

model_path = BASE_DIR / "ai_model" / "best_cnn_v3.keras"
class_names_path = BASE_DIR / "ai_model" / "class_names.json"

SAMPLE_RATE = 16000
AUDIO_LENGTH = 80000
EXPECTED_LABEL = "Roeselianaroeselii"


# ============================================================
# CHECK FILES
# ============================================================

for path in [wav_path, segment_path, model_path, class_names_path]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

print("=" * 70)
print("PEST GUARD AUDIO PREPROCESSING COMPARISON")
print("=" * 70)

print("\nLoading model...")
model = tf.keras.models.load_model(
    str(model_path),
    compile=False
)

with open(class_names_path, "r", encoding="utf-8") as f:
    class_names = json.load(f)

print(f"Model input shape:  {model.input_shape}")
print(f"Model output shape: {model.output_shape}")
print(f"Number of classes:  {len(class_names)}")
print(f"Expected label:     {EXPECTED_LABEL}")


# ============================================================
# LOAD ORIGINAL AUDIO AND TRAINING SEGMENT
# ============================================================

print("\nLoading original WAV...")
original_audio, original_sr = sf.read(wav_path)

if original_audio.ndim > 1:
    original_audio = original_audio.mean(axis=1)

print(f"Original sample rate: {original_sr}")
print(f"Original duration:    {len(original_audio) / original_sr:.2f} sec")

if original_sr != SAMPLE_RATE:
    original_audio = librosa.resample(
        original_audio.astype(np.float32),
        orig_sr=original_sr,
        target_sr=SAMPLE_RATE
    )

original_audio = original_audio.astype(np.float32)[:AUDIO_LENGTH]

print("\nLoading training segment...")
training_segment = np.load(segment_path).astype(np.float32)

if training_segment.ndim > 1:
    training_segment = training_segment.mean(axis=-1)

print(f"Training segment shape: {training_segment.shape}")


# ============================================================
# AUDIO PREPARATION
# ============================================================

def prepare_audio(audio):
    """Match the backend's 5-second crop/pad and amplitude normalization."""

    audio = np.asarray(audio, dtype=np.float32).flatten()

    if len(audio) > AUDIO_LENGTH:
        audio = audio[:AUDIO_LENGTH]
    elif len(audio) < AUDIO_LENGTH:
        audio = np.pad(
            audio,
            (0, AUDIO_LENGTH - len(audio)),
            mode="constant"
        )

    peak = np.max(np.abs(audio)) if len(audio) else 0.0

    if peak > 0:
        audio = audio / peak

    return audio


# ============================================================
# PREPROCESSING METHODS
# ============================================================

def make_mel_filter(fmin, fmax):
    return tf.signal.linear_to_mel_weight_matrix(
        num_mel_bins=128,
        num_spectrogram_bins=513,
        sample_rate=SAMPLE_RATE,
        lower_edge_hertz=fmin,
        upper_edge_hertz=fmax,
        dtype=tf.float32
    )


# Method 1: Current compare_audio.py preprocessing
LEGACY_MEL_FILTER = make_mel_filter(80, 7600)

# Method 2: Current backend/main.py preprocessing
BACKEND_MEL_FILTER = make_mel_filter(50, 8000)


def create_features(audio, method):
    audio = prepare_audio(audio)

    stft = tf.signal.stft(
        audio,
        frame_length=1024,
        frame_step=512,
        fft_length=1024
    )

    magnitude = tf.abs(stft)
    power = tf.square(magnitude)

    if method == "LEGACY":
        # Earlier backend configuration
        mel = tf.matmul(power, LEGACY_MEL_FILTER)

    elif method == "BACKEND":
        # Current backend configuration
        mel = tf.matmul(power, BACKEND_MEL_FILTER)

    else:
        raise ValueError(f"Unknown preprocessing method: {method}")

    features = tf.math.log(mel + 1e-6)

    mean = tf.reduce_mean(features)
    std = tf.math.reduce_std(features)

    features = (features - mean) / (std + 1e-6)

    return features.numpy()[None, ..., None].astype(np.float32)


# ============================================================
# RUN PREDICTIONS
# ============================================================

def test_audio(audio_name, audio):
    print("\n" + "#" * 70)
    print(f"AUDIO: {audio_name}")
    print("#" * 70)

    for method in ["LEGACY", "BACKEND"]:
        features = create_features(audio, method)

        predictions = model.predict(features, verbose=0)[0]

        top_indices = np.argsort(predictions)[-5:][::-1]
        best_index = int(top_indices[0])
        best_label = class_names[best_index]

        print(f"\nPreprocessing: {method}")
        print(f"Feature shape: {features.shape}")
        print(f"Top prediction: {best_label}")
        print(f"Top score: {predictions[best_index] * 100:.2f}%")
        print("Top 5 predictions:")

        for rank, index in enumerate(top_indices, start=1):
            print(
                f"  {rank}. {class_names[index]}: "
                f"{predictions[index] * 100:.2f}%"
            )

        print(
            "Expected label ranked:",
            (
                next(
                    (
                        f"Top {rank}"
                        for rank, index in enumerate(
                            np.argsort(predictions)[::-1], start=1
                        )
                        if class_names[index] == EXPECTED_LABEL
                    ),
                    "Not found in class names"
                )
            )
        )


# ============================================================
# EXECUTE TESTS
# ============================================================

# 1. Original Roeseliana WAV, resampled and cropped to 5 seconds
test_audio("Original Roeseliana WAV", original_audio)

# 2. Processed training segment
test_audio("Roeseliana training segment", training_segment)

# 3. Audio recorded by the ESP32 device
device_path = BASE_DIR / "pest_test.wav"

if device_path.exists():
    device_audio, device_sr = sf.read(device_path)

    if device_audio.ndim > 1:
        device_audio = device_audio.mean(axis=1)

    if device_sr != SAMPLE_RATE:
        device_audio = librosa.resample(
            device_audio.astype(np.float32),
            orig_sr=device_sr,
            target_sr=SAMPLE_RATE
        )

    test_audio("ESP32 device recording", device_audio)
else:
    print(f"\nESP32 recording not found: {device_path}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("No model, ESP32 code, or backend files were changed.")
print("=" * 70)
