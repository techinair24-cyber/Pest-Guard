from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    root = Path.cwd()
    if not (root / ".git").exists() or not (root / "backend" / "main.py").is_file():
        fail("Run this script from the Pest guard repository root (the folder containing .git and backend/main.py).")

    backend = root / "backend"
    main_path = backend / "main.py"
    requirements_path = backend / "requirements.txt"
    candidate_dir = backend / "ai_model" / "pest_new_dataset_candidate"
    classes_path = candidate_dir / "class_names.json"
    common_path = candidate_dir / "common_names.json"

    for path in (main_path, requirements_path, classes_path, common_path):
        if not path.is_file():
            fail(f"Required file missing: {path.relative_to(root)}")

    classes = json.loads(classes_path.read_text(encoding="utf-8"))
    common_names = json.loads(common_path.read_text(encoding="utf-8"))
    if not isinstance(classes, list) or not isinstance(common_names, list):
        fail("class_names.json and common_names.json must both contain JSON arrays.")
    if len(classes) != 47 or len(common_names) != 47 or len(classes) != len(common_names):
        fail(f"Expected exactly 47 matched classes/common names, got {len(classes)} and {len(common_names)}.")
    if not all(isinstance(x, str) and x.strip() for x in classes + common_names):
        fail("The class and common-name arrays contain an empty or invalid value.")

    # Keep the original backend in TEMP in case the user wants to review/undo the edit.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = Path(os.environ.get("TEMP", str(root))) / f"pest_guard_main_pre_47class_{stamp}.py"
    old_main = main_path.read_text(encoding="utf-8")
    old_requirements = requirements_path.read_text(encoding="utf-8")
    backup.write_text(old_main, encoding="utf-8")

    # The supplied common-name list is the source of display labels. Do not infer an agricultural
    # risk tier where no species-specific evidence has been verified.
    metadata = []
    for scientific, common in zip(classes, common_names):
        is_taxonomically_qualified = bool(re.search(r"(?:^|\s)(?:sp\.|cf\.)(?:\s|$)", scientific, re.IGNORECASE))
        query = quote(scientific, safe="")
        aliases = [common] if common.casefold() != scientific.casefold() else []
        metadata.append({
            "model_class": scientific,
            "scientific_name": None if is_taxonomically_qualified else scientific,
            "common_name": common,
            "aliases": aliases,
            "risk": "UNKNOWN",
            "risk_rationale": "No species-specific crop-risk category has been verified for this model label. Treat the sound-model result as an unverified candidate, not a confirmed pest identification.",
            "affected_crops": [],
            "source_name": "GBIF taxonomic search",
            "source_url": f"https://api.gbif.org/v1/species/search?q={query}&limit=5",
            "geographic_limitations": "Agricultural impact depends on the exact species and region; no crop-specific impact has been verified for this metadata entry."
        })
    metadata_path = candidate_dir / "class_metadata.json"
    old_metadata = metadata_path.read_text(encoding="utf-8") if metadata_path.exists() else None
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Replace the old dual-model loader with a fail-closed loader for the selected 47-class model.
    try:
        start_marker = "PEST_MODEL = os.getenv("
        metadata_marker = "MODEL_SPECIES_METADATA = {}"
        mel_marker = "MEL_MATRIX = tf.signal.linear_to_mel_weight_matrix("
        start = old_main.index(start_marker)
        metadata_start = old_main.index(metadata_marker, start)
        mel_start = old_main.index(mel_marker, metadata_start)

        loader = '''PEST_MODEL = os.getenv("PEST_MODEL", "new_dataset_candidate").strip().lower()
if PEST_MODEL != "new_dataset_candidate":
    raise RuntimeError(
        "Only PEST_MODEL=new_dataset_candidate is supported; obsolete model paths have been removed."
    )

AI_DIR = Path(__file__).resolve().parent / "ai_model"
CANDIDATE_DIR = AI_DIR / "pest_new_dataset_candidate"
ai_model = tf.keras.models.load_model(
    CANDIDATE_DIR / "best_candidate.keras",
    compile=False,
)
with open(CANDIDATE_DIR / "class_names.json", "r", encoding="utf-8") as f:
    class_names = json.load(f)
with open(CANDIDATE_DIR / "common_names.json", "r", encoding="utf-8") as f:
    common_names = json.load(f)
if len(common_names) != len(class_names):
    raise RuntimeError("Candidate common names do not match model classes.")
if len(class_names) != 47:
    raise RuntimeError(f"Expected 47 model classes, found {len(class_names)}.")
print(f"Loaded NEW candidate model: {len(class_names)} species")

'''
        text = old_main[:start] + loader + old_main[metadata_start:]
        metadata_start = text.index(metadata_marker)
        mel_start = text.index(mel_marker, metadata_start)
        new_metadata_load = '''MODEL_SPECIES_METADATA = {}
metadata_path = CANDIDATE_DIR / "class_metadata.json"
with open(metadata_path, "r", encoding="utf-8") as f:
    metadata_entries = json.load(f)

expected_labels = {_normalize_pest_label(label) for label in class_names}
for entry in metadata_entries:
    model_class = entry.get("model_class")
    if not isinstance(model_class, str) or not model_class.strip():
        raise RuntimeError("Model metadata contains an invalid model_class.")
    normalized_class = _normalize_pest_label(model_class)
    if normalized_class not in expected_labels:
        raise RuntimeError(
            f"Model metadata contains an inactive class: {model_class}"
        )
    if normalized_class in MODEL_SPECIES_METADATA:
        raise RuntimeError(
            f"Model metadata contains a duplicate class: {model_class}"
        )
    if entry.get("risk") not in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}:
        raise RuntimeError(
            f"Model metadata has an invalid risk for {model_class}."
        )
    if not str(entry.get("common_name") or "").strip():
        raise RuntimeError(
            f"Model metadata is missing a common-name fallback for {model_class}."
        )
    if not str(entry.get("source_name") or "").strip() or not str(
        entry.get("source_url") or ""
    ).startswith("https://"):
        raise RuntimeError(
            f"Model metadata is missing a source for {model_class}."
        )
    if not str(entry.get("risk_rationale") or "").strip():
        raise RuntimeError(
            f"Model metadata is missing a risk rationale for {model_class}."
        )
    if not isinstance(entry.get("affected_crops"), list):
        raise RuntimeError(
            f"Model metadata has invalid affected crops for {model_class}."
        )
    MODEL_SPECIES_METADATA[normalized_class] = entry

missing_labels = expected_labels - set(MODEL_SPECIES_METADATA)
if missing_labels:
    raise RuntimeError(
        "Model metadata is missing active classes: "
        + ", ".join(sorted(missing_labels))
    )

MODEL_SPECIES_METADATA_BY_NAME = {}
for metadata in MODEL_SPECIES_METADATA.values():
    for name in (
        metadata.get("model_class"),
        metadata.get("scientific_name"),
        metadata.get("common_name"),
        *(metadata.get("aliases") or []),
    ):
        normalized_name = _normalize_pest_label(name)
        if normalized_name:
            MODEL_SPECIES_METADATA_BY_NAME.setdefault(
                normalized_name,
                metadata,
            )

'''
        text = text[:metadata_start] + new_metadata_load + text[mel_start:]

        # Remove the alternate YAMNet inference path and use the candidate's CNN preprocessing.
        fn_start = text.index("def predict_pest(audio):")
        fn_end = text.index("class AISolutionRequest", fn_start)
        new_fn = '''def predict_pest(audio):
    waveform = decode_audio_samples(audio)
    features = prepare_audio(waveform)
    prediction = ai_model.predict(
        tf.expand_dims(features, 0),
        verbose=0,
    )[0]

    prediction = np.asarray(prediction, dtype=np.float32)
    if prediction.shape != (len(class_names),):
        raise RuntimeError(
            "Model output does not match the class labels."
        )
    if not np.all(np.isfinite(prediction)):
        raise RuntimeError("Model output contains non-finite scores.")

    index = int(np.argmax(prediction))
    return {
        "pest": class_names[index],
        "confidence": float(prediction[index]),
    }


'''
        text = text[:fn_start] + new_fn + text[fn_end:]

        old_shape = "if not USE_YAMNET and ai_model.input_shape != (None, 155, 128, 1):"
        if old_shape not in text:
            raise ValueError("Could not find the expected legacy model-input validation line.")
        text = text.replace(old_shape, "if ai_model.input_shape != (None, 155, 128, 1):", 1)
        old_logger = '"yamnet" if USE_YAMNET else "cnn",'
        if old_logger not in text:
            raise ValueError("Could not find the expected legacy model logger label.")
        text = text.replace(old_logger, "PEST_MODEL,", 1)

        legacy_patterns = [r"\bUSE_YAMNET\b", r"\bYAMNET_DIR\b", r"\bYAMNET_CLASS_NAMES\b", r"best_cnn_v3", r"tensorflow_hub", r"\byamnet\b"]
        remaining = [pattern for pattern in legacy_patterns if re.search(pattern, text, re.IGNORECASE)]
        if remaining:
            raise ValueError("Legacy model references remain in main.py: " + ", ".join(remaining))

        main_path.write_text(text, encoding="utf-8")

        # Remove tensorflow-hub only when no other tracked source references it.
        outside_refs = subprocess.run(
            ["git", "grep", "-n", "-E", "tensorflow_hub|tensorflow-hub|tfhub.dev", "--", ".", ":!backend/main.py", ":!backend/requirements.txt"],
            cwd=root,
            text=True,
            capture_output=True,
        )
        requirements = old_requirements
        if outside_refs.returncode == 1:
            requirements = re.sub(r"(?im)^\s*tensorflow-hub\s*\r?\n", "", requirements)
            requirements_path.write_text(requirements, encoding="utf-8")
        elif outside_refs.returncode == 0:
            print("Keeping tensorflow-hub in requirements because other tracked files still reference it:")
            print(outside_refs.stdout.strip())
        else:
            raise RuntimeError("Could not check repository for remaining TensorFlow Hub references.")

        # Syntax-check before removing obsolete trained artifacts.
        compile_result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(main_path)],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if compile_result.returncode != 0:
            raise RuntimeError("Python syntax check failed: " + compile_result.stderr)

        # Permanently remove obsolete active model files from the working tree and stage deletions.
        obsolete = [
            "backend/ai_model/best_cnn_v3.keras",
            "backend/ai_model/class_names.json",
            "backend/ai_model/pest_yamnet_updated_candidate",
        ]
        existing = [p for p in obsolete if (root / p).exists()]
        if existing:
            subprocess.run(["git", "rm", "-rf", "--", *existing], cwd=root, check=True)

        # Ensure the candidate metadata remains present and complete after the changes.
        final_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if len(final_metadata) != 47:
            raise RuntimeError("Final candidate metadata does not contain 47 records.")
        for entry in final_metadata:
            if entry.get("risk") != "UNKNOWN" or not entry.get("common_name") or not entry.get("source_url", "").startswith("https://"):
                raise RuntimeError("Candidate metadata validation failed.")

    except Exception as exc:
        # Roll source files back if edits did not complete; don't restore deleted models automatically.
        main_path.write_text(old_main, encoding="utf-8")
        requirements_path.write_text(old_requirements, encoding="utf-8")
        if old_metadata is None:
            metadata_path.unlink(missing_ok=True)
        else:
            metadata_path.write_text(old_metadata, encoding="utf-8")
        fail(f"Cleanup stopped and source edits were rolled back: {exc}. Main backup: {backup}")

    print("\nSUCCESS")
    print("- Backend now loads only the 47-class new_dataset_candidate model.")
    print("- Generated matching metadata for all 47 classes.")
    print("- Unverified crop-risk labels remain UNKNOWN; no risk tiers were guessed.")
    print("- Removed and staged obsolete CNN/YAMNet model artifacts.")
    print("- Python syntax check passed.")
    print(f"- Backup of the previous main.py: {backup}")
    print("\nNext: review `git status --short`, run the backend tests, then commit and push.")


if __name__ == "__main__":
    main()
