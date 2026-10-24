import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
from pathlib import Path
from collections import Counter

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform

root = Path("backend/ai_model")
manifest = json.loads(
    (root / "combined_split_manifest.json").read_text(encoding="utf-8")
)
labels = json.loads(
    (root / "class_names.json").read_text(encoding="utf-8")
)
items = manifest["validation"]
y_true = np.array([x["label_index"] for x in items], dtype=int)
paths = [x["path"] for x in items]

original = GlorotUniform.from_config

@classmethod
def compatible_from_config(cls, config):
    config = dict(config)
    config.pop("input_axes", None)
    config.pop("output_axes", None)
    return original.__func__(cls, config)

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, 16000, 50.0, 8000.0
)

def preprocess(audio):
    audio = tf.cast(tf.reshape(audio, [-1]), tf.float32)
    audio = audio[:80000]
    audio = tf.pad(
        audio, [[0, tf.maximum(0, 80000 - tf.shape(audio)[0])]]
    )
    audio = audio[:80000]
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
    return mel[..., tf.newaxis].numpy()

def load_model(path):
    GlorotUniform.from_config = compatible_from_config
    try:
        return tf.keras.models.load_model(path, compile=False)
    finally:
        GlorotUniform.from_config = original

def get_predictions(filename):
    model = load_model(root / filename)
    predictions = []

    for start in range(0, len(paths), 16):
        batch = np.stack([
            preprocess(np.load(p, allow_pickle=False))
            for p in paths[start:start + 16]
        ]).astype(np.float32)

        probabilities = model.predict(batch, verbose=0)
        predictions.extend(np.argmax(probabilities, axis=1))

        print(
            f"\r{filename}: {min(start + 16, len(paths))}/{len(paths)}",
            end="", flush=True
        )

    print()
    del model
    return np.asarray(predictions, dtype=int)

old = get_predictions("best_cnn_v3.keras")
new = get_predictions("candidate_combined.keras")

# Show the largest recall regressions and the most common
# incorrect predictions for each affected class.
old_recall = {}
new_recall = {}

for i, name in enumerate(labels):
    mask = y_true == i
    if mask.any():
        old_recall[name] = np.mean(old[mask] == i)
        new_recall[name] = np.mean(new[mask] == i)

regressed = sorted(
    labels,
    key=lambda name: new_recall[name] - old_recall[name]
)[:10]

print("\nTOP REGRESSED CLASSES: CANDIDATE CONFUSIONS")
for name in regressed:
    i = labels.index(name)
    mask = y_true == i
    wrong = Counter(new[mask & (new != i)].tolist())
    top_wrong = [
        f"{labels[j]} ({count})"
        for j, count in wrong.most_common(3)
    ]
    print(
        f"\n{name}: {old_recall[name]:.1%} -> "
        f"{new_recall[name]:.1%}"
    )
    print("  Candidate mistakes:", ", ".join(top_wrong) or "None")

print("\nReport complete. No model files were modified.")
