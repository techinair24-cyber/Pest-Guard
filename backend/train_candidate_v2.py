from pathlib import Path
import json
import os
import random

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
SPLIT_MANIFEST = AI_DIR / "combined_split_manifest.json"

OUT_MODEL = AI_DIR / "candidate_combined_v2.keras"
OUT_HISTORY = AI_DIR / "candidate_combined_v2_history.json"

BATCH_SIZE = 4
EPOCHS = 25
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

for path in (MODEL_PATH, LABELS_PATH, SPLIT_MANIFEST):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

if OUT_MODEL.exists() or OUT_HISTORY.exists():
    raise FileExistsError(
        "V2 output already exists. Stop and inspect it before rerunning."
    )

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
split = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))

if len(labels) != 66:
    raise RuntimeError(f"Expected 66 classes, got {len(labels)}")
if split.get("recording_group_overlap") != 0:
    raise RuntimeError("Recording-group overlap detected.")
if split.get("classes_without_validation"):
    raise RuntimeError("Some classes have no validation recordings.")
if split.get("classes") != labels:
    raise RuntimeError("Split labels do not match class_names.json.")

train_records = split.get("train", [])
val_records = split.get("validation", [])

if not train_records or not val_records:
    raise RuntimeError("Training or validation data is empty.")

train_paths = [r["path"] for r in train_records]
train_labels = np.asarray(
    [r["label_index"] for r in train_records], dtype=np.int32
)
val_paths = [r["path"] for r in val_records]
val_labels = np.asarray(
    [r["label_index"] for r in val_records], dtype=np.int32
)

if len(train_paths) != int(split.get("train_segments", -1)):
    raise RuntimeError("Training count does not match the manifest.")
if len(val_paths) != int(split.get("validation_segments", -1)):
    raise RuntimeError("Validation count does not match the manifest.")

for record in train_records + val_records:
    i = int(record["label_index"])
    if i < 0 or i >= len(labels) or labels[i] != record["label"]:
        raise RuntimeError(f"Invalid class label: {record}")

all_paths = [
    str(Path(p).resolve()).lower()
    for p in train_paths + val_paths
]
if len(set(all_paths)) != len(all_paths):
    raise RuntimeError("Duplicate paths detected across the split.")

missing = [p for p in train_paths + val_paths if not Path(p).is_file()]
if missing:
    raise FileNotFoundError(f"Missing data file: {missing[0]}")

print("Classes:", len(labels))
print("Training samples:", len(train_paths))
print("Validation samples:", len(val_paths))
print("Recording-group overlap: 0")
print("V2 model output:", OUT_MODEL)

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
        return np.load(
            p.decode("utf-8"), allow_pickle=False
        ).astype(np.float32, copy=False)

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
    return ds.prefetch(1)

train_ds = make_dataset(train_paths, train_labels, True)
val_ds = make_dataset(val_paths, val_labels, False)

model = load_compatible_model(MODEL_PATH)
if model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(f"Unexpected input shape: {model.input_shape}")
if model.output_shape != (None, 66):
    raise RuntimeError(f"Unexpected output shape: {model.output_shape}")

model.trainable = True
model.compile(
    optimizer=tf.keras.optimizers.Adam(
        learning_rate=LEARNING_RATE
    ),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

callbacks = [
    tf.keras.callbacks.ModelCheckpoint(
        str(OUT_MODEL),
        monitor="val_loss",
        save_best_only=True,
        verbose=1,
    ),
    tf.keras.callbacks.ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,
        patience=2,
        min_lr=1e-7,
        verbose=1,
    ),
    tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=6,
        restore_best_weights=True,
        verbose=1,
    ),
]

print("\nStarting V2 training for up to", EPOCHS, "epochs.")
history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS,
    callbacks=callbacks,
    verbose=1,
)

history_data = {
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
    "split_manifest": str(SPLIT_MANIFEST),
    "batch_size": BATCH_SIZE,
    "initial_learning_rate": LEARNING_RATE,
    "max_epochs": EPOCHS,
}

OUT_HISTORY.write_text(
    json.dumps(history_data, indent=2),
    encoding="utf-8",
)

print("\nV2 training finished.")
print("Candidate:", OUT_MODEL)
print("History:", OUT_HISTORY)
print("Do not deploy before evaluation.")
