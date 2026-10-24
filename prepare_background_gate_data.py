"""Prepare data for Pest Guard's experimental insect/background gate.

Run from the Pest guard project root with:
    python .\\prepare_background_gate_data.py

This script creates new files only. It does not edit main.py, the active
insect classifier, firmware, or the original gate pilot script.
"""
from __future__ import annotations

import csv
import io
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

METADATA_URL = "https://raw.githubusercontent.com/karolpiczak/ESC-50/master/meta/esc50.csv"
RAW_AUDIO_BASE = "https://raw.githubusercontent.com/karolpiczak/ESC-50/master/audio/"
SEED = 459
FILES_PER_CATEGORY = 20
BACKGROUND_CATEGORIES = (
    "rain",
    "wind",
    "water_drops",
    "thunderstorm",
    "breathing",
    "coughing",
    "footsteps",
    "keyboard_typing",
    "vacuum_cleaner",
    "clock_alarm",
    "mouse_click",
    "washing_machine",
    "car_horn",
    "engine",
    "siren",
)


def fetch_bytes(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PestGuard-BackgroundGate-Prep/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def find_project_root() -> Path:
    here = Path.cwd().resolve()
    if (here / "backend" / "main.py").is_file():
        return here
    if Path(__file__).resolve().parent.joinpath("backend", "main.py").is_file():
        return Path(__file__).resolve().parent
    raise RuntimeError(
        "Run this script from the Pest guard project root, the folder that contains backend\\main.py."
    )


def prepare_background_audio() -> tuple[int, int]:
    target = Path.home() / "Desktop" / "InsectSound1000_Training" / "ESC50_background_pilot"
    target.mkdir(parents=True, exist_ok=True)
    print(f"Background WAV folder: {target}")
    print("Fetching ESC-50 metadata...")
    try:
        metadata_text = fetch_bytes(METADATA_URL).decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"Could not fetch ESC-50 metadata: {exc}") from exc

    rows = list(csv.DictReader(io.StringIO(metadata_text)))
    if not rows or not {"filename", "category"}.issubset(rows[0]):
        raise RuntimeError("ESC-50 metadata format was not recognized.")

    grouped: dict[str, list[str]] = {}
    for row in rows:
        category = row.get("category", "").strip()
        filename = row.get("filename", "").strip()
        if category in BACKGROUND_CATEGORIES and filename:
            grouped.setdefault(category, []).append(filename)

    missing_categories = sorted(set(BACKGROUND_CATEGORIES) - set(grouped))
    if missing_categories:
        raise RuntimeError(
            "These requested categories were not found in ESC-50 metadata: "
            + ", ".join(missing_categories)
        )

    rng = random.Random(SEED)
    selected: list[tuple[str, str]] = []
    for category in BACKGROUND_CATEGORIES:
        files = sorted(grouped[category])
        rng.shuffle(files)
        if len(files) < FILES_PER_CATEGORY:
            raise RuntimeError(
                f"ESC-50 category {category!r} only has {len(files)} files; "
                f"need {FILES_PER_CATEGORY}."
            )
        selected.extend((category, name) for name in files[:FILES_PER_CATEGORY])

    def download_one(item: tuple[str, str]) -> tuple[str, str | None]:
        category, filename = item
        destination = target / filename
        if destination.exists() and destination.stat().st_size > 1000:
            return filename, None
        try:
            data = fetch_bytes(RAW_AUDIO_BASE + filename, timeout=60)
            if len(data) < 1000 or not data.startswith(b"RIFF"):
                raise RuntimeError("downloaded content does not look like a WAV file")
            temp_path = destination.with_suffix(destination.suffix + ".part")
            temp_path.write_bytes(data)
            temp_path.replace(destination)
            return filename, None
        except Exception as exc:
            return filename, f"{category}: {exc}"

    print(
        f"Downloading up to {len(selected)} recordings from "
        f"{len(BACKGROUND_CATEGORIES)} non-insect categories..."
    )
    failed: list[tuple[str, str]] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(download_one, item) for item in selected]
        for future in as_completed(futures):
            filename, error = future.result()
            completed += 1
            if error:
                failed.append((filename, error))
            if completed % 25 == 0 or completed == len(futures):
                print(f"Background recordings checked: {completed}/{len(futures)}")

    if failed:
        example = "\n".join(f"  {name}: {why}" for name, why in failed[:8])
        raise RuntimeError(
            f"{len(failed)} audio download(s) failed. Partial downloads were kept "
            f"so you can safely retry this script. Examples:\n{example}"
        )

    # Defensive check: don't silently label known insect/cricket classes as background.
    actual_categories = {
        row["filename"]: row["category"]
        for row in rows
        if row.get("filename") and row.get("category")
    }
    chosen_categories = {actual_categories.get(name) for _, name in selected}
    if chosen_categories.intersection({"insects", "crickets"}):
        raise RuntimeError("Safety check failed: insect/cricket recordings were selected as background.")

    print(f"Background audio ready: {len(selected)} selected WAV files.")
    print("Excluded categories: insects, crickets.")
    return len(selected), len(BACKGROUND_CATEGORIES)


