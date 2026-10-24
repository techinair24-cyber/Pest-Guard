import json
import random
import time
from pathlib import Path

import numpy as np
import tensorflow_hub as hub
import tensorflow as tf
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parent
AI = ROOT / "ai_model"
MANIFEST = AI / "combined_split_manifest.json"
OUT = AI / "yamnet_pilot"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 459
TRAIN_PER_CLASS = 20
VAL_PER_CLASS = 10
SAMPLE_RATE = 16000

random.seed(SEED)
np.random.seed(SEED)

def load_manifest():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return data["train"], data["validation"], data["classes"]

def sample_per_class(rows, limit):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["label_index"], []).append(row)
    selected = []
    for label_index in sorted(grouped):
        items = grouped[label_index]
        random.shuffle(items)
        selected.extend(items[:limit])
    random.shuffle(selected)
    return selected

def extract_embeddings(rows, yamnet):
    X, y = [], []
    total = len(rows)
    start = time.time()

    for i, row in enumerate(rows, 1):
        path = Path(row["path"])
        audio = np.load(path, allow_pickle=False).astype(np.float32, copy=False)

        if audio.ndim != 1 or audio.size != 80000:
            raise ValueError(f"Unexpected audio shape {audio.shape}: {path}")

        # YAMNet accepts mono float32 audio at 16 kHz.
        # Average frame embeddings to obtain one vector per 5-second segment.
        _, embeddings, _ = yamnet(audio)
        vector = tf.reduce_mean(embeddings, axis=0).numpy()

        X.append(vector)
        y.append(int(row["label_index"]))

        if i % 25 == 0 or i == total:
            elapsed = time.time() - start
            print(f"Embeddings: {i}/{total} | elapsed {elapsed:.1f}s", flush=True)

    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int64)

def main():
    train_rows, val_rows, classes = load_manifest()
    train_sample = sample_per_class(train_rows, TRAIN_PER_CLASS)
    val_sample = sample_per_class(val_rows, VAL_PER_CLASS)

    print("Classes:", len(classes))
    print("Pilot training segments:", len(train_sample))
    print("Pilot validation segments:", len(val_sample))
    print("Loading YAMNet...", flush=True)
    yamnet = hub.load("https://tfhub.dev/google/yamnet/1")

    print("\nExtracting training embeddings...", flush=True)
    X_train, y_train = extract_embeddings(train_sample, yamnet)
    print("\nExtracting validation embeddings...", flush=True)
    X_val, y_val = extract_embeddings(val_sample, yamnet)

    np.savez_compressed(
        OUT / "embeddings.npz",
        X_train=X_train, y_train=y_train,
        X_val=X_val, y_val=y_val
    )
    (OUT / "classes.json").write_text(
        json.dumps(classes, indent=2), encoding="utf-8"
    )

    print("\nTraining lightweight classifier...", flush=True)
    classifier = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=500,
            class_weight="balanced",
            random_state=SEED,
            solver="lbfgs"
        )
    )
    classifier.fit(X_train, y_train)
    pred = classifier.predict(X_val)

    result = {
        "method": "YAMNet mean embeddings + balanced logistic regression",
        "seed": SEED,
        "train_per_class_max": TRAIN_PER_CLASS,
        "validation_per_class_max": VAL_PER_CLASS,
        "train_segments": int(len(y_train)),
        "validation_segments": int(len(y_val)),
        "classes": len(classes),
        "accuracy": float(accuracy_score(y_val, pred)),
        "macro_f1": float(f1_score(y_val, pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_val, pred, average="weighted", zero_division=0)),
        "classification_report": classification_report(
            y_val, pred, labels=list(range(len(classes))),
            target_names=classes, output_dict=True, zero_division=0
        )
    }

    (OUT / "results.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print("\nPILOT RESULTS")
    print("Accuracy:", f"{result['accuracy'] * 100:.2f}%")
    print("Macro F1:", f"{result['macro_f1']:.4f}")
    print("Weighted F1:", f"{result['weighted_f1']:.4f}")
    print("Results saved to:", OUT / "results.json")
    print("Existing models were not modified.")

if __name__ == "__main__":
    main()
