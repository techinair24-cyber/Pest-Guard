#!/usr/bin/env python3
"""Safely connect Pest Guard's trained experimental background gate to the API.

Run from the Pest guard project root:
    python .\\connect_background_gate.py

Creates timestamped backups of backend/main.py and backend/requirements.txt.
It does not modify the active 47-class insect model or ESP32 firmware.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path

GATE_RELATIVE = Path("backend/ai_model/yamnet_background_gate_pilot/background_gate.joblib")
THRESHOLD = "0.30"

INJECTION = r'''# --- Pest Guard experimental insect/background gate ---
# This binary gate must accept the audio before the 47-class insect model runs.
# A rejection raises HTTP 422 here, before the API can save or broadcast a detection.
_PEST_BACKGROUND_GATE = None
_PEST_YAMNET_MODEL = None
_PEST_BACKGROUND_GATE_LOCK = __import__("threading").Lock()
_PEST_BACKGROUND_GATE_THRESHOLD = float(os.getenv("PEST_BACKGROUND_GATE_THRESHOLD", "0.30"))
_PEST_BACKGROUND_GATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ai_model", "yamnet_background_gate_pilot", "background_gate.joblib",
)


def _load_pest_background_gate():
    global _PEST_BACKGROUND_GATE, _PEST_YAMNET_MODEL
    if _PEST_BACKGROUND_GATE is not None and _PEST_YAMNET_MODEL is not None:
        return _PEST_BACKGROUND_GATE, _PEST_YAMNET_MODEL

    with _PEST_BACKGROUND_GATE_LOCK:
        if _PEST_BACKGROUND_GATE is not None and _PEST_YAMNET_MODEL is not None:
            return _PEST_BACKGROUND_GATE, _PEST_YAMNET_MODEL

        if not os.path.isfile(_PEST_BACKGROUND_GATE_PATH):
            logger.error("Pest Guard background gate file is missing: %s", _PEST_BACKGROUND_GATE_PATH)
            raise HTTPException(
                status_code=503,
                detail="Background sound filter is not installed on this backend.",
            )

        try:
            import joblib
            import tensorflow_hub as hub
            gate = joblib.load(_PEST_BACKGROUND_GATE_PATH)
            yamnet = hub.load("https://tfhub.dev/google/yamnet/1")
        except Exception as error:
            logger.exception("Could not load Pest Guard background gate")
            raise HTTPException(
                status_code=503,
                detail="Background sound filter failed to load.",
            ) from error

        _PEST_BACKGROUND_GATE = gate
        _PEST_YAMNET_MODEL = yamnet
        logger.info("Pest Guard background gate loaded (threshold=%.2f)", _PEST_BACKGROUND_GATE_THRESHOLD)
        return _PEST_BACKGROUND_GATE, _PEST_YAMNET_MODEL


def _pest_background_gate_score(waveform):
    """Return the experimental insect-like score using training-matched framing."""
    gate, yamnet = _load_pest_background_gate()
    audio = np.asarray(waveform, dtype=np.float32).reshape(-1)
    target_length = 80000  # 5 seconds at the backend's 16 kHz sample rate

    if audio.size < SAMPLE_RATE:
        raise HTTPException(status_code=422, detail="Audio must contain at least one second of samples.")
    if audio.size > target_length:
        audio = audio[:target_length]
    elif audio.size < target_length:
        padded = np.zeros(target_length, dtype=np.float32)
        padded[:audio.size] = audio
        audio = padded

    # Match the exact peak-normalization used when the gate was trained and tested.
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak

    try:
        _, embeddings, _ = yamnet(audio)
        vector = tf.reduce_mean(embeddings, axis=0).numpy().reshape(1, -1)
        probabilities = np.asarray(gate.predict_proba(vector), dtype=np.float64)
        if probabilities.ndim != 2 or probabilities.shape[0] != 1 or probabilities.shape[1] < 2:
            raise RuntimeError("Background gate returned an unexpected probability shape.")
        score = float(probabilities[0, 1])
        if not np.isfinite(score) or score < 0.0 or score > 1.0:
            raise RuntimeError("Background gate returned an invalid score.")
        return score
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Pest Guard background-gate scoring failed")
        raise HTTPException(
            status_code=503,
            detail="Background sound filter could not score this recording.",
        ) from error


# --- End experimental insect/background gate ---

'''


def locate_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "backend" / "main.py").is_file():
        return cwd
    script_root = Path(__file__).resolve().parent
    if (script_root / "backend" / "main.py").is_file():
        return script_root
    raise RuntimeError("Run this script from the Pest guard project root (the folder containing backend\\main.py).")


def backup(path: Path, stamp: str) -> Path:
    out = path.with_name(path.name + f".before_background_gate_{stamp}.bak")
    if out.exists():
        raise RuntimeError(f"Backup already exists; refusing to overwrite it: {out}")
    shutil.copy2(path, out)
    return out


def requirements_additions(req_path: Path) -> tuple[str, list[str]]:
    original = req_path.read_text(encoding="utf-8-sig") if req_path.exists() else ""
    normalized = {}
    for line in original.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "-")):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", s)
        if match:
            normalized[re.sub(r"[-_.]+", "-", match.group(1)).lower()] = s

    needed = [
        ("tensorflow-hub", "tensorflow-hub==0.16.1"),
        ("scikit-learn", "scikit-learn==1.9.0"),
        ("joblib", "joblib==1.6.0"),
    ]
    additions = []
    notes = []
    for name, pinned in needed:
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key not in normalized:
            additions.append(pinned)
        else:
            notes.append(f"Found existing dependency declaration: {normalized[key]}")
    if not additions:
        return original, notes
    prefix = "" if not original or original.endswith("\n") else "\n"
    new_text = original + prefix + "\n# Dependencies for the Pest Guard experimental background gate\n" + "\n".join(additions) + "\n"
    return new_text, notes


def main() -> int:
    root = locate_root()
    main_path = root / "backend" / "main.py"
    req_path = root / "backend" / "requirements.txt"
    gate_path = root / GATE_RELATIVE

    if not gate_path.is_file():
        raise RuntimeError(
            f"Trained gate file was not found: {gate_path}\n"
            "Run the background-gate trainer first. No source code was changed."
        )

    source = main_path.read_text(encoding="utf-8-sig")
    if "_pest_background_gate_score" in source or "_PEST_BACKGROUND_GATE_PATH" in source:
        raise RuntimeError("A background-gate integration marker already exists in backend/main.py; refusing to duplicate it.")

    predictor_marker = "def predict_pest(audio):"
    if source.count(predictor_marker) != 1:
        raise RuntimeError("Could not uniquely locate def predict_pest(audio): in backend/main.py; no source code was changed.")
    decode_marker = "    waveform = decode_audio_samples(audio)"
    if source.count(decode_marker) != 1:
        raise RuntimeError("Could not uniquely locate the waveform decode line inside predict_pest(); no source code was changed.")
    if "import os" not in source.split("def decode_audio_samples", 1)[0]:
        raise RuntimeError("backend/main.py does not appear to import os; no source code was changed.")
    if "import numpy as np" not in source.split("def decode_audio_samples", 1)[0]:
        raise RuntimeError("backend/main.py does not appear to import numpy as np; no source code was changed.")
    if "import tensorflow as tf" not in source.split("def decode_audio_samples", 1)[0]:
        raise RuntimeError("backend/main.py does not appear to import tensorflow as tf; no source code was changed.")
    if "HTTPException" not in source.split("def decode_audio_samples", 1)[0]:
        raise RuntimeError("HTTPException is not imported/available in backend/main.py; no source code was changed.")
    if "logger" not in source[:source.find("def decode_audio_samples")]:
        raise RuntimeError("Could not confirm a logger is initialized before the prediction functions; no source code was changed.")

    updated = source.replace(predictor_marker, INJECTION + predictor_marker, 1)
    score_call = (
        decode_marker + "\n"
        "    gate_score = _pest_background_gate_score(waveform)\n"
        "    if gate_score < _PEST_BACKGROUND_GATE_THRESHOLD:\n"
        "        logger.info(\"Background gate rejected audio (score=%.4f, threshold=%.2f)\", gate_score, _PEST_BACKGROUND_GATE_THRESHOLD)\n"
        "        raise HTTPException(\n"
        "            status_code=422,\n"
        "            detail=\"Audio rejected by background-sound filter. No detection was saved.\",\n"
        "        )\n"
        "    logger.info(\"Background gate accepted audio (score=%.4f, threshold=%.2f)\", gate_score, _PEST_BACKGROUND_GATE_THRESHOLD)"
    )
    updated = updated.replace(decode_marker, score_call, 1)

    # Validate syntax before writing any files.
    compile(updated, str(main_path), "exec")
    req_updated, requirement_notes = requirements_additions(req_path)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backups: list[Path] = []
    try:
        backups.append(backup(main_path, stamp))
        if req_path.exists() and req_updated != req_path.read_text(encoding="utf-8-sig"):
            backups.append(backup(req_path, stamp))
        main_path.write_text(updated, encoding="utf-8", newline="")
        if req_updated != (req_path.read_text(encoding="utf-8-sig") if req_path.exists() else ""):
            req_path.write_text(req_updated, encoding="utf-8", newline="")
        # Read back and compile what was actually written.
        compile(main_path.read_text(encoding="utf-8"), str(main_path), "exec")
    except Exception:
        # Roll back source files if any write or verification fails.
        for b in backups:
            original = b.name.split(".before_background_gate_", 1)[0]
            target = b.with_name(original)
            shutil.copy2(b, target)
        raise

    print("BACKGROUND GATE INTEGRATION PATCH APPLIED")
    print(f"Backend updated: {main_path}")
    print(f"Gate model: {gate_path}")
    print(f"Threshold: {THRESHOLD} (override with PEST_BACKGROUND_GATE_THRESHOLD)")
    print("Rejected audio raises HTTP 422 before classification, database commit, and WebSocket broadcast.")
    print("Backups:")
    for b in backups:
        print(f"  {b}")
    for note in requirement_notes:
        print(f"Dependency note: {note}")
    if requirement_notes:
        print("If an existing dependency is pinned to a different version, verify that version can load the saved gate artifact before deploying.")
    print("Not modified: best_candidate.keras, ESP32 firmware, database, or deployment service.")
    print("NEXT: run tests locally, then deploy backend and only after deployment succeeds re-enable live ESP32 requests.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PREPARATION FAILED SAFELY: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
