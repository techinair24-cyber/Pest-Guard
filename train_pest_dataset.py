import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
import random
from pathlib import Path

import numpy as np
import librosa
import tensorflow as tf

# -------------------- Reproducibility --------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

# -------------------- Paths --------------------
DATA_ROOT = Path.home() / "Desktop" / "Pest Guard Dataset"
PROJECT_ROOT = Path.cwd()

# Safety check: require running from the Pest guard project root.
if PROJECT_ROOT.name.lower() != "pest guard":
    raise RuntimeError(
        "Wrong working directory. Open PowerShell in "
        r"C:\Users\Deepthi MG\Desktop\Pest guard"
        " and run this script again."
    )

OUT_DIR = PROJECT_ROOT / "backend" / "ai_model" / "pest_dataset_candidate_v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

if not DATA_ROOT.is_dir():
    raise FileNotFoundError(f"Dataset folder missing: {DATA_ROOT}")

# -------------------- Training settings --------------------
SAMPLE_RATE = 16000
CLIP_SECONDS = 5
TARGET_LENGTH = SAMPLE_RATE * CLIP_SECONDS
BATCH_SIZE = 16
EPOCHS = 70
VALIDATION_FRACTION = 0.20
AUDIO_EXTENSIONS = {".wav", ".mp3", ".oga"}

# -------------------- Discover labelled recordings --------------------
samples = []

for category_dir in sorted(p for p in DATA_ROOT.iterdir() if p.is_dir()):
    # A species folder is any nested folder that directly contains audio.
    species_dirs = sorted(
        p for p in category_dir.rglob("*")
        if p.is_dir()
        and any(
            f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
            for f in p.iterdir()
        )
    )

    if species_dirs:
        for species_dir in species_dirs:
            for audio_file in sorted(species_dir.iterdir()):
                if audio_file.is_file() and audio_file.suffix.lower() in AUDIO_EXTENSIONS:
                    samples.append((audio_file, species_dir.name))
    else:
        # Categories without species subfolders use the category name.
        for audio_file in sorted(category_dir.iterdir()):
            if audio_file.is_file() and audio_file.suffix.lower() in AUDIO_EXTENSIONS:
                samples.append((audio_file, category_dir.name))

if not samples:
    raise RuntimeError(f"No supported audio recordings found under: {DATA_ROOT}")

class_names = sorted({label for _, label in samples})
if len(class_names) < 2:
    raise RuntimeError(f"Need at least 2 classes; found {len(class_names)}.")

label_index = {name: index for index, name in enumerate(class_names)}

# -------------------- Split by original recording --------------------
# This prevents clips from the same recording appearing in both sets.
train_files, val_files = [], []
for name in class_names:
    class_files = [(path, label) for path, label in samples if label == name]
    random.shuffle(class_files)

    if len(class_files) >= 3:
        n_val = max(1, round(len(class_files) * VALIDATION_FRACTION))
        val_files.extend(class_files[:n_val])
        train_files.extend(class_files[n_val:])
    else:
        # Very small classes remain in training; they cannot provide a
        # meaningful held-out validation sample.
        train_files.extend(class_files)

if not val_files:
    raise RuntimeError("Validation set is empty.")

# Save split and class mapping before training so the run is auditable.
(OUT_DIR / "class_names.json").write_text(
    json.dumps(class_names, indent=2), encoding="utf-8"
)
(OUT_DIR / "split_manifest.json").write_text(
    json.dumps(
        {
            "seed": SEED,
            "data_root": str(DATA_ROOT),
            "train_recordings": [
                {"path": str(path), "label": label} for path, label in train_files
            ],
            "validation_recordings": [
                {"path": str(path), "label": label} for path, label in val_files
            ],
        },
        indent=2,
    ),
    encoding="utf-8",
)

# -------------------- Audio features --------------------
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
        clips.append(clip)
    return clips

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
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)
    spectrum = tf.signal.stft(
        audio, frame_length=1024, frame_step=512, fft_length=1024
    )
    mel = tf.matmul(tf.square(tf.abs(spectrum)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
    return mel[..., tf.newaxis].numpy().astype(np.float32)

def prepare(files, description):
    features, targets = [], []
    for index, (path, label) in enumerate(files, 1):
        clips = split_into_clips(read_audio(path))
        if not clips:
            print(f"Skipped very short recording: {path}", flush=True)
            continue
        for clip in clips:
            features.append(make_feature(clip))
            targets.append(label_index[label])
        print(f"{description}: {index}/{len(files)} recordings", flush=True)

    if not features:
        raise RuntimeError(f"No usable {description} clips.")
    return np.stack(features), np.asarray(targets, dtype=np.int32)

print("Dataset:", DATA_ROOT)
print("Output candidate:", OUT_DIR)
print("Classes:", len(class_names))
print("Training recordings:", len(train_files))
print("Validation recordings:", len(val_files))
print("Preparing clips...", flush=True)

X_train, y_train = prepare(train_files, "Training")
X_val, y_val = prepare(val_files, "Validation")

print("Training clips:", len(y_train))
print("Validation clips:", len(y_val))

# -------------------- Fresh candidate model --------------------
# This does not load, overwrite, or promote any existing model.
model = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(155, 128, 1)),
    tf.keras.layers.Conv2D(16, 3, padding="same", activation="relu"),
    tf.keras.layers.MaxPooling2D(2),
    tf.keras.layers.Conv2D(32, 3, padding="same", activation="relu"),
    tf.keras.layers.MaxPooling2D(2),
    tf.keras.layers.Conv2D(64, 3, padding="same", activation="relu"),
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
    tf.keras.callbacks.ModelCheckpoint(
        filepath=str(OUT_DIR / "best_candidate.keras"),
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
    callbacks=callbacks,
)

(OUT_DIR / "training_history.json").write_text(
    json.dumps(history.history, indent=2), encoding="utf-8"
)

best_val_accuracy = max(history.history.get("val_accuracy", [0.0]))
print("\nCandidate training finished.")
print(f"Best validation accuracy: {best_val_accuracy:.2%}")
print("Candidate folder:", OUT_DIR)
print("Existing v2 candidate and production model were not changed.")
