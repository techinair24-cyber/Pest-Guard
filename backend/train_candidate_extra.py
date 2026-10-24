from pathlib import Path
import json
import os
import random

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

PROJECT = Path.cwd()
BASE = PROJECT / "backend" / "ai_model"
MANIFEST_PATH = BASE / "candidate_extra_manifest.json"
SOURCE_MODEL = BASE / "candidate_insectset459.keras"
OUT_MODEL = BASE / "candidate_insectset459_extra.keras"
OUT_HISTORY = BASE / "candidate_extra_training_history.json"

SAMPLE_RATE = 16000
TARGET_LENGTH = 80000
BATCH_SIZE = 16
EPOCHS = 3

for path in (MANIFEST_PATH, SOURCE_MODEL):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
labels = manifest["classes"]
train_paths = manifest["train_paths"]
train_labels = manifest["train_labels"]
val_paths = manifest["validation_paths"]
val_labels = manifest["validation_labels"]

if len(train_paths) != len(train_labels):
    raise RuntimeError("Training paths and labels have different lengths")
if len(val_paths) != len(val_labels):
    raise RuntimeError("Validation paths and labels have different lengths")
if len(labels) != 66:
    raise RuntimeError(f"Expected 66 classes, got {len(labels)}")

# Verify all paths exist and target-class examples are present.
if not all(Path(p).is_file() for p in train_paths + val_paths):
    raise RuntimeError("At least one manifest audio segment is missing")

target_id = labels.index("Chorthippusalbomarginatus")
target_train = sum(int(y) == target_id for y in train_labels)
target_val = sum(int(y) == target_id for y in val_labels)

print("Training segments:", len(train_paths))
print("Validation segments:", len(val_paths))
print("Target-class training segments:", target_train)
print("Target-class validation segments:", target_val)

original = GlorotUniform.from_config

@classmethod
def compatible_from_config(cls, config):
    config = dict(config)
    config.pop("input_axes", None)
    config.pop("output_axes", None)
    return original.__func__(cls, config)

GlorotUniform.from_config = compatible_from_config
try:
    model = tf.keras.models.load_model(SOURCE_MODEL, compile=False)
finally:
    GlorotUniform.from_config = original

if model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(f"Unexpected model input: {model.input_shape}")
if model.output_shape != (None, 66):
    raise RuntimeError(f"Unexpected model output: {model.output_shape}")

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
    audio = tf.pad(audio, [[0, tf.maximum(0, TARGET_LENGTH - tf.shape(audio)[0])]])
    audio = audio[:TARGET_LENGTH]

    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)

    stft = tf.signal.stft(
        audio, frame_length=1024, frame_step=512, fft_length=1024
    )
    power = tf.square(tf.abs(stft))
    mel = tf.matmul(power, mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (
        tf.math.reduce_std(mel) + 1e-6
    )
    return mel[..., tf.newaxis]

def load_one(path, label):
    audio = tf.numpy_function(
        lambda p: np.load(
            p.decode("utf-8"), allow_pickle=False
        ).astype(np.float32, copy=False),
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
    return ds.map(load_one, num_parallel_calls=2).batch(BATCH_SIZE).prefetch(1)

train_ds = make_dataset(train_paths, train_labels, True)
val_ds = make_dataset(val_paths, val_labels, False)

model.trainable = True
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

callbacks = [
    tf.keras.callbacks.ModelCheckpoint(
        str(OUT_MODEL),
        monitor="val_loss",
        save_best_only=True,
    ),
]

print("\nStarting extra-data candidate fine-tuning.")
print("Source model:", SOURCE_MODEL.name)
print("Output model:", OUT_MODEL.name)
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
                key: [float(v) for v in values]
                for key, values in history.history.items()
            },
            "training_segments": len(train_paths),
            "validation_segments": len(val_paths),
            "target_training_segments": target_train,
            "target_validation_segments": target_val,
            "classes": labels,
            "source_model": str(SOURCE_MODEL),
            "candidate_model": str(OUT_MODEL),
            "manifest": str(MANIFEST_PATH),
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("\nCandidate saved:", OUT_MODEL)
print("History saved:", OUT_HISTORY)
print("Do not deploy until evaluated.")
