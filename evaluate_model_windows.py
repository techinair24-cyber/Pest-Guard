"""Evaluate the active 47-class model on the manifest validation recordings,
using the SAME windowing and loading as train_pest_new_dataset.py:
  librosa.load(sr=16000, mono=True) -> consecutive non-overlapping 5 s windows,
  fragments < 1 s dropped, shorter windows zero-padded, features stored as float16.

Run from the project root:
    backend\\.venv311\\Scripts\\python.exe evaluate_model_windows.py

NOTE: validation data was used to pick the best checkpoint, so this is NOT an
untouched test set. It is the baseline to compare against the 70.39% training log.
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from math import gcd
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix, f1_score

try:
    import librosa
    HAVE_LIBROSA = True
except ImportError:
    HAVE_LIBROSA = False
    from scipy.io import wavfile
    from scipy.signal import resample_poly

ROOT = Path.cwd()
AI_DIR = ROOT / "backend" / "ai_model"
MODEL_DIR = AI_DIR / "pest_new_dataset_candidate"
MANIFEST = AI_DIR / "combined_split_manifest.json"
OUT_DIR = ROOT / "test_results"
SR = 16000
TARGET = SR * 5
CONF_LIMIT = 0.70

MEL_MATRIX = tf.signal.linear_to_mel_weight_matrix(
    num_mel_bins=128, num_spectrogram_bins=513, sample_rate=SR,
    lower_edge_hertz=50.0, upper_edge_hertz=8000.0)


def load_audio(path):
    if HAVE_LIBROSA:
        audio, _ = librosa.load(str(path), sr=SR, mono=True)
        return audio
    rate, data = wavfile.read(path)
    if data.ndim > 1:
        data = data.astype(np.float64).mean(axis=1)
    if data.dtype == np.int16:
        x = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        x = data.astype(np.float32) / 2147483648.0
    else:
        x = np.asarray(data, dtype=np.float32)
    if rate != SR:
        g = gcd(int(rate), SR)
        x = resample_poly(x, SR // g, int(rate) // g).astype(np.float32)
    return x


def make_feature(audio):
    audio = tf.convert_to_tensor(audio, dtype=tf.float32)
    peak = tf.reduce_max(tf.abs(audio))
    audio = tf.cond(peak > 0, lambda: audio / peak, lambda: audio)
    spec = tf.signal.stft(audio, frame_length=1024, frame_step=512, fft_length=1024)
    mel = tf.matmul(tf.square(tf.abs(spec)), MEL_MATRIX)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
    return mel[..., tf.newaxis].numpy().astype(np.float32)


def main():
    print("Audio loader:", "librosa (same as training)" if HAVE_LIBROSA else "scipy fallback (librosa not installed; small differences possible)")
    class_names = json.load(open(MODEL_DIR / "class_names.json", encoding="utf-8"))
    items = json.load(open(MANIFEST, encoding="utf-8"))["validation"]
    print(f"Classes: {len(class_names)} | validation recordings: {len(items)}")
    model = tf.keras.models.load_model(MODEL_DIR / "best_candidate.keras", compile=False)

    feats, y_true, rec_ids, win_paths = [], [], [], []
    failed = 0
    for i, it in enumerate(items, 1):
        try:
            audio = load_audio(it["path"])
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("Skipped unreadable:", Path(it["path"]).name, type(e).__name__)
            continue
        if audio.size == 0:
            failed += 1
            continue
        for start in range(0, len(audio), TARGET):
            clip = audio[start:start + TARGET]
            if len(clip) < SR:
                continue
            if len(clip) < TARGET:
                clip = np.pad(clip, (0, TARGET - len(clip)))
            f = make_feature(clip)
            if not np.all(np.isfinite(f)):
                continue
            feats.append(f.astype(np.float16))
            y_true.append(int(it["label_index"]))
            rec_ids.append(i)
            win_paths.append(it["path"])
        if i % 50 == 0 or i == len(items):
            print(f"  prepared {i}/{len(items)} recordings, {len(feats)} windows")
    if not feats:
        sys.exit("No windows produced. Check manifest paths.")
    print(f"Unreadable recordings: {failed}")

    X = np.stack(feats)
    probs = np.concatenate([model.predict(X[i:i + 32].astype(np.float32), verbose=0)
                            for i in range(0, len(X), 32)])
    if probs.shape[1] != len(class_names):
        sys.exit(f"Model has {probs.shape[1]} outputs but class_names has {len(class_names)}")
    y_true = np.array(y_true)
    y_pred = probs.argmax(axis=1)
    conf = probs.max(axis=1)
    labels = list(range(len(class_names)))

    acc = float((y_pred == y_true).mean())
    macro = float(f1_score(y_true, y_pred, average="macro", labels=labels, zero_division=0))
    top3 = float(np.mean([t in np.argsort(p)[-3:] for t, p in zip(y_true, probs)]))
    print("\n=== PER-WINDOW RESULTS (compare with 70.39% in training log) ===")
    print(f"windows scored : {len(y_true)}")
    print(f"accuracy       : {acc * 100:.2f}%")
    print(f"macro F1       : {macro * 100:.2f}%")
    print(f"top-3 accuracy : {top3 * 100:.2f}%")

    # Per-recording: average probabilities over the recording's windows
    by_rec = defaultdict(list)
    for idx, r in enumerate(rec_ids):
        by_rec[r].append(idx)
    rt, rp = [], []
    for r, idxs in by_rec.items():
        rt.append(y_true[idxs[0]])
        rp.append(int(probs[idxs].mean(axis=0).argmax()))
    rt, rp = np.array(rt), np.array(rp)
    print("\n=== PER-RECORDING RESULTS (mean of windows) ===")
    print(f"recordings     : {len(rt)}")
    print(f"accuracy       : {float((rt == rp).mean()) * 100:.2f}%")
    print(f"macro F1       : {float(f1_score(rt, rp, average='macro', labels=labels, zero_division=0)) * 100:.2f}%")

    print("\n=== TOP SCORE vs CORRECTNESS (per window) ===")
    for lo, hi, label in [(CONF_LIMIT, 1.01, f">= {CONF_LIMIT:.2f}"), (0.40, CONF_LIMIT, f"0.40 - {CONF_LIMIT:.2f}"), (0.0, 0.40, "< 0.40")]:
        m = (conf >= lo) & (conf < hi)
        if m.any():
            print(f"top score {label:>10}: {int(m.sum()):5d} windows, {float((y_pred[m] == y_true[m]).mean()) * 100:5.1f}% correct")
        else:
            print(f"top score {label:>10}:     0 windows")

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    rec = [(class_names[c], cm[c, c] / cm[c].sum(), int(cm[c].sum())) for c in labels if cm[c].sum() > 0]
    print("\n=== WEAKEST 12 CLASSES (per-window recall) ===")
    for name, r, n in sorted(rec, key=lambda x: x[1])[:12]:
        print(f"{name:40s} recall={r * 100:5.1f}%  windows={n}")
    pairs = Counter((int(t), int(p)) for t, p in zip(y_true, y_pred) if t != p)
    print("\n=== TOP 12 CONFUSIONS (true -> predicted) ===")
    for (t, p), n in pairs.most_common(12):
        print(f"{n:4d}x  {class_names[t]}  ->  {class_names[p]}")

    OUT_DIR.mkdir(exist_ok=True)
    np.savetxt(OUT_DIR / "confusion_matrix_windows.csv", cm, fmt="%d", delimiter=",",
               header=",".join(class_names), comments="")
    with open(OUT_DIR / "per_window_predictions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "true", "predicted", "confidence", "correct"])
        for pth, t, p, c in zip(win_paths, y_true, y_pred, conf):
            w.writerow([pth, class_names[t], class_names[p], f"{c:.4f}", int(t == p)])
    with open(OUT_DIR / "classification_report_windows.txt", "w", encoding="utf-8") as f:
        f.write(classification_report(y_true, y_pred, labels=labels, target_names=class_names, zero_division=0))
    print(f"\nSaved results in {OUT_DIR}")


if __name__ == "__main__":
    main()
