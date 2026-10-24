import csv
import io
import json
import random
import time
from math import gcd
from pathlib import Path
from urllib.request import urlopen

import joblib
import librosa
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
from scipy.io import wavfile
from scipy.signal import resample_poly
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, accuracy_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
AI_DIR = ROOT / "ai_model"
MANIFEST = AI_DIR / "combined_split_manifest.json"
BACKGROUND_DIR = (
    Path.home() / "Desktop" / "InsectSound1000_Training"
    / "ESC50_background_pilot"
)
OUT = AI_DIR / "yamnet_background_gate_pilot"
OUT.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 16000
TARGET_LENGTH = 80000
SEED = 459
INSECT_TRAIN_PER_CLASS = 5
INSECT_VAL_PER_CLASS = 2

random.seed(SEED)
np.random.seed(SEED)


def load_background_groups():
    metadata_url = (
        "https://raw.githubusercontent.com/"
        "karolpiczak/ESC-50/master/meta/esc50.csv"
    )

    with urlopen(metadata_url, timeout=45) as response:
        rows = list(
            csv.DictReader(
                io.StringIO(response.read().decode("utf-8"))
            )
        )

    filename_to_category = {
        row["filename"]: row["category"] for row in rows
    }

    groups = {}
    for path in BACKGROUND_DIR.glob("*.wav"):
        category = filename_to_category.get(path.name)
        if category:
            groups.setdefault(category, []).append(path)

    train_files = []
    validation_files = []

    rng = random.Random(SEED)

    for category, paths in sorted(groups.items()):
        paths = list(paths)
        rng.shuffle(paths)

        if len(paths) < 2:
            print(
                f"Skipping {category}: only {len(paths)} clip(s)"
            )
            continue

        # Use a held-out 20% from every background category, not one file only.
        split_index = max(1, min(len(paths) - 1, int(round(len(paths) * 0.8))))
        train_files.extend(paths[:split_index])
        validation_files.extend(paths[split_index:])

    if not train_files or not validation_files:
        raise RuntimeError(
            "No suitable background files found. Check "
            f"{BACKGROUND_DIR} and ESC-50 metadata access."
        )

    return train_files, validation_files


def sample_per_class(rows, limit):
    grouped = {}

    for row in rows:
        grouped.setdefault(int(row["label_index"]), []).append(row)

    rng = random.Random(SEED)
    selected = []

    for label in sorted(grouped):
        items = list(grouped[label])
        rng.shuffle(items)
        selected.extend(items[:limit])

    return selected


def prepare_waveform(audio, source_rate):
    audio = np.asarray(audio)

    if audio.ndim == 2:
        audio = audio.astype(np.float32).mean(axis=1)
    elif audio.ndim != 1:
        raise ValueError(f"Unexpected audio dimensions: {audio.shape}")

    if np.issubdtype(audio.dtype, np.integer):
        info = np.iinfo(audio.dtype)

        if info.min < 0:
            scale = float(max(abs(info.min), info.max))
            audio = audio.astype(np.float32) / scale
        else:
            midpoint = (float(info.max) + 1.0) / 2.0
            audio = (audio.astype(np.float32) - midpoint) / midpoint
    else:
        audio = audio.astype(np.float32)

    if source_rate != SAMPLE_RATE:
        factor = gcd(int(source_rate), SAMPLE_RATE)
        audio = resample_poly(
            audio,
            SAMPLE_RATE // factor,
            int(source_rate) // factor
        ).astype(np.float32)

    audio = np.nan_to_num(audio, copy=False)

    if len(audio) < TARGET_LENGTH:
        padded = np.zeros(TARGET_LENGTH, dtype=np.float32)
        padded[:len(audio)] = audio
        audio = padded
    else:
        audio = audio[:TARGET_LENGTH]

    # Match the existing backend's peak-normalized audio input.
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak

    return audio.astype(np.float32)


def load_insect_audio(row):
    # Existing manifest entries are source WAV files, not prepared .npy arrays.
    # Load/resample them the same way as training, then make a five-second clip.
    audio, _ = librosa.load(
        str(Path(row["path"])),
        sr=SAMPLE_RATE,
        mono=True,
    )
    return prepare_waveform(audio, SAMPLE_RATE)

def load_background_audio(path):
    rate, audio = wavfile.read(path)
    return prepare_waveform(audio, rate)


def extract_embeddings(items, yamnet, label, loader):
    vectors = []
    labels = []

    for index, item in enumerate(items, 1):
        waveform = loader(item)

        _, embeddings, _ = yamnet(waveform)
        vector = tf.reduce_mean(embeddings, axis=0).numpy()

        vectors.append(vector)
        labels.append(label)

        if index % 25 == 0 or index == len(items):
            print(
                f"Embeddings label={label}: "
                f"{index}/{len(items)}",
                flush=True
            )

    return (
        np.asarray(vectors, dtype=np.float32),
        np.asarray(labels, dtype=np.int64)
    )


