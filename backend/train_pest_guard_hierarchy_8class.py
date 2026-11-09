#!/usr/bin/env python
"""Pest Guard: eight-group hierarchical training pipeline (revision 4).

Changes from revision 3:
  * Production manifest exports an inference feature config with exactly the
    keys the backend reads. Cache-specific metadata lives in cache_provenance.
  * Caches that fail validation, and interrupted staging directories, are
    quarantined by renaming. Nothing is removed with shutil.rmtree.
  * Empty or non-finite decoded audio is rejected with the recording path.
  * Command-line arguments are validated before any work starts.
  * Training refuses to call model.fit() unless train and validation data
    contain every class label.
  * Split algorithm, class handling, and all 12,097 recordings are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable

os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")

import librosa  # noqa: E402
import numpy as np  # noqa: E402
import tensorflow as tf  # noqa: E402
from sklearn.metrics import classification_report, confusion_matrix  # noqa: E402

# ---------------------------------------------------------------------------
# Constants and dataset ground truth
# ---------------------------------------------------------------------------
GROUPS = [
    "Beetles", "Cicada", "Crickets", "Flies",
    "Grasshopper", "Katydid", "Mole Crickets", "Termite",
]
GROUP_TO_INDEX = {name: i for i, name in enumerate(GROUPS)}

EXPECTED_CLASS_COUNTS = {
    "Beetles": 11,
    "Cicada": 4298,
    "Crickets": 1922,
    "Flies": 6,
    "Grasshopper": 2100,
    "Katydid": 3550,
    "Mole Crickets": 205,
    "Termite": 5,
}
EXPECTED_RECORDING_COUNT = sum(EXPECTED_CLASS_COUNTS.values())  # 12,097

SPLITS = ("train", "validation", "test")
FRACTIONS = {"train": 0.80, "validation": 0.10, "test": 0.10}
DEFAULT_MAX_SPLIT_DEVIATION = 0.10
MIN_COMPONENTS_PER_CLASS = 3
SPLIT_RESTARTS = 500

SR = 16_000
CLIP_SECONDS = 5
N_SAMPLES = SR * CLIP_SECONDS
FRAME_LENGTH = 1_024
FRAME_STEP = 512
FFT_LENGTH = 1_024
MEL_BINS = 128
MEL_LOW_HZ = 50.0
MEL_HIGH_HZ = 8_000.0
FEATURE_SHAPE = (155, 128, 1)
FEATURE_BYTES = int(np.prod(FEATURE_SHAPE)) * 4

FEATURE_CODE_VERSION = "logmel-peaknorm-zscore-v1"
CACHE_FORMAT_VERSION = 4
MANIFEST_FORMAT_VERSION = 2

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
SOURCE_ID_PATTERN = re.compile(r"XC\d+", re.IGNORECASE)

BATCH_SIZE = 32
LEARNING_RATE = 3e-4
MAX_EPOCHS = 40
SEED = 42

MIN_PRECISION = 0.90
MIN_COVERAGE = 0.10
CLASS_WEIGHT_CAP = 10.0
MIN_SUBTYPE_TRAIN = 3
MIN_SUBTYPE_CLASSES = 2

MEL_MATRIX = tf.signal.linear_to_mel_weight_matrix(
    num_mel_bins=MEL_BINS,
    num_spectrogram_bins=FFT_LENGTH // 2 + 1,
    sample_rate=SR,
    lower_edge_hertz=MEL_LOW_HZ,
    upper_edge_hertz=MEL_HIGH_HZ,
)


@dataclass(frozen=True)
class AudioRecord:
    path: Path
    relative_path: str
    group: str
    subtype: str | None
    content_hash: str
    source_ids: tuple[str, ...]
    component_id: str = ""
    split: str = ""


@dataclass
class SegmentMetadata:
    segment_index: int
    parent_relative_path: str
    group: str
    subtype: str | None
    split: str


@dataclass
class FeatureCache:
    features: np.ndarray
    segments: list[SegmentMetadata]
    parent_to_indices: dict[str, list[int]]


@dataclass
class PredictionSet:
    probs: np.ndarray
    trues: np.ndarray
    skipped: list[str]

    @property
    def n(self) -> int:
        return len(self.trues)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def seed_everything(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)
    try:
        tf.config.experimental.enable_op_determinism()
    except Exception as exc:
        print(f"Warning: could not enable TensorFlow op determinism: {exc}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, Path):
        return str(obj)
    return obj


def write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(to_jsonable(obj), indent=2), encoding="utf-8")
    os.replace(tmp, path)


def quarantine(path: Path, reason: str) -> Path:
    """Rename a directory aside instead of deleting it. Returns the new location."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.corrupt-{stamp}-{uuid.uuid4().hex[:8]}")
    os.replace(path, target)
    if target.is_dir():
        (target / "QUARANTINE_REASON.txt").write_text(reason, encoding="utf-8")
    print(f"Quarantined '{path.name}' -> '{target.name}': {reason}")
    return target


def validate_args(args: argparse.Namespace) -> None:
    if args.epochs < 1:
        raise ValueError(f"--epochs must be at least 1 (got {args.epochs}).")
    if not (0.0 <= args.max_split_deviation <= 1.0):
        raise ValueError(
            f"--max-split-deviation must be between 0 and 1 as a fraction "
            f"(got {args.max_split_deviation})."
        )


