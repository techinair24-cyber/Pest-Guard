from pathlib import Path
import json
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform
from sklearn.metrics import confusion_matrix

BASE = Path("backend/ai_model")
MODEL_PATH = BASE / "candidate_aug_v2.keras"
MANIFEST_PATH = BASE / "combined_split_manifest.json"
LABELS_PATH = BASE / "class_names.json"
OUTPUT = BASE / "candidate_aug_v2_confusion.json"

if OUTPUT.exists():
    raise FileExistsError(f"{OUTPUT} already exists; nothing overwritten.")

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
records = manifest["validation"]

if len(records) != 5622 or labels != manifest["classes"]:
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

if model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(f"Unexpected input shape: {model.input_shape}")

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

y_pred = []
batch_size = 16

for start in range(0, len(paths), batch_size):
    batch = []
    for p in paths[start:start + batch_size]:
        audio = np.load(p, allow_pickle=False).astype(
            np.float32, copy=False
        )
        batch.append(preprocess(audio).numpy())

    features = np.stack(batch).astype(np.float32)
    probs = model.predict(features, verbose=0)
    y_pred.extend(np.argmax(probs, axis=1).tolist())
    print(
        f"\rProcessed {min(start + batch_size, len(paths))}/{len(paths)}",
        end="", flush=True
    )

y_pred = np.asarray(y_pred, dtype=np.int32)
matrix = confusion_matrix(
    y_true, y_pred, labels=list(range(len(labels)))
)

weak_classes = [
    "Stenobothrusstigmaticus",
    "Atrapsaltacollina",
    "Omocestusrufipes",
    "Clinopsaltaautumna",
    "Barbitistesyersini",
    "Chrysochraondispar",
    "Chorthippusbrunneus",
    "Atrapsaltaencaustica",
    "Chorthippusmollis",
    "Chorthippusbiguttulus",
]

results = {}
for name in weak_classes:
    if name not in labels:
        continue
    i = labels.index(name)
    row = matrix[i]
    wrong = [
        {"predicted_as": labels[j], "count": int(row[j])}
        for j in range(len(labels))
        if j != i and row[j] > 0
    ]
    wrong.sort(key=lambda x: x["count"], reverse=True)
    results[name] = {
        "support": int(row.sum()),
        "correct": int(matrix[i, i]),
        "wrong_predictions": wrong[:8],
    }

OUTPUT.write_text(
    json.dumps(results, indent=2), encoding="utf-8"
)

print("\n\nMOST COMMON CONFUSIONS")
for name, data in results.items():
    print(f"\n{name}: {data['correct']}/{data['support']} correct")
    for item in data["wrong_predictions"][:5]:
        print(f"  -> {item['predicted_as']}: {item['count']}")

print("\nSaved:", OUTPUT)
print("No model or dataset files were modified.")
