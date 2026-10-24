from pathlib import Path
import json
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform
from sklearn.metrics import accuracy_score, classification_report

PROJECT = Path.cwd()
MODEL_DIR = PROJECT / "backend" / "ai_model"
MODEL_PATH = MODEL_DIR / "candidate_aug_v2.keras"
MANIFEST = MODEL_DIR / "combined_split_manifest.json"
LABELS = MODEL_DIR / "class_names.json"
OUTPUT = MODEL_DIR / "candidate_aug_v2_evaluation.json"

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


for path in (MODEL_PATH, MANIFEST, LABELS):
    if not path.is_file():
        raise FileNotFoundError(f"Required file missing: {path}")

if OUTPUT.exists():
    raise FileExistsError(
        f"{OUTPUT.name} already exists. Nothing was overwritten."
    )

labels = json.loads(LABELS.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
validation = manifest["validation"]

if len(validation) != 5622:
    raise RuntimeError(
        f"Expected 5622 validation samples, got {len(validation)}"
    )
if labels != manifest["classes"]:
    raise RuntimeError("Class order mismatch.")
if manifest.get("recording_group_overlap") != 0:
    raise RuntimeError("Recording-group overlap detected.")

paths = [r["path"] for r in validation]
y_true = np.asarray(
    [r["label_index"] for r in validation], dtype=np.int32
)

for item in validation:
    i = int(item["label_index"])
    if i < 0 or i >= len(labels) or labels[i] != item["label"]:
        raise RuntimeError(f"Invalid validation label: {item}")
    if not Path(item["path"]).is_file():
        raise FileNotFoundError(item["path"])

print("Model:", MODEL_PATH.name)
print("Validation samples:", len(paths))
print("Classes:", len(labels))
print("Recording-group overlap:", manifest["recording_group_overlap"])

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, SAMPLE_RATE, 50.0, 8000.0
)


def preprocess(audio):
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


def batch_features(batch_paths):
    features = []
    for path in batch_paths:
        audio = np.load(path, allow_pickle=False).astype(
            np.float32, copy=False
        )
        features.append(preprocess(audio).numpy())
    return np.stack(features).astype(np.float32)


model = load_model_compat(MODEL_PATH)
if model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(f"Unexpected input shape: {model.input_shape}")
if model.output_shape != (None, 66):
    raise RuntimeError(f"Unexpected output shape: {model.output_shape}")

predictions = []
print("\nEvaluating candidate_aug_v2...")

for start in range(0, len(paths), BATCH_SIZE):
    batch = batch_features(paths[start:start + BATCH_SIZE])
    probabilities = model.predict(batch, verbose=0)

    if probabilities.shape != (len(batch), len(labels)):
        raise RuntimeError(
            f"Unexpected model output shape: {probabilities.shape}"
        )

    predictions.extend(np.argmax(probabilities, axis=1).tolist())
    print(
        f"\rProcessed {min(start + BATCH_SIZE, len(paths))}/{len(paths)}",
        end="", flush=True
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

result = {
    "model": MODEL_PATH.name,
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

OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

print("\n\nCANDIDATE AUG V2 RESULTS")
print(f"Accuracy:   {result['accuracy']:.4%}")
print(f"Macro F1:   {result['macro_f1']:.4f}")
print(f"Weighted F1:{result['weighted_f1']:.4f}")
print("Saved evaluation:", OUTPUT)
print("No model files were modified.")