# ---------------------------------------------------------------------------
# 1. Discovery and exact per-class count validation
# ---------------------------------------------------------------------------
def discover_records(root: Path) -> list[AudioRecord]:
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset root does not exist: {root}")

    group_dirs = {d.name: d for d in root.iterdir() if d.is_dir()}
    missing = set(GROUPS) - set(group_dirs)
    if missing:
        raise FileNotFoundError(f"Missing required class directories: {sorted(missing)}")

    records: list[AudioRecord] = []
    print("Scanning and hashing audio files...")
    for group in GROUPS:
        folder = group_dirs[group]
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rel_parts = path.relative_to(folder).parts
            subtype = rel_parts[0] if len(rel_parts) > 1 else None
            matches = SOURCE_ID_PATTERN.findall(path.stem)
            source_ids = (matches[0].upper(),) if matches else ()
            records.append(AudioRecord(
                path=path.resolve(),
                relative_path=str(path.relative_to(root)).replace("\\", "/"),
                group=group,
                subtype=subtype,
                content_hash=file_sha256(path),
                source_ids=source_ids,
            ))

    paths = [r.relative_path for r in records]
    if len(paths) != len(set(paths)):
        raise RuntimeError("Duplicate relative paths found during discovery.")

    actual = Counter(r.group for r in records)
    mismatches = [
        f"  - {g:16s}: expected {EXPECTED_CLASS_COUNTS[g]:,}, found {actual.get(g, 0):,}"
        for g in GROUPS if actual.get(g, 0) != EXPECTED_CLASS_COUNTS[g]
    ]
    if mismatches or len(records) != EXPECTED_RECORDING_COUNT:
        lines = ["CRITICAL DATASET INTEGRITY MISMATCH:", *mismatches,
                 f"Total recordings: expected {EXPECTED_RECORDING_COUNT:,}, found {len(records):,}"]
        raise RuntimeError("\n".join(lines))

    print(f"Dataset integrity: PASS ({len(records):,} recordings, all class counts match).")
    return records


# ---------------------------------------------------------------------------
# 2. Leakage-free splits with explicit per-class reporting (algorithm unchanged)
# ---------------------------------------------------------------------------
def build_components(records: list[AudioRecord]) -> tuple[list[str], dict[str, list[int]]]:
    """Union recordings sharing a content hash or an XC source ID."""
    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    def tokens_of(rec: AudioRecord) -> set[str]:
        return {f"sha256:{rec.content_hash}", *(f"source:{s}" for s in rec.source_ids)}

    owner: dict[str, int] = {}
    for i, rec in enumerate(records):
        for tok in tokens_of(rec):
            if tok in owner:
                union(i, owner[tok])
            else:
                owner[tok] = i

    roots: dict[int, list[int]] = defaultdict(list)
    root_tokens: dict[int, set[str]] = defaultdict(set)
    for i, rec in enumerate(records):
        root = find(i)
        roots[root].append(i)
        root_tokens[root].update(tokens_of(rec))

    comp_of: list[str] = [""] * len(records)
    comps: dict[str, list[int]] = {}
    for root, members in roots.items():
        cid = hashlib.sha256("\n".join(sorted(root_tokens[root])).encode("utf-8")).hexdigest()
        comps[cid] = members
        for m in members:
            comp_of[m] = cid
    return comp_of, comps


def best_assignment(group: str, comps: list[tuple[str, list[int]]], seed: int):
    """Assign components to all splits, then minimise allocation deviation."""
    if len(comps) < len(SPLITS):
        raise RuntimeError(
            f"'{group}' has only {len(comps)} independent components; "
            "three non-empty leakage-free splits are impossible."
        )

    total = sum(len(members) for _, members in comps)
    target = {s: FRACTIONS[s] * total for s in SPLITS}
    rng = random.Random(f"{seed}:{group}")
    base = sorted(comps, key=lambda c: c[0])

    best = None
    for _ in range(SPLIT_RESTARTS):
        trial = list(base)
        rng.shuffle(trial)
        trial.sort(key=lambda c: len(c[1]), reverse=True)

        # Guarantee one independent component in every split.
        smallest = sorted(trial, key=lambda c: len(c[1]))
        reserved = {
            "train": trial[0],
            "validation": smallest[0],
            "test": smallest[1],
        }

        reserved_ids = {cid for cid, _ in reserved.values()}
        remaining = [c for c in trial if c[0] not in reserved_ids]

        alloc = {s: 0 for s in SPLITS}
        assign: dict[str, str] = {}

        for split, (cid, members) in reserved.items():
            assign[cid] = split
            alloc[split] += len(members)

        for cid, members in remaining:
            # Prioritise the split with the largest proportional deficit.
            chosen = max(
                SPLITS,
                key=lambda s: (target[s] - alloc[s]) / target[s],
            )
            assign[cid] = chosen
            alloc[chosen] += len(members)

        worst = max(
            abs(alloc[s] - target[s]) / total
            for s in SPLITS
        )

        if best is None or worst < best[0]:
            best = (worst, assign, alloc)

    return best[1], best[2], total


def check_split_deviation(stats: dict[str, tuple[dict[str, int], int]], max_deviation: float) -> list[dict]:
    rows = []
    for g in GROUPS:
        alloc, total = stats[g]
        per_split = {}
        for s in SPLITS:
            fraction = alloc[s] / total
            per_split[s] = {
                "recordings": alloc[s],
                "fraction": fraction,
                "deviation": fraction - FRACTIONS[s],
            }
        worst = max(abs(v["deviation"]) for v in per_split.values())
        rows.append({
            "group": g,
            "total": total,
            "splits": per_split,
            "worst_deviation": worst,
            "within_tolerance": worst <= max_deviation,
        })
    return rows


def print_split_report(rows: list[dict], max_deviation: float) -> None:
    print(f"\nPer-class split allocation (target 80/10/10, tolerance ±{max_deviation * 100:.0f} points):")
    header = (f"{'Class':16s} {'Total':>6s} | {'Train':>15s} {'Validation':>15s} "
              f"{'Test':>15s} | {'Worst':>6s}  Status")
    print(header)
    print("-" * len(header))
    for row in rows:
        cells = [
            f"{row['splits'][s]['recordings']:>4,} ({row['splits'][s]['fraction'] * 100:5.1f}%)"
            for s in SPLITS
        ]
        status = "OK" if row["within_tolerance"] else "OUTSIDE TOLERANCE"
        print(f"{row['group']:16s} {row['total']:>6,} | {cells[0]:>15s} {cells[1]:>15s} "
              f"{cells[2]:>15s} | {row['worst_deviation'] * 100:5.1f}%  {status}")
    print()


