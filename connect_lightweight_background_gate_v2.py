#!/usr/bin/env python3
"""Safely integrate the compact RandomForest gate into Pest Guard.

Run from the project root. Does not use TensorFlow Hub/YAMNet and does not
modify the 47-class insect model or ESP32 firmware.
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

GATE_REL = Path("backend/ai_model/lightweight_background_gate/background_gate.joblib")
THRESHOLD = "0.45"

INJECTION = r'''# --- Pest Guard lightweight insect/background gate ---
# Compact NumPy + scikit-learn feature gate. No YAMNet/TensorFlow Hub is loaded.
_PEST_LIGHT_GATE = None
_PEST_LIGHT_GATE_LOCK = __import__("threading").Lock()
_PEST_LIGHT_GATE_THRESHOLD = float(os.getenv("PEST_BACKGROUND_GATE_THRESHOLD", "0.45"))
_PEST_LIGHT_GATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ai_model", "lightweight_background_gate", "background_gate.joblib",
)


def _pest_light_gate_features(audio):
    """Keep features exactly aligned with train_lightweight_background_gate.py."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    target_samples = 5 * SAMPLE_RATE
    if x.size < target_samples:
        padded = np.zeros(target_samples, dtype=np.float32)
        padded[:x.size] = x
        x = padded
    else:
        x = x[:target_samples]

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

    values = [np.log10(raw_rms + eps), np.log10(raw_peak + eps), float(np.std(x))]
    rms_frames = np.sqrt(np.mean(np.square(frames.astype(np.float64)), axis=1) + eps)
    values.extend([float(np.mean(rms_frames)), float(np.std(rms_frames)), float(np.percentile(rms_frames, 90))])

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
    if norm_power.shape[0] > 1:
        flux = np.sqrt(np.mean(np.square(np.diff(norm_power, axis=0)), axis=1))
        values.extend([float(np.mean(flux)), float(np.std(flux)), float(np.percentile(flux, 90))])
    else:
        values.extend([0.0, 0.0, 0.0])

    result = np.asarray(values, dtype=np.float32)
    if result.shape != (59,) or not np.all(np.isfinite(result)):
        raise RuntimeError(f"Background-gate feature vector invalid: {result.shape}")
    return result


def _load_pest_light_gate():
    global _PEST_LIGHT_GATE, _PEST_LIGHT_GATE_THRESHOLD
    if _PEST_LIGHT_GATE is not None:
        return _PEST_LIGHT_GATE
    with _PEST_LIGHT_GATE_LOCK:
        if _PEST_LIGHT_GATE is not None:
            return _PEST_LIGHT_GATE
        if not os.path.isfile(_PEST_LIGHT_GATE_PATH):
            logger.error("Pest Guard lightweight background gate is missing: %s", _PEST_LIGHT_GATE_PATH)
            raise HTTPException(status_code=503, detail="Background sound filter is not installed on this backend.")
        try:
            import joblib
            artifact = joblib.load(_PEST_LIGHT_GATE_PATH)
            if not isinstance(artifact, dict) or "model" not in artifact:
                raise RuntimeError("Saved background gate is not the expected model bundle.")
            gate = artifact["model"]
            artifact_feature_count = artifact.get("feature_count")
            artifact_threshold = artifact.get("threshold")
            if artifact_feature_count != 59 or getattr(gate, "n_features_in_", None) != 59:
                raise RuntimeError("Loaded gate does not match the 59-feature training schema.")
            if not isinstance(artifact_threshold, (int, float)) or not 0.0 <= float(artifact_threshold) <= 1.0:
                raise RuntimeError(f"Invalid saved gate threshold: {artifact_threshold!r}")
            if "PEST_BACKGROUND_GATE_THRESHOLD" not in os.environ:
                _PEST_LIGHT_GATE_THRESHOLD = float(artifact_threshold)
            classes = list(getattr(gate, "classes_", []))
            if 0 not in classes or 1 not in classes:
                raise RuntimeError(f"Unexpected background-gate classes: {classes}")
            import numpy as np
            probe = np.asarray(gate.predict_proba(np.zeros((1, 59), dtype=np.float32)))
            if probe.shape != (1, len(classes)) or not np.all(np.isfinite(probe)):
                raise RuntimeError("Loaded gate failed its prediction smoke test.")
        except Exception as error:
            logger.exception("Could not load Pest Guard lightweight background gate")
            raise HTTPException(status_code=503, detail="Background sound filter failed to load.") from error
        _PEST_LIGHT_GATE = gate
        logger.info("Pest Guard lightweight background gate loaded (threshold=%.2f)", _PEST_LIGHT_GATE_THRESHOLD)
        return _PEST_LIGHT_GATE


