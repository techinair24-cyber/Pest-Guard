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

paths = [x["path"] for x in items]
y = np.array([x["label_index"] for x in items], dtype=np.int32)
for p in paths:
    if not Path(p).is_file():
        raise FileNotFoundError(p)

original = GlorotUniform.from_config


@classmethod
def compatible(cls, config):
    config = dict(config)
    config.pop("input_axes", None)
    config.pop("output_axes", None)
    return original.__func__(cls, config)


GlorotUniform.from_config = compatible
try:
    models = [
        tf.keras.models.load_model(MD / name, compile=False)
        for name in ["candidate_aug_v1.keras", "candidate_aug_v2.keras"]
    ]
finally:
    GlorotUniform.from_config = original

for name, model in zip(
    ["candidate_aug_v1.keras", "candidate_aug_v2.keras"], models
):
    if model.output_shape[-1] != len(labels):
        raise RuntimeError(f"Wrong output size: {name} {model.output_shape}")

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, 16000, 50.0, 8000.0
)


def preprocess(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)[:80000]
    audio = tf.pad(audio, [[0, tf.maximum(0, 80000 - tf.shape(audio)[0])]])
    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)
    stft = tf.signal.stft(audio, 1024, 512, 1024)
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    return ((mel - tf.reduce_mean(mel)) /
            (tf.math.reduce_std(mel) + 1e-6))[..., tf.newaxis]


preds = [[], []]
for start in range(0, len(paths), 16):
    batch = np.stack([
        preprocess(np.load(p, allow_pickle=False).astype(np.float32)).numpy()
        for p in paths[start:start + 16]
    ]).astype(np.float32)

    for i, model in enumerate(models):
        probs = model.predict(batch, verbose=0)
        if probs.shape != (len(batch), len(labels)):
            raise RuntimeError(f"Unexpected prediction shape: {probs.shape}")
        preds[i].append(probs)

    print(f"\rEvaluated {min(start + 16, len(paths))}/{len(paths)}", end="")

p1, p2 = [np.concatenate(x, axis=0) for x in preds]
results = {}

for name, probs in [
    ("candidate_aug_v1", p1),
    ("candidate_aug_v2", p2),
    ("soft_voting_equal", (p1 + p2) / 2.0),
]:
    report = classification_report(
        y, np.argmax(probs, axis=1),
        labels=list(range(len(labels))),
        target_names=labels, output_dict=True, zero_division=0,
    )
    results[name] = {
        "accuracy": float(accuracy_score(y, np.argmax(probs, axis=1))),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "weighted_f1": float(report["weighted avg"]["f1-score"]),
    }

out = MD / "ensemble_evaluation.json"
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
print("\n\nRESULTS")
for name, r in results.items():
    print(f"{name}: accuracy={r['accuracy']:.4%}, "
          f"macro_f1={r['macro_f1']:.4f}, "
          f"weighted_f1={r['weighted_f1']:.4f}")
print("Saved:", out)