def main():
    if not MANIFEST.exists():
        raise FileNotFoundError(MANIFEST)

    if not BACKGROUND_DIR.exists():
        raise FileNotFoundError(BACKGROUND_DIR)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    train_rows = sample_per_class(
        manifest["train"], INSECT_TRAIN_PER_CLASS
    )
    val_rows = sample_per_class(
        manifest["validation"], INSECT_VAL_PER_CLASS
    )

    bg_train, bg_val = load_background_groups()

    print("Insect training clips:", len(train_rows))
    print("Insect validation clips:", len(val_rows))
    print("Background training clips:", len(bg_train))
    print("Background validation clips:", len(bg_val))
    print("Loading YAMNet...", flush=True)

    yamnet = hub.load("https://tfhub.dev/google/yamnet/1")

    print("\nExtracting insect training features...", flush=True)
    X_it, y_it = extract_embeddings(
        train_rows, yamnet, 1, load_insect_audio
    )

    print("\nExtracting background training features...", flush=True)
    X_bt, y_bt = extract_embeddings(
        bg_train, yamnet, 0, load_background_audio
    )

    print("\nExtracting insect validation features...", flush=True)
    X_iv, y_iv = extract_embeddings(
        val_rows, yamnet, 1, load_insect_audio
    )

    print("\nExtracting background validation features...", flush=True)
    X_bv, y_bv = extract_embeddings(
        bg_val, yamnet, 0, load_background_audio
    )

    X_train = np.concatenate([X_it, X_bt])
    y_train = np.concatenate([y_it, y_bt])
    X_val = np.concatenate([X_iv, X_bv])
    y_val = np.concatenate([y_iv, y_bv])

    rng = np.random.default_rng(SEED)
    train_order = rng.permutation(len(y_train))
    val_order = rng.permutation(len(y_val))

    X_train, y_train = X_train[train_order], y_train[train_order]
    X_val, y_val = X_val[val_order], y_val[val_order]

    print("\nTraining separate binary gate...", flush=True)

    gate = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            random_state=SEED
        )
    )
    gate.fit(X_train, y_train)

    probabilities = gate.predict_proba(X_val)[:, 1]
    predictions = (probabilities >= 0.5).astype(np.int64)

    threshold_sweep = []

    for threshold in (0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
        trial = (probabilities >= threshold).astype(np.int64)
        tn_t, fp_t, fn_t, tp_t = confusion_matrix(
            y_val, trial, labels=[0, 1]
        ).ravel()

        threshold_sweep.append({
            "threshold": threshold,
            "background_rejection_rate": float(tn_t / (tn_t + fp_t)),
            "background_false_accept_rate": float(fp_t / (tn_t + fp_t)),
            "insect_acceptance_rate": float(tp_t / (tp_t + fn_t)),
            "insect_false_rejection_rate": float(fn_t / (tp_t + fn_t)),
        })

    print("\nTHRESHOLD COMPARISON")
    print(json.dumps(threshold_sweep, indent=2))

    # Labels: 0 = background, 1 = insect sound.
    tn, fp, fn, tp = confusion_matrix(
        y_val, predictions, labels=[0, 1]
    ).ravel()

    background_count = int(tn + fp)
    insect_count = int(tp + fn)

    results = {
        "model": "YAMNet embeddings + binary logistic regression",
        "purpose": "Experimental background sound rejection",
        "seed": SEED,
        "threshold": 0.5,
        "insect_training_clips": int(len(y_it)),
        "background_training_clips": int(len(y_bt)),
        "insect_validation_clips": int(insect_count),
        "background_validation_clips": int(background_count),
        "validation_accuracy": float(
            accuracy_score(y_val, predictions)
        ),
        "background_rejection_rate": (
            float(tn / background_count) if background_count else None
        ),
        "background_false_accept_rate": (
            float(fp / background_count) if background_count else None
        ),
        "insect_acceptance_rate": (
            float(tp / insect_count) if insect_count else None
        ),
        "insect_false_rejection_rate": (
            float(fn / insect_count) if insect_count else None
        ),
        "confusion_matrix": {
            "background_correctly_rejected": int(tn),
            "background_mistaken_for_insect": int(fp),
            "insect_mistaken_for_background": int(fn),
            "insect_correctly_accepted": int(tp),
        },
        "note": (
            "Experimental pilot. ESC-50 sounds are a limited proxy and do not represent all field environments. "
            "and do not represent all real farm environments. "
            "Not approved for production deployment."
        )
    }

    joblib.dump(gate, OUT / "background_gate.joblib")
    (OUT / "results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )

    print("\n--- BACKGROUND GATE PILOT RESULTS ---")
    print(json.dumps(results, indent=2))
    print("\nSaved experimental gate to:", OUT)
    print("Production model and backend were not modified.")


if __name__ == "__main__":
    main()
