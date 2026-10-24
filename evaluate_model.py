"""Evaluate the active 47-class Pest Guard model on the manifest's validation clips.

Run from the project root (the folder containing backend):
    backend\\.venv311\\Scripts\\python.exe evaluate_model.py

Preprocessing copies backend/main.py: 16 kHz mono, cut/pad to 80000 samples,
peak-normalise, STFT(1024/512/1024), MEL_MATRIX(128, 513, 16000, 50, 8000),
log(mel + 1e-6), per-clip standardisation.

NOTE: the validation split was used to pick the best checkpoint, so this is NOT an
untouched test set. It is the honest baseline until a real test set exists.
"""
import csv
import json
import os
import sys
from collections import Counter
from math import gcd
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from scipy.io import wavfile
from scipy.signal import resample_poly
from sklearn.metrics import classification_report, confusion_matrix, f1_score

ROOT = Path.cwd()
AI_DIR = ROOT / "backend" / "ai_model"
MODEL_DIR = AI_DIR / "pest_new_dataset_candidate"
MANIFEST = AI_DIR / "combined_split_manifest.json"
OUT_DIR = ROOT / "test_results"
SR = 16000
TARGET = 80000
CONF_LIMIT = 0.70  # PEST_IDENTIFICATION_CONFIDENCE in backend/main.py

MEL_MATRIX = tf.signal.linear_to_mel_weight_matrix(128, 513, 16000, 50, 8000)


def read_wav(path):
    rate, data = wavfile.read(path)
    if data.ndim > 1:
        data = data.astype(np.float64).mean(axis=1)
    if data.dtype == np.int16:
        x = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        x = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        x = (data.astype(np.float32) - 128.0) / 128.0
    else:
        x = np.asarray(data, dtype=np.float32)
    if rate != SR:
        g = gcd(int(rate), SR)
        x = resample_poly(x, SR // g, int(rate) // g).astype(np.float32)
    return x


def prepare_audio(audio):
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) > TARGET:
        audio = audio[:TARGET]
    elif len(audio) < TARGET:
        padded = np.zeros(TARGET, dtype=np.float32)
        padded[:len(audio)] = audio
        audio = padded
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak
    stft = tf.signal.stft(audio, frame_length=1024, frame_step=512, fft_length=1024)
    spec = tf.abs(stft)
    mel = tf.matmul(tf.square(spec), MEL_MATRIX)
    mel = tf.math.log(mel + 1e-6)
    mean = tf.reduce_mean(mel)
    std = tf.math.reduce_std(mel)
    mel = (mel - mean) / (std + 1e-6)
    return mel[..., tf.newaxis].numpy()


def main():
    class_names = json.load(open(MODEL_DIR / "class_names.json", encoding="utf-8"))
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    items = manifest["validation"]
    print(f"Classes: {len(class_names)} | validation clips in manifest: {len(items)}")

    model = tf.keras.models.load_model(MODEL_DIR / "best_candidate.keras", compile=False)

    feats, y_true, paths, failed = [], [], [], []
    for i, it in enumerate(items, 1):
        try:
            feats.append(prepare_audio(read_wav(it["path"])))
            y_true.append(int(it["label_index"]))
            paths.append(it["path"])
        except Exception as e:  # noqa: BLE001
            failed.append((it["path"], f"{type(e).__name__}: {e}"))
        if i % 100 == 0:
            print(f"  prepared {i}/{len(items)}")
    if not feats:
        sys.exit("No clips could be read. Check the paths in the manifest.")
    if failed:
        print(f"WARNING: {len(failed)} clips could not be read (first 3): {failed[:3]}")

    X = np.stack(feats)
    probs = np.concatenate([model.predict(X[i:i + 32], verbose=0) for i in range(0, len(X), 32)])
    if probs.shape[1] != len(class_names):
        sys.exit(f"Model outputs {probs.shape[1]} classes but class_names has {len(class_names)}")
    y_true = np.array(y_true)
    y_pred = probs.argmax(axis=1)
    conf = probs.max(axis=1)

    acc = float((y_pred == y_true).mean())
    macro = float(f1_score(y_true, y_pred, average="macro", labels=range(len(class_names)), zero_division=0))
    print("\n=== OVERALL (validation split, not untouched) ===")
    print(f"clips scored   : {len(y_true)}")
    print(f"accuracy       : {acc * 100:.2f}%")
    print(f"macro F1       : {macro * 100:.2f}%")
    top3 = float(np.mean([t in np.argsort(p)[-3:] for t, p in zip(y_true, probs)]))
    print(f"top-3 accuracy : {top3 * 100:.2f}%")

    print("\n=== CONFIDENCE vs CORRECTNESS ===")
    for lo, hi, label in [(CONF_LIMIT, 1.01, f">= {CONF_LIMIT:.2f}"), (0.40, CONF_LIMIT, f"0.40 - {CONF_LIMIT:.2f}"), (0.0, 0.40, "< 0.40")]:
        m = (conf >= lo) & (conf < hi)
        if m.any():
            print(f"top score {label:>10}: {int(m.sum()):4d} clips, {float((y_pred[m] == y_true[m]).mean()) * 100:5.1f}% correct")
        else:
            print(f"top score {label:>10}:    0 clips")

    cm = confusion_matrix(y_true, y_pred, labels=range(len(class_names)))
    recalls = [(class_names[c], cm[c, c] / cm[c].sum() if cm[c].sum() else float("nan"), int(cm[c].sum())) for c in range(len(class_names))]
    print("\n=== WEAKEST 12 CLASSES (recall) ===")
    for name, r, n in sorted((x for x in recalls if x[2] > 0), key=lambda x: x[1])[:12]:
        print(f"{name:40s} recall={r * 100:5.1f}%  clips={n}")

    pairs = Counter((int(t), int(p)) for t, p in zip(y_true, y_pred) if t != p)
    print("\n=== TOP 12 CONFUSIONS (true -> predicted) ===")
    for (t, p), n in pairs.most_common(12):
        print(f"{n:3d}x  {class_names[t]}  ->  {class_names[p]}")

    OUT_DIR.mkdir(exist_ok=True)
    np.savetxt(OUT_DIR / "confusion_matrix.csv", cm, fmt="%d", delimiter=",",
               header=",".join(class_names), comments="")
    with open(OUT_DIR / "per_clip_predictions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "true", "predicted", "confidence", "correct"])
        for pth, t, p, c in zip(paths, y_true, y_pred, conf):
            w.writerow([pth, class_names[t], class_names[p], f"{c:.4f}", int(t == p)])
    with open(OUT_DIR / "classification_report.txt", "w", encoding="utf-8") as f:
        f.write(classification_report(y_true, y_pred, labels=range(len(class_names)),
                                      target_names=class_names, zero_division=0))
    print(f"\nSaved confusion_matrix.csv, per_clip_predictions.csv, classification_report.txt in {OUT_DIR}")


if __name__ == "__main__":
    main()