def enforce_split_tolerance(rows: list[dict], max_deviation: float, accept: bool) -> list[str]:
    outside = [r for r in rows if not r["within_tolerance"]]
    if not outside:
        return []

    lines = []
    for r in outside:
        step = 100.0 / r["total"]
        lines.append(
            f"  - {r['group']} ({r['total']} recordings): worst deviation {r['worst_deviation'] * 100:.1f} points. "
            f"With {r['total']} recordings, one recording moves the ratio by {step:.1f} points."
        )
    explanation = (
        "Per-class split ratios exceed the tolerance for these classes:\n"
        + "\n".join(lines)
        + "\nThe deviation comes from whole-recording counts in small classes, not from the allocation "
          "algorithm. The closest leakage-free split found for each class is shown in the table above. "
          "All eight classes remain in the dataset and in every split."
    )
    if not accept:
        raise RuntimeError(
            explanation
            + "\nTo proceed with these ratios, rerun with --accept-split-deviation. "
              "The actual per-class ratios will be recorded in the manifest."
        )
    print("WARNING: accepting split deviation (--accept-split-deviation).\n" + explanation + "\n")
    return [r["group"] for r in outside]


def assign_splits(records: list[AudioRecord], seed: int, max_deviation: float,
                  accept: bool) -> tuple[list[AudioRecord], dict]:
    comp_of, comps = build_components(records)

    by_group: dict[str, list[tuple[str, list[int]]]] = defaultdict(list)
    conflicts = []
    for cid, members in comps.items():
        groups = {records[m].group for m in members}
        if len(groups) > 1:
            conflicts.append((groups, [records[m].relative_path for m in members][:10]))
        else:
            by_group[next(iter(groups))].append((cid, members))

    if conflicts:
        lines = ["CRITICAL DATASET CONFLICT: files sharing hash or source ID span different classes:"]
        for groups, paths in conflicts[:5]:
            lines.append(f"  Classes: {sorted(groups)}\n  Files (first 10): {paths}")
        raise RuntimeError("\n".join(lines))

    too_few = [g for g in GROUPS if len(by_group[g]) < MIN_COMPONENTS_PER_CLASS]
    if too_few:
        lines = [
            f"A leakage-free train/validation/test split is not possible for these classes "
            f"(each needs at least {MIN_COMPONENTS_PER_CLASS} independent components):"
        ]
        for g in too_few:
            n_rec = sum(len(m) for _, m in by_group[g])
            lines.append(f"  - {g}: {n_rec} recording(s) in {len(by_group[g])} independent component(s)")
        lines.append(
            "All recordings are kept. Splitting these classes would require placing recordings that share "
            "a source or identical audio into more than one split. The script does not do this silently; "
            "a decision is needed before the run can continue."
        )
        raise RuntimeError("\n".join(lines))

    split_of: dict[str, str] = {}
    stats: dict[str, tuple[dict[str, int], int]] = {}
    for g in GROUPS:
        assignment, alloc, total = best_assignment(g, by_group[g], seed)
        split_of.update(assignment)
        stats[g] = (alloc, total)

    rows = check_split_deviation(stats, max_deviation)
    print_split_report(rows, max_deviation)
    outside = enforce_split_tolerance(rows, max_deviation, accept)

    finalized = [
        replace(rec, component_id=comp_of[i], split=split_of[comp_of[i]])
        for i, rec in enumerate(records)
    ]
    for s in SPLITS:
        missing = set(GROUPS) - {r.group for r in finalized if r.split == s}
        if missing:
            raise RuntimeError(f"Split '{s}' has no recordings for: {sorted(missing)}")

    report = {
        "max_deviation": max_deviation,
        "deviation_accepted": bool(outside),
        "classes_outside_tolerance": outside,
        "per_class": rows,
    }
    return finalized, report


# ---------------------------------------------------------------------------
# 3. Audio slicing and log-mel features
# ---------------------------------------------------------------------------
def slice_audio(waveform: np.ndarray) -> list[np.ndarray]:
    if len(waveform) == 0:
        raise ValueError("slice_audio received an empty waveform.")
    if len(waveform) <= N_SAMPLES:
        return [np.pad(waveform, (0, N_SAMPLES - len(waveform)))]
    segments = []
    for start in range(0, len(waveform), N_SAMPLES):
        seg = waveform[start:start + N_SAMPLES]
        if len(seg) < N_SAMPLES:
            seg = np.pad(seg, (0, N_SAMPLES - len(seg)))
        segments.append(seg)
    return segments


def extract_features(waveform: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(waveform))) if len(waveform) else 0.0
    if peak > 0.0:
        waveform = waveform / peak
    stft = tf.signal.stft(waveform, frame_length=FRAME_LENGTH, frame_step=FRAME_STEP, fft_length=FFT_LENGTH)
    mel = tf.matmul(tf.square(tf.abs(stft)), MEL_MATRIX)
    mel = tf.math.log(mel + 1e-6)
    mel = (mel - tf.reduce_mean(mel)) / (tf.math.reduce_std(mel) + 1e-6)
    features = mel[..., tf.newaxis].numpy().astype(np.float32)
    if features.shape != FEATURE_SHAPE or not np.all(np.isfinite(features)):
        raise ValueError(f"Feature calculation error. Shape: {features.shape}")
    return features


# ---------------------------------------------------------------------------
# 4. Feature configuration and feature cache
# ---------------------------------------------------------------------------
def inference_feature_config() -> dict:
    """Exact feature configuration consumed by pest_guard_hierarchy_inference_8class.py."""
    return {
        "sample_rate": SR,
        "clip_seconds": CLIP_SECONDS,
        "samples": N_SAMPLES,
        "frame_length": FRAME_LENGTH,
        "frame_step": FRAME_STEP,
        "fft_length": FFT_LENGTH,
        "mel_bins": MEL_BINS,
        "mel_low_hz": MEL_LOW_HZ,
        "mel_high_hz": MEL_HIGH_HZ,
        "feature_shape": list(FEATURE_SHAPE),
    }


def cache_config() -> dict:
    """Inference features plus cache-only version fields, used to validate the cache."""
    return {
        **inference_feature_config(),
        "cache_format": CACHE_FORMAT_VERSION,
        "feature_code": FEATURE_CODE_VERSION,
    }


def dataset_fingerprint(records: list[AudioRecord]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(cache_config(), sort_keys=True).encode("utf-8"))
    for r in sorted(records, key=lambda x: x.relative_path):
        h.update(f"{r.relative_path}|{r.content_hash}|{r.group}|{r.subtype}|{r.split}\n".encode("utf-8"))
    return h.hexdigest()


