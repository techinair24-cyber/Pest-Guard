import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
import random
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import librosa
import tensorflow as tf

# Reproducible training
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

# Use only the three NEW datasets
DATA_ROOT = (
    Path.home()
    / "Desktop"
    / "Pest_Guard_New_Datasets"
)

# Separate output. The production model is not overwritten.
OUT_DIR = (
    Path.cwd()
    / "backend"
    / "ai_model"
    / "pest_new_dataset_candidate"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 16000
CLIP_SECONDS = 5
TARGET_LENGTH = SAMPLE_RATE * CLIP_SECONDS
BATCH_SIZE = 16
EPOCHS = 30
VALIDATION_FRACTION = 0.20

AUDIO_EXTENSIONS = {".wav"}

if not DATA_ROOT.is_dir():
    raise FileNotFoundError(
        f"New dataset folder missing: {DATA_ROOT}"
    )

# Discover recordings and derive species from filename prefixes.
paths = sorted(
    p for p in DATA_ROOT.rglob("*")
    if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
)

if not paths:
    raise RuntimeError("No WAV files were found.")

label_display = {}
records = []
seen_names_and_sizes = set()

for path in paths:
    raw_label = path.stem.split("_", 1)[0]
    label_key = re.sub(
        r"[^a-z0-9]", "", raw_label.casefold()
    )

    if not label_key:
        print("Skipped filename without a species label:", path.name)
        continue

    # Avoid counting obvious copies with the same filename and size.
    signature = (path.name.casefold(), path.stat().st_size)
    if signature in seen_names_and_sizes:
        continue
    seen_names_and_sizes.add(signature)

    label_display.setdefault(label_key, raw_label)

    # Remove edit suffixes so edited versions stay in one group.
    recording_id = re.sub(
        r"_edit\d+$", "", path.stem, flags=re.IGNORECASE
    )
    group_key = re.sub(
        r"[^a-z0-9]", "", recording_id.casefold()
    )

    records.append({
        "path": path,
        "label": label_key,
        "group": group_key,
    })

class_keys = sorted(label_display)
if len(class_keys) < 2:
    raise RuntimeError("Need at least two insect species.")

class_names = [label_display[key] for key in class_keys]
label_index = {
    key: index for index, key in enumerate(class_keys)
}

# Group the recordings before splitting. Related edits cannot leak
# across the training and validation sets.
grouped = defaultdict(lambda: defaultdict(list))

for record in records:
    grouped[record["label"]][record["group"]].append(record)

train_records = []
val_records = []
split_manifest = []

rng = random.Random(SEED)

for label in class_keys:
    group_keys = sorted(grouped[label])
    rng.shuffle(group_keys)

    if len(group_keys) < 2:
        print(
            "WARNING: Only one recording group for",
            label_display[label],
            "- training cannot be independently validated for this class."
        )
        train_groups = group_keys
        val_groups = []
    else:
        val_count = max(
            1, round(len(group_keys) * VALIDATION_FRACTION)
        )
        val_count = min(val_count, len(group_keys) - 1)

        val_groups = group_keys[:val_count]
        train_groups = group_keys[val_count:]

    for group in train_groups:
        for record in grouped[label][group]:
            train_records.append(record)
            split_manifest.append({
                "file": str(record["path"].relative_to(DATA_ROOT)),
                "label": label_display[label],
                "group": group,
                "split": "train",
            })

    for group in val_groups:
        for record in grouped[label][group]:
            val_records.append(record)
            split_manifest.append({
                "file": str(record["path"].relative_to(DATA_ROOT)),
                "label": label_display[label],
                "group": group,
                "split": "validation",
            })

print("\nNEW DATASET")
print("Audio files:", len(records))
print("Species:", len(class_names))
print("Training recordings:", len(train_records))
print("Validation recordings:", len(val_records))

print("\nSpecies with fewer than 5 recording groups:")
for label in class_keys:
    count = len(grouped[label])
    if count < 5:
        print(f"  {label_display[label]}: {count} groups")

# Same 16 kHz, 5-second mel-spectrogram input format as the CNN.
mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    num_mel_bins=128,
    num_spectrogram_bins=513,
    sample_rate=SAMPLE_RATE,
    lower_edge_hertz=50.0,
    upper_edge_hertz=8000.0,
)

