import json
from pathlib import Path
from collections import Counter

import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform

PROJECT = Path.cwd()
MODEL_DIR = PROJECT / "backend" / "ai_model"
MANIFEST = MODEL_DIR / "candidate_validation_manifest.json"
LABELS = MODEL_DIR / "class_names.json"
TARGET = "Chorthippusalbomarginatus"

labels = json.loads(LABELS.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
paths = manifest["validation_paths"]
y_true = np.asarray(manifest["validation_labels"], dtype=np.int32)

target_id = labels.index(TARGET)
indices = np.where(y_true == target_id)[0]

print("Target:", TARGET)
print("Validation examples:", len(indices))
print("Distinct source groups:", len({
    Path(paths[i]).name.split("_seg")[0] for i in indices
}))

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, 16000, 50.0, 8000.0
)

def preprocess(path):
    audio = np.load(path, allow_pickle=False).astype(np.float32)
    audio = tf.reshape(audio, [-1])[:80000]
    audio = tf.pad(audio, [[0, tf.maximum(0, 80000 - tf.shape(audio)[0])]])
    audio = audio[:80000]
    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)
    stft = tf.signal.stft(audio, 1024, 512, 1024)
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
    return mel[..., tf.newaxis].numpy()

original = GlorotUniform.from_config

@classmethod
def compatible_from_config(cls, config):
    config = dict(config)
    config.pop("input_axes", None)
    config.pop("output_axes", None)
    return original.__func__(cls, config)

GlorotUniform.from_config = compatible_from_config
try:
    for filename, name in [
        ("best_cnn_v3.keras", "PRODUCTION"),
        ("candidate_insectset459.keras", "CANDIDATE"),
        ("candidate_insectset459_extra.keras", "CANDIDATE_EXTRA"),
    ]:
        model = tf.keras.models.load_model(
            MODEL_DIR / filename, compile=False
        )
        counts = Counter()
        print(f"\n===== {name} =====")

        for i in indices:
            x = np.expand_dims(preprocess(paths[i]), axis=0)
            probs = model.predict(x, verbose=0)[0]
            pred_id = int(np.argmax(probs))
            counts[labels[pred_id]] += 1
            print(
                Path(paths[i]).name,
                "=>", labels[pred_id],
                f"(confidence {probs[pred_id]:.3f})"
            )

        print("Prediction totals:")
        for label, count in counts.most_common():
            print(f"  {label}: {count}/{len(indices)}")

        del model
finally:
    GlorotUniform.from_config = original
