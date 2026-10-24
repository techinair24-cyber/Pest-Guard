import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
from pathlib import Path

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform
from sklearn.metrics import accuracy_score, classification_report

MODEL_DIR = Path.cwd() / "backend" / "ai_model"
MANIFEST = MODEL_DIR / "combined_split_manifest.json"
LABELS = MODEL_DIR / "class_names.json"
OUTPUT = MODEL_DIR / "candidate_weighted_v1_evaluation.json"

SAMPLE_RATE = 16000
TARGET_LENGTH = 80000
BATCH_SIZE = 16

MODELS = [
    ("best_cnn_v3.keras", "production"),
    ("candidate_combined.keras", "candidate_combined"),
    ("candidate_weighted_v1.keras", "candidate_weighted_v1"),
]

def load_model_compat(path):
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

for required in (MANIFEST, LABELS):
    if not required.is_file():
        raise FileNotFoundError(required)

for filename, _ in MODELS:
    if not (MODEL_DIR / filename).is_file():
        raise FileNotFoundError(MODEL_DIR / filename)

if OUTPUT.exists():
    raise FileExistsError(
        f"Evaluation report already exists: {OUTPUT}. "
        "Nothing was overwritten."
    )

labels = json.loads(LABELS.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
validation = manifest["validation"]

if len(validation) != 5622:
    raise RuntimeError(f"Unexpected validation count: {len(validation)}")

if labels != manifest["classes"]:
    raise RuntimeError("Class order mismatch.")

if manifest.get("recording_group_overlap") != 0:
    raise RuntimeError("Recording-group overlap detected.")

paths = [item["path"] for item in validation]
y_true = np.asarray(
    [item["label_index"] for item in validation], dtype=np.int32
)

for item in validation:
    idx = int(item["label_index"])
    if idx < 0 or idx >= len(labels) or labels[idx] != item["label"]:
        raise RuntimeError(f"Label/index mismatch: {item}")
    if not Path(item["path"]).is_file():
        raise FileNotFoundError(item["path"])

print("Validation samples:", len(paths))
print("Classes:", len(labels))
print("Recording-group overlap:", manifest["recording_group_overlap"])
print("All three models will use identical validation samples.")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, SAMPLE_RATE, 50.0, 8000.0
)

def preprocess(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)
    audio = audio[:TARGET_LENGTH]
    audio = tf.pad(
        audio,
        [[0, tf.maximum(0, TARGET_LENGTH - tf.shape(audio)[0])]],
    )
    audio = audio[:TARGET_LENGTH]

    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(
        peak > 0,
        lambda: audio / peak,
        lambda: audio,
    )

    stft = tf.signal.stft(audio, 1024, 512, 1024)
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (
        tf.math.reduce_std(mel) + 1e-6
    )
    return mel[..., tf.newaxis]

def batch_features(batch_paths):
    features = []
    for item in batch_paths:
        audio = np.load(item, allow_pickle=False).astype(
            np.float32, copy=False
        )
        features.append(preprocess(audio).numpy())
    return np.stack(features).astype(np.float32)

results = {}

for filename, name in MODELS:
    model_path = MODEL_DIR / filename
    model = load_model_compat(model_path)
    predictions = []

    if model.input_shape != (None, 155, 128, 1):
        raise RuntimeError(
            f"Unexpected input shape for {filename}: {model.input_shape}"
        )
    if model.output_shape != (None, len(labels)):
        raise RuntimeError(
            f"Unexpected output shape for {filename}: {model.output_shape}"
        )

    print(f"\nEvaluating {name}: {filename}")

    for start in range(0, len(paths), BATCH_SIZE):
        batch = batch_features(paths[start:start + BATCH_SIZE])
        probs = model.predict(batch, verbose=0)

        if probs.ndim != 2 or probs.shape[1] != len(labels):
            raise RuntimeError(f"Invalid predictions from {filename}")

        predictions.extend(np.argmax(probs, axis=1).tolist())
        print(
            f"\rProcessed {min(start + BATCH_SIZE, len(paths))}/{len(paths)}",
            end="",
            flush=True,
        )

    y_pred = np.asarray(predictions, dtype=np.int32)
    report = classification_report(
        y_true,
        y_pred,
        labels=list(range(len(labels))),
        target_names=labels,
        output_dict=True,
        zero_division=0,
    )

    results[name] = {
        "model": filename,
        "validation_samples": len(paths),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "weighted_f1": float(report["weighted avg"]["f1-score"]),
        "per_class": {
            label: {
                "precision": float(report[label]["precision"]),
                "recall": float(report[label]["recall"]),
                "f1": float(report[label]["f1-score"]),
                "support": int(report[label]["support"]),
            }
            for label in labels
        },
    }

    print(f"\n{name} accuracy: {results[name]['accuracy']:.4%}")
    print(f"{name} macro F1: {results[name]['macro_f1']:.4f}")
    print(f"{name} weighted F1: {results[name]['weighted_f1']:.4f}")

    del model

OUTPUT.write_text(json.dumps(results, indent=2), encoding="utf-8")

print("\nSaved evaluation:", OUTPUT)
print("\nSUMMARY")
for name, result in results.items():
    print(
        f"{name}: accuracy={result['accuracy']:.4%}, "
        f"macro_f1={result['macro_f1']:.4f}, "
        f"weighted_f1={result['weighted_f1']:.4f}"
    )