def create_compatible_manifest(project: Path) -> tuple[int, int]:
    dataset_root = Path.home() / "Desktop" / "Pest_Guard_New_Datasets"
    source_manifest = (
        project / "backend" / "ai_model" / "pest_new_dataset_candidate" / "split_manifest.json"
    )
    output_manifest = project / "backend" / "ai_model" / "combined_split_manifest.json"

    if not source_manifest.is_file():
        raise RuntimeError(f"Existing candidate manifest not found: {source_manifest}")
    if not dataset_root.is_dir():
        raise RuntimeError(f"Dataset folder not found: {dataset_root}")
    if output_manifest.exists():
        raise RuntimeError(
            f"Refusing to overwrite existing file: {output_manifest}. "
            "Rename it only after verifying it is safe to replace."
        )

    source_rows = json.loads(source_manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(source_rows, list):
        raise RuntimeError("Candidate manifest is not a flat list as expected.")

    by_split: dict[str, list[dict[str, object]]] = {"train": [], "validation": []}
    split_counts: dict[str, int] = {}
    missing_audio: list[str] = []

    for row in source_rows:
        if not isinstance(row, dict):
            continue
        split_raw = str(row.get("split", "")).strip().lower()
        split_counts[split_raw] = split_counts.get(split_raw, 0) + 1
        if split_raw in {"train", "training"}:
            split = "train"
        elif split_raw in {"validation", "valid", "val", "dev"}:
            split = "validation"
        else:
            continue

        filename = row.get("file") or row.get("path")
        class_index = row.get("class_index", row.get("label_index"))
        if not filename or class_index is None:
            raise RuntimeError("A candidate manifest record is missing file/path or class_index/label_index.")

        relative = Path(str(filename).replace("\\", os.sep).replace("/", os.sep))
        audio_path = relative if relative.is_absolute() else dataset_root / relative
        if not audio_path.is_file():
            missing_audio.append(str(audio_path))
            continue

        by_split[split].append({
            "path": str(audio_path.resolve()),
            "label_index": int(class_index),
            "scientific_name": str(row.get("scientific_name", "")),
            "split": split,
        })

    if missing_audio:
        sample = "\n".join(f"  {path}" for path in missing_audio[:8])
        raise RuntimeError(
            f"{len(missing_audio)} training/validation audio path(s) were not found. "
            f"No new manifest was written. Examples:\n{sample}"
        )
    if not by_split["train"] or not by_split["validation"]:
        raise RuntimeError(
            f"Could not build train/validation rows. Manifest split values found: {split_counts}"
        )

    # Validate the sampling quotas the gate trainer will use.
    for class_index in sorted({int(r["label_index"]) for r in by_split["train"]}):
        n_train = sum(int(r["label_index"]) == class_index for r in by_split["train"])
        n_val = sum(int(r["label_index"]) == class_index for r in by_split["validation"])
        if n_train < 5 or n_val < 2:
            raise RuntimeError(
                f"Class index {class_index} has only {n_train} train and {n_val} validation files; "
                "the gate pilot expects at least 5 and 2 respectively. No manifest was written."
            )

    output_manifest.write_text(
        json.dumps({"train": by_split["train"], "validation": by_split["validation"]}, indent=2),
        encoding="utf-8",
    )
    print(f"Created compatible manifest: {output_manifest}")
    print(f"Training recordings: {len(by_split['train'])}")
    print(f"Validation recordings: {len(by_split['validation'])}")
    print(f"Skipped non-train/validation splits: {split_counts}")
    return len(by_split["train"]), len(by_split["validation"])


def create_wav_compatible_trainer(project: Path) -> Path:
    original = project / "backend" / "train_background_gate_pilot.py"
    destination = project / "backend" / "train_background_gate_pilot_wav.py"
    if not original.is_file():
        raise RuntimeError(f"Original gate pilot script not found: {original}")
    if destination.exists():
        raise RuntimeError(
            f"Refusing to overwrite existing file: {destination}. "
            "No original project code has been changed."
        )

    source = original.read_text(encoding="utf-8")
    if "import librosa" not in source:
        if "import joblib\n" not in source:
            raise RuntimeError("Could not safely locate the import section in the original gate script.")
        source = source.replace("import joblib\n", "import joblib\nimport librosa\n", 1)

    old_loader_start = source.find("def load_insect_audio(row):")
    old_loader_end = source.find("\ndef load_background_audio", old_loader_start)
    if old_loader_start < 0 or old_loader_end < 0:
        raise RuntimeError("Could not safely identify the insect audio loader to adapt.")
    new_loader = '''def load_insect_audio(row):
    # Existing manifest entries are source WAV files, not prepared .npy arrays.
    # Load/resample them the same way as training, then make a five-second clip.
    audio, _ = librosa.load(
        str(Path(row["path"])),
        sr=SAMPLE_RATE,
        mono=True,
    )
    return prepare_waveform(audio, SAMPLE_RATE)

'''
    source = source[:old_loader_start] + new_loader + source[old_loader_end + 1:]

    old_split = '''        # Keep different files from each category in each split.
        train_files.extend(paths[: max(1, len(paths) - 1)])
        validation_files.append(paths[-1])'''
    new_split = '''        # Use a held-out 20% from every background category, not one file only.
        split_index = max(1, min(len(paths) - 1, int(round(len(paths) * 0.8))))
        train_files.extend(paths[:split_index])
        validation_files.extend(paths[split_index:])'''
    if old_split not in source:
        raise RuntimeError("Could not safely identify the background split logic to adapt.")
    source = source.replace(old_split, new_split, 1)
    source = source.replace(
        '"Small pilot only. ESC-50 validation clips are limited "',
        '"Experimental pilot. ESC-50 sounds are a limited proxy and do not represent all field environments. "',
        1,
    )
    destination.write_text(source, encoding="utf-8")
    print(f"Created separate WAV-compatible trainer: {destination}")
    print("Original train_background_gate_pilot.py was not modified.")
    return destination


def main() -> int:
    try:
        project = find_project_root()
        print(f"Project root: {project}")
        print("This setup will not edit main.py, the active candidate model, or ESP32 firmware.")
        background_count, category_count = prepare_background_audio()
        train_count, validation_count = create_compatible_manifest(project)
        trainer = create_wav_compatible_trainer(project)
        summary = {
            "background_audio_files_selected": background_count,
            "background_categories": category_count,
            "background_folder": str(Path.home() / "Desktop" / "InsectSound1000_Training" / "ESC50_background_pilot"),
            "insect_train_records": train_count,
            "insect_validation_records": validation_count,
            "compatible_manifest": str(project / "backend" / "ai_model" / "combined_split_manifest.json"),
            "trainer": str(trainer),
            "production_backend_modified": False,
            "active_insect_model_modified": False,
            "firmware_modified": False,
            "note": "Preparation only. The gate must be trained and evaluated before any production integration.",
        }
        report = project / "backend" / "ai_model" / "background_gate_preparation_report.json"
        if report.exists():
            report = project / "backend" / "ai_model" / "background_gate_preparation_report_new.json"
        report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("\n--- PREPARATION SUMMARY ---")
        print(json.dumps(summary, indent=2))
        print("\nPreparation is complete. The background gate has NOT been trained or connected to the API.")
        return 0
    except (RuntimeError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"\nPREPARATION STOPPED SAFELY: {exc}", file=sys.stderr)
        print("Any downloaded WAV files are kept for retry. Existing model/backend/firmware remain unchanged.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
