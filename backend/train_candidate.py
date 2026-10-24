import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
import random
import re
from pathlib import Path

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

PROJECT = Path.cwd()
MODEL_PATH = PROJECT / "backend" / "ai_model" / "best_cnn_v3.keras"
LABELS_PATH = PROJECT / "backend" / "ai_model" / "class_names.json"
DATA_ROOT = Path.home() / "Desktop" / "InsectSound1000_Training" / "InsectSet459_Processed"
OUT_MODEL = PROJECT / "backend" / "ai_model" / "candidate_insectset459.keras"
OUT_HISTORY = PROJECT / "backend" / "ai_model" / "candidate_training_history.json"

SAMPLE_RATE = 16000
TARGET_LENGTH = 80000
BATCH_SIZE = 16
EPOCHS = 3
VALIDATION_FRACTION = 0.15

def norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())

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

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
if len(labels) != 66:
    raise RuntimeError(f"Expected 66 labels, got {len(labels)}")

label_index = {norm(name): i for i, name in enumerate(labels)}
if len(label_index) != 66:
    raise RuntimeError("Duplicate normalized labels")

for path in (MODEL_PATH, LABELS_PATH, DATA_ROOT):
    if not path.exists():
        raise FileNotFoundError(f"Required path missing: {path}")

# Split by original recording stem, never by individual segment.
train_paths, train_labels = [], []
val_paths, val_labels = [], []
class_counts = {}

for folder in sorted(p for p in DATA_ROOT.iterdir() if p.is_dir()):
    key = norm(folder.name)
    if key not in label_index:
        print(f"Skipping folder without matching label: {folder.name}")
        continue

    files = sorted(folder.glob("*.npy"))
    if not files:
        continue

    groups = {}
    for file in files:
        stem = re.sub(r"_seg\d+$", "", file.stem, flags=re.IGNORECASE)
        groups.setdefault(stem, []).append(file)

    group_names = sorted(groups)
    random.shuffle(group_names)
    val_group_count = (
        max(1, round(len(group_names) * VALIDATION_FRACTION))
        if len(group_names) >= 2 else 0
    )
    val_groups = set(group_names[:val_group_count])
    class_id = label_index[key]

    for group_name, group_files in groups.items():
        destination = (
            (val_paths, val_labels)
            if group_name in val_groups
            else (train_paths, train_labels)
        )
        destination[0].extend(str(p) for p in group_files)
        destination[1].extend([class_id] * len(group_files))

    class_counts[labels[class_id]] = len(files)

if not train_paths or not val_paths:
    raise RuntimeError("Training or validation set is empty")

missing = [name for name in labels if name not in class_counts]
if missing:
    raise RuntimeError(
        "Classes without processed segments: " + ", ".join(missing)
    )

print("Classes:", len(labels))
print("Processed segments:", sum(class_counts.values()))
print("Training segments:", len(train_paths))
print("Validation segments:", len(val_paths))
print("Class segment counts:")
for name in labels:
    print(f"  {name}: {class_counts[name]}")

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
    audio = tf.pad(audio, [[0, padding]])
    audio = audio[:TARGET_LENGTH]

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
    magnitude = tf.abs(stft)
    mel = tf.matmul(tf.square(magnitude), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (
        tf.math.reduce_std(mel) + 1e-6
    )
    return mel[..., tf.newaxis]

def load_one(path, label):
    audio = tf.numpy_function(
        lambda p: np.load(p.decode("utf-8"), allow_pickle=False).astype(
            np.float32, copy=False
        ),
        [path],
        tf.float32,
    )
    audio.set_shape([None])
    features = waveform_to_mel(audio)
    features.set_shape([155, 128, 1])
    return features, label

def make_dataset(paths, targets, training):
    ds = tf.data.Dataset.from_tensor_slices(
        (np.asarray(paths, dtype=str), np.asarray(targets, dtype=np.int32))
    )
    if training:
        ds = ds.shuffle(
            min(len(paths), 10000),
            seed=SEED,
            reshuffle_each_iteration=True,
        )
    ds = ds.map(load_one, num_parallel_calls=2)
    ds = ds.batch(BATCH_SIZE).prefetch(1)
    return ds

train_ds = make_dataset(train_paths, train_labels, True)
val_ds = make_dataset(val_paths, val_labels, False)

model = load_compatible_model(MODEL_PATH)
if model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(f"Unexpected model input: {model.input_shape}")
if model.output_shape != (None, 66):
    raise RuntimeError(f"Unexpected model output: {model.output_shape}")

# Fine-tune the existing network at a conservative learning rate.
model.trainable = True
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

callbacks = [
    tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=1,
        restore_best_weights=True,
    ),
    tf.keras.callbacks.ModelCheckpoint(
        str(OUT_MODEL),
        monitor="val_loss",
        save_best_only=True,
    ),
]

print("\nStarting candidate fine-tuning.")
print("Production model will not be overwritten.")
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
                key: [float(value) for value in values]
                for key, values in history.history.items()
            },
            "training_segments": len(train_paths),
            "validation_segments": len(val_paths),
            "classes": labels,
            "candidate_model": str(OUT_MODEL),
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("\nCandidate saved to:", OUT_MODEL)
print("History saved to:", OUT_HISTORY)
print("Do not deploy until the candidate is independently evaluated.")
