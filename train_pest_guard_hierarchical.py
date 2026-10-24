"""Train a lightweight four-group hierarchical classifier for Pest Guard.

Place this file at backend/tools/train_pest_guard_hierarchical.py and run it
inside the project's existing Python environment. It does not overwrite the
production .keras model or modify backend/main.py.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import soundfile as sf
import tensorflow as tf
from scipy.signal import resample_poly
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, top_k_accuracy_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "backend" / "ai_model" / "pest_new_dataset_candidate"
MODEL_PATH = MODEL_DIR / "best_candidate.keras"
MANIFEST_PATH = MODEL_DIR / "split_manifest.json"
LABELS_PATH = MODEL_DIR / "class_names.json"
OUTPUT_PATH = MODEL_DIR / "hierarchical_audio_classifier.joblib"
DATASET_ROOT = Path.home() / "Desktop" / "Pest_Guard_New_Datasets"

SAMPLE_RATE = 16_000
AUDIO_SAMPLES = 80_000
FRAME_LENGTH = 1_024
FRAME_STEP = 512
FFT_LENGTH = 1_024
MEL_BINS = 128
LOWER_HZ = 50.0
UPPER_HZ = 8_000.0
BATCH_SIZE = 12

# Taxonomic group assignment using the genus of each scientific label.
GENUS_GROUP = {
    # True crickets / tree crickets
    "Acheta": "true_crickets",
    "Gryllus": "true_crickets",
    "Melanogryllus": "true_crickets",
    "Nemobius": "true_crickets",
    "Oecanthus": "true_crickets",
    # Bush-crickets / katydids
    "Barbitistes": "bush_crickets_katydids",
    "Conocephalus": "bush_crickets_katydids",
    "Decticus": "bush_crickets_katydids",
    "Ephippiger": "bush_crickets_katydids",
    "Eupholidoptera": "bush_crickets_katydids",
    "Gampsocleis": "bush_crickets_katydids",
    "Leptophyes": "bush_crickets_katydids",
    "Metrioptera": "bush_crickets_katydids",
    "Phaneroptera": "bush_crickets_katydids",
    "Pholidoptera": "bush_crickets_katydids",
    "Platycleis": "bush_crickets_katydids",
    "Roeseliana": "bush_crickets_katydids",
    "Tettigonia": "bush_crickets_katydids",
    "Tylopsis": "bush_crickets_katydids",
    # Grasshoppers
    "Chorthippus": "grasshoppers",
    "Chrysochraon": "grasshoppers",
    "Gomphocerippus": "grasshoppers",
    "Gomphocerus": "grasshoppers",
    "Myrmeleotettix": "grasshoppers",
    "Omocestus": "grasshoppers",
    "Pseudochorthippus": "grasshoppers",
    "Stenobothrus": "grasshoppers",
    # Cicadas
    "Platypleura": "cicadas",
}


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_labels(data: Any) -> list[str]:
    if isinstance(data, list):
        labels = [str(x) for x in data]
    elif isinstance(data, dict):
        for key in ("class_names", "labels", "classes"):
            if isinstance(data.get(key), list):
                labels = [str(x) for x in data[key]]
                break
        else:
            if data and all(str(k).isdigit() for k in data):
                labels = [str(data[k] if k in data else data[str(k)]) for k in range(len(data))]
            else:
                raise ValueError("Unrecognized class_names.json format")
    else:
        raise ValueError("Unrecognized class_names.json format")
    if not labels or len(set(labels)) != len(labels):
        raise ValueError("Class labels are empty or contain duplicates")
    return labels


def normalize_manifest(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = None
        for key in ("records", "items", "samples", "manifest"):
            if isinstance(data.get(key), list):
                records = data[key]
                break
        if records is None:
            raise ValueError("Unrecognized split_manifest.json format")
    else:
        raise ValueError("Unrecognized split_manifest.json format")
    if not records:
        raise ValueError("Split manifest contains no records")
    return records


def resolve_audio_path(value: str) -> Path:
    raw = Path(value)
    candidates = [raw]
    if not raw.is_absolute():
        candidates.extend([ROOT / raw, DATASET_ROOT / raw, DATASET_ROOT / raw.name])
    # Manifests sometimes include the dataset-folder name inside relative paths.
    if not raw.is_absolute() and raw.parts:
        if raw.parts[0].lower() == DATASET_ROOT.name.lower() and len(raw.parts) > 1:
            candidates.append(DATASET_ROOT.joinpath(*raw.parts[1:]))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Last-resort filename lookup, used only when manifest paths differ by folder prefix.
    matches = list(DATASET_ROOT.rglob(raw.name)) if DATASET_ROOT.is_dir() else []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise FileNotFoundError(f"Ambiguous audio filename {raw.name!r}; manifest path did not resolve")
    raise FileNotFoundError(f"Audio file not found: {value}")


def group_for_label(label: str) -> str:
    genus = label.strip().split()[0]
    if genus not in GENUS_GROUP:
        raise ValueError(f"No taxonomic group assigned for label: {label}")
    return GENUS_GROUP[genus]


def audio_to_model_input(path: Path, mel_matrix: tf.Tensor) -> np.ndarray:
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)
    audio = np.mean(audio, axis=1, dtype=np.float32)
    if audio.size == 0:
        raise ValueError(f"Empty audio file: {path}")
    if sr != SAMPLE_RATE:
        # Reduce the ratio first to keep resampling efficient.
        import math
        divisor = math.gcd(int(sr), SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor, int(sr) // divisor).astype(np.float32)
    if len(audio) > AUDIO_SAMPLES:
        audio = audio[:AUDIO_SAMPLES]
    elif len(audio) < AUDIO_SAMPLES:
        audio = np.pad(audio, (0, AUDIO_SAMPLES - len(audio))).astype(np.float32)

    peak = float(np.max(np.abs(audio)))
    if peak > 1e-8:
        audio = audio / peak

    waveform = tf.convert_to_tensor(audio, dtype=tf.float32)
    stft = tf.signal.stft(
        waveform,
        frame_length=FRAME_LENGTH,
        frame_step=FRAME_STEP,
        fft_length=FFT_LENGTH,
        pad_end=False,
    )
    power = tf.square(tf.abs(stft))
    mel_power = tf.matmul(power, mel_matrix)
    log_mel = tf.math.log(mel_power + 1e-6)
    mean = tf.reduce_mean(log_mel)
    std = tf.math.reduce_std(log_mel)
    normalized = (log_mel - mean) / tf.maximum(std, 1e-6)
    result = normalized.numpy().astype(np.float32)
    expected = (155, MEL_BINS)
    if result.shape != expected:
        raise ValueError(f"Unexpected feature shape {result.shape} for {path}; expected {expected}")
    return result[..., np.newaxis]


def choose_embedding_tensor(model: tf.keras.Model, num_classes: int):
    # Choose the nearest previous vector layer, avoiding the 47-class output.
    for layer in reversed(model.layers[:-1]):
        try:
            shape = tuple(layer.output.shape)
        except Exception:
            continue
        if len(shape) == 2 and shape[-1] is not None and int(shape[-1]) != num_classes:
            return layer.output, layer.name, int(shape[-1])
    raise RuntimeError(
        "Could not find a feature-vector layer before the species output. "
        "No model files were changed."
    )


def main() -> int:
    for p in (MODEL_PATH, MANIFEST_PATH, LABELS_PATH):
        if not p.is_file():
            raise FileNotFoundError(f"Required project file missing: {p}")

    labels = normalize_labels(load_json(LABELS_PATH))
    raw_records = normalize_manifest(load_json(MANIFEST_PATH))
    label_to_index = {name: i for i, name in enumerate(labels)}

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in raw_records:
        try:
            name = str(row.get("scientific_name", "")).strip()
            idx_value = row.get("class_index")
            idx = int(idx_value) if idx_value is not None else label_to_index[name]
            if not (0 <= idx < len(labels)):
                raise ValueError(f"Class index out of range: {idx}")
            if name and name != labels[idx]:
                # Class index is authoritative for this project; still stop on a mismatch.
                raise ValueError(f"Label/index mismatch: manifest {name!r}, index {idx} -> {labels[idx]!r}")
            if not name:
                name = labels[idx]
            group = group_for_label(labels[idx])
            path_value = row.get("file") or row.get("path") or row.get("filepath")
            if not path_value:
                raise ValueError("Record is missing file/path")
            audio_path = resolve_audio_path(str(path_value))
            split = str(row.get("split", "train")).lower()
            records.append({"path": audio_path, "y": idx, "group": group, "split": split, "label": labels[idx]})
        except Exception as exc:
            errors.append(f"{row.get('file', row.get('path', '<no path>'))}: {exc}")
    if errors:
        preview = "\n".join(errors[:10])
        raise RuntimeError(
            f"Could not prepare {len(errors)} manifest records. No production files were changed.\n{preview}"
        )

    train_records = [r for r in records if r["split"].startswith("train")]
    val_records = [r for r in records if r["split"].startswith(("val", "valid", "test"))]
    if not train_records or not val_records:
        raise ValueError("Manifest must contain both training and validation/test records")
    if len({r["y"] for r in train_records}) != len(labels):
        missing = sorted(set(range(len(labels))) - {r["y"] for r in train_records})
        raise ValueError(f"Some classes have no training recordings: {[labels[i] for i in missing]}")

    # Check that all declared labels have a group before doing model inference.
    groups_by_class = [group_for_label(name) for name in labels]
    unique_groups = sorted(set(groups_by_class))
    print(f"Classes: {len(labels)} | Groups: {len(unique_groups)} | Train: {len(train_records)} | Validation/test: {len(val_records)}")
    print("Group counts:")
    for group in unique_groups:
        class_count = sum(g == group for g in groups_by_class)
        rec_count = sum(r["group"] == group for r in train_records)
        print(f"  {group}: {class_count} species, {rec_count} training recordings")

    model = tf.keras.models.load_model(MODEL_PATH, compile=False)
    if tuple(model.input_shape[1:]) != (155, 128, 1):
        raise ValueError(f"Unexpected model input shape: {model.input_shape}")
    if int(model.output_shape[-1]) != len(labels):
        raise ValueError(f"Model has {model.output_shape[-1]} outputs but class_names has {len(labels)} labels")
    feature_tensor, feature_layer_name, feature_dim = choose_embedding_tensor(model, len(labels))
    combined = tf.keras.Model(inputs=model.inputs, outputs=[feature_tensor, model.output])
    mel_matrix = tf.signal.linear_to_mel_weight_matrix(
        num_mel_bins=MEL_BINS,
        num_spectrogram_bins=FFT_LENGTH // 2 + 1,
        sample_rate=SAMPLE_RATE,
        lower_edge_hertz=LOWER_HZ,
        upper_edge_hertz=UPPER_HZ,
        dtype=tf.float32,
    )
    print(f"Using feature layer: {feature_layer_name} ({feature_dim} features)")
    print("Extracting learned audio features from the existing model. This may take a few minutes...")

    all_features: list[np.ndarray] = []
    all_probs: list[np.ndarray] = []
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start : start + BATCH_SIZE]
        xs = np.stack([audio_to_model_input(r["path"], mel_matrix) for r in batch], axis=0)
        features, probs = combined.predict(xs, batch_size=len(batch), verbose=0)
        features = np.asarray(features, dtype=np.float32)
        if features.ndim > 2:
            features = features.reshape(features.shape[0], -1)
        all_features.extend(list(features))
        all_probs.extend(list(np.asarray(probs, dtype=np.float32)))
        done = min(start + len(batch), len(records))
        if done % 100 < BATCH_SIZE or done == len(records):
            print(f"  Extracted {done}/{len(records)} recordings")

    feature_by_path = {str(r["path"]): (all_features[i], all_probs[i]) for i, r in enumerate(records)}
    def collect(subset):
        items = [feature_by_path[str(r["path"])] for r in subset]
        return np.stack([x[0] for x in items]), np.stack([x[1] for x in items]), np.asarray([r["y"] for r in subset], dtype=int), [r["group"] for r in subset]

    X_train, base_train_probs, y_train, group_train = collect(train_records)
    X_val, base_val_probs, y_val, group_val = collect(val_records)

    group_train_ids = np.asarray([unique_groups.index(g) for g in group_train], dtype=int)
    group_val_ids = np.asarray([unique_groups.index(g) for g in group_val], dtype=int)
    group_model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=3000, class_weight="balanced", random_state=24),
    )
    group_model.fit(X_train, group_train_ids)
    group_classes = group_model[-1].classes_
    group_probs = group_model.predict_proba(X_val)

    experts: dict[str, Any] = {}
    for group in unique_groups:
        mask = np.asarray([g == group for g in group_train], dtype=bool)
        class_ids = np.unique(y_train[mask])
        if len(class_ids) < 2:
            raise ValueError(f"Group {group} needs at least two represented species")
        expert = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=3000, class_weight="balanced", random_state=24),
        )
        expert.fit(X_train[mask], y_train[mask])
        experts[group] = expert

    # Joint class probabilities = P(group | sound) * P(species | group, sound).
    hierarchical_probs = np.zeros((len(y_val), len(labels)), dtype=np.float64)
    group_column = {int(group_id): i for i, group_id in enumerate(group_classes)}
    # Build group probability columns explicitly by mapping estimator's class IDs.
    for group in unique_groups:
        group_id = unique_groups.index(group)
        if group_id not in group_column:
            continue
        pg = group_probs[:, group_column[group_id]]
        expert = experts[group]
        specialist_probs = expert.predict_proba(X_val)
        specialist_classes = expert[-1].classes_
        hierarchical_probs[:, specialist_classes.astype(int)] = (
            hierarchical_probs[:, specialist_classes.astype(int)] + (pg[:, None] * specialist_probs)
        )

    hierarchical_pred = np.argmax(hierarchical_probs, axis=1)
    baseline_pred = np.argmax(base_val_probs, axis=1)
    class_ids = np.arange(len(labels))
    baseline_top3 = top_k_accuracy_score(y_val, base_val_probs, k=3, labels=class_ids)
    hier_top3 = top_k_accuracy_score(y_val, hierarchical_probs, k=3, labels=class_ids)

    baseline_acc = accuracy_score(y_val, baseline_pred)
    baseline_f1 = f1_score(y_val, baseline_pred, average="macro", zero_division=0)
    hier_acc = accuracy_score(y_val, hierarchical_pred)
    hier_f1 = f1_score(y_val, hierarchical_pred, average="macro", zero_division=0)

    print("\nSAME-SPLIT COMPARISON")
    print(f"Recordings: {len(y_val)}")
    print(f"Existing model accuracy:       {baseline_acc * 100:.2f}%")
    print(f"Hierarchical accuracy:         {hier_acc * 100:.2f}% ({(hier_acc - baseline_acc) * 100:+.2f} pp)")
    print(f"Existing model macro F1:       {baseline_f1 * 100:.2f}%")
    print(f"Hierarchical macro F1:         {hier_f1 * 100:.2f}% ({(hier_f1 - baseline_f1) * 100:+.2f} pp)")
    print(f"Existing model top-3 accuracy: {baseline_top3 * 100:.2f}%")
    print(f"Hierarchical top-3 accuracy:   {hier_top3 * 100:.2f}% ({(hier_top3 - baseline_top3) * 100:+.2f} pp)")

    bundle = {
        "version": 1,
        "labels": labels,
        "groups": unique_groups,
        "group_by_label": groups_by_class,
        "group_model": group_model,
        "experts": experts,
        "feature_layer_name": feature_layer_name,
        "feature_dim": feature_dim,
        "source_model_name": MODEL_PATH.name,
        "validation_metrics": {
            "recordings": int(len(y_val)),
            "baseline_accuracy": float(baseline_acc),
            "hierarchical_accuracy": float(hier_acc),
            "baseline_macro_f1": float(baseline_f1),
            "hierarchical_macro_f1": float(hier_f1),
            "baseline_top3_accuracy": float(baseline_top3),
            "hierarchical_top3_accuracy": float(hier_top3),
        },
    }
    joblib.dump(bundle, OUTPUT_PATH)
    print(f"\nSaved experimental classifier: {OUTPUT_PATH}")
    print("The production Keras model and backend code were not changed.")
    if hier_acc > baseline_acc and hier_f1 >= baseline_f1:
        print("RESULT: Hierarchical classifier improved accuracy and did not reduce macro F1. Ready for backend integration review.")
    else:
        print("RESULT: Do not deploy yet; this grouping did not improve both accuracy and macro F1 on this split.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