def load_valid_cache(cache_dir: Path, records: list[AudioRecord]) -> FeatureCache:
    """Raise ValueError on any inconsistency; return a memory-mapped cache otherwise."""
    manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("fingerprint") != dataset_fingerprint(records):
        raise ValueError("fingerprint does not match the current dataset")
    if manifest.get("config") != cache_config():
        raise ValueError("cache configuration differs from current code")

    rec_meta = manifest["records"]
    meta_paths = [m["relative_path"] for m in rec_meta]
    if len(meta_paths) != len(set(meta_paths)):
        dups = [p for p, c in Counter(meta_paths).items() if c > 1][:5]
        raise ValueError(f"duplicate recording entries in manifest: {dups}")

    current = {r.relative_path: r for r in records}
    if set(meta_paths) != set(current) or len(meta_paths) != len(current):
        raise ValueError("cached recordings do not match the current dataset one-to-one")

    meta_by_path = {m["relative_path"]: m for m in rec_meta}
    for path, rec in current.items():
        m = meta_by_path[path]
        if (m["content_hash"], m["group"], m["subtype"], m["split"]) != (
                rec.content_hash, rec.group, rec.subtype, rec.split):
            raise ValueError(f"metadata for '{path}' differs from the current dataset")

    expected_counts = {p: int(m["segment_count"]) for p, m in meta_by_path.items()}
    if any(c < 1 for c in expected_counts.values()):
        raise ValueError("a recording has a non-positive segment count")
    total = int(manifest["total_segments"])
    if sum(expected_counts.values()) != total:
        raise ValueError(f"segment counts sum to {sum(expected_counts.values())}, manifest says {total}")

    segments = [SegmentMetadata(**item) for item in manifest["segments"]]
    if len(segments) != total:
        raise ValueError(f"manifest lists {len(segments)} segments, expected {total}")

    features_path = cache_dir / "features.npy"
    if file_sha256(features_path) != manifest["features_sha256"]:
        raise ValueError("features.npy checksum mismatch")
    feats = np.load(features_path, mmap_mode="r")
    if feats.shape != (total, *FEATURE_SHAPE) or feats.dtype != np.float32:
        raise ValueError(f"features shape/dtype {feats.shape}/{feats.dtype} unexpected")

    parent_to_indices: dict[str, list[int]] = defaultdict(list)
    for i, seg in enumerate(segments):
        if seg.segment_index != i:
            raise ValueError(f"segment_index {seg.segment_index} stored at position {i}")
        m = meta_by_path.get(seg.parent_relative_path)
        if m is None:
            raise ValueError(f"segment {i} references an unknown recording")
        if (seg.group, seg.subtype, seg.split) != (m["group"], m["subtype"], m["split"]):
            raise ValueError(f"segment {i} metadata does not match its recording")
        parent_to_indices[seg.parent_relative_path].append(i)

    if set(parent_to_indices) != set(expected_counts):
        raise ValueError("some recordings have no segments")
    for path, idxs in parent_to_indices.items():
        n = expected_counts[path]
        if len(idxs) != n or idxs != list(range(idxs[0], idxs[0] + n)):
            raise ValueError(f"segments for '{path}' are not one contiguous range of {n}")

    return FeatureCache(features=feats, segments=segments, parent_to_indices=dict(parent_to_indices))


def _write_features(records: list[AudioRecord], raw_path: Path):
    segments: list[SegmentMetadata] = []
    counts: dict[str, int] = {}
    start = time.perf_counter()
    with raw_path.open("wb") as out:
        for idx, r in enumerate(records, start=1):
            try:
                waveform, _ = librosa.load(str(r.path), sr=SR, mono=True, dtype=np.float32)
            except Exception as exc:
                raise RuntimeError(f"Failed to decode recording {r.path}: {exc}") from exc
            if waveform.size == 0:
                raise ValueError(
                    f"Decoded waveform is empty; refusing to create padded features for recording: {r.path}"
                )
            if not np.isfinite(waveform).all():
                raise ValueError(f"Decoded waveform contains non-finite samples: {r.path}")

            slices = slice_audio(waveform)
            counts[r.relative_path] = len(slices)
            for seg in slices:
                out.write(extract_features(seg).tobytes(order="C"))
                segments.append(SegmentMetadata(len(segments), r.relative_path, r.group, r.subtype, r.split))
            if idx % 500 == 0 or idx == len(records):
                print(f"  Processed {idx:>5,}/{len(records):,} files | {len(segments):,} segments "
                      f"({(time.perf_counter() - start) / 60:.1f}m)")
    return segments, counts


def _write_npy_from_raw(raw_path: Path, npy_path: Path, total: int) -> None:
    expected = total * FEATURE_BYTES
    actual = raw_path.stat().st_size
    if actual != expected:
        raise RuntimeError(f"raw feature file is {actual} bytes, expected {expected}")
    with npy_path.open("wb") as out:
        np.lib.format.write_array_header_1_0(
            out, {"descr": "<f4", "fortran_order": False, "shape": (total, *FEATURE_SHAPE)}
        )
        with raw_path.open("rb") as src:
            shutil.copyfileobj(src, out, length=16 * 1024 * 1024)


def build_cache(records: list[AudioRecord], cache_root: Path) -> FeatureCache:
    cache_root.mkdir(parents=True, exist_ok=True)

    fp = dataset_fingerprint(records)
    final_dir = cache_root / fp[:16]
    if final_dir.exists():
        try:
            cache = load_valid_cache(final_dir, records)
            print(f"Feature cache verified ({len(cache.segments):,} segments). Reusing.")
            return cache
        except Exception as exc:
            quarantine(final_dir, f"failed validation: {exc}")

    print("\nBuilding feature cache...")
    staging = cache_root / f".staging-{fp[:16]}-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        raw_path = staging / "features.f32.bin"
        segments, counts = _write_features(records, raw_path)
        total = len(segments)
        _write_npy_from_raw(raw_path, staging / "features.npy", total)
        raw_path.unlink()

        manifest = {
            "fingerprint": fp,
            "config": cache_config(),
            "total_segments": total,
            "records": [
                {
                    "relative_path": r.relative_path,
                    "content_hash": r.content_hash,
                    "group": r.group,
                    "subtype": r.subtype,
                    "split": r.split,
                    "segment_count": counts[r.relative_path],
                }
                for r in records
            ],
            "features_sha256": file_sha256(staging / "features.npy"),
            "segments": [asdict(s) for s in segments],
        }
        write_json_atomic(staging / "manifest.json", manifest)

        load_valid_cache(staging, records)  # verify before publishing
        os.replace(staging, final_dir)
    except BaseException as exc:
        if staging.exists():
            quarantine(staging, f"cache build failed: {exc}")
        raise

    cache = load_valid_cache(final_dir, records)
    print(f"Feature cache complete and verified: {len(cache.segments):,} segments.")
    return cache