def make_feature(audio):
    audio = tf.convert_to_tensor(audio, dtype=tf.float32)

    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(
        peak > 0,
        lambda: audio / peak,
        lambda: audio,
    )

    spec = tf.signal.stft(
        audio,
        frame_length=1024,
        frame_step=512,
        fft_length=1024,
    )

    mel = tf.matmul(tf.square(tf.abs(spec)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (
        tf.math.reduce_std(mel) + 1e-6
    )

    return mel[..., tf.newaxis].numpy().astype(np.float32)

def prepare(record_list, description):
    features, targets = [], []
    skipped = 0

    for index, record in enumerate(record_list, 1):
        path = record["path"]

        try:
            audio, _ = librosa.load(
                str(path),
                sr=SAMPLE_RATE,
                mono=True,
            )
        except Exception as error:
            print("Skipped unreadable audio:", path.name, type(error).__name__)
            skipped += 1
            continue

        # Create non-overlapping clips. Ignore fragments shorter than 1 s.
        for start in range(0, len(audio), TARGET_LENGTH):
            clip = audio[start:start + TARGET_LENGTH]

            if len(clip) < SAMPLE_RATE:
                continue

            if len(clip) < TARGET_LENGTH:
                clip = np.pad(
                    clip, (0, TARGET_LENGTH - len(clip))
                )

            feature = make_feature(clip)

            if not np.all(np.isfinite(feature)):
                continue

            features.append(feature)
            targets.append(label_index[record["label"]])

        if index % 25 == 0 or index == len(record_list):
            print(
                f"{description}: {index}/{len(record_list)} recordings",
                flush=True,
            )

    print(f"{description} unreadable files: {skipped}")

    if not features:
        raise RuntimeError(f"No usable {description} clips.")

    return (
        np.stack(features),
        np.asarray(targets, dtype=np.int32),
    )

print("\nPreparing audio features...", flush=True)

X_train, y_train = prepare(train_records, "Training")
X_val, y_val = prepare(val_records, "Validation")

print("\nTraining clips:", len(y_train))
print("Validation clips:", len(y_val))

if len(y_val) == 0:
    raise RuntimeError("Validation set is empty.")

train_class_counts = np.bincount(
    y_train, minlength=len(class_names)
)

missing_train = [
    class_names[i]
    for i, count in enumerate(train_class_counts)
    if count == 0
]
if missing_train:
    raise RuntimeError(
        "These species have no usable training clips: "
        + ", ".join(missing_train)
    )

print("\nTraining clips per species:")
for index, name in enumerate(class_names):
    print(f"  {name}: {train_class_counts[index]}")

# Balance the training loss across the species.
total_clips = len(y_train)
class_weight = {
    index: min(
        5.0,
        total_clips / (
            len(class_names) * train_class_counts[index]
        ),
    )
    for index in range(len(class_names))
    if train_class_counts[index] > 0
}

# Fresh CNN. Never load or overwrite the production model.
model = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(155, 128, 1)),
    tf.keras.layers.Conv2D(
        16, 3, padding="same", activation="relu"
    ),
    tf.keras.layers.MaxPooling2D(2),
    tf.keras.layers.Conv2D(
        32, 3, padding="same", activation="relu"
    ),
    tf.keras.layers.MaxPooling2D(2),
    tf.keras.layers.Conv2D(
        64, 3, padding="same", activation="relu"
    ),
    tf.keras.layers.GlobalAveragePooling2D(),
    tf.keras.layers.Dropout(0.35),
    tf.keras.layers.Dense(64, activation="relu"),
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
        patience=5,
        restore_best_weights=True,
    ),
    tf.keras.callbacks.ModelCheckpoint(
        str(OUT_DIR / "best_candidate.keras"),
        monitor="val_loss",
        save_best_only=True,
    ),
]

(OUT_DIR / "class_names.json").write_text(
    json.dumps(class_names, indent=2),
    encoding="utf-8",
)

(OUT_DIR / "split_manifest.json").write_text(
    json.dumps(split_manifest, indent=2),
    encoding="utf-8",
)

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

(OUT_DIR / "training_history.json").write_text(
    json.dumps(history.history, indent=2),
    encoding="utf-8",
)

print("\nCandidate training finished.")
print("Candidate folder:", OUT_DIR)
print("Production model unchanged.")