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
MANIFEST = MODEL_DIR / "combined_split_manifest.json"
LABELS = MODEL_DIR / "class_names.json"
OUTPUT = MODEL_DIR / "candidate_combined_v2_evaluation.json"

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
validation = manifest["validation"]

if len(validation) != 5622:
    raise RuntimeError(
        f"Expected 5622 validation samples, got {len(validation)}"
    )

if labels != manifest["classes"]:
    raise RuntimeError("Class order mismatch. Evaluation stopped.")

paths = [item["path"] for item in validation]
y_true = np.asarray(
    [item["label_index"] for item in validation], dtype=np.int32
)

for item in validation:
    i = int(item["label_index"])
    if i < 0 or i >= len(labels) or labels[i] != item["label"]:
        raise RuntimeError(f"Invalid validation label: {item}")
    if not Path(item["path"]).is_file():
        raise FileNotFoundError(item["path"])

print("Validation samples:", len(paths))
print("Classes:", len(labels))
print("Recording-group overlap:", manifest["recording_group_overlap"])
print("All three models use identical validation samples.")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, SAMPLE_RATE, 50.0, 8000.0
)

def preprocess(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)
    audio = audio[:TARGET_LENGTH]
    audio = tf.pad(
        audio, [[0, tf.maximum(0, TARGET_LENGTH - tf.shape(audio)[0])]]
    )
    audio = audio[:TARGET_LENGTH]

    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(
        peak > 0, lambda: audio / peak, lambda: audio
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
        audio = np.load(
            item, allow_pickle=False
        ).astype(np.float32, copy=False)
        features.append(preprocess(audio).numpy())
    return np.stack(features).astype(np.float32)

models_to_test = [
    ("best_cnn_v3.keras", "production"),
    ("candidate_combined.keras", "candidate_v1"),
    ("candidate_combined_v2.keras", "candidate_v2"),
]

results = {}

for filename, name in models_to_test:
    model_path = MODEL_DIR / filename
    if not model_path.is_file():
        raise FileNotFoundError(f"Required model missing: {model_path}")

    model = load_model_compat(model_path)
    predictions = []

    print(f"\nEvaluating {name}: {filename}")

    for start in range(0, len(paths), BATCH_SIZE):
        batch = batch_features(paths[start:start + BATCH_SIZE])
        probabilities = model.predict(batch, verbose=0)

        if probabilities.shape != (len(batch), len(labels)):
            raise RuntimeError(
                f"Unexpected output shape from {filename}: "
                f"{probabilities.shape}"
            )

        predictions.extend(
            np.argmax(probabilities, axis=1).tolist()
        )

        print(
            f"\rProcessed {min(start + BATCH_SIZE, len(paths))}"
            f"/{len(paths)}",
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
    tf.keras.backend.clear_session()

OUTPUT.write_text(
    json.dumps(results, indent=2),
    encoding="utf-8",
)

print("\nSaved evaluation:", OUTPUT)
print("\nFINAL COMPARISON")
for name, data in results.items():
    print(
        f"{name}: accuracy={data['accuracy']:.4%}, "
        f"macro_f1={data['macro_f1']:.4f}, "
        f"weighted_f1={data['weighted_f1']:.4f}"
    )

print("\nEvaluation complete. No model files were modified.")
