
import json
import random
from pathlib import Path

import numpy as np
import librosa
import tensorflow as tf
import tensorflow_hub as hub
from sklearn.metrics import classification_report, confusion_matrix

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

ROOT = Path.cwd()
DATA_ROOT = Path.home() / "Desktop" / "Pest Sound Dataset"
MODEL_DIR = ROOT / "backend" / "ai_model" / "pest_yamnet_updated_candidate"
MODEL_PATH = MODEL_DIR / "best_candidate.keras"
LABELS_PATH = MODEL_DIR / "class_names.json"

SAMPLE_RATE = 16000
CLIP_SECONDS = 5
TARGET_LENGTH = SAMPLE_RATE * CLIP_SECONDS

for path in (DATA_ROOT, MODEL_PATH, LABELS_PATH):
    if not path.exists():
        raise FileNotFoundError(f"Missing required path: {path}")

class_names = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
label_index = {name: i for i, name in enumerate(class_names)}

# Recreate the same recording-level split used by the training script.
train_files, val_files = [], []
for name in class_names:
    files = sorted(
        f for f in (DATA_ROOT / name).iterdir()
        if f.is_file() and f.suffix.lower() in (".mp3", ".oga")
    )
    random.shuffle(files)
    if len(files) >= 3:
        n_val = max(1, round(len(files) * 0.20))
        val_files.extend((f, name) for f in files[:n_val])
        train_files.extend((f, name) for f in files[n_val:])
    else:
        train_files.extend((f, name) for f in files)

print("Loading YAMNet and candidate model...", flush=True)
yamnet = hub.load("https://tfhub.dev/google/yamnet/1")
model = tf.keras.models.load_model(MODEL_PATH, compile=False)

def extract_clips(path):
    audio, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    audio = np.asarray(audio, dtype=np.float32)
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

y_true, y_pred = [], []
recording_results = []

for i, (path, true_name) in enumerate(val_files, 1):
    clips = extract_clips(path)
    clip_probs = []

    for clip in clips:
        _, embeddings, _ = yamnet(tf.convert_to_tensor(clip))
        feature = tf.reduce_mean(embeddings, axis=0).numpy()[None, :]
        clip_probs.append(model.predict(feature, verbose=0)[0])

    if not clip_probs:
        print("Skipping short recording:", path.name)
        continue

    # Average predictions across the recording for recording-level evaluation.
    probabilities = np.mean(clip_probs, axis=0)
    pred_id = int(np.argmax(probabilities))
    true_id = label_index[true_name]

    y_true.append(true_id)
    y_pred.append(pred_id)
    recording_results.append(
        (path.name, true_name, class_names[pred_id],
         float(probabilities[pred_id]))
    )
    print(f"Evaluated {i}/{len(val_files)}: {path.name}", flush=True)

if not y_true:
    raise RuntimeError("No validation recordings could be evaluated.")

print("\nRECORDING-LEVEL ACCURACY:",
      f"{np.mean(np.asarray(y_true) == np.asarray(y_pred)):.1%}")

print("\nCLASSIFICATION REPORT:")
print(classification_report(
    y_true, y_pred,
    labels=list(range(len(class_names))),
    target_names=class_names,
    zero_division=0,
))

print("\nCONFUSION MATRIX (rows=true, columns=predicted):")
print(confusion_matrix(
    y_true, y_pred, labels=list(range(len(class_names)))
))

print("\nPER-RECORDING PREDICTIONS:")
for filename, actual, predicted, confidence in recording_results:
    status = "CORRECT" if actual == predicted else "WRONG"
    print(
        f"{status} | actual={actual} | predicted={predicted} "
        f"| score={confidence:.3f} | {filename}"
    )

print("\nEvaluation complete. Production model unchanged.")
