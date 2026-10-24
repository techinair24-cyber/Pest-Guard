#!/usr/bin/env python3
"""
Build a safe, index-only Pest Guard audio library from the existing 47-class manifest.

This script does not move/copy audio, retrain or replace a model, or modify the backend/UI.
Run from the Pest Guard project root:
    python backend/tools/build_pest_audio_library.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "backend" / "ai_model" / "pest_new_dataset_candidate"
MANIFEST = MODEL_DIR / "split_manifest.json"
CLASS_NAMES = MODEL_DIR / "class_names.json"
COMMON_NAMES = MODEL_DIR / "common_names.json"
METADATA = MODEL_DIR / "class_metadata.json"
OUTPUT_DIR = ROOT / "backend" / "ai_model" / "pest_audio_library"


def read_json(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_name_list(path: Path):
    if not path.is_file():
        return []
    data = read_json(path)
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict):
        # Preserve class-index order for mappings such as {"0": "...", ...}.
        try:
            return [str(v) for k, v in sorted(data.items(), key=lambda item: int(item[0]))]
        except (TypeError, ValueError):
            return [str(v) for v in data.values()]
    return []


def main():
    manifest = read_json(MANIFEST)
    if not isinstance(manifest, list):
        raise ValueError("split_manifest.json must contain a list of recording entries.")

    class_names = load_name_list(CLASS_NAMES)
    common_names = load_name_list(COMMON_NAMES)
    metadata = read_json(METADATA) if METADATA.is_file() else {}

    # Metadata can have different shapes across versions; keep it as source data
    # and use manifest labels as the primary record-level source.
    rows = []
    species = {}
    missing = []
    split_counts = Counter()
    species_split_counts = defaultdict(Counter)
    seen_paths = set()

    for index, entry in enumerate(manifest):
        if not isinstance(entry, dict):
            continue

        rel = str(entry.get("file", "")).strip()
        sci = str(entry.get("scientific_name", "")).strip()
        common = str(entry.get("common_name", "")).strip()
        class_index = entry.get("class_index")
        split = str(entry.get("split", "unknown")).strip().lower() or "unknown"
        group = str(entry.get("group", "")).strip()

        # Manifest paths are expected to be relative to the project root.
        relative_path = Path(rel.replace("\\", "/")) if rel else None
        candidate = (ROOT / relative_path).resolve() if relative_path else None
        exists = bool(candidate and candidate.is_file())

        # Original recordings are stored beside the project in this folder.
        if not exists and relative_path:
            alternate_root = ROOT.parent / "Pest_Guard_New_Datasets"
            alternate_candidate = (alternate_root / relative_path).resolve()
            if alternate_candidate.is_file():
                candidate = alternate_candidate
                exists = True

        if not exists:
            missing.append(rel)

        try:
            ci = int(class_index)
        except (TypeError, ValueError):
            ci = None

        if ci is not None:
            fallback_sci = class_names[ci] if 0 <= ci < len(class_names) else ""
            if not sci:
                sci = fallback_sci
            fallback_common = common_names[ci] if 0 <= ci < len(common_names) else ""
            if not common:
                common = fallback_common

        species_key = sci or (f"class_{ci}" if ci is not None else "unknown")
        if species_key not in species:
            species[species_key] = {
                "scientific_name": sci or None,
                "common_name": common or None,
                "class_index": ci,
                "recording_count": 0,
                "existing_recording_count": 0,
                "missing_recording_count": 0,
                "splits": {"train": 0, "validation": 0, "test": 0, "other": 0},
                "recordings": [],
            }

        item = {
            "file": rel,
            "resolved_path": str(candidate) if candidate else None,
            "exists": exists,
            "scientific_name": sci or None,
            "common_name": common or None,
            "class_index": ci,
            "group": group or None,
            "split": split,
        }
        species[species_key]["recordings"].append(item)
        species[species_key]["recording_count"] += 1
        species[species_key]["existing_recording_count"] += int(exists)
        species[species_key]["missing_recording_count"] += int(not exists)
        bucket = split if split in ("train", "validation", "test") else "other"
        species[species_key]["splits"][bucket] += 1
        split_counts[split] += 1
        species_split_counts[species_key][split] += 1
        rows.append(item)
        if rel:
            seen_paths.add(rel)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    library = {
        "library_name": "Pest Guard Audio Library",
        "source_manifest": str(MANIFEST.relative_to(ROOT)),
        "source_class_names": str(CLASS_NAMES.relative_to(ROOT)),
        "source_common_names": str(COMMON_NAMES.relative_to(ROOT)),
        "note": (
            "Index only. Audio files are not copied or moved. Missing paths are reported. "
            "Use the existing split labels to avoid mixing train/validation/test data."
        ),
        "summary": {
            "manifest_entries": len(rows),
            "unique_species_labels": len(species),
            "unique_recording_paths": len(seen_paths),
            "existing_audio_files": sum(1 for r in rows if r["exists"]),
            "missing_audio_files": sum(1 for r in rows if not r["exists"]),
            "split_counts": dict(split_counts),
            "class_names_count": len(class_names),
            "common_names_count": len(common_names),
            "metadata_loaded": bool(metadata),
        },
        "species": sorted(species.values(), key=lambda x: (
            x["class_index"] is None,
            x["class_index"] if x["class_index"] is not None else 10**9,
            x["scientific_name"] or "",
        )),
    }

    json_out = OUTPUT_DIR / "library_manifest.json"
    csv_out = OUTPUT_DIR / "recordings_index.csv"
    missing_out = OUTPUT_DIR / "missing_audio_paths.txt"
    summary_out = OUTPUT_DIR / "build_summary.txt"

    with json_out.open("w", encoding="utf-8") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

    with csv_out.open("w", newline="", encoding="utf-8-sig") as f:
        fields = [
            "scientific_name", "common_name", "class_index", "split",
            "group", "file", "resolved_path", "exists",
        ]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    with missing_out.open("w", encoding="utf-8") as f:
        f.write("\n".join(missing))
        if missing:
            f.write("\n")

    summary_lines = [
        "PEST GUARD AUDIO LIBRARY BUILD SUMMARY",
        f"Project root: {ROOT}",
        f"Manifest entries: {len(rows)}",
        f"Unique species labels: {len(species)}",
        f"Unique recording paths: {len(seen_paths)}",
        f"Audio files found: {sum(1 for r in rows if r['exists'])}",
        f"Audio files missing: {sum(1 for r in rows if not r['exists'])}",
        f"Class names: {len(class_names)}",
        f"Common names: {len(common_names)}",
        "",
        "Entries by split:",
    ]
    summary_lines.extend(f"  {k}: {v}" for k, v in sorted(split_counts.items()))
    summary_lines.extend([
        "",
        "Outputs:",
        f"  {json_out}",
        f"  {csv_out}",
        f"  {missing_out}",
        "",
        "No audio files were moved/copied. No model, backend, or UI files were changed.",
    ])
    summary_out.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
