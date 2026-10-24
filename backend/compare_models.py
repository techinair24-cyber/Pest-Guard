import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
from pathlib import Path

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform
from sklearn.metrics import accuracy_score, classification_report

PROJECT = Path.cwd()
MODEL_DIR = PROJECT / "backend" / "ai_model"
MANIFEST = MODEL_DIR / "candidate_validation_manifest.json"
LABELS = MODEL_DIR / "class_names.json"

SAMPLE_RATE = 16000
TARGET_LENGTH = 80000
BATCH_SIZE = 16

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

labels = json.loads(LABELS.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
paths = manifest["validation_paths"]
y_true = np.asarray(manifest["validation_labels"], dtype=np.int32)

if len(paths) != len(y_true) or not paths:
    raise RuntimeError("Validation manifest is empty or inconsistent")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, SAMPLE_RATE, 50.0, 8000.0
)

def preprocess(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)
    audio = audio[:TARGET_LENGTH]
    audio = tf.pad(audio, [[0, tf.maximum(0, TARGET_LENGTH - tf.shape(audio)[0])]])
    audio = audio[:TARGET_LENGTH]
    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)
    stft = tf.signal.stft(audio, 1024, 512, 1024)
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
    return mel[..., tf.newaxis]

def batch_features(batch_paths):
    result = []
    for item in batch_paths:
        audio = np.load(item, allow_pickle=False).astype(np.float32, copy=False)
        result.append(preprocess(audio).numpy())
    return np.stack(result).astype(np.float32)

results = {}

for filename, name in [
    ("best_cnn_v3.keras", "production"),
    ("candidate_insectset459.keras", "candidate"),
]:
    model_path = MODEL_DIR / filename
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    model = load_model_compat(model_path)
    predictions = []

    print(f"\nEvaluating {name}: {filename}")
    for start in range(0, len(paths), BATCH_SIZE):
        batch = batch_features(paths[start:start + BATCH_SIZE])
        probs = model.predict(batch, verbose=0)
        predictions.extend(np.argmax(probs, axis=1).tolist())
        print(
            f"\rProcessed {min(start + BATCH_SIZE, len(paths))}/{len(paths)}",
            end="",
            flush=True,
        )

    y_pred = np.asarray(predictions, dtype=np.int32)
    accuracy = float(accuracy_score(y_true, y_pred))
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
        "accuracy": accuracy,
        "macro_f1": report["macro avg"]["f1-score"],
        "weighted_f1": report["weighted avg"]["f1-score"],
        "per_class": {
            label: {
                "precision": report[label]["precision"],
                "recall": report[label]["recall"],
                "f1": report[label]["f1-score"],
                "support": report[label]["support"],
            }
            for label in labels
        },
    }
    print(f"\n{name} accuracy: {accuracy:.4%}")
    print(f"{name} macro F1: {report['macro avg']['f1-score']:.4f}")
    del model

out = MODEL_DIR / "candidate_comparison_results.json"
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
print("\nSaved comparison:", out)
print("\nSUMMARY")
for name, data in results.items():
    print(
        f"{name}: accuracy={data['accuracy']:.4%}, "
        f"macro_f1={data['macro_f1']:.4f}, "
        f"weighted_f1={data['weighted_f1']:.4f}"
    )
