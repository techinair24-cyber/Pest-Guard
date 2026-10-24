
import json
from pathlib import Path
from collections import defaultdict, Counter

import numpy as np
import librosa
import tensorflow as tf

# -------------------- Paths --------------------
PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_ROOT / "backend" / "ai_model" / "pest_dataset_candidate_v3" / "best_candidate.keras"
CLASS_PATH = PROJECT_ROOT / "backend" / "ai_model" / "pest_dataset_candidate_v3" / "class_names.json"
MANIFEST_PATH = PROJECT_ROOT / "backend" / "ai_model" / "pest_dataset_candidate_v3" / "split_manifest.json"
REPORT_PATH = PROJECT_ROOT / "backend" / "ai_model" / "pest_dataset_candidate_v3" / "evaluation_report.json"

SAMPLE_RATE = 16000
TARGET_LENGTH = SAMPLE_RATE * 5
BATCH_SIZE = 32

# -------------------- Load saved files --------------------
for path in (MODEL_PATH, CLASS_PATH, MANIFEST_PATH):
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")

with open(CLASS_PATH, encoding="utf-8") as f:
    class_names = json.load(f)

with open(MANIFEST_PATH, encoding="utf-8") as f:
    manifest = json.load(f)

validation = manifest["validation_recordings"]

if not validation:
    raise RuntimeError("No validation recordings found.")

label_index = {name: i for i, name in enumerate(class_names)}

# -------------------- Same preprocessing as training --------------------
mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    num_mel_bins=128,
    num_spectrogram_bins=513,
    sample_rate=SAMPLE_RATE,
    lower_edge_hertz=50.0,
    upper_edge_hertz=8000.0,
)

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

def make_feature(audio):
    audio = tf.convert_to_tensor(audio, dtype=tf.float32)
    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(
        peak > 0,
        lambda: audio / peak,
        lambda: audio,
    )
    spectrum = tf.signal.stft(
        audio, frame_length=1024, frame_step=512, fft_length=1024
    )
    mel = tf.matmul(tf.square(tf.abs(spectrum)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (
        tf.math.reduce_std(mel) + 1e-6
    )
    return mel[..., tf.newaxis].numpy().astype(np.float32)

# -------------------- Load model read-only --------------------
model = tf.keras.models.load_model(MODEL_PATH, compile=False)

if model.output_shape[-1] != len(class_names):
    raise RuntimeError(
        f"Model outputs {model.output_shape[-1]} classes, "
        f"but class_names.json contains {len(class_names)}."
    )

# -------------------- Evaluate validation clips --------------------
correct = 0
total = 0
skipped = []
per_class = defaultdict(lambda: {"correct": 0, "total": 0})
confusions = Counter()
clip_batch = []
label_batch = []

def evaluate_batch():
    global correct, total

    if not clip_batch:
        return

    features = np.stack(clip_batch)
    targets = np.asarray(label_batch, dtype=np.int32)

    probabilities = model.predict(features, verbose=0)
    predictions = np.argmax(probabilities, axis=1)

    for true_idx, pred_idx in zip(targets, predictions):
        true_name = class_names[int(true_idx)]
        pred_name = class_names[int(pred_idx)]

        total += 1
        per_class[true_name]["total"] += 1

        if true_idx == pred_idx:
            correct += 1
            per_class[true_name]["correct"] += 1
        else:
            confusions[(true_name, pred_name)] += 1

    clip_batch.clear()
    label_batch.clear()

print(f"Validation recordings: {len(validation)}")
print(f"Model classes: {len(class_names)}")
print("Starting evaluation...", flush=True)

for recording_number, item in enumerate(validation, 1):
    path = Path(item["path"])
    label = item["label"]

    if label not in label_index:
        skipped.append({"path": str(path), "reason": f"Unknown label: {label}"})
        continue

    if not path.is_file():
        skipped.append({"path": str(path), "reason": "File not found"})
        continue

    try:
        audio = read_audio(path)
        clips = split_into_clips(audio)

        if not clips:
            skipped.append({"path": str(path), "reason": "Recording too short"})
            continue

        for clip in clips:
            clip_batch.append(make_feature(clip))
            label_batch.append(label_index[label])

            if len(clip_batch) >= BATCH_SIZE:
                evaluate_batch()

    except Exception as exc:
        skipped.append({"path": str(path), "reason": str(exc)})

    if recording_number % 25 == 0 or recording_number == len(validation):
        print(
            f"Processed {recording_number}/{len(validation)} recordings",
            flush=True,
        )

evaluate_batch()

if total == 0:
    raise RuntimeError("No validation clips could be evaluated.")

accuracy = correct / total * 100

class_report = {}
for name in class_names:
    stats = per_class[name]
    class_report[name] = {
        "correct": stats["correct"],
        "total": stats["total"],
        "accuracy_percent": (
            round(stats["correct"] / stats["total"] * 100, 2)
            if stats["total"] else None
        ),
    }

top_confusions = [
    {"true_class": true_name, "predicted_class": pred_name, "count": count}
    for (true_name, pred_name), count in confusions.most_common(20)
]

report = {
    "model": str(MODEL_PATH),
    "validation_recordings_in_manifest": len(validation),
    "evaluated_clips": total,
    "correct_clips": correct,
    "overall_clip_accuracy_percent": round(accuracy, 2),
    "per_class": class_report,
    "top_confusions": top_confusions,
    "skipped_recordings": skipped,
}

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print("\n========== VALIDATION RESULTS ==========")
print(f"Evaluated clips: {total}")
print(f"Correct clips: {correct}")
print(f"Overall clip accuracy: {accuracy:.2f}%")
print(f"Skipped recordings: {len(skipped)}")

print("\nLOWEST-PERFORMING CLASSES:")
available = [
    (name, stats) for name, stats in class_report.items()
    if stats["total"] > 0
]
for name, stats in sorted(
    available, key=lambda item: item[1]["accuracy_percent"]
)[:15]:
    print(
        f"{name}: {stats['correct']}/{stats['total']} "
        f"({stats['accuracy_percent']:.2f}%)"
    )

print("\nMOST COMMON CONFUSIONS:")
for item in top_confusions[:10]:
    print(
        f"{item['true_class']} -> {item['predicted_class']}: "
        f"{item['count']} clips"
    )

print(f"\nFull report saved to: {REPORT_PATH}")
print("Production model and candidate v2 were not modified.")