# ---------------------------------------------------------------------------
# 5. Data pipeline and SpecAugment
# ---------------------------------------------------------------------------
def spec_augment(
    feature: tf.Tensor,
    label: tf.Tensor,
    sample_weight: tf.Tensor,
):
    noise_floor = tf.reduce_min(feature)
    shape = tf.shape(feature)

    freq_w = tf.random.uniform([], 0, 13, dtype=tf.int32)
    freq_s = tf.random.uniform(
        [], 0, tf.maximum(1, 128 - freq_w + 1), dtype=tf.int32
    )
    freq_mask = tf.logical_and(
        tf.range(128) >= freq_s,
        tf.range(128) < freq_s + freq_w,
    )

    time_w = tf.random.uniform([], 0, 19, dtype=tf.int32)
    time_s = tf.random.uniform(
        [], 0, tf.maximum(1, shape[0] - time_w + 1), dtype=tf.int32
    )
    time_mask = tf.logical_and(
        tf.range(shape[0]) >= time_s,
        tf.range(shape[0]) < time_s + time_w,
    )

    mask = tf.logical_or(time_mask[:, None], freq_mask[None, :])
    feature = tf.where(
        mask[:, :, None],
        tf.fill(shape, noise_floor),
        feature,
    )

    return feature, label, sample_weight


def make_tf_dataset(
    cache: FeatureCache,
    indices: list[int],
    labels: list[int],
    is_training: bool,
    sample_weights: list[float] | None = None,
    seed: int = SEED,
) -> tf.data.Dataset:
    idx = np.asarray(indices, dtype=np.int64)
    lbl = np.asarray(labels, dtype=np.int32)
    if len(idx) != len(lbl):
        raise ValueError("Feature indices and labels have different lengths.")

    if sample_weights is None:
        weights = np.ones(len(idx), dtype=np.float32)
    else:
        weights = np.asarray(sample_weights, dtype=np.float32)

    if len(weights) != len(idx):
        raise ValueError("Sample weights and feature indices have different lengths.")

    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("Sample weights must be finite and greater than zero.")

    epoch = {"n": 0}

    def generator():
        order = np.arange(len(idx))
        if is_training:
            rng = np.random.default_rng(seed + epoch["n"])
            epoch["n"] += 1
            rng.shuffle(order)
        for i in order:
            yield cache.features[idx[i]], lbl[i], weights[i]

    ds = tf.data.Dataset.from_generator(
        generator,
        output_signature=(
            tf.TensorSpec(shape=FEATURE_SHAPE, dtype=tf.float32),
            tf.TensorSpec(shape=(), dtype=tf.int32),
            tf.TensorSpec(shape=(), dtype=tf.float32),
        ),
    )
    if is_training:
        ds = ds.map(
            spec_augment,
            num_parallel_calls=tf.data.AUTOTUNE,
            deterministic=True,
        )
    ds = ds.batch(BATCH_SIZE, drop_remainder=False)
    if is_training:
        ds = ds.repeat()
    return ds.prefetch(tf.data.AUTOTUNE)


