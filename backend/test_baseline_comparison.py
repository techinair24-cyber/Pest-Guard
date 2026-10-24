import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
from pathlib import Path
import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform
from sklearn.metrics import accuracy_score, classification_report

ROOT = Path.cwd()
MD = ROOT / "backend" / "ai_model"

manifest = json.loads((MD / "combined_split_manifest.json").read_text())
labels = json.loads((MD / "class_names.json").read_text())
assert labels == manifest["classes"], "Class order mismatch"

items = manifest["validation"]
assert len(items) == 5622, f"Unexpected validation size: {len(items)}"

paths = [item["path"] for item in items]
y = np.array([item["label_index"] for item in items], dtype=np.int32)

for path in paths:
    if not Path(path).is_file():
        raise FileNotFoundError(path)

original = GlorotUniform.from_config

@classmethod
def compatible(cls, config):
    config = dict(config)
    config.pop("input_axes", None)
    config.pop("output_axes", None)
    return original.__func__(cls, config)

GlorotUniform.from_config = compatible
try:
    names = [
        "best_cnn_v3.keras",
        "candidate_aug_v1.keras",
        "candidate_aug_v2.keras",
    ]
    models = [
        tf.keras.models.load_model(MD / name, compile=False)
        for name in names
    ]
finally:
    GlorotUniform.from_config = original

for name, model in zip(names, models):
    if model.output_shape[-1] != len(labels):
        raise RuntimeError(f"Class count mismatch: {name}")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, 16000, 50.0, 8000.0
)

def preprocess(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)[:80000]
    audio = tf.pad(audio, [[0, tf.maximum(0, 80000 - tf.shape(audio)[0])]])
    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(
        peak > 0,
        lambda: audio / peak,
        lambda: audio
    )
    stft = tf.signal.stft(audio, 1024, 512, 1024)
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    return (
        (mel - tf.reduce_mean(mel)) /
        (tf.math.reduce_std(mel) + 1e-6)
    )[..., tf.newaxis]

predictions = [[] for _ in models]

for start in range(0, len(paths), 16):
    batch_paths = paths[start:start + 16]
    batch = np.stack([
        preprocess(
            np.load(path, allow_pickle=False).astype(np.float32)
        ).numpy()
        for path in batch_paths
    ]).astype(np.float32)

    for i, model in enumerate(models):
        probs = model.predict(batch, verbose=0)
        if probs.shape != (len(batch), len(labels)):
            raise RuntimeError(f"Unexpected output shape: {names[i]}")
        predictions[i].append(probs)

    print(f"\rEvaluated {min(start + 16, len(paths))}/{len(paths)}", end="")

p_base, p1, p2 = [
    np.concatenate(parts, axis=0) for parts in predictions
]

comparisons = [
    ("best_cnn_v3", p_base),
    ("candidate_aug_v1", p1),
    ("candidate_aug_v2", p2),
    ("soft_voting_equal", (p1 + p2) / 2.0),
]

results = {}
for name, probs in comparisons:
    predicted = np.argmax(probs, axis=1)
    report = classification_report(
        y, predicted,
        labels=list(range(len(labels))),
        target_names=labels,
        output_dict=True,
        zero_division=0,
    )
    results[name] = {
        "accuracy": float(accuracy_score(y, predicted)),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "weighted_f1": float(report["weighted avg"]["f1-score"]),
    }

output = MD / "baseline_candidate_comparison.json"
output.write_text(json.dumps(results, indent=2), encoding="utf-8")

print("\n\nSAME VALIDATION SET: 5,622 samples")
for name, result in results.items():
    print(
        f"{name}: accuracy={result['accuracy']:.4%}, "
        f"macro_f1={result['macro_f1']:.4f}, "
        f"weighted_f1={result['weighted_f1']:.4f}"
    )
print("\nSaved:", output)

from sklearn.metrics import confusion_matrix

print("\nPER-CLASS CHECK")
for name, probs in [
    ("best_cnn_v3", p_base),
    ("candidate_aug_v1", p1),
    ("candidate_aug_v2", p2),
    ("soft_voting_equal", (p1 + p2) / 2.0),
]:
    pred = np.argmax(probs, axis=1)
    report = classification_report(
        y, pred,
        labels=list(range(len(labels))),
        target_names=labels,
        output_dict=True,
        zero_division=0,
    )
    print(f"\n{name}")
    for label in labels:
        print(
            f"{label}: recall={report[label]['recall']:.4f}, "
            f"F1={report[label]['f1-score']:.4f}"
        )
    print("Confusion matrix:")
    print(confusion_matrix(y, pred, labels=list(range(len(labels)))))
