from pathlib import Path
import json
import os
import random
from collections import Counter

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform
from sklearn.utils.class_weight import compute_class_weight

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

OUT_MODEL = AI_DIR / "candidate_weighted_v1.keras"
OUT_HISTORY = AI_DIR / "candidate_weighted_v1_history.json"

BATCH_SIZE = 4
EPOCHS = 5
LEARNING_RATE = 1e-5
SAMPLE_RATE = 16000
TARGET_LENGTH = 80000
MAX_CLASS_WEIGHT = 5.0

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

if OUT_MODEL.exists() or OUT_HISTORY.exists():
    raise FileExistsError(
        "Weighted experiment output already exists. "
        "Nothing was overwritten. Choose a new output filename first."
    )

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
if len(labels) != 66:
    raise RuntimeError(f"Expected 66 labels, got {len(labels)}")

with DATA_MANIFEST.open("r", encoding="utf-8") as f:
    data = json.load(f)
with SPLIT_MANIFEST.open("r", encoding="utf-8") as f:
    split = json.load(f)

if split.get("recording_group_overlap") != 0:
    raise RuntimeError("Recording-group overlap detected.")
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
    raise RuntimeError("Training segment count mismatch.")
if len(val_paths) != int(split.get("validation_segments", -1)):
    raise RuntimeError("Validation segment count mismatch.")

for record in train_records + val_records:
    idx = int(record["label_index"])
    if idx < 0 or idx >= len(labels) or labels[idx] != record["label"]:
        raise RuntimeError(f"Invalid label/index: {record}")

resolved_paths = [
    str(Path(p).resolve()).lower()
    for p in train_paths + val_paths
]
if len(set(resolved_paths)) != len(resolved_paths):
    raise RuntimeError("Duplicate file path detected.")

missing_paths = [p for p in train_paths + val_paths if not Path(p).is_file()]
if missing_paths:
    raise RuntimeError(f"Missing data file: {missing_paths[0]}")

# Calculate weights from the training split only.
classes_present = np.unique(train_labels)
raw_weights = compute_class_weight(
    class_weight="balanced",
    classes=classes_present,
    y=train_labels,
)

class_weight = {
    int(class_id): float(min(weight, MAX_CLASS_WEIGHT))
    for class_id, weight in zip(classes_present, raw_weights)
}

# Report the weights before training.
counts = Counter(train_labels.tolist())
print("Classes:", len(labels))
print("Training segments:", len(train_paths))
print("Validation segments:", len(val_paths))
print("Recording-group overlap:", split["recording_group_overlap"])
print("Class weighting: balanced, capped at", MAX_CLASS_WEIGHT)
print("Rare-class weight examples:")
for class_id in sorted(counts, key=counts.get)[:10]:
    print(f"  {labels[class_id]}: count={counts[class_id]}, "
          f"weight={class_weight[class_id]:.3f}")
print("Largest-class weight examples:")
for class_id in sorted(counts, key=counts.get, reverse=True)[:5]:
    print(f"  {labels[class_id]}: count={counts[class_id]}, "
          f"weight={class_weight[class_id]:.3f}")

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
    return ds.prefetch(1)

print("Loading training and validation datasets...")
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

print("\nStarting weighted candidate training.")
history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS,
    callbacks=callbacks,
    class_weight=class_weight,
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
            "split_manifest": str(SPLIT_MANIFEST),
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
            "max_class_weight": MAX_CLASS_WEIGHT,
            "class_weight": {
                labels[i]: float(class_weight[i])
                for i in class_weight
            },
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("\nCandidate saved:", OUT_MODEL)
print("History saved:", OUT_HISTORY)
print("Do not deploy before independent evaluation.")
