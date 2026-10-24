
import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
import random
from pathlib import Path

import numpy as np
import librosa
import tensorflow as tf
import tensorflow_hub as hub

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path.home() / "Desktop" / "Pest Sound Dataset"

# Save to a new experiment folder. Do not overwrite existing candidates.
OUT_DIR = ROOT / "backend" / "ai_model" / "pest_yamnet_updated_candidate"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 16000
CLIP_SECONDS = 5
TARGET_LENGTH = SAMPLE_RATE * CLIP_SECONDS
EPOCHS = 100
BATCH_SIZE = 16
VALIDATION_FRACTION = 0.20

if not DATA_ROOT.is_dir():
    raise FileNotFoundError(f"Dataset folder missing: {DATA_ROOT}")

class_names = sorted(
    p.name for p in DATA_ROOT.iterdir()
    if p.is_dir() and any(
        f.is_file() and f.suffix.lower() in (".mp3", ".oga")
        for f in p.iterdir()
    )
)

if len(class_names) < 2:
    raise RuntimeError("Need at least two classes.")

label_index = {name: i for i, name in enumerate(class_names)}

train_files, val_files = [], []
class_counts = {}

# Split whole recordings, never individual clips from a recording.
for name in class_names:
    files = sorted(
        f for f in (DATA_ROOT / name).iterdir()
        if f.is_file() and f.suffix.lower() in (".mp3", ".oga")
    )
    random.shuffle(files)
    class_counts[name] = len(files)

    if len(files) < 3:
        print(
            f"WARNING: {name}: only {len(files)} recording(s). "
            "Keeping them in training; no independent validation "
            "is possible for this class."
        )
        train_files.extend((f, name) for f in files)
        continue

    n_val = max(1, round(len(files) * VALIDATION_FRACTION))
    val_files.extend((f, name) for f in files[:n_val])
    train_files.extend((f, name) for f in files[n_val:])

print("\nRecordings per class:")
for name, count in class_counts.items():
    print(f"  {name}: {count}")

if not train_files or not val_files:
    raise RuntimeError("Training or validation recordings are missing.")

print("\nClasses:", len(class_names))
print("Training recordings:", len(train_files))
print("Validation recordings:", len(val_files))
print("Loading pretrained YAMNet...", flush=True)

yamnet = hub.load("https://tfhub.dev/google/yamnet/1")


def read_audio(path):
    audio, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    return np.asarray(audio, dtype=np.float32)


def split_into_clips(audio):
    clips = []

    for start in range(0, len(audio), TARGET_LENGTH):
        clip = audio[start:start + TARGET_LENGTH]

        if len(clip) < SAMPLE_RATE:
            continue

        if len(clip) < TARGET_LENGTH:
            clip = np.pad(clip, (0, TARGET_LENGTH - len(clip)))

        peak = np.max(np.abs(clip))
        if peak > 0:
            clip = clip / peak

        clips.append(clip.astype(np.float32))

    return clips


def extract_embedding(clip):
    _, embeddings, _ = yamnet(
        tf.convert_to_tensor(clip, dtype=tf.float32)
    )
    return tf.reduce_mean(embeddings, axis=0).numpy().astype(np.float32)


def prepare(files, description):
    features, targets = [], []

    for i, (path, name) in enumerate(files, 1):
        audio = read_audio(path)
        clips = split_into_clips(audio)

        if not clips:
            print("Skipping very short recording:", path.name)
            continue

        for clip in clips:
            features.append(extract_embedding(clip))
            targets.append(label_index[name])

        print(
            f"{description}: {i}/{len(files)} recordings",
            flush=True,
        )

    if not features:
        raise RuntimeError(f"No usable {description} clips.")

    return (
        np.stack(features),
        np.asarray(targets, dtype=np.int32),
    )


print("\nExtracting YAMNet embeddings...", flush=True)
X_train, y_train = prepare(train_files, "Training")
X_val, y_val = prepare(val_files, "Validation")

print("Training clips:", len(y_train))
print("Validation clips:", len(y_val))

# Compute weights only for classes actually present in training.
counts = np.bincount(y_train, minlength=len(class_names))
present = counts > 0

class_weight = {
    i: float(len(y_train) / (int(np.sum(present)) * counts[i]))
    for i in range(len(class_names))
    if counts[i] > 0
}

print(
    "Classes represented in training:",
    int(np.sum(present)),
    "/",
    len(class_names),
)

# Keep the same 1024-dimensional YAMNet embedding input.
model = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(1024,)),
    tf.keras.layers.LayerNormalization(),
    tf.keras.layers.Dense(128, activation="relu"),
    tf.keras.layers.Dropout(0.35),
    tf.keras.layers.Dense(len(class_names), activation="softmax"),
])

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

callbacks = [
    tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=12,
        restore_best_weights=True,
    ),
    tf.keras.callbacks.ModelCheckpoint(
        str(OUT_DIR / "best_candidate.keras"),
        monitor="val_loss",
        save_best_only=True,
    ),
]

history = model.fit(
    X_train,
    y_train,
    validation_data=(X_val, y_val),
    batch_size=BATCH_SIZE,
    epochs=EPOCHS,
    shuffle=True,
    class_weight=class_weight,
    callbacks=callbacks,
)

# Save the model and matching labels together in the experiment folder.
# Best checkpoint is already saved by ModelCheckpoint.

(OUT_DIR / "class_names.json").write_text(
    json.dumps(class_names, indent=2),
    encoding="utf-8",
)

(OUT_DIR / "training_history.json").write_text(
    json.dumps(history.history, indent=2),
    encoding="utf-8",
)

print("\nYAMNet candidate training finished.")
print("Candidate folder:", OUT_DIR)
print("Production model unchanged.")