# ---------------------------------------------------------------------------
# 6. Model
# ---------------------------------------------------------------------------
def conv_block(x: tf.Tensor, filters: int, dropout: float) -> tf.Tensor:
    reg = tf.keras.regularizers.l2(1e-4)
    for _ in range(2):
        x = tf.keras.layers.Conv2D(filters, 3, padding="same", use_bias=False, kernel_regularizer=reg)(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.Activation("relu")(x)
    x = tf.keras.layers.MaxPooling2D(2)(x)
    if dropout > 0.0:
        x = tf.keras.layers.Dropout(dropout)(x)
    return x


def build_cnn(num_classes: int) -> tf.keras.Model:
    inputs = tf.keras.layers.Input(shape=FEATURE_SHAPE, name="logmel_input")
    x = conv_block(inputs, 32, 0.05)
    x = conv_block(x, 64, 0.10)
    x = conv_block(x, 128, 0.15)
    avg_p = tf.keras.layers.GlobalAveragePooling2D()(x)
    max_p = tf.keras.layers.GlobalMaxPooling2D()(x)
    x = tf.keras.layers.Concatenate()([avg_p, max_p])
    x = tf.keras.layers.Dense(128, use_bias=False, kernel_regularizer=tf.keras.regularizers.l2(1e-4))(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Activation("relu")(x)
    x = tf.keras.layers.Dropout(0.20)(x)
    x = tf.keras.layers.Dense(64, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.10)(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax")(x)
    model = tf.keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def compute_recording_aware_sample_weights(
    segments: list[SegmentMetadata],
    labels: list[int],
    num_classes: int,
) -> list[float]:
    """
    Give each original recording equal total influence within its class.

    Longer recordings create more segments, so each segment receives
    only a fraction of its parent recording's weight.
    """

    if len(segments) != len(labels):
        raise ValueError("Segments and labels have different lengths.")

    if not segments:
        raise ValueError("Cannot calculate weights for an empty dataset.")

    recording_classes: dict[str, int] = {}
    segments_per_recording = Counter()

    for segment, label in zip(segments, labels):
        if label < 0 or label >= num_classes:
            raise ValueError(f"Invalid class label: {label}")

        parent = segment.parent_relative_path

        if parent in recording_classes and recording_classes[parent] != label:
            raise ValueError(
                f"Recording '{parent}' has inconsistent class labels."
            )

        recording_classes[parent] = label
        segments_per_recording[parent] += 1

    recordings_per_class = Counter(recording_classes.values())

    missing = [
        c for c in range(num_classes)
        if recordings_per_class[c] == 0
    ]

    if missing:
        raise ValueError(
            f"Cannot calculate sample weights. Missing classes: {missing}"
        )

    total_recordings = len(recording_classes)

    class_weights = {
        c: math.sqrt(
            total_recordings /
            (num_classes * recordings_per_class[c])
        )
        for c in range(num_classes)
    }

    # Normalize class weights to a recording-weighted mean of 1.
    weighted_mean = sum(
        class_weights[c] * recordings_per_class[c]
        for c in range(num_classes)
    ) / total_recordings

    class_weights = {
        c: min(class_weights[c] / weighted_mean, CLASS_WEIGHT_CAP)
        for c in range(num_classes)
    }

    sample_weights = []

    for segment, label in zip(segments, labels):
        parent = segment.parent_relative_path

        weight = (
            class_weights[label] /
            segments_per_recording[parent]
        )

        sample_weights.append(float(weight))

    # Keep the average segment weight at 1.
    mean_weight = sum(sample_weights) / len(sample_weights)

    sample_weights = [
        weight / mean_weight
        for weight in sample_weights
    ]

    if not all(math.isfinite(w) and w > 0 for w in sample_weights):
        raise ValueError("Calculated sample weights are invalid.")

    return sample_weights


def make_callbacks() -> list[tf.keras.callbacks.Callback]:
    return [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=8, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3, min_lr=1e-6),
    ]


def require_all_labels(split_name: str, labels: list[int], class_names: list[str]) -> None:
    present = set(labels)
    missing = [class_names[i] for i in range(len(class_names)) if i not in present]
    if missing:
        raise RuntimeError(
            f"{split_name} segments lack labels {missing}. Training stopped before model.fit()."
        )


def train_model(cache: FeatureCache, train_segs: list[SegmentMetadata], val_segs: list[SegmentMetadata],
                label_of: Callable[[SegmentMetadata], int], class_names: list[str],
                epochs: int) -> tf.keras.Model:
    if not train_segs or not val_segs:
        raise RuntimeError("Training requires non-empty train and validation segments.")
    num_classes = len(class_names)
    tr_lbl = [label_of(s) for s in train_segs]
    va_lbl = [label_of(s) for s in val_segs]
    require_all_labels("Training", tr_lbl, class_names)
    require_all_labels("Validation", va_lbl, class_names)

    train_weights = compute_recording_aware_sample_weights(
        train_segs,
        tr_lbl,
        num_classes,
    )

    ds_tr = make_tf_dataset(
        cache,
        [s.segment_index for s in train_segs],
        tr_lbl,
        is_training=True,
        sample_weights=train_weights,
    )
    ds_va = make_tf_dataset(
        cache,
        [s.segment_index for s in val_segs],
        va_lbl,
        is_training=False,
    )
    model = build_cnn(num_classes)
    model.fit(
        ds_tr,
        validation_data=ds_va,
        epochs=epochs,
        steps_per_epoch=math.ceil(len(train_segs) / BATCH_SIZE),
        validation_steps=math.ceil(len(val_segs) / BATCH_SIZE),
        callbacks=make_callbacks(),
        verbose=1,
        shuffle=False,
    )
    return model


# ---------------------------------------------------------------------------
# 7. Prediction, threshold calibration, evaluation
# ---------------------------------------------------------------------------
def predict_split(model: tf.keras.Model, records: list[AudioRecord], cache: FeatureCache,
                  class_labels: list[str], label_fn: Callable[[AudioRecord], str | None]) -> PredictionSet:
    idx_of = {name: i for i, name in enumerate(class_labels)}
    probs, trues, skipped = [], [], []
    for r in records:
        label = label_fn(r)
        if label not in idx_of:
            continue
        seg_idx = cache.parent_to_indices.get(r.relative_path)
        if not seg_idx:
            skipped.append(r.relative_path)
            continue
        feats = cache.features[np.asarray(seg_idx)]
        probs.append(model.predict(feats, batch_size=BATCH_SIZE, verbose=0).mean(axis=0))
        trues.append(idx_of[label])
    matrix = np.stack(probs) if probs else np.zeros((0, len(class_labels)), dtype=np.float32)
    return PredictionSet(matrix, np.asarray(trues, dtype=np.int64), skipped)


def threshold_metrics(pred: PredictionSet, t: float) -> dict:
    conf = pred.probs.max(axis=1)
    guess = pred.probs.argmax(axis=1)
    accepted = conf >= t
    n_acc = int(accepted.sum())
    precision = float((guess[accepted] == pred.trues[accepted]).mean()) if n_acc else None
    return {
        "threshold": float(t),
        "coverage": float(accepted.mean()) if pred.n else 0.0,
        "precision": precision,
        "accepted_recordings": n_acc,
        "evaluated_recordings": pred.n,
    }


def calibrate_threshold(val: PredictionSet) -> tuple[float | None, dict]:
    """Lowest threshold on validation reaching MIN_PRECISION at MIN_COVERAGE.

    Returns (None, status) on failure. There is no silent fallback value.
    """
    if val.n == 0:
        return None, {"calibration_status": "failed_no_validation_recordings"}
    for t in sorted(set(val.probs.max(axis=1).tolist())):
        m = threshold_metrics(val, t)
        if m["coverage"] >= MIN_COVERAGE and m["precision"] is not None and m["precision"] >= MIN_PRECISION:
            return float(t), {"calibration_status": "ok", "validation": m}
    return None, {
        "calibration_status": "failed_no_threshold_meets_precision",
        "required_precision": MIN_PRECISION,
        "required_coverage": MIN_COVERAGE,
    }


def evaluate(pred: PredictionSet, class_labels: list[str]) -> dict:
    if pred.n == 0:
        raise RuntimeError("No evaluable recordings with cached segments in this split.")
    labels = list(range(len(class_labels)))
    guess = pred.probs.argmax(axis=1)
    report = classification_report(
        pred.trues, guess, labels=labels, target_names=class_labels,
        output_dict=True, zero_division=0,
    )
    return {
        "recordings_evaluated": pred.n,
        "recordings_skipped_no_segments": len(pred.skipped),
        "accuracy": float((guess == pred.trues).mean()),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "classification_report": report,
        "confusion_matrix": confusion_matrix(pred.trues, guess, labels=labels).tolist(),
    }


# ---------------------------------------------------------------------------
# 8. Subtype planning and experts
# ---------------------------------------------------------------------------
def plan_subtypes(group: str, records: list[AudioRecord]) -> tuple[list[str], dict[str, str]]:
    group_recs = [r for r in records if r.group == group and r.subtype]
    train_counts = Counter(r.subtype for r in group_recs if r.split == "train")
    val_subs = {r.subtype for r in group_recs if r.split == "validation"}
    test_subs = {r.subtype for r in group_recs if r.split == "test"}

    eligible: list[str] = []
    excluded: dict[str, str] = {}
    for st in sorted({r.subtype for r in group_recs}):
        reasons = []
        if train_counts[st] < MIN_SUBTYPE_TRAIN:
            reasons.append(f"{train_counts[st]} train recordings (< {MIN_SUBTYPE_TRAIN})")
        if st not in val_subs:
            reasons.append("no validation recordings")
        if st not in test_subs:
            reasons.append("no test recordings")
        if reasons:
            excluded[st] = "; ".join(reasons)
        else:
            eligible.append(st)
    return eligible, excluded


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def train_subtype_expert(group: str, records: list[AudioRecord], cache: FeatureCache,
                         epochs: int, out_dir: Path) -> dict:
    eligible, excluded = plan_subtypes(group, records)
    if len(eligible) < MIN_SUBTYPE_CLASSES:
        print(f"Subtype expert skipped for '{group}': {len(eligible)} eligible subtype(s).")
        return {
            "status": "skipped",
            "reason": f"fewer than {MIN_SUBTYPE_CLASSES} eligible subtypes",
            "model_file": None,
            "labels": [],
            "excluded_subtypes": excluded,
            "threshold": {"minimum_confidence": None, "calibration_status": "not_trained"},
        }

    print(f"\nTraining subtype expert for '{group}' ({len(eligible)} classes)")
    st_map = {name: i for i, name in enumerate(eligible)}
    train_segs = [s for s in cache.segments if s.split == "train" and s.group == group and s.subtype in st_map]
    val_segs = [s for s in cache.segments if s.split == "validation" and s.group == group and s.subtype in st_map]
    model = train_model(cache, train_segs, val_segs, lambda s: st_map[s.subtype], eligible, epochs)

    filename = f"subtype_{slugify(group)}.keras"
    model.save(out_dir / filename)

    val_recs = [
        r for r in records
        if r.group == group
        and r.split == "validation"
        and r.subtype
    ]

    test_recs = [
        r for r in records
        if r.group == group
        and r.split == "test"
        and r.subtype
    ]

    eligible_set = set(eligible)

    excluded_test_counts = Counter(
        r.subtype
        for r in test_recs
        if r.subtype not in eligible_set
    )

    eligible_test_recordings = sum(
        1 for r in test_recs
        if r.subtype in eligible_set
    )

    val_pred = predict_split(
        model,
        val_recs,
        cache,
        eligible,
        lambda r: r.subtype,
    )

    test_pred = predict_split(
        model,
        test_recs,
        cache,
        eligible,
        lambda r: r.subtype,
    )

    thr, status = calibrate_threshold(val_pred)

    if thr is not None:
        status["test_check"] = threshold_metrics(test_pred, thr)

    evaluation = evaluate(test_pred, eligible)

    evaluation["test_recordings_total_for_group"] = len(test_recs)
    evaluation["test_recordings_eligible_for_expert"] = (
        eligible_test_recordings
    )
    evaluation["test_recordings_evaluated_by_expert"] = test_pred.n
    evaluation["test_recordings_excluded_from_expert"] = (
        len(test_recs) - test_pred.n
    )
    evaluation["excluded_test_recordings_by_subtype"] = dict(
        excluded_test_counts
    )

    print(
        f"'{group}' subtype test macro-F1: "
        f"{evaluation['macro_f1']:.4f} | "
        f"evaluated: {test_pred.n}/{len(test_recs)} | "
        f"excluded: {len(test_recs) - test_pred.n} | "
        f"threshold: {thr} ({status['calibration_status']})"
    )

    return {
        "status": "trained",
        "model_file": filename,
        "labels": eligible,
        "excluded_subtypes": excluded,
        "threshold": {"minimum_confidence": thr, **status},
        "test_evaluation": evaluation,
    }


# ---------------------------------------------------------------------------
# 9. Pipeline smoke test (runs in every mode)
# ---------------------------------------------------------------------------
def run_pipeline_smoke_test() -> None:
    """Runs the real generator, SpecAugment, class weights, training, prediction,
    calibration and evaluation on small synthetic data. Verifies code paths only;
    it does not validate model quality."""
    print("Pipeline smoke test (synthetic features through the real training path)...")
    rng = np.random.default_rng(SEED)
    per_class = 4
    segments: list[SegmentMetadata] = []
    records: list[AudioRecord] = []
    parent_to_indices: dict[str, list[int]] = {}
    feats: list[np.ndarray] = []

    for split in SPLITS:
        for g in GROUPS:
            for k in range(per_class):
                idx = len(segments)
                rel = f"__smoke__/{split}/{g}/{k}.wav"
                segments.append(SegmentMetadata(idx, rel, g, None, split))
                parent_to_indices[rel] = [idx]
                feats.append(rng.standard_normal(FEATURE_SHAPE).astype(np.float32))
                records.append(AudioRecord(
                    path=Path(rel), relative_path=rel, group=g, subtype=None,
                    content_hash=f"smoke{idx}", source_ids=(), split=split,
                ))
    cache = FeatureCache(np.stack(feats), segments, parent_to_indices)

    train_segs = [s for s in segments if s.split == "train"]
    val_segs = [s for s in segments if s.split == "validation"]
    train_lbl = [GROUP_TO_INDEX[s.group] for s in train_segs]

    weights = compute_recording_aware_sample_weights(
        train_segs,
        train_lbl,
        len(GROUPS),
    )
    assert len(weights) == len(train_segs), "sample weights missing segments"
    assert all(np.isfinite(v) and v > 0 for v in weights), "non-finite sample weight"

    ds = make_tf_dataset(
        cache,
        [s.segment_index for s in train_segs],
        train_lbl,
        is_training=True,
        sample_weights=weights,
    )
    x, y, sample_weight = next(iter(ds))
    assert tuple(x.shape[1:]) == FEATURE_SHAPE and x.dtype == tf.float32, "bad batch shape or dtype"
    assert y.dtype == tf.int32, "bad label dtype"
    assert sample_weight.dtype == tf.float32, "bad sample-weight dtype"

    model = train_model(cache, train_segs, val_segs, lambda s: GROUP_TO_INDEX[s.group], GROUPS, epochs=1)

    val_recs = [r for r in records if r.split == "validation"]
    test_recs = [r for r in records if r.split == "test"]
    val_pred = predict_split(model, val_recs, cache, GROUPS, lambda r: r.group)
    test_pred = predict_split(model, test_recs, cache, GROUPS, lambda r: r.group)
    assert val_pred.n == len(val_recs) and test_pred.n == len(test_recs), "prediction count mismatch"
    calibrate_threshold(val_pred)
    evaluate(test_pred, GROUPS)
    print("Pipeline smoke test: PASS.")


# ---------------------------------------------------------------------------
# 10. Training, export, and pipeline
# ---------------------------------------------------------------------------
def train_and_export(records: list[AudioRecord], cache: FeatureCache, epochs: int,
                     out_dir: Path, dataset_root: Path, split_report: dict,
                     fingerprint: str) -> dict:
    by_split = {s: [r for r in records if r.split == s] for s in SPLITS}
    seg_by = {s: [seg for seg in cache.segments if seg.split == s] for s in SPLITS}

    print("\n--------------------------------------------------------")
    print("Training primary 8-group model")
    print("--------------------------------------------------------")
    group_model = train_model(
        cache, seg_by["train"], seg_by["validation"],
        lambda s: GROUP_TO_INDEX[s.group], GROUPS, epochs,
    )
    group_model.save(out_dir / "group_model.keras")

    val_pred = predict_split(group_model, by_split["validation"], cache, GROUPS, lambda r: r.group)
    test_pred = predict_split(group_model, by_split["test"], cache, GROUPS, lambda r: r.group)
    group_thr, group_status = calibrate_threshold(val_pred)
    if group_thr is not None:
        group_status["test_check"] = threshold_metrics(test_pred, group_thr)
    group_eval = evaluate(test_pred, GROUPS)
    print(f"\nGroup test accuracy: {group_eval['accuracy']:.4f} | macro-F1: {group_eval['macro_f1']:.4f}")
    print(f"Group threshold: {group_thr} ({group_status['calibration_status']})")

    subtype_sections: dict[str, dict] = {}
    for group in GROUPS:
        subtype_sections[group] = train_subtype_expert(group, records, cache, epochs, out_dir)

    mappings = {g: {lbl: lbl for lbl in sec["labels"]} for g, sec in subtype_sections.items()}
    per_group_split = {
        g: {s: sum(1 for r in by_split[s] if r.group == g) for s in SPLITS} for g in GROUPS
    }

    return {
        "format_version": MANIFEST_FORMAT_VERSION,
        "candidate_status": "trained_candidate",
        "dataset_root": str(dataset_root),
        "group_labels": GROUPS,
        "feature_config": inference_feature_config(),
        "cache_provenance": {
            "cache_format": CACHE_FORMAT_VERSION,
            "feature_code": FEATURE_CODE_VERSION,
            "dataset_fingerprint": fingerprint,
        },
        "group_model": {
            "model_file": "group_model.keras",
            "labels": GROUPS,
            "threshold": {"minimum_confidence": group_thr, **group_status},
            "test_evaluation": group_eval,
        },
        "subtype_models": subtype_sections,
        "dataset_provenance": {
            "subclass_label_mappings": mappings,
            "recordings_per_group_per_split": per_group_split,
            "split_recording_counts": {s: len(by_split[s]) for s in SPLITS},
            "split_report": split_report,
        },
    }


def run(args: argparse.Namespace) -> None:
    validate_args(args)
    seed_everything(SEED)
    run_pipeline_smoke_test()

    if args.dry_run_train:
        print("Dry run completed. No artifacts written.")
        return

    dataset_root = args.dataset.resolve()
    records = discover_records(dataset_root)
    records, split_report = assign_splits(
        records, SEED, args.max_split_deviation, args.accept_split_deviation
    )

    if args.check_only:
        print("Split check completed. No cache or models were built.")
        return

    output_dir = args.output.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Output directory '{output_dir}' already exists and is not empty. "
            "Pass a new versioned folder via --output."
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    fingerprint = dataset_fingerprint(records)
    cache = build_cache(records, args.cache.resolve())

    staging = output_dir.parent / f".{output_dir.name}.staging-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        manifest = train_and_export(
            records, cache, args.epochs, staging, dataset_root, split_report, fingerprint
        )
        write_json_atomic(staging / "manifest.json", manifest)
        if output_dir.exists():
            output_dir.rmdir()  # removes only an empty directory
        os.replace(staging, output_dir)
    except BaseException as exc:
        if staging.exists():
            quarantine(staging, f"training or export failed: {exc}")
        raise

    print("\n========================================================")
    print(f"Hierarchical training complete. Manifest: {output_dir / 'manifest.json'}")
    print("========================================================")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pest Guard eight-group hierarchical trainer")
    parser.add_argument("--dataset", type=Path, required=True,
                        help="Root folder containing the eight class directories.")
    parser.add_argument("--output", type=Path,
                        default=Path("backend/ai_model/pest_guard_8group_production"))
    parser.add_argument("--cache", type=Path, default=Path("backend/ai_model/_feature_cache"))
    parser.add_argument("--epochs", type=int, default=MAX_EPOCHS,
                        help="Training epochs (at least 1).")
    parser.add_argument("--max-split-deviation", type=float, default=DEFAULT_MAX_SPLIT_DEVIATION,
                        help="Allowed per-class deviation from 80/10/10, as a fraction between 0 and 1.")
    parser.add_argument("--accept-split-deviation", action="store_true",
                        help="Proceed when classes exceed the tolerance. Actual ratios are recorded in the manifest.")
    parser.add_argument("--check-only", action="store_true",
                        help="Validate the dataset and print the split table, then exit.")
    parser.add_argument("--dry-run-train", action="store_true",
                        help="Run the pipeline smoke test and exit.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()