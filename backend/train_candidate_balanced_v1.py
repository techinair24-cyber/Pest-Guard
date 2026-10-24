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

ROOT = Path.cwd()
AI = ROOT / "backend" / "ai_model"

START_MODEL = AI / "candidate_aug_v1.keras"
LABELS_PATH = AI / "class_names.json"
MANIFEST_PATH = AI / "combined_split_manifest.json"

OUT_MODEL = AI / "candidate_balanced_v1.keras"
OUT_HISTORY = AI / "candidate_balanced_v1_history.json"

SAMPLE_RATE = 16000
TARGET_LENGTH = 80000
BATCH_SIZE = 4
EPOCHS = 10
LEARNING_RATE = 1e-6

# Partial balancing avoids aggressively oversampling the smallest classes.
BALANCE_POWER = 0.5
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


for path in (START_MODEL, LABELS_PATH, MANIFEST_PATH):
    if not path.is_file():
        raise FileNotFoundError(f"Required file missing: {path}")

if OUT_MODEL.exists() or OUT_HISTORY.exists():
    raise FileExistsError(
        "Balanced candidate output already exists. Nothing overwritten."
    )

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

if len(labels) != 66 or manifest.get("classes") != labels:
    raise RuntimeError("Class count or class order mismatch.")
if manifest.get("recording_group_overlap") != 0:
    raise RuntimeError("Recording-group overlap detected.")
if manifest.get("classes_without_validation"):
    raise RuntimeError("Some classes have no validation samples.")

train_records = manifest["train"]
val_records = manifest["validation"]

train_paths = [r["path"] for r in train_records]
train_y = np.asarray(
    [r["label_index"] for r in train_records], dtype=np.int32
)
val_paths = [r["path"] for r in val_records]
val_y = np.asarray(
    [r["label_index"] for r in val_records], dtype=np.int32
)

for r in train_records + val_records:
    idx = int(r["label_index"])
    if idx < 0 or idx >= len(labels) or labels[idx] != r["label"]:
        raise RuntimeError(f"Invalid class index: {r}")

for p in train_paths + val_paths:
    if not Path(p).is_file():
        raise FileNotFoundError(p)

counts = np.bincount(train_y, minlength=len(labels)).astype(np.float64)
if np.any(counts == 0):
    raise RuntimeError("At least one class has no training samples.")

# Square-root inverse-frequency sampling. Every epoch has the original
# number of training examples, with more opportunities for rare classes.
sample_weights = np.power(counts[train_y], -BALANCE_POWER)
sample_weights /= sample_weights.sum()

print("Starting model:", START_MODEL.name)
print("Classes:", len(labels))
print("Training segments:", len(train_paths))
print("Validation segments:", len(val_paths))
print("Balance power:", BALANCE_POWER)
print("Maximum epochs:", EPOCHS)
print("Existing models will not be overwritten.")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, SAMPLE_RATE, 50.0, 8000.0
)


def waveform_to_mel(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)
    audio = audio[:TARGET_LENGTH]
    audio = tf.pad(
        audio, [[0, tf.maximum(0, TARGET_LENGTH - tf.shape(audio)[0])]]
    )[:TARGET_LENGTH]

    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)

    stft = tf.signal.stft(audio, 1024, 512, 1024)
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


def make_validation_dataset():
    ds = tf.data.Dataset.from_tensor_slices(
        (np.asarray(val_paths, dtype=str), val_y)
    )
    ds = ds.map(
        lambda p, y: load_one(p, y, False),
        num_parallel_calls=2,
    )
    return ds.batch(BATCH_SIZE).prefetch(1)


def make_balanced_training_dataset():
    # Resample indices each epoch, preserving the total epoch size.
    indices = np.random.choice(
        len(train_paths),
        size=len(train_paths),
        replace=True,
        p=sample_weights,
    )
    sampled_paths = np.asarray(train_paths, dtype=str)[indices]
    sampled_y = train_y[indices]

    ds = tf.data.Dataset.from_tensor_slices((sampled_paths, sampled_y))
    ds = ds.map(
        lambda p, y: load_one(p, y, True),
        num_parallel_calls=2,
    )
    return ds.batch(BATCH_SIZE).prefetch(1)


model = load_compatible_model(START_MODEL)

if model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(f"Unexpected input shape: {model.input_shape}")
if model.output_shape != (None, len(labels)):
    raise RuntimeError(f"Unexpected output shape: {model.output_shape}")

model.trainable = True
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

val_ds = make_validation_dataset()

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

class BalancedDatasetCallback(tf.keras.callbacks.Callback):
    def on_epoch_begin(self, epoch, logs=None):
        self.model.stop_training = False

print("\nStarting balanced fine-tuning...")
history = {
    "loss": [],
    "accuracy": [],
    "val_loss": [],
    "val_accuracy": [],
}

# Build a fresh balanced sample for each epoch.
for epoch in range(EPOCHS):
    print(f"\nBalanced epoch {epoch + 1}/{EPOCHS}")
    ds = make_balanced_training_dataset()
    result = model.fit(
        ds,
        validation_data=val_ds,
        initial_epoch=epoch,
        epochs=epoch + 1,
        callbacks=callbacks,
        verbose=1,
    )

    for key in history:
        history[key].extend(
            float(x) for x in result.history.get(key, [])
        )

    # Stop when EarlyStopping has restored the best weights.
    if model.stop_training:
        break

OUT_HISTORY.write_text(
    json.dumps(
        {
            "experiment": "sqrt_inverse_frequency_balanced_finetuning",
            "initial_model": START_MODEL.name,
            "candidate_model": OUT_MODEL.name,
            "epochs_completed": len(history["loss"]),
            "best_val_loss": min(history["val_loss"]),
            "best_val_accuracy": max(history["val_accuracy"]),
            "history": history,
            "training_segments": len(train_paths),
            "validation_segments": len(val_paths),
            "classes": labels,
            "balance_power": BALANCE_POWER,
            "learning_rate": LEARNING_RATE,
            "split_manifest": str(MANIFEST_PATH),
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("\nTraining complete.")
print("Candidate:", OUT_MODEL)
print("History:", OUT_HISTORY)
print("Evaluate before considering deployment.")
