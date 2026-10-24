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

# Continue from the best existing augmentation candidate.
MODEL_PATH = AI_DIR / "candidate_aug_v1.keras"
LABELS_PATH = AI_DIR / "class_names.json"
SPLIT_MANIFEST = AI_DIR / "combined_split_manifest.json"

OUT_MODEL = AI_DIR / "candidate_aug_v2.keras"
OUT_HISTORY = AI_DIR / "candidate_aug_v2_history.json"

BATCH_SIZE = 4
EPOCHS = 10
LEARNING_RATE = 1e-6
SAMPLE_RATE = 16000
TARGET_LENGTH = 80000

NOISE_STD_FRACTION = 0.003
GAIN_MIN = 0.90
GAIN_MAX = 1.10


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
    if not path.is_file():
        raise FileNotFoundError(f"Required file missing: {path}")

if OUT_MODEL.exists() or OUT_HISTORY.exists():
    raise FileExistsError(
        "candidate_aug_v2 output already exists. "
        "Nothing was overwritten."
    )

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
split = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))

if len(labels) != 66 or split.get("classes") != labels:
    raise RuntimeError("Class count or class order does not match.")
if split.get("recording_group_overlap") != 0:
    raise RuntimeError("Recording-group overlap detected.")
if split.get("classes_without_validation"):
    raise RuntimeError("Some classes have no validation recordings.")

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

for record in train_records + val_records:
    idx = int(record["label_index"])
    if idx < 0 or idx >= len(labels) or labels[idx] != record["label"]:
        raise RuntimeError(f"Invalid label/index: {record}")

all_paths = train_paths + val_paths
missing = [p for p in all_paths if not Path(p).is_file()]
if missing:
    raise FileNotFoundError(f"Missing split file: {missing[0]}")

resolved = [str(Path(p).resolve()).lower() for p in all_paths]
if len(set(resolved)) != len(resolved):
    raise RuntimeError("Duplicate paths found across the split.")

print("Starting model:", MODEL_PATH)
print("Training segments:", len(train_paths))
print("Validation segments:", len(val_paths))
print("Maximum additional epochs:", EPOCHS)
print("Production and v1 models will remain unchanged.")

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
    audio = tf.pad(
        audio, [[0, tf.maximum(0, TARGET_LENGTH - tf.shape(audio)[0])]]
    )[:TARGET_LENGTH]

    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)

    stft = tf.signal.stft(
        audio, frame_length=1024, frame_step=512, fft_length=1024
    )
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (
        tf.math.reduce_std(mel) + 1e-6
    )
    return mel[..., tf.newaxis]


def load_one(path, label, training):
    def read_array(p):
        return np.load(
            p.decode("utf-8"), allow_pickle=False
        ).astype(np.float32, copy=False)

    audio = tf.numpy_function(read_array, [path], tf.float32)
    audio.set_shape([None])
    audio = audio[:TARGET_LENGTH]
    audio = tf.pad(
        audio, [[0, tf.maximum(0, TARGET_LENGTH - tf.shape(audio)[0])]]
    )[:TARGET_LENGTH]

    if training:
        audio = audio * tf.random.uniform([], GAIN_MIN, GAIN_MAX)
        rms = tf.sqrt(tf.reduce_mean(tf.square(audio)) + 1e-12)
        noise = tf.random.normal(
            tf.shape(audio),
            mean=0.0,
            stddev=rms * NOISE_STD_FRACTION,
        )
        audio = audio + noise

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
    ds = ds.map(
        lambda path, label: load_one(path, label, training),
        num_parallel_calls=2,
    )
    return ds.batch(BATCH_SIZE).prefetch(1)


train_ds = make_dataset(train_paths, train_labels, True)
val_ds = make_dataset(val_paths, val_labels, False)

model = load_compatible_model(MODEL_PATH)

if model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(f"Unexpected input shape: {model.input_shape}")
if model.output_shape != (None, 66):
    raise RuntimeError(f"Unexpected output shape: {model.output_shape}")

model.trainable = True
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

callbacks = [
    tf.keras.callbacks.ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,
        patience=2,
        min_lr=1e-7,
        verbose=1,
    ),
    tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=4,
        min_delta=0.001,
        restore_best_weights=True,
        verbose=1,
    ),
    tf.keras.callbacks.ModelCheckpoint(
        str(OUT_MODEL),
        monitor="val_loss",
        save_best_only=True,
        verbose=1,
    ),
]

print("\nContinuing training from candidate_aug_v1...")
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
            "experiment": "continued_conservative_waveform_augmentation",
            "initial_model": str(MODEL_PATH),
            "candidate_model": str(OUT_MODEL),
            "epochs_completed": len(history.history["loss"]),
            "best_val_loss": float(min(history.history["val_loss"])),
            "best_val_accuracy": float(
                max(history.history["val_accuracy"])
            ),
            "history": {
                key: [float(v) for v in values]
                for key, values in history.history.items()
            },
            "training_segments": len(train_paths),
            "validation_segments": len(val_paths),
            "classes": labels,
            "split_manifest": str(SPLIT_MANIFEST),
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
            "noise_std_fraction": NOISE_STD_FRACTION,
            "gain_range": [GAIN_MIN, GAIN_MAX],
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("\nCandidate saved:", OUT_MODEL)
print("History saved:", OUT_HISTORY)
print("Next: evaluate candidate_aug_v2 on the same validation split.")
print("Do not deploy before evaluation.")