def _pest_light_gate_score(waveform):
    gate = _load_pest_light_gate()
    vector = _pest_light_gate_features(waveform).reshape(1, -1)
    try:
        probabilities = np.asarray(gate.predict_proba(vector), dtype=np.float64)
        classes = list(gate.classes_)
        positive_index = classes.index(1)
        if probabilities.ndim != 2 or probabilities.shape != (1, len(classes)):
            raise RuntimeError(f"Unexpected background-gate probability shape: {probabilities.shape}")
        score = float(probabilities[0, positive_index])
        if not np.isfinite(score) or score < 0.0 or score > 1.0:
            raise RuntimeError("Background gate returned an invalid score.")
        return score
    except Exception as error:
        logger.exception("Pest Guard lightweight background-gate scoring failed")
        raise HTTPException(status_code=503, detail="Background sound filter could not score this recording.") from error


# --- End Pest Guard lightweight background gate ---

'''


def locate_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "backend" / "main.py").is_file():
        return cwd
    script_root = Path(__file__).resolve().parent
    if (script_root / "backend" / "main.py").is_file():
        return script_root
    raise RuntimeError("Run this script from the Pest guard project root (the folder containing backend\\main.py).")


def update_requirements(path: Path) -> tuple[str, list[str]]:
    original = path.read_text(encoding="utf-8-sig")
    lines = original.splitlines()
    notes = []
    found = set()
    updated_lines = []
    for line in lines:
        stripped = line.strip()
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", stripped)
        if not match or stripped.startswith(("#", "-")):
            updated_lines.append(line)
            continue
        raw_name = match.group(1)
        key = re.sub(r"[-_.]+", "-", raw_name).lower()
        if key == "scikit-learn":
            updated_lines.append("scikit-learn==1.9.0")
            found.add(key)
            if stripped != "scikit-learn==1.9.0":
                notes.append(f"Pinned scikit-learn to 1.9.0 for the trained gate artifact (was: {stripped})")
        elif key == "joblib":
            updated_lines.append("joblib==1.6.0")
            found.add(key)
            if stripped != "joblib==1.6.0":
                notes.append(f"Pinned joblib to 1.6.0 for the trained gate artifact (was: {stripped})")
        else:
            updated_lines.append(line)
            found.add(key)

    if "scikit-learn" not in found:
        updated_lines.append("scikit-learn==1.9.0")
        notes.append("Added scikit-learn==1.9.0")
    if "joblib" not in found:
        updated_lines.append("joblib==1.6.0")
        notes.append("Added joblib==1.6.0")

    updated = "\n".join(updated_lines).rstrip() + "\n"
    return updated, notes


def backup(path: Path, stamp: str) -> Path:
    target = path.with_name(path.name + f".before_lightweight_gate_{stamp}.bak")
    if target.exists():
        raise RuntimeError(f"Refusing to overwrite existing backup: {target}")
    shutil.copy2(path, target)
    return target


def main() -> int:
    root = locate_root()
    main_path = root / "backend" / "main.py"
    req_path = root / "backend" / "requirements.txt"
    gate_path = root / GATE_REL
    if not gate_path.is_file():
        raise RuntimeError(f"Trained lightweight gate missing: {gate_path}. Run train_lightweight_background_gate.py first.")

    # The trainer intentionally saves a bundle (model + threshold + schema), not
    # a bare estimator. Validate the bundle and prediction API before editing.
    import joblib
    import numpy as np
    artifact = joblib.load(gate_path)
    if not isinstance(artifact, dict) or "model" not in artifact:
        raise RuntimeError("The saved gate artifact is not the expected model bundle. No files changed.")
    model = artifact["model"]
    saved_feature_count = artifact.get("feature_count")
    saved_threshold = artifact.get("threshold")
    if saved_feature_count != 59 or getattr(model, "n_features_in_", None) != 59:
        raise RuntimeError(
            f"The saved gate bundle/model feature schema is incompatible "
            f"(bundle={saved_feature_count}, model={getattr(model, 'n_features_in_', None)}). No files changed."
        )
    classes = list(getattr(model, "classes_", []))
    if not {0, 1}.issubset(set(classes)):
        raise RuntimeError(f"The saved model is not a binary gate (classes={classes}). No files changed.")
    if not isinstance(saved_threshold, (int, float)) or not 0.0 <= float(saved_threshold) <= 1.0:
        raise RuntimeError(f"The saved gate threshold is invalid: {saved_threshold!r}. No files changed.")
    probs = np.asarray(model.predict_proba(np.zeros((1, 59), dtype=np.float32)))
    if probs.shape != (1, len(classes)) or not np.all(np.isfinite(probs)):
        raise RuntimeError("The saved gate failed a local prediction smoke test. No files changed.")

    source = main_path.read_text(encoding="utf-8-sig")
    if "_pest_light_gate_score" in source or "_PEST_LIGHT_GATE_PATH" in source:
        raise RuntimeError("A lightweight gate integration marker already exists in backend/main.py; refusing duplicate patch.")
    if "_pest_background_gate_score" in source or "_PEST_BACKGROUND_GATE_PATH" in source:
        raise RuntimeError("A previous YAMNet gate integration is still present. Restore the intended backend version first.")
    predictor_marker = "def predict_pest(audio):"
    decode_marker = "    waveform = decode_audio_samples(audio)"
    if source.count(predictor_marker) != 1 or source.count(decode_marker) != 1:
        raise RuntimeError("Could not uniquely locate prediction insertion points; no source files changed.")
    header = source.split("def decode_audio_samples", 1)[0]
    for required in ("import os", "import numpy as np", "HTTPException", "logger"):
        if required not in header:
            raise RuntimeError(f"Could not confirm required backend symbol/import: {required}; no source files changed.")

    updated = source.replace(predictor_marker, INJECTION + predictor_marker, 1)
    insertion = (
        decode_marker + "\n"
        "    gate_score = _pest_light_gate_score(waveform)\n"
        "    if gate_score < _PEST_LIGHT_GATE_THRESHOLD:\n"
        "        logger.info(\"Background gate rejected audio (score=%.4f, threshold=%.2f)\", gate_score, _PEST_LIGHT_GATE_THRESHOLD)\n"
        "        raise HTTPException(status_code=422, detail=\"Audio rejected by background-sound filter. No detection was saved.\")\n"
        "    logger.info(\"Background gate accepted audio (score=%.4f, threshold=%.2f)\", gate_score, _PEST_LIGHT_GATE_THRESHOLD)"
    )
    updated = updated.replace(decode_marker, insertion, 1)
    compile(updated, str(main_path), "exec")
    req_updated, req_notes = update_requirements(req_path)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backups = []
    try:
        backups.append(backup(main_path, stamp))
        if req_updated != req_path.read_text(encoding="utf-8-sig"):
            backups.append(backup(req_path, stamp))
        main_path.write_text(updated, encoding="utf-8", newline="")
        if req_updated != req_path.read_text(encoding="utf-8-sig"):
            req_path.write_text(req_updated, encoding="utf-8", newline="")
        compile(main_path.read_text(encoding="utf-8"), str(main_path), "exec")
    except Exception:
        for b in backups:
            original_name = b.name.split(".before_lightweight_gate_", 1)[0]
            shutil.copy2(b, b.with_name(original_name))
        raise

    print("LIGHTWEIGHT BACKGROUND GATE PATCH APPLIED")
    print(f"Backend: {main_path}")
    print(f"Gate artifact: {gate_path} ({gate_path.stat().st_size:,} bytes)")
    print(f"Threshold default: {float(saved_threshold):.2f} from the trained artifact (override via PEST_BACKGROUND_GATE_THRESHOLD)")
    print("Gate uses NumPy spectral features + scikit-learn only; no TensorFlow Hub/YAMNet is loaded.")
    print("Rejections raise HTTP 422 before insect classification/database persistence/WebSocket broadcast.")
    print("Backups:")
    for b in backups:
        print(f"  {b}")
    for note in req_notes:
        print("Dependency update:", note)
    print("Unchanged: active 47-class model, database, and ESP32 firmware.")
    print("Next: run safety tests and a local gate smoke test before committing/deploying.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"LIGHTWEIGHT GATE PATCH FAILED SAFELY: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
