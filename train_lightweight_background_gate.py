"""Train a lightweight (no YAMNet/TensorFlow-Hub) Pest Guard sound gate.

Run from the Pest guard project root:
    python .\\train_lightweight_background_gate.py

Reads an explicitly supplied, verified eight-group split manifest and
downloaded ESC-50 background WAVs. Writes only to a new output directory.
Does not edit backend/main.py, the active insect model, or ESP32 firmware.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import joblib
import librosa
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix

SAMPLE_RATE = 16000
TARGET_SAMPLES = 5 * SAMPLE_RATE
SEED = 459
GROUP_LABELS = (
    "Beetles",
    "Cicada",
    "Crickets",
    "Flies",
    "Grasshopper",
    "Katydid",
    "Mole Crickets",
    "Termite",
)
SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav", ".flac", ".ogg", ".aiff", ".aif", ".mp3",
    ".m4a", ".mp4", ".aac", ".wma",
}
BACKGROUND_DIR = Path.home() / "Desktop" / "InsectSound1000_Training" / "ESC50_background_pilot"
METADATA_URL = "https://raw.githubusercontent.com/karolpiczak/ESC-50/master/meta/esc50.csv"


def project_root() -> Path:
    root = Path.cwd().resolve()
    if (root / "backend" / "main.py").is_file():
        return root
    raise RuntimeError("Run this script from the Pest guard project root (the folder containing backend\\main.py).")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as audio_file:
        for chunk in iter(lambda: audio_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path, dataset_root: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required manifest missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Split manifest must be the versioned eight-group JSON manifest "
            "with recording provenance; CSV and legacy 47-class manifests "
            "are not accepted."
        ) from exc
    if not isinstance(data, dict) or data.get("format_version") != 1:
        raise ValueError(
            "Unsupported split manifest format; expected versioned eight-group JSON."
        )
    if Path(data.get("dataset_root", "")).resolve() != dataset_root.resolve():
        raise ValueError("Split manifest dataset_root does not match --dataset.")
    if data.get("group_labels") != list(GROUP_LABELS):
        raise ValueError("Split manifest group labels do not match the approved eight groups.")

    expected_subclasses = {
        group: sorted(
            child.name
            for child in (dataset_root / group).iterdir()
            if child.is_dir()
        )
        for group in GROUP_LABELS
    }
    if data.get("subclass_labels") != expected_subclasses:
        raise ValueError("Split manifest subclass labels do not match the dataset folders.")

    expected_paths = {
        path.relative_to(dataset_root).as_posix()
        for group in GROUP_LABELS
        for path in (dataset_root / group).rglob("*")
        if path.is_file() and path.suffix.casefold() in SUPPORTED_AUDIO_EXTENSIONS
    }
    rows = data.get("recordings")
    if not isinstance(rows, list) or len(rows) != len(expected_paths):
        raise ValueError("Split manifest recording count does not match the dataset.")

    seen_paths: set[str] = set()
    component_splits: dict[str, set[str]] = defaultdict(set)
    hash_splits: dict[str, set[str]] = defaultdict(set)
    source_splits: dict[str, set[str]] = defaultdict(set)
    train: list[dict] = []
    validation: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Split manifest contains an invalid recording row.")
        relative = Path(str(row.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 1:
            raise ValueError("Split manifest contains a path outside the dataset.")
        relative_text = relative.as_posix()
        if relative_text in seen_paths or relative_text not in expected_paths:
            raise ValueError(f"Split manifest path is duplicated or absent from the dataset: {relative_text}")
        seen_paths.add(relative_text)
        audio_path = dataset_root / relative
        group = row.get("group")
        expected_group = relative.parts[0]
        expected_subclass = relative.parts[1] if len(relative.parts) > 2 else None
        if group != expected_group or group not in GROUP_LABELS:
            raise ValueError(f"Split manifest group does not match its path: {relative_text}")
        if row.get("subtype") != expected_subclass:
            raise ValueError(f"Split manifest subclass does not match its path: {relative_text}")
        if row.get("sha256") != sha256_file(audio_path):
            raise ValueError(f"Dataset content differs from the split manifest: {relative_text}")
        component_id = row.get("component_id")
        split = row.get("split")
        if not isinstance(component_id, str) or not component_id or split not in {
            "train", "validation", "test", "excluded_group_label_conflict"
        }:
            raise ValueError(f"Invalid component or split assignment: {relative_text}")
        component_splits[component_id].add(split)
        content_hash = str(row["sha256"]).lower()
        hash_splits[content_hash].add(split)
        source_ids = row.get("source_ids")
        if not isinstance(source_ids, list) or any(not isinstance(value, str) for value in source_ids):
            raise ValueError(f"Invalid source recording IDs: {relative_text}")
        for source_id in source_ids:
            source_splits[source_id].add(split)
        if split in ("train", "validation"):
            selected = {
                "path": str(audio_path),
                "label_index": GROUP_LABELS.index(group),
            }
            (train if split == "train" else validation).append(selected)

    if seen_paths != expected_paths:
        raise ValueError("Split manifest does not cover every supported dataset recording.")
    if any(len(splits) != 1 for splits in component_splits.values()):
        raise ValueError("A source component crosses splits in the manifest.")
    if any(len(splits) != 1 for splits in hash_splits.values()):
        raise ValueError("An exact duplicate hash crosses splits in the manifest.")
    if any(len(splits) != 1 for splits in source_splits.values()):
        raise ValueError("A source recording ID crosses splits in the manifest.")
    return {
        "train": train,
        "validation": validation,
        "manifest_sha256": sha256_file(path),
        "dataset_root": str(dataset_root.resolve()),
    }


def sample_per_class(rows: list[dict], limit: int) -> list[dict]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        label = row.get("label_index")
        if path and label is not None:
            grouped[int(label)].append(row)
    rng = random.Random(SEED)
    selected: list[dict] = []
    for label in sorted(grouped):
        items = list(grouped[label])
        rng.shuffle(items)
        selected.extend(items[:limit])
    return selected


def background_splits(folder: Path) -> tuple[list[Path], list[Path]]:
    if not folder.is_dir():
        raise FileNotFoundError(f"Background WAV folder missing: {folder}")
    files = sorted(folder.glob("*.wav"))
    if len(files) < 50:
        raise RuntimeError(f"Only {len(files)} background WAV files found; expected the 300 downloaded files.")
    try:
        request = urllib.request.Request(METADATA_URL, headers={"User-Agent": "PestGuard-LightGate/1.0"})
        with urllib.request.urlopen(request, timeout=25) as response:
            rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8"))))
        filename_to_category = {r["filename"]: r["category"] for r in rows if r.get("filename") and r.get("category")}
    except Exception as exc:
        raise RuntimeError(f"Could not load ESC-50 category metadata to create a stratified holdout: {exc}") from exc

    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        category = filename_to_category.get(path.name)
        if category and category not in {"insects", "crickets"}:
            grouped[category].append(path)
    train: list[Path] = []
    validation: list[Path] = []
    rng = random.Random(SEED)
    for category, paths in sorted(grouped.items()):
        paths = list(paths)
        rng.shuffle(paths)
        if len(paths) < 5:
            continue
        val_count = max(1, round(len(paths) * 0.20))
        validation.extend(paths[-val_count:])
        train.extend(paths[:-val_count])
    if len(train) < 100 or len(validation) < 20:
        raise RuntimeError(f"Background split too small ({len(train)} train, {len(validation)} validation).")
    return train, validation


def load_5s(path: Path) -> np.ndarray:
    audio, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0 or not np.all(np.isfinite(audio)):
        raise ValueError(f"Empty or invalid audio: {path}")
    if audio.size < TARGET_SAMPLES:
        padded = np.zeros(TARGET_SAMPLES, dtype=np.float32)
        padded[:audio.size] = audio
        audio = padded
    else:
        audio = audio[:TARGET_SAMPLES]
    return audio


def features(audio: np.ndarray) -> np.ndarray:
    """Small deterministic spectral features; deliberately does not peak-normalize.

    Retaining raw RMS/peak helps the gate recognize near-silent input; normalized
    spectral descriptors describe sound shape independently of loudness.
    """
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if x.size < TARGET_SAMPLES:
        tmp = np.zeros(TARGET_SAMPLES, np.float32)
        tmp[:x.size] = x
        x = tmp
    else:
        x = x[:TARGET_SAMPLES]
    x = x - float(np.mean(x, dtype=np.float64))
    eps = 1e-12
    raw_rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64)) + eps))
    raw_peak = float(np.max(np.abs(x)) + eps)
    frame_len = 1024
    hop = 512
    frames = np.lib.stride_tricks.sliding_window_view(x, frame_len)[::hop]
    window = np.hanning(frame_len).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames * window[None, :], axis=1)).astype(np.float64)
    power = spec * spec + eps
    freqs = np.fft.rfftfreq(frame_len, d=1.0 / SAMPLE_RATE)
    frame_sum = np.sum(power, axis=1) + eps
    norm_power = power / frame_sum[:, None]

    values: list[float] = [np.log10(raw_rms + eps), np.log10(raw_peak + eps), float(np.std(x))]
    rms_frames = np.sqrt(np.mean(np.square(frames.astype(np.float64)), axis=1) + eps)
    values.extend([float(np.mean(rms_frames)), float(np.std(rms_frames)), float(np.percentile(rms_frames, 90))])

    # Relative energy in frequency bands (texture), plus log absolute band energy.
    edges = [0, 125, 250, 500, 1000, 2000, 3000, 4000, 6000, 8000]
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (freqs >= lo) & (freqs < hi if hi < 8000 else freqs <= hi)
        band = np.sum(power[:, mask], axis=1) if np.any(mask) else np.zeros(len(power))
        band_fraction = band / frame_sum
        values.extend([float(np.mean(band_fraction)), float(np.std(band_fraction)), float(np.log10(np.mean(band) + eps))])

    centroid = np.sum(norm_power * freqs[None, :], axis=1)
    bandwidth = np.sqrt(np.sum(norm_power * (freqs[None, :] - centroid[:, None]) ** 2, axis=1))
    cdf = np.cumsum(norm_power, axis=1)
    roll_idx = np.argmax(cdf >= 0.85, axis=1)
    rolloff = freqs[roll_idx]
    flatness = np.exp(np.mean(np.log(power), axis=1)) / (np.mean(power, axis=1) + eps)
    entropy = -np.sum(norm_power * np.log(norm_power + eps), axis=1)
    peakiness = np.max(power, axis=1) / (np.mean(power, axis=1) + eps)
    dominant_freq = freqs[np.argmax(power, axis=1)]
    for descriptor in (centroid, bandwidth, rolloff, flatness, entropy, peakiness, dominant_freq):
        values.extend([float(np.mean(descriptor)), float(np.std(descriptor)), float(np.percentile(descriptor, 90))])

    zcr = np.mean((frames[:, 1:] * frames[:, :-1]) < 0, axis=1)
    values.extend([float(np.mean(zcr)), float(np.std(zcr))])
    # Spectral flux on unit-normalized spectra.
    if norm_power.shape[0] > 1:
        flux = np.sqrt(np.mean(np.square(np.diff(norm_power, axis=0)), axis=1))
        values.extend([float(np.mean(flux)), float(np.std(flux)), float(np.percentile(flux, 90))])
    else:
        values.extend([0.0, 0.0, 0.0])
    result = np.asarray(values, dtype=np.float32)
    if not np.all(np.isfinite(result)):
        raise ValueError("Feature extraction produced non-finite values")
    return result


def extract(rows: list, label: int, source_kind: str) -> tuple[list[np.ndarray], list[int]]:
    vectors: list[np.ndarray] = []
    labels: list[int] = []
    for index, row in enumerate(rows, 1):
        path = Path(row["path"] if isinstance(row, dict) else row)
        if not path.is_file():
            raise FileNotFoundError(f"Audio file missing: {path}")
        try:
            vectors.append(features(load_5s(path)))
            labels.append(label)
        except Exception as exc:
            raise RuntimeError(f"Failed extracting {source_kind} audio {index}/{len(rows)}: {path}: {exc}") from exc
        if index % 25 == 0 or index == len(rows):
            print(f"{source_kind}: {index}/{len(rows)}", flush=True)
    return vectors, labels


def metrics(y_true: np.ndarray, prob: np.ndarray, threshold: float) -> dict:
    pred = (prob >= threshold).astype(np.int32)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    bg = int(tn + fp)
    insect = int(tp + fn)
    return {
        "threshold": round(float(threshold), 3),
        "validation_accuracy": float(accuracy_score(y_true, pred)),
        "background_rejection_rate": float(tn / bg) if bg else None,
        "background_false_accept_rate": float(fp / bg) if bg else None,
        "insect_acceptance_rate": float(tp / insect) if insect else None,
        "insect_false_rejection_rate": float(fn / insect) if insect else None,
        "confusion_matrix": {"background_correctly_rejected": int(tn), "background_mistaken_for_insect": int(fp), "insect_mistaken_for_background": int(fn), "insect_correctly_accepted": int(tp)},
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New, non-existing output directory; the active gate bundle is never overwritten.",
    )
    args = parser.parse_args()

    project_root()
    dataset_root = args.dataset.resolve()
    split_manifest = args.split_manifest.resolve()
    output_dir = args.output_dir.resolve()
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"Dataset directory missing: {dataset_root}")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite an existing gate output directory: {output_dir}")
    manifest = load_manifest(split_manifest, dataset_root)
    insect_train = sample_per_class(manifest["train"], 5)
    insect_val = sample_per_class(manifest["validation"], 2)
    if len(insect_train) < 50 or len(insect_val) < 20:
        raise RuntimeError(f"Too few insect recordings after per-class sampling ({len(insect_train)} train, {len(insect_val)} validation).")
    bg_train, bg_val = background_splits(BACKGROUND_DIR)
    print("Lightweight binary gate training (no TensorFlow Hub/YAMNet)")
    print(f"Insect train/validation: {len(insect_train)}/{len(insect_val)}")
    print(f"Background train/validation: {len(bg_train)}/{len(bg_val)}")
    print("Extracting feature vectors...", flush=True)
    x_it, y_it = extract(insect_train, 1, "Insect train")
    x_bt, y_bt = extract(bg_train, 0, "Background train")
    x_iv, y_iv = extract(insect_val, 1, "Insect validation")
    x_bv, y_bv = extract(bg_val, 0, "Background validation")
    x_train = np.vstack(x_it + x_bt)
    y_train = np.asarray(y_it + y_bt, dtype=np.int32)
    x_val = np.vstack(x_iv + x_bv)
    y_val = np.asarray(y_iv + y_bv, dtype=np.int32)
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(y_train))
    x_train, y_train = x_train[order], y_train[order]

    print("Training low-memory RandomForest gate...", flush=True)
    model = RandomForestClassifier(
        n_estimators=300,
        max_features="sqrt",
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=SEED,
        n_jobs=1,
    )
    model.fit(x_train, y_train)
    positive_idx = list(model.classes_).index(1)
    prob = model.predict_proba(x_val)[:, positive_idx]
    sweep = [metrics(y_val, prob, threshold) for threshold in np.arange(0.10, 0.901, 0.05)]
    eligible = [m for m in sweep if m["background_false_accept_rate"] is not None and m["background_false_accept_rate"] <= 0.05]
    if eligible:
        best = max(eligible, key=lambda m: (m["insect_acceptance_rate"], -m["threshold"]))
        selection_reason = "Highest insect acceptance among thresholds with <=5% background false acceptance on this pilot validation set."
        deploy_candidate = True
    else:
        best = max(sweep, key=lambda m: (m["validation_accuracy"], m["insect_acceptance_rate"]))
        selection_reason = "No threshold met the <=5% background false-accept target; chosen by validation accuracy for analysis only."
        deploy_candidate = False

    report = {
        "model": "scikit-learn RandomForest on compact spectral/audio features",
        "purpose": "Experimental low-memory insect-versus-background gate",
        "seed": SEED,
        "sample_rate": SAMPLE_RATE,
        "clip_seconds": 5,
        "feature_count": int(x_train.shape[1]),
        "sklearn_version_training": sklearn.__version__,
        "dataset": str(dataset_root),
        "split_manifest": str(split_manifest),
        "split_manifest_sha256": manifest["manifest_sha256"],
        "insect_training_provenance": "verified_eight_group_dataset_manifest",
        "insect_training_clips": len(x_it),
        "background_training_clips": len(x_bt),
        "insect_validation_clips": len(x_iv),
        "background_validation_clips": len(x_bv),
        "chosen_validation_metrics": best,
        "threshold_comparison": sweep,
        "threshold_selection_reason": selection_reason,
        "candidate_for_backend_integration": deploy_candidate,
        "caution": "ESC-50 categories are a limited proxy, and these validation files do not establish field performance. Test raw ESP32 microphone recordings before enabling live requests.",
    }
    outdir = output_dir
    outdir.mkdir(parents=True, exist_ok=False)
    joblib.dump({"model": model, "threshold": float(best["threshold"]), "feature_count": int(x_train.shape[1]), "sklearn_version": sklearn.__version__}, outdir / "background_gate.joblib", compress=3)
    (outdir / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n--- LIGHTWEIGHT GATE RESULTS ---")
    print(json.dumps(report, indent=2))
    print("Saved model:", outdir / "background_gate.joblib")
    print("Saved report:", outdir / "results.json")
    print("Backend, active insect model, and ESP32 firmware were not modified.")
    if not deploy_candidate:
        print("WARNING: No tested threshold met the background false-accept goal. Do not integrate this gate yet.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nSTOPPED SAFELY: {exc}", file=sys.stderr)
        raise SystemExit(1)
