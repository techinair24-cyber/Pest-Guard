import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
from pathlib import Path
import numpy as np
import tensorflow as tf
from keras.initializers import GlorotUniform

root = Path.cwd()
md = root / "backend" / "ai_model"

labels = json.loads((md / "class_names.json").read_text())
manifest = json.loads((md / "combined_split_manifest.json").read_text())
audio_path = Path(manifest["validation"][0]["path"])

if not audio_path.is_file():
    raise FileNotFoundError(audio_path)

original = GlorotUniform.from_config

@classmethod
def compatible(cls, config):
    config = dict(config)
    config.pop("input_axes", None)
    config.pop("output_axes", None)
    return original.__func__(cls, config)

GlorotUniform.from_config = compatible
try:
    model = tf.keras.models.load_model(
        md / "best_cnn_v3.keras", compile=False
    )
finally:
    GlorotUniform.from_config = original

audio = tf.cast(
    np.load(audio_path, allow_pickle=False).astype(np.float32).reshape(-1),
    tf.float32
)[:80000]
audio = tf.pad(audio, [[0, tf.maximum(0, 80000 - tf.shape(audio)[0])]])
peak = tf.reduce_max(tf.abs(audio))
audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)

mel_matrix = tf.signal.linear_to_mel_weight_matrix(
    128, 513, 16000, 50.0, 8000.0
)
stft = tf.signal.stft(audio, 1024, 512, 1024)
mel = tf.math.log(tf.matmul(tf.square(tf.abs(stft)), mel_matrix) + 1e-6)
features = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
batch = features.numpy()[None, ..., None].astype(np.float32)

probs = model.predict(batch, verbose=0)[0]
if len(probs) != len(labels) or not np.isfinite(probs).all():
    raise RuntimeError("Prediction output failed validation.")

idx = int(np.argmax(probs))
print("Model loaded: PASS")
print("Output classes:", len(probs))
print("Class labels match:", len(probs) == len(labels))
print("Prediction finite: PASS")
print("Sample predicted pest:", labels[idx])
print("Confidence:", f"{float(probs[idx]):.2%}")
print("LOCAL TEST ONLY. No deployment performed.")
