from pathlib import Path
import json
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform
from sklearn.metrics import accuracy_score, classification_report

AI = Path("backend/ai_model")
MODEL_PATH = AI / "candidate_balanced_v1.keras"
MANIFEST_PATH = AI / "combined_split_manifest.json"
LABELS_PATH = AI / "class_names.json"
OUTPUT = AI / "candidate_balanced_v1_evaluation.json"

for p in (MODEL_PATH, MANIFEST_PATH, LABELS_PATH):
    if not p.is_file():
        raise FileNotFoundError(p)

if OUTPUT.exists():
    raise FileExistsError(f"{OUTPUT} exists. Nothing overwritten.")

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
records = manifest["validation"]

if labels != manifest["classes"] or len(records) != 5622:
    raise RuntimeError("Validation size or class order mismatch.")
if manifest.get("recording_group_overlap") != 0:
    raise RuntimeError("Recording-group overlap detected.")

paths = [r["path"] for r in records]
y_true = np.asarray([r["label_index"] for r in records], dtype=np.int32)

for p in paths:
    if not Path(p).is_file():
        raise FileNotFoundError(p)

original = GlorotUniform.from_config

@classmethod
def compatible_from_config(cls, config):
    config = dict(config)
    config.pop("input_axes", None)
    config.pop("output_axes", None)
    return original.__func__(cls, config)

GlorotUniform.from_config = compatible_from_config
try:
    model = tf.keras.models.load_model(MODEL_PATH, compile=False)
finally:
    GlorotUniform.from_config = original

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, 16000, 50.0, 8000.0
)

def preprocess(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)
    audio = audio[:80000]
    audio = tf.pad(
        audio, [[0, tf.maximum(0, 80000 - tf.shape(audio)[0])]]
    )[:80000]
    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)
    stft = tf.signal.stft(audio, 1024, 512, 1024)
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (
        tf.math.reduce_std(mel) + 1e-6
    )
    return mel[..., tf.newaxis]

predictions = []
batch_size = 16

print("Evaluating balanced candidate on", len(paths), "samples")

for start in range(0, len(paths), batch_size):
    features = []
    for p in paths[start:start + batch_size]:
        audio = np.load(p, allow_pickle=False).astype(
            np.float32, copy=False
        )
        features.append(preprocess(audio).numpy())

    probs = model.predict(np.stack(features), verbose=0)
    predictions.extend(np.argmax(probs, axis=1).tolist())
    print(
        f"\rProcessed {min(start + batch_size, len(paths))}/{len(paths)}",
        end="", flush=True
    )

y_pred = np.asarray(predictions, dtype=np.int32)
report = classification_report(
    y_true, y_pred,
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
        name: {
            "precision": float(report[name]["precision"]),
            "recall": float(report[name]["recall"]),
            "f1": float(report[name]["f1-score"]),
            "support": int(report[name]["support"]),
        }
        for name in labels
    },
}

OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

print("\n\nBALANCED CANDIDATE RESULTS")
print(f"Accuracy:    {result['accuracy']:.4%}")
print(f"Macro F1:    {result['macro_f1']:.4f}")
print(f"Weighted F1: {result['weighted_f1']:.4f}")
print("Saved:", OUTPUT)
print("No existing models or evaluation files were modified.")
