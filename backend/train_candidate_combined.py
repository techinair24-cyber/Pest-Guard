from pathlib import Path
import json
import os
import random
import re

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform

SEED = 459
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

PROJECT = Path.cwd()
AI_DIR = PROJECT / "backend" / "ai_model"
MODEL_PATH = AI_DIR / "best_cnn_v3.keras"
LABELS_PATH = AI_DIR / "class_names.json"
DATA_MANIFEST = AI_DIR / "combined_training_manifest.json"
SPLIT_MANIFEST = AI_DIR / "combined_split_manifest.json"
OUT_MODEL = AI_DIR / "candidate_combined.keras"
OUT_HISTORY = AI_DIR / "candidate_combined_history.json"

BATCH_SIZE = 4
EPOCHS = 5
LEARNING_RATE = 1e-5
SAMPLE_RATE = 16000
TARGET_LENGTH = 80000

def load_compatible_model(path):
    original = GlorotUniform.from_config

    @classmethod
    def compatible_from_config(cls, config):
        config = dict(config)
        config.pop("input_axes", None)
        config.pop("output_axes", None)
        return original.__func__(cls, config)

    GlorotUniform.from_config = compatible_from_config
    try:
        return tf.keras.models.load_model(path, compile=False)
    finally:
        GlorotUniform.from_config = original

for path in (MODEL_PATH, LABELS_PATH, DATA_MANIFEST, SPLIT_MANIFEST):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
if len(labels) != 66:
    raise RuntimeError(f"Expected 66 labels, got {len(labels)}")

with DATA_MANIFEST.open("r", encoding="utf-8") as f:
    data = json.load(f)
with SPLIT_MANIFEST.open("r", encoding="utf-8") as f:
    split = json.load(f)

# The split manifest stores complete records under train and validation.
if split.get("recording_group_overlap") != 0:
    raise RuntimeError("Split manifest reports recording-group overlap.")
if split.get("classes_without_validation"):
    raise RuntimeError("Some classes have no validation recordings.")
if split.get("classes") != labels:
    raise RuntimeError("Split class order does not match class_names.json.")

train_records = split.get("train", [])
val_records = split.get("validation", [])
if not train_records or not val_records:
    raise RuntimeError("Training or validation records are missing.")

train_paths = [r["path"] for r in train_records]
train_labels = np.asarray(
    [r["label_index"] for r in train_records], dtype=np.int32
)
val_paths = [r["path"] for r in val_records]
val_labels = np.asarray(
    [r["label_index"] for r in val_records], dtype=np.int32
)

if len(train_paths) != int(split.get("train_segments", -1)):
    raise RuntimeError("Training segment count does not match manifest.")
if len(val_paths) != int(split.get("validation_segments", -1)):
    raise RuntimeError("Validation segment count does not match manifest.")

# Confirm every split record has the correct class name and label index.
for record in train_records + val_records:
    idx = int(record["label_index"])
    if idx < 0 or idx >= len(labels) or labels[idx] != record["label"]:
        raise RuntimeError(
            f"Invalid label/index in split manifest: {record}"
        )

# Verify that every training and validation file exists.
missing_paths = [
    path for path in train_paths + val_paths
    if not Path(path).is_file()
]
if missing_paths:
    raise RuntimeError(
        f"{len(missing_paths)} split files are missing. "
        f"First missing file: {missing_paths[0]}"
    )

# Verify the split contains no duplicated file paths.
all_paths = [
    str(Path(path).resolve()).lower()
    for path in train_paths + val_paths
]
if len(set(all_paths)) != len(all_paths):
    raise RuntimeError("Duplicate file path detected across the split.")

print("Classes:", len(labels))
print("Training segments:", len(train_paths))
print("Validation segments:", len(val_paths))
print("Recording-group overlap:", split["recording_group_overlap"])
print("All split files and labels verified.")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    num_mel_bins=128,
    num_spectrogram_bins=513,
    sample_rate=SAMPLE_RATE,
    lower_edge_hertz=50.0,
    upper_edge_hertz=8000.0,
)

def waveform_to_mel(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)
    audio = audio[:TARGET_LENGTH]
    padding = tf.maximum(0, TARGET_LENGTH - tf.shape(audio)[0])
    audio = tf.pad(audio, [[0, padding]])[:TARGET_LENGTH]

    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(
        peak > 0,
        lambda: audio / peak,
        lambda: audio,
    )

    stft = tf.signal.stft(
        audio,
        frame_length=1024,
        frame_step=512,
        fft_length=1024,
    )
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (
        tf.math.reduce_std(mel) + 1e-6
    )
    return mel[..., tf.newaxis]

def load_one(path, label):
    def read_array(p):
        filename = p.decode("utf-8")
        return np.load(filename, allow_pickle=False).astype(
            np.float32, copy=False
        )

    audio = tf.numpy_function(read_array, [path], tf.float32)
    audio.set_shape([None])
    features = waveform_to_mel(audio)
    features.set_shape([155, 128, 1])
    return features, label

def make_dataset(paths, targets, training):
    ds = tf.data.Dataset.from_tensor_slices(
        (np.asarray(paths, dtype=str), targets)
    )
    if training:
        ds = ds.shuffle(
            min(len(paths), 10000),
            seed=SEED,
            reshuffle_each_iteration=True,
        )
    ds = ds.map(load_one, num_parallel_calls=2)
    ds = ds.batch(BATCH_SIZE, drop_remainder=False)
    ds = ds.prefetch(1)
    return ds

print("Classes:", len(labels))
print("Training segments:", len(train_paths))
print("Validation segments:", len(val_paths))
print("Batch size:", BATCH_SIZE)
print("Epochs:", EPOCHS)
print("Production model remains unchanged.")

train_ds = make_dataset(train_paths, train_labels, True)
val_ds = make_dataset(val_paths, val_labels, False)

model = load_compatible_model(MODEL_PATH)
if model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(f"Unexpected model input: {model.input_shape}")
if model.output_shape != (None, 66):
    raise RuntimeError(f"Unexpected model output: {model.output_shape}")

model.trainable = True
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

callbacks = [
    tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=2,
        restore_best_weights=True,
    ),
    tf.keras.callbacks.ModelCheckpoint(
        str(OUT_MODEL),
        monitor="val_loss",
        save_best_only=True,
    ),
]

print("\nStarting combined-data candidate training.")
history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS,
    callbacks=callbacks,
    verbose=1,
)

OUT_HISTORY.write_text(
    json.dumps(
        {
            "epochs_completed": len(history.history.get("loss", [])),
            "history": {
                key: [float(v) for v in values]
                for key, values in history.history.items()
            },
            "training_segments": len(train_paths),
            "validation_segments": len(val_paths),
            "classes": labels,
            "initial_model": str(MODEL_PATH),
            "candidate_model": str(OUT_MODEL),
            "manifest": str(DATA_MANIFEST),
            "split_manifest": str(SPLIT_MANIFEST),
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("\nCandidate saved:", OUT_MODEL)
print("History saved:", OUT_HISTORY)
print("Do not deploy before independent evaluation.")
