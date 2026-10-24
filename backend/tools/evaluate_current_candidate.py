import json
from pathlib import Path
import numpy as np
import soundfile as sf
import tensorflow as tf
from scipy.signal import resample_poly
from sklearn.metrics import accuracy_score, f1_score, classification_report

root = Path.cwd()
model_dir = root / "backend" / "ai_model" / "pest_new_dataset_candidate"
dataset_root = Path.home() / "Desktop" / "Pest_Guard_New_Datasets"

manifest = json.loads((model_dir / "split_manifest.json").read_text(encoding="utf-8"))
labels = json.loads((model_dir / "class_names.json").read_text(encoding="utf-8"))
items = [x for x in manifest if x.get("split") == "validation"]

if len(items) != 412:
    raise RuntimeError(f"Expected 412 validation recordings, found {len(items)}")

model = tf.keras.models.load_model(model_dir / "best_candidate.keras", compile=False)
mel_matrix = tf.signal.linear_to_mel_weight_matrix(128, 513, 16000, 50, 8000)

def features(path):
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != 16000:
        from math import gcd
        g = gcd(sr, 16000)
        audio = resample_poly(audio, 16000 // g, sr // g).astype(np.float32)
    audio = audio[:80000]
    if len(audio) < 80000:
        audio = np.pad(audio, (0, 80000 - len(audio)))
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak
    stft = tf.signal.stft(audio, 1024, 512, 1024)
    mel = tf.matmul(tf.square(tf.abs(stft)), mel_matrix)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
    return mel[..., None].numpy()

y_true, y_pred, top3 = [], [], []
for i, item in enumerate(items, 1):
    path = dataset_root / item["file"]
    if not path.is_file():
        raise FileNotFoundError(path)
    x = features(path)
    probs = model.predict(x[None, ...], verbose=0)[0]
    y_true.append(int(item["class_index"]))
    y_pred.append(int(np.argmax(probs)))
    top3.append(set(np.argsort(probs)[-3:]))
    print(f"\rEvaluated {i}/{len(items)}", end="", flush=True)

print("\n\nMODEL VALIDATION RESULTS")
print("Classes:", len(labels))
print("Recordings:", len(y_true))
print(f"Accuracy: {accuracy_score(y_true, y_pred):.2%}")
print(f"Macro F1: {f1_score(y_true, y_pred, average='macro', zero_division=0):.2%}")
print(f"Top-3 accuracy: {np.mean([y in t for y, t in zip(y_true, top3)]):.2%}")
print("\nPER-CLASS REPORT")
print(classification_report(y_true, y_pred, labels=list(range(len(labels))), target_names=labels, zero_division=0))
