import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import logging

import os

import uuid

from twilio.rest import Client

import difflib
import json

import numpy as np

from pathlib import Path

from typing import List

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import desc, inspect, text

from sqlalchemy.orm import Session

from database import Base, engine, get_db

from models import (

    Device,
    Detection,
    DetectionControlCommand,

    Pest,

    Crop,
    PestCropSolution,
    PestSolutionCoverage,

    HighRiskSolutionHistory,

)

from crop_data import CROP_DATA
from pest_data import PEST_DATA
from solution_data import PEST_COVERAGE_DATA, SOLUTION_RECORDS
from pest_guard_hierarchy_inference_8class import (
    PestGuardHierarchy8Class as PestGuardHierarchy,
)
from insect_groups import (
    UNKNOWN_INSECT_GROUP,
    enrich_top_predictions,
    resolve_saved_group_prediction,
)
from schemas import (

    DetectionCreate,

    DetectionResponse,

    DeviceHeartbeat,

    HealthResponse,
    CropResponse,
    PestCropSolutionListResponse,
    PestCropSolutionResponse,
    PestResponse,
)

logger = logging.getLogger(__name__)

def _normalize_pest_label(value: str | None) -> str:
    return "".join(
        character
        for character in (value or "").casefold()
        if character.isalnum()
    )


AI_DIR = Path(__file__).resolve().parent / "ai_model"
PEST_GUARD_HIERARCHY_DIR = AI_DIR / "pest_guard_8group_candidate_20261108"
PEST_GUARD_HIERARCHY_MANIFEST = PEST_GUARD_HIERARCHY_DIR / "manifest.json"
if not PEST_GUARD_HIERARCHY_MANIFEST.is_file():
    raise FileNotFoundError(
        "Required eight-group hierarchy manifest is missing: "
        f"{PEST_GUARD_HIERARCHY_MANIFEST.resolve()}"
    )

_PEST_GUARD_HIERARCHY = PestGuardHierarchy(PEST_GUARD_HIERARCHY_DIR)
_ACTIVE_HIERARCHICAL_LABELS = set()
_ACTIVE_HIERARCHICAL_LABEL_GROUPS = {}
MODEL_COMMON_NAMES = {}
_ACTIVE_HIERARCHICAL_GROUP_NAMES = set(_PEST_GUARD_HIERARCHY.groups)
_ACTIVE_HIERARCHICAL_GROUP_LABELS = {
    _normalize_pest_label(group_name)
    for group_name in _PEST_GUARD_HIERARCHY.groups
}

for _group_name in _PEST_GUARD_HIERARCHY.groups:
    _normalized_group = _normalize_pest_label(_group_name)
    _ACTIVE_HIERARCHICAL_LABELS.add(_normalized_group)
    _ACTIVE_HIERARCHICAL_LABEL_GROUPS[_normalized_group] = _group_name
    MODEL_COMMON_NAMES[_normalized_group] = _group_name

for _group_name, _item in _PEST_GUARD_HIERARCHY.subtype_manifest.items():
    for _subtype_name in _item.get("labels") or []:
        if _subtype_name not in _PEST_GUARD_HIERARCHY.verified_subtype_labels.get(
            _group_name, set()
        ):
            continue
        _normalized_subtype = _normalize_pest_label(_subtype_name)
        _ACTIVE_HIERARCHICAL_LABELS.add(_normalized_subtype)
        _ACTIVE_HIERARCHICAL_LABEL_GROUPS[_normalized_subtype] = _group_name
        MODEL_COMMON_NAMES[_normalized_subtype] = _subtype_name

MODEL_SPECIES_GROUPS = dict(_ACTIVE_HIERARCHICAL_LABEL_GROUPS)
logger.info(
    "Pest Guard group/subtype classifier loaded: groups=%d, candidate labels=%d, artifact=%s",
    len(_PEST_GUARD_HIERARCHY.groups),
    len(_ACTIVE_HIERARCHICAL_LABELS),
    PEST_GUARD_HIERARCHY_DIR.resolve(),
)

SAMPLE_RATE = 16000
# One signed-int16 LSB at the PCM amplitude scale; less than this is not resolvable.
PCM16_RMS_FLOOR = 1.0 / 32768.0

PEST_IDENTIFICATION_CONFIDENCE = 0.70


def _is_active_prediction_label(label) -> bool:
    if not isinstance(label, str) or not label.strip():
        return False
    return _normalize_pest_label(label) in _ACTIVE_HIERARCHICAL_LABELS


def _is_active_species_label(label) -> bool:
    return (
        _is_active_prediction_label(label)
        and _normalize_pest_label(label) not in _ACTIVE_HIERARCHICAL_GROUP_LABELS
    )


def _active_group_for_label(label):
    if not isinstance(label, str) or not label.strip():
        return UNKNOWN_INSECT_GROUP
    normalized = _normalize_pest_label(label)
    return _ACTIVE_HIERARCHICAL_LABEL_GROUPS.get(normalized, UNKNOWN_INSECT_GROUP)


def decode_audio_samples(audio):
    try:
        samples = np.asarray(audio)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail="Audio must be a one-dimensional numeric sample array.",
        ) from error

    if samples.ndim != 1 or not samples.size:
        raise HTTPException(
            status_code=400,
            detail="Audio must be a non-empty one-dimensional sample array.",
        )

    if samples.size < SAMPLE_RATE:
        raise HTTPException(
            status_code=422,
            detail="Audio must contain at least one second of samples.",
        )

    if np.issubdtype(samples.dtype, np.integer):
        if np.any(samples < -32768) or np.any(samples > 32767):
            raise HTTPException(
                status_code=400,
                detail="Integer audio samples must be signed 16-bit PCM.",
            )
        waveform = samples.astype(np.float32) / 32768.0
    elif np.issubdtype(samples.dtype, np.floating):
        waveform = samples.astype(np.float32)
        if not np.all(np.isfinite(waveform)):
            raise HTTPException(
                status_code=400,
                detail="Audio samples must contain only finite values.",
            )
        if np.any(np.abs(waveform) > 1.0):
            raise HTTPException(
                status_code=400,
                detail="Floating-point audio samples must be in [-1, 1].",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Audio samples must be signed 16-bit integers or floats in [-1, 1].",
        )

    signal_rms = float(np.std(waveform, dtype=np.float64))
    if signal_rms <= PCM16_RMS_FLOOR:
        raise HTTPException(
            status_code=422,
            detail="Audio signal is silent or below the 16-bit PCM quantization floor.",
        )

    return waveform


# --- Pest Guard lightweight insect/background gate ---
# Compact NumPy + scikit-learn feature gate. No YAMNet/TensorFlow Hub is loaded.
_PEST_LIGHT_GATE = None
_PEST_LIGHT_GATE_LOCK = __import__("threading").Lock()
_PEST_LIGHT_GATE_THRESHOLD_OVERRIDE = os.getenv("PEST_BACKGROUND_GATE_THRESHOLD")
try:
    _PEST_LIGHT_GATE_THRESHOLD = (
        float(_PEST_LIGHT_GATE_THRESHOLD_OVERRIDE)
        if _PEST_LIGHT_GATE_THRESHOLD_OVERRIDE is not None
        else None
    )
except ValueError as error:
    raise RuntimeError("PEST_BACKGROUND_GATE_THRESHOLD must be a number from 0 to 1.") from error
if _PEST_LIGHT_GATE_THRESHOLD is not None and not 0.0 <= _PEST_LIGHT_GATE_THRESHOLD <= 1.0:
    raise RuntimeError("PEST_BACKGROUND_GATE_THRESHOLD must be from 0 to 1.")
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
            # Do not silently use a stale hard-coded 0.15 threshold when the
            # trained gate artifact contains its own calibrated operating point.
            if _PEST_LIGHT_GATE_THRESHOLD_OVERRIDE is None:
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
        logger.info(
            "Pest Guard lightweight background gate loaded "
            "(runtime threshold=%.2f, artifact threshold=%.2f)",
            _PEST_LIGHT_GATE_THRESHOLD,
            float(artifact_threshold),
        )
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

def predict_pest(audio):
    waveform = decode_audio_samples(audio)
    gate_score = _pest_light_gate_score(waveform)
    if gate_score < _PEST_LIGHT_GATE_THRESHOLD:
        logger.info("Background gate rejected audio (score=%.4f, threshold=%.2f)", gate_score, _PEST_LIGHT_GATE_THRESHOLD)
        raise HTTPException(status_code=422, detail=f"Audio rejected by background-sound filter. Gate score={gate_score:.4f}, threshold={_PEST_LIGHT_GATE_THRESHOLD:.2f}. No detection was saved.")
    logger.info("Background gate accepted audio (score=%.4f, threshold=%.2f)", gate_score, _PEST_LIGHT_GATE_THRESHOLD)

    result = _PEST_GUARD_HIERARCHY.predict(waveform)
    result["background_gate_score"] = gate_score
    return result


def _find_verified_pest_record(db: Session, pest_name: str, pest_id: str = ""):
    if not pest_name:
        return None

    if pest_id:
        pest = db.query(Pest).filter(Pest.pest_id == pest_id).first()
        if not pest:
            return None

        verified_labels = {
            _normalize_pest_label(pest.pest_id),
            _normalize_pest_label(pest.name),
            _normalize_pest_label(pest.scientific_name),
        }
        return (
            pest
            if _normalize_pest_label(pest_name) in verified_labels
            else None
        )

    return _find_pest_record_normalized(db, pest_name)


def _find_pest_record_normalized(db: Session, pest_name: str | None):
    normalized_name = _normalize_pest_label(pest_name)
    if not normalized_name:
        return None

    pests = db.query(Pest).all()
    catalog_record = next(
        (
            item
            for item in PEST_DATA
            if normalized_name
            in {
                _normalize_pest_label(item.get("pest_id")),
                _normalize_pest_label(item.get("name")),
                _normalize_pest_label(item.get("scientific_name")),
            }
        ),
        None,
    )
    if catalog_record:
        pest = next(
            (
                item
                for item in pests
                if item.pest_id == catalog_record["pest_id"]
            ),
            None,
        )
        if pest:
            return pest

    for pest in pests:
        if normalized_name in {
            _normalize_pest_label(pest.pest_id),
            _normalize_pest_label(pest.name),
            _normalize_pest_label(pest.scientific_name),
        }:
            return pest

    return None


def _resolve_species_metadata(
    pest_name: str | None,
    db: Session | None = None,
) -> dict:
    pest_record = (
        _find_pest_record_normalized(db, pest_name)
        if db is not None and pest_name
        else None
    )
    catalog_risk = str(getattr(pest_record, "risk", "") or "").strip().upper()
    catalog_risk_is_valid = catalog_risk in {
        "HIGH", "MEDIUM", "LOW", "NO_RISK"
    }
    risk = catalog_risk if catalog_risk_is_valid else "LOW"

    common_name = (
        str(getattr(pest_record, "name", "") or "").strip()
        or str(pest_name or "").strip()
        or "Unidentified sound"
    )
    scientific_name = (
        str(getattr(pest_record, "scientific_name", "") or "").strip()
        or None
    )

    return {
        "scientific_name": scientific_name,
        "common_name": common_name,
        "pest_id": getattr(pest_record, "pest_id", None),
        "risk": risk,
        "catalog_record_found": pest_record is not None,
        "catalog_risk_is_valid": catalog_risk_is_valid,
        "risk_rationale": (
            "Risk category recorded in the matching pest catalogue entry."
            if catalog_risk_is_valid
            else "Identification or catalogue risk is unconfirmed. "
            "LOW is a precautionary default."
        ),
        "affected_crops": [],
        "metadata_source_name": (
            "Pest Guard pest catalogue"
            if pest_record
            else None
        ),
        "metadata_source_url": None,
    }


def _serialize_detection(detection: Detection, db: Session | None) -> dict:
    resolved = _resolve_species_metadata(detection.pest, db)
    stored_risk = str(detection.risk or "").strip().upper()
    stored_crops = []
    if detection.affected_crops:
        try:
            stored_crops = json.loads(detection.affected_crops)
        except json.JSONDecodeError:
            stored_crops = []

    expected_group = _active_group_for_label(detection.pest)
    stored_group = str(getattr(detection, "insect_group", None) or "").strip()
    accepted_prediction = bool(
        detection.status == "HARMFUL_PEST"
        and _is_active_species_label(detection.pest)
        and expected_group in _ACTIVE_HIERARCHICAL_GROUP_NAMES
        and (not stored_group or stored_group == expected_group)
        and resolved["catalog_record_found"]
    )
    status = (
        "HARMFUL_PEST"
        if accepted_prediction
        else "NON_PEST"
        if detection.status == "NON_PEST"
        else "UNKNOWN"
    )
    if status == "NON_PEST":
        risk = "LOW"
        serialized_pest = None
        scientific_name = None
        common_name = "Unidentified sound"
        risk_rationale = "No pest was identified."
        metadata_source_name = None
        metadata_source_url = None
    elif accepted_prediction:
        risk = resolved["risk"]
        serialized_pest = MODEL_COMMON_NAMES.get(
            _normalize_pest_label(detection.pest),
            detection.pest,
        )
        scientific_name = resolved["scientific_name"]
        common_name = resolved["common_name"]
        risk_rationale = resolved["risk_rationale"]
        metadata_source_name = resolved["metadata_source_name"]
        metadata_source_url = resolved["metadata_source_url"]
    else:
        risk = (
            stored_risk
            if stored_risk in {"HIGH", "MEDIUM", "LOW", "NO_RISK"}
            else resolved["risk"]
        )
        serialized_pest = detection.pest
        scientific_name = (
            detection.scientific_name or resolved["scientific_name"]
        )
        common_name = (
            resolved["common_name"]
            if resolved["catalog_record_found"]
            else detection.common_name or resolved["common_name"]
        )
        risk_rationale = (
            detection.risk_rationale or resolved["risk_rationale"]
        )
        metadata_source_name = (
            detection.metadata_source_name or resolved["metadata_source_name"]
        )
        metadata_source_url = (
            detection.metadata_source_url or resolved["metadata_source_url"]
        )
    stored_predictions = []
    stored_broad_group = None
    stored_broad_group_confidence = None
    stored_broad_group_top_predictions = []
    if detection.top_predictions:
        try:
            parsed_predictions = json.loads(detection.top_predictions)
            if isinstance(parsed_predictions, dict):
                stored_predictions = parsed_predictions.get("species", [])
                stored_broad_group = parsed_predictions.get("broad_group_prediction")
                stored_broad_group_confidence = parsed_predictions.get("broad_group_confidence")
                stored_broad_group_top_predictions = parsed_predictions.get(
                    "broad_group_top_predictions", []
                )
            elif isinstance(parsed_predictions, list):
                stored_predictions = parsed_predictions
        except (json.JSONDecodeError, TypeError):
            stored_predictions = []

    response = {
        "id": detection.id,
        "device_id": detection.device_id,
        "status": status,
        "pest": serialized_pest,
        "scientific_name": scientific_name,
        "common_name": common_name,
        "confidence": detection.confidence,
        "insect_group": None,
        "group_score": None,
        "broad_group_prediction": stored_broad_group,
        "broad_group_confidence": stored_broad_group_confidence,
        "broad_group_top_predictions": stored_broad_group_top_predictions,
        "top_predictions": enrich_top_predictions(
            stored_predictions,
            MODEL_COMMON_NAMES,
        ),
        "risk": risk,
        "risk_rationale": risk_rationale,
        "affected_crops": stored_crops or resolved["affected_crops"],
        "metadata_source_name": metadata_source_name,
        "metadata_source_url": metadata_source_url,
        "pest_id": resolved["pest_id"] if accepted_prediction else None,
        "pest_verified": accepted_prediction,
        "temperature": detection.temperature,
        "humidity": detection.humidity,
        "audio_file": detection.audio_file,
        "message": detection.message,
        "detected_at": detection.detected_at,
    }
    response["insect_group"], response["group_score"] = resolve_saved_group_prediction(
        None if status == "NON_PEST" else detection.pest,
        None
        if status == "NON_PEST"
        else getattr(detection, "insect_group", None),
        None
        if status == "NON_PEST"
        else getattr(detection, "group_score", None),
        MODEL_SPECIES_GROUPS,
    )
    detection_message = str(detection.message or "")
    normalized_message = detection_message.casefold()
    if normalized_message.startswith("inference_error:"):
        identification_status = "ERROR"
        identification_label = "Inference error"
    elif status == "NON_PEST":
        identification_status = "NON_PEST"
        identification_label = "No pest detected"
    elif accepted_prediction:
        identification_status = "MODEL_PREDICTED"
        identification_label = response["common_name"]
    else:
        identification_status = "UNCONFIRMED"
        identification_label = (
            "Possible match"
            if _is_active_species_label(detection.pest)
            else "Possible group match"
            if (
                expected_group in _ACTIVE_HIERARCHICAL_GROUP_NAMES
                or stored_group in _ACTIVE_HIERARCHICAL_GROUP_NAMES
            )
            else "Unidentified sound"
        )
    response.update(
        {
            "identification_status": identification_status,
            "identification_label": identification_label,
            "source": (
                "AI_MODEL_PREDICTION"
                if (
                    detection.top_predictions
                    or normalized_message.startswith(
                        (
                            "unverified model prediction",
                            "low-confidence model prediction rejected",
                            "model-predicted harmful pest",
                        )
                    )
                )
                else "DEVICE_DETECTION"
            ),
        }
    )
    return response


# -------------------------------------------------------------------

# Database

# -------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

def _migrate_detection_metadata_columns():
    required_columns = {
        "scientific_name": "VARCHAR(200)",
        "common_name": "VARCHAR(150)",
        "risk_rationale": "TEXT",
        "affected_crops": "TEXT",
        "metadata_source_name": "VARCHAR(200)",
        "metadata_source_url": "VARCHAR(1000)",
        "top_predictions": "TEXT",
        "insect_group": "VARCHAR(100)",
        "group_score": "FLOAT",
    }
    with engine.begin() as connection:
        existing_columns = {
            column["name"]
            for column in inspect(connection).get_columns("detections")
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE detections ADD COLUMN "
                        f"{column_name} {column_type}"
                    )
                )


_migrate_detection_metadata_columns()

def _migrate_solution_history_source_column():
    with engine.begin() as connection:
        existing_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "high_risk_solution_history"
            )
        }
        if "solution_source" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE high_risk_solution_history "
                    "ADD COLUMN solution_source VARCHAR(20)"
                )
            )


_migrate_solution_history_source_column()

# -------------------------------------------------------------------

# FastAPI application

# -------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    startup_event()
    yield


DEVICE_SENSOR_REPORTS = {}

app = FastAPI(

    title="Pest Guard API",

    description="Backend API for the Pest Guard AI pest detection system.",

    version="1.0.0",

    lifespan=lifespan,

)

# -------------------------------------------------------------------

# CORS

# -------------------------------------------------------------------

app.add_middleware(

    CORSMiddleware,

    allow_origins=[

        "http://localhost:5173",

        "http://127.0.0.1:5173",

        "https://pest-guard-eight.vercel.app",

    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)

# -------------------------------------------------------------------

# -------------------------------------------------------------------

# HIGH-risk Solution History API

# -------------------------------------------------------------------

@app.get("/api/solutions/history/high-risk")

def get_high_risk_solution_history(

    limit: int = Query(default=50, ge=1, le=500),

    db: Session = Depends(get_db),

):

    history = db.query(HighRiskSolutionHistory).order_by(

        desc(HighRiskSolutionHistory.detected_at)

    ).limit(limit).all()

    return {
        "total": db.query(HighRiskSolutionHistory).count(),
        "history": [
            _high_risk_solution_history_response(item, db)
            for item in history
        ]
    }

@app.delete("/api/solutions/history/high-risk")
def clear_high_risk_solution_history(
    db: Session = Depends(get_db),
):
    deleted_count = db.query(HighRiskSolutionHistory).delete(
        synchronize_session=False
    )
    db.commit()

    return {
        "message": "High-risk solution history cleared successfully.",
        "deleted": deleted_count,
    }

# WebSocket connection manager

# -------------------------------------------------------------------

class ConnectionManager:

    def __init__(self):

        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):

        await websocket.accept()

        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):

        if websocket in self.active_connections:

            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):

        disconnected = []

        for websocket in self.active_connections:

            try:

                await websocket.send_json(data)

            except Exception:

                disconnected.append(websocket)

        for websocket in disconnected:

            self.disconnect(websocket)

manager = ConnectionManager()

# -------------------------------------------------------------------

# Startup data

# -------------------------------------------------------------------

def seed_pest_data(db: Session):
    """
    Seed the catalogue, supported crop names, and reviewed solution records.
    """
    pest_columns = {column.name for column in Pest.__table__.columns}

    for item in PEST_DATA:
        pest_values = {
            key: value
            for key, value in item.items()
            if key in pest_columns
        }
        existing = (
            db.query(Pest)
            .filter(Pest.pest_id == item["pest_id"])
            .first()
        )

        if existing:
            for key, value in pest_values.items():
                setattr(existing, key, value)
        else:
            db.add(Pest(**pest_values))

    for item in CROP_DATA:
        existing = (
            db.query(Crop)
            .filter(Crop.crop_id == item["crop_id"])
            .first()
        )

        if existing:
            for key, value in item.items():
                setattr(existing, key, value)
        else:
            db.add(Crop(**item))

    for item in PEST_COVERAGE_DATA:
        existing = (
            db.query(PestSolutionCoverage)
            .filter(PestSolutionCoverage.pest_id == item["pest_id"])
            .first()
        )
        if existing:
            for key, value in item.items():
                setattr(existing, key, value)
        else:
            db.add(PestSolutionCoverage(**item))

    pest_by_id = {item["pest_id"]: item for item in PEST_DATA}
    crop_ids = {item["crop_id"] for item in CROP_DATA}
    solution_ids = set()
    for item in SOLUTION_RECORDS:
        pest = pest_by_id.get(item["pest_id"])
        if not pest:
            raise ValueError(f"Unknown pest_id in solution record: {item['pest_id']}")
        if item["crop_id"] not in crop_ids:
            raise ValueError(f"Unknown crop_id in solution record: {item['crop_id']}")
        if item["risk_level"] not in {"HIGH", "MEDIUM"}:
            raise ValueError(
                f"Unsupported solution risk for pest_id={item['pest_id']}: "
                f"{item['risk_level']}"
            )
        if item["risk_level"] != pest["risk"]:
            raise ValueError(
                f"Solution risk does not match catalogue for pest_id={item['pest_id']}"
            )
        if item["solution_id"] in solution_ids:
            raise ValueError(f"Duplicate solution_id: {item['solution_id']}")
        solution_ids.add(item["solution_id"])
        if item["status"] == "VERIFIED":
            required_fields = (
                "scientific_name",
                "description",
                "identification_signs",
                "crop_damage",
                "recommended_treatment",
                "immediate_control_measures",
                "biological_control_options",
                "cultural_control_methods",
                "mechanical_control_methods",
                "chemical_control_options",
                "prevention",
                "monitoring",
                "safety_precautions",
                "expert_advice",
                "reviewed_on",
            )
            if any(not item.get(field) for field in required_fields):
                raise ValueError(
                    f"Verified solution is incomplete: {item['solution_id']}"
                )
            if not item.get("source_references"):
                raise ValueError(
                    f"Verified solution has no sources: {item['solution_id']}"
                )
        existing = (
            db.query(PestCropSolution)
            .filter(PestCropSolution.solution_id == item["solution_id"])
            .first()
        )
        if existing:
            for key, value in item.items():
                setattr(existing, key, value)
        else:
            db.add(PestCropSolution(**item))
    db.commit()

def startup_event():
    logger.info(
        "Pest Guard inference ready: artifact=%s; groups=%s; subtype_models=%d",
        PEST_GUARD_HIERARCHY_DIR.resolve(),
        ",".join(_PEST_GUARD_HIERARCHY.groups),
        len(_PEST_GUARD_HIERARCHY.experts),
    )

    db = next(get_db())

    try:

        seed_pest_data(db)

        default_device_id = "FIELD-UNIT-01"

        device = (

            db.query(Device)

            .filter(Device.device_id == default_device_id)

            .first()

        )

        if not device:

            device = Device(

                device_id=default_device_id,

                name="Pest Guard Field Unit",

                status="OFFLINE",

                connection="DISCONNECTED",

            )

            db.add(device)

            db.commit()

    finally:

        db.close()

# -------------------------------------------------------------------

# Health

# -------------------------------------------------------------------

@app.get(

    "/api/health",

    response_model=HealthResponse,

)

def health():

    return {

        "status": "ok",

        "service": "Pest Guard Backend",

    }

# -------------------------------------------------------------------

# Device API
# -------------------------------------------------------------------
DEVICE_STALE_SECONDS = 60

def _device_response(device):
    last_seen = device.last_seen
    if isinstance(last_seen, str):
        try:
            last_seen = datetime.fromisoformat(
                last_seen.strip().replace("Z", "+00:00").replace("z", "+00:00")
            )
        except ValueError:
            last_seen = None
    is_online = False
    now = datetime.now(timezone.utc)
    if isinstance(last_seen, datetime):
        if last_seen.tzinfo is None or last_seen.utcoffset() is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        else:
            last_seen = last_seen.astimezone(timezone.utc)
        age_seconds = (now - last_seen).total_seconds()
        is_online = 0 <= age_seconds <= DEVICE_STALE_SECONDS

    sensor_report = DEVICE_SENSOR_REPORTS.get(device.device_id)
    sensor_values_are_fresh = False
    if sensor_report and is_online:
        sensor_age = (now - sensor_report["reported_at"]).total_seconds()
        sensor_values_are_fresh = 0 <= sensor_age <= DEVICE_STALE_SECONDS

    return {
        "device_id": device.device_id,
        "name": device.name,
        "status": "ONLINE" if is_online else "OFFLINE",
        "connection": "CONNECTED" if is_online else "DISCONNECTED",
        "last_seen": device.last_seen,
        "temperature": (
            sensor_report["temperature"] if sensor_values_are_fresh else None
        ),
        "humidity": sensor_report["humidity"] if sensor_values_are_fresh else None,
    }

@app.get("/api/devices")
def get_devices(db: Session = Depends(get_db)):
    devices = db.query(Device).order_by(Device.id.asc()).all()
    return {
        "devices": [
            _device_response(device)
            for device in devices
        ]
    }
@app.get(
    "/api/devices/{device_id}",
)
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
):
    device = (
        db.query(Device)
        .filter(Device.device_id == device_id)
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )
    return {
        "device": _device_response(device)
    }
@app.post(
    "/api/devices/{device_id}/heartbeat",
)

def device_heartbeat(

    device_id: str,

    payload: DeviceHeartbeat,

    db: Session = Depends(get_db),

):

    device = (

        db.query(Device)

        .filter(Device.device_id == device_id)

        .first()

    )

    if not device:

        device = Device(

            device_id=device_id,

            name="Pest Guard Field Unit",

        )

        db.add(device)

    device.status = payload.status

    device.connection = payload.connection

    for field in ("temperature", "humidity"):
        value = getattr(payload, field)
        if value is not None and not np.isfinite(value):
            value = None
        if field == "humidity" and value is not None and not 0 <= value <= 100:
            value = None
        setattr(device, field, value)

    heartbeat_time = datetime.now(timezone.utc)
    device.last_seen = heartbeat_time.replace(tzinfo=None)
    DEVICE_SENSOR_REPORTS[device_id] = {
        "temperature": device.temperature,
        "humidity": device.humidity,
        "reported_at": heartbeat_time,
    }

    if (
        payload.detection_enabled is not None
        and payload.control_command_id
    ):
        command = (
            db.query(DetectionControlCommand)
            .filter(DetectionControlCommand.device_id == device_id)
            .first()
        )
        if command and payload.control_command_id == command.command_id:
            command.acknowledged_enabled = payload.detection_enabled
            command.acknowledged_command_id = payload.control_command_id
            command.acknowledged_at = heartbeat_time.replace(tzinfo=None)

    db.commit()
    db.refresh(device)
    return {
        "message": "Heartbeat received",
        "device": _device_response(device),
    }

# PEST_GUARD_DETECTION_CONTROL_ENDPOINTS
CONTROL_COMMAND_TIMEOUT_SECONDS = 60


def _as_utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _detection_control_response(device_id, db):
    command = (
        db.query(DetectionControlCommand)
        .filter(DetectionControlCommand.device_id == device_id)
        .first()
    )
    device = db.query(Device).filter(Device.device_id == device_id).first()
    requested_enabled = bool(command.enabled) if command else False
    command_received = command is not None
    command_id = command.command_id if command else None
    now = datetime.now(timezone.utc)
    device_online = False
    if device and device.last_seen:
        age_seconds = (now - _as_utc(device.last_seen)).total_seconds()
        device_online = 0 <= age_seconds <= DEVICE_STALE_SECONDS

    device_enabled = None
    reported_at = None
    if command:
        acknowledged_at = command.acknowledged_at
        if (
            acknowledged_at is not None
            and command.acknowledged_command_id == command_id
        ):
            age_seconds = (now - _as_utc(acknowledged_at)).total_seconds()
            if 0 <= age_seconds <= DEVICE_STALE_SECONDS and device_online:
                device_enabled = command.acknowledged_enabled
                reported_at = acknowledged_at

    command_age = (
        (now - _as_utc(command.created_at)).total_seconds()
        if command_received
        else None
    )
    if not command_received:
        status = "UNKNOWN"
    elif not device_online:
        status = "DEVICE_OFFLINE"
    elif device_enabled is not None:
        if device_enabled == requested_enabled:
            status = "RUNNING" if device_enabled else "STOPPED"
        else:
            status = (
                "TIMEOUT"
                if command_age > CONTROL_COMMAND_TIMEOUT_SECONDS
                else "REQUESTED"
            )
    else:
        status = (
            "TIMEOUT"
            if command_age > CONTROL_COMMAND_TIMEOUT_SECONDS
            else "REQUESTED"
        )

    return {
        "device_id": device_id,
        "enabled": requested_enabled,
        "command_received": command_received,
        "command_id": command_id,
        "device_online": device_online,
        "device_enabled": device_enabled,
        "status": status,
        "reported_at": reported_at.isoformat() if reported_at else None,
    }


@app.get("/api/devices/{device_id}/detection-control")
def get_detection_control(device_id: str, db: Session = Depends(get_db)):
    return _detection_control_response(device_id, db)


@app.post("/api/devices/{device_id}/detection-control")
def set_detection_control(
    device_id: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(
            status_code=422,
            detail="Field 'enabled' must be true or false",
        )

    command = (
        db.query(DetectionControlCommand)
        .filter(DetectionControlCommand.device_id == device_id)
        .first()
    )
    if command is None:
        command = DetectionControlCommand(
            device_id=device_id,
            enabled=enabled,
            command_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(command)
    else:
        command.enabled = enabled
        command.command_id = str(uuid.uuid4())
        command.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        command.acknowledged_enabled = None
        command.acknowledged_command_id = None
        command.acknowledged_at = None
    db.commit()
    db.refresh(command)
    return _detection_control_response(device_id, db)


@app.post("/api/ai/predict")

async def ai_predict(
    request: Request,
    db: Session = Depends(get_db),
):

    try:

        content_type = request.headers.get("content-type", "")

        # Compact ESP32 transport: signed 16-bit little-endian PCM samples.

        # 80,000 samples = 160 KB, much smaller than the JSON payload.

        if content_type.startswith("application/octet-stream"):

            raw_audio = await request.body()

            if not raw_audio:

                raise HTTPException(

                    status_code=400,

                    detail="Audio data is required",

                )

            if len(raw_audio) % 2 != 0:

                raise HTTPException(

                    status_code=400,

                    detail="Invalid PCM audio length",

                )

            audio = np.frombuffer(raw_audio, dtype="<i2")

        else:

            try:
                payload = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                logger.warning(
                    "AI prediction rejected invalid JSON request "
                    "(content_type=%r, error=%s)",
                    content_type,
                    type(error).__name__,
                )
                raise HTTPException(
                    status_code=400,
                    detail="Request body must contain valid JSON.",
                ) from error

            if not isinstance(payload, dict):
                raise HTTPException(
                    status_code=400,
                    detail="JSON request body must be an object.",
                )

            if "audio" not in payload:

                raise HTTPException(

                    status_code=400,

                    detail="Audio data is required",

                )

            audio = payload["audio"]

        result = await asyncio.to_thread(predict_pest, audio)

        # Preserve a subtype candidate for display, but only accept it when
        # the hierarchy, active catalog, and rejection state all agree.
        model_confidence = float(result["confidence"])
        top_predictions = result.get("top_predictions", [])
        raw_predicted_pest = result.get("pest")
        predicted_pest = (
            raw_predicted_pest
            if _is_active_species_label(raw_predicted_pest)
            else None
        )
        expected_group = _active_group_for_label(predicted_pest)
        insect_group = str(result.get("insect_group") or UNKNOWN_INSECT_GROUP)
        if insect_group not in _ACTIVE_HIERARCHICAL_GROUP_NAMES:
            insect_group = UNKNOWN_INSECT_GROUP
        group_score = result.get("group_score") if insect_group != UNKNOWN_INSECT_GROUP else None
        rejection_reason = result.get("rejection_reason")
        species_metadata = _resolve_species_metadata(predicted_pest, db)
        common_name = species_metadata["common_name"] if predicted_pest else None
        resolved_risk = (
            species_metadata["risk"] if predicted_pest else "LOW"
        )
        prediction_is_accepted = bool(
            predicted_pest
            and expected_group in _ACTIVE_HIERARCHICAL_GROUP_NAMES
            and insect_group == expected_group
            and not rejection_reason
            and species_metadata["catalog_record_found"]
        )
        prediction_status = (
            "HARMFUL_PEST" if prediction_is_accepted else "UNKNOWN"
        )
        if prediction_is_accepted:
            prediction_message = "Model-predicted harmful pest"
        elif rejection_reason:
            prediction_message = (
                f"Low-confidence model prediction rejected: {rejection_reason}"
            )
        else:
            prediction_message = "Unverified model prediction"

        # Persist the model decision so all response surfaces can derive the
        # same accepted or unconfirmed status from structured detection data.
        detected_time = datetime.now(timezone.utc).replace(tzinfo=None)

        detection = Detection(
            device_id=os.getenv("PEST_DEVICE_ID", "FIELD-UNIT-01"),
            status=prediction_status,
            pest=predicted_pest,
            scientific_name=(
                species_metadata["scientific_name"] if predicted_pest else None
            ),
            common_name=common_name,
            confidence=model_confidence,
            top_predictions=json.dumps({
                "species": top_predictions,
                "broad_group_prediction": result.get("broad_group_prediction"),
                "broad_group_confidence": result.get("broad_group_confidence"),
                "broad_group_top_predictions": result.get("broad_group_top_predictions", []),
            }),
            insect_group=insect_group,
            group_score=group_score,
            risk=resolved_risk,
            risk_rationale=(
                species_metadata["risk_rationale"] if predicted_pest else None
            ),
            affected_crops=json.dumps(
                species_metadata["affected_crops"] if predicted_pest else []
            ),
            metadata_source_name=(
                species_metadata["metadata_source_name"] if predicted_pest else None
            ),
            metadata_source_url=(
                species_metadata["metadata_source_url"] if predicted_pest else None
            ),
            message=prediction_message,
            detected_at=detected_time,
        )

        db.add(detection)
        db.commit()
        db.refresh(detection)

        # Send the saved record to the live website.
        prediction_data = _serialize_detection(detection, db)
        prediction_data["detected_at"] = detection.detected_at.replace(
            tzinfo=timezone.utc
        ).isoformat()

        await manager.broadcast(prediction_data)
        return prediction_data

    except HTTPException:

        raise

    except Exception as error:
        logger.exception("AI prediction failed")

        raise HTTPException(

            status_code=500,

            detail=f"AI prediction failed: {str(error)}",

        )

def _high_risk_solution_history_response(item, db: Session) -> dict:
    pest_name = getattr(item, "pest", None)
    stored_pest_id = str(getattr(item, "pest_id", None) or "").strip()
    pest_record = (
        _find_verified_pest_record(db, pest_name, stored_pest_id)
        if pest_name and stored_pest_id
        else None
    )
    common_name = (
        str(getattr(item, "common_name", None) or "").strip()
        or str(getattr(pest_record, "name", None) or "").strip()
        or str(pest_name or "").strip()
        or None
    )
    risk_value = str(getattr(pest_record, "risk", None) or "").strip().upper()
    if risk_value not in {"HIGH", "MEDIUM", "LOW", "NO_RISK"}:
        risk_value = str(getattr(item, "risk", None) or "").strip().upper()
    risk = risk_value if risk_value in {"HIGH", "MEDIUM", "LOW", "NO_RISK"} else None
    pest_verified = bool(
        pest_record
        and _is_active_species_label(pest_name)
    )
    return {
        "id": getattr(item, "id", None),
        "detection_id": getattr(item, "detection_id", None),
        "device_id": getattr(item, "device_id", None),
        "pest_verified": pest_verified,
        "pest_id": stored_pest_id or None,
        "pest": pest_name,
        "common_name": common_name,
        "pest_description": getattr(pest_record, "description", None) or "",
        "pest_symptoms": getattr(pest_record, "symptoms", None) or "",
        "image_url": getattr(item, "image_url", None),
        "risk": risk,
        "confidence": getattr(item, "confidence", None),
        "temperature": getattr(item, "temperature", None),
        "humidity": getattr(item, "humidity", None),
        "solution_title": None,
        "solution_source": None,
        "solution_description": None,
        "recommended_action": None,
        "prevention": None,
        "detected_at": getattr(item, "detected_at", None),
        "created_at": getattr(item, "created_at", None),
    }


# -------------------------------------------------------------------

# SMS ALERT

# -------------------------------------------------------------------

def send_high_risk_sms(detection):

    """

    Send a Twilio trial SMS for HIGH-risk pest detections.

    """

    if (
        detection.get("status") != "HARMFUL_PEST"
        or detection.get("identification_status") != "MODEL_PREDICTED"
        or detection.get("pest_verified") is not True
        or detection.get("risk") != "HIGH"
    ):
        return

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")

    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    from_number = os.getenv("TWILIO_FROM_NUMBER")

    to_number_1 = os.getenv("TWILIO_TO_NUMBER")

    to_number_2 = os.getenv("TWILIO_TO_NUMBER_2")

    if not account_sid or not auth_token or not from_number:

        print("Twilio is not configured.")

        return

    recipients = [

        number

        for number in [to_number_1, to_number_2]

        if number

    ]

    if not recipients:

        print("No Twilio recipient numbers configured.")

        return

    try:

        client = Client(account_sid, auth_token)

        for recipient in recipients:

            message = client.messages.create(

                body="sms_internal_alerts",

                from_=from_number,

                to=recipient,

            )

            print(

                f"Trial SMS sent to {recipient}. "

                f"Message SID: {message.sid}"

            )

    except Exception as error:

        print("Twilio SMS error:", repr(error))

# -------------------------------------------------------------------

# Detection API

# -------------------------------------------------------------------

@app.post(

    "/api/device/detection",

    response_model=DetectionResponse,

)

async def create_detection(

    payload: DetectionCreate,

    db: Session = Depends(get_db),

):

    if payload.status not in {

        "HARMFUL_PEST",

        "NON_PEST",

        "UNKNOWN",

    }:

        raise HTTPException(

            status_code=400,

            detail="Invalid detection status",

        )

    if payload.confidence is not None:
        if not 0 <= payload.confidence <= 1:

            raise HTTPException(

                status_code=400,

                detail="Confidence must be between 0 and 1",

            )

    candidate_pest = (
        payload.pest if _is_active_species_label(payload.pest) else None
    )
    if candidate_pest:
        candidate_pest = MODEL_COMMON_NAMES.get(
            _normalize_pest_label(candidate_pest),
            candidate_pest,
        )
    pest_record = (
        _find_pest_record_normalized(db, candidate_pest)
        if candidate_pest
        else None
    )
    species_metadata = _resolve_species_metadata(candidate_pest, db)
    expected_group = _active_group_for_label(candidate_pest)
    accepted_prediction = bool(
        payload.status == "HARMFUL_PEST"
        and candidate_pest
        and pest_record
        and expected_group in _ACTIVE_HIERARCHICAL_GROUP_NAMES
        and payload.confidence is not None
        and payload.confidence >= PEST_IDENTIFICATION_CONFIDENCE
    )
    detection_status = (
        "HARMFUL_PEST"
        if accepted_prediction
        else "UNKNOWN"
        if payload.status == "HARMFUL_PEST"
        else payload.status
    )
    detection_pest = (
        candidate_pest
        if detection_status in {"HARMFUL_PEST", "UNKNOWN"}
        else None
    )
    detection_risk = (
        species_metadata["risk"] if detection_pest else "LOW"
    )

    detected_time = payload.detected_at or datetime.now(timezone.utc).replace(
        tzinfo=None
    )

    detection = Detection(

        device_id=payload.device_id,

        status=detection_status,

        pest=detection_pest,
        scientific_name=(
            species_metadata["scientific_name"] if detection_pest else None
        ),
        common_name=species_metadata["common_name"] if detection_pest else None,

        confidence=payload.confidence,
        insect_group=_active_group_for_label(detection_pest),
        group_score=None,

        risk=detection_risk,
        risk_rationale=(
            species_metadata["risk_rationale"] if detection_pest else None
        ),
        affected_crops=json.dumps(
            species_metadata["affected_crops"] if detection_pest else []
        ),
        metadata_source_name=(
            species_metadata["metadata_source_name"] if detection_pest else None
        ),
        metadata_source_url=(
            species_metadata["metadata_source_url"] if detection_pest else None
        ),

        temperature=payload.temperature,

        humidity=payload.humidity,

        audio_file=payload.audio_file,

        message=payload.message,

        detected_at=detected_time,

    )

    db.add(detection)

    db.flush()

    # Preserve the detection record; crop-specific guidance is looked up only
    # after a crop has been selected and a reviewed catalogue record exists.

    if detection.status == "HARMFUL_PEST" and detection.risk == "HIGH":
        common_name = pest_record.name
        pest_id = pest_record.pest_id
        db.add(
            HighRiskSolutionHistory(
                detection_id=detection.id,
                device_id=payload.device_id,
                pest_id=pest_id,
                pest=detection_pest,
                common_name=common_name,
                image_url=None,
                risk=detection.risk,
                confidence=payload.confidence,
                temperature=payload.temperature,
                humidity=payload.humidity,
                solution_title=None,
                solution_source=None,
                solution_description=None,
                recommended_action=None,
                prevention=None,
                detected_at=detected_time,
            )
        )

    # Update device information from the detection.

    device = (

        db.query(Device)

        .filter(Device.device_id == payload.device_id)

        .first()

    )

    if not device:

        device = Device(

            device_id=payload.device_id,

            name="Pest Guard Field Unit",

        )

        db.add(device)

    device.status = "ONLINE"

    device.connection = "CONNECTED"

    device.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)

    if payload.temperature is not None:

        device.temperature = payload.temperature

    if payload.humidity is not None:

        device.humidity = payload.humidity

    db.commit()

    db.refresh(detection)

    detection_data = _serialize_detection(detection, db)
    if detection.detected_at:
        detection_data["detected_at"] = detection.detected_at.isoformat()

    # Send SMS only for HIGH-risk detections.

    send_high_risk_sms(detection_data)

    # Send the new detection immediately to connected website clients.

    await manager.broadcast(detection_data)

    return detection_data

@app.get(

    "/api/detections/latest",

)

def get_latest_detection(
    device_id: str | None = None,
    db: Session = Depends(get_db),

):

    query = db.query(Detection)
    if device_id:
        query = query.filter(Detection.device_id == device_id)
    detection = query.order_by(desc(Detection.detected_at)).first()

    if not detection:

        return {

            "detection": None

        }

    return {"detection": _serialize_detection(detection, db)}

@app.get(

    "/api/detections",

)

def get_detection_history(

    device_id: str | None = Query(default=None),

    status: str | None = Query(default=None),

    limit: int = Query(default=50, ge=1, le=500),

    db: Session = Depends(get_db),

):

    query = db.query(Detection)

    if device_id:

        query = query.filter(

            Detection.device_id == device_id

        )

    if status:

        query = query.filter(

            Detection.status == status

        )

    detections = (

        query

        .order_by(desc(Detection.detected_at))

        .limit(limit)

        .all()

    )

    return {

        "detections": [_serialize_detection(item, db) for item in detections],
    }

# -------------------------------------------------------------------

# Pest API

# -------------------------------------------------------------------

@app.get("/api/pests")
def get_pests(db: Session = Depends(get_db)):
    active_pest_ids = [item["pest_id"] for item in PEST_DATA]

    pests = (
        db.query(Pest)
        .filter(Pest.pest_id.in_(active_pest_ids))
        .order_by(Pest.name.asc())
        .all()
    )

    return {
        "pests": [
            {
                "pest_id": pest.pest_id,
                "name": pest.name,
                "scientific_name": pest.scientific_name,
                "description": pest.description,
                "risk": pest.risk,
                "symptoms": pest.symptoms,
            }
            for pest in pests
        ]
    }

@app.get("/api/pests/{pest_id}", response_model=PestResponse)
def get_pest(pest_id: str, db: Session = Depends(get_db)):
    active_pest_ids = {item["pest_id"] for item in PEST_DATA}

    if pest_id not in active_pest_ids:
        raise HTTPException(status_code=404, detail="Pest not found")

    pest = (
        db.query(Pest)
        .filter(Pest.pest_id == pest_id)
        .first()
    )

    if not pest:
        raise HTTPException(status_code=404, detail="Pest not found")

    return pest

# -------------------------------------------------------------------

# Crop and verified solution API

# -------------------------------------------------------------------

def _serialize_crop(crop: Crop) -> dict:
    return {
        "crop_id": crop.crop_id,
        "name": crop.name,
        "category": crop.category,
        "aliases": crop.aliases or [],
    }


@app.get("/api/crops", response_model=list[CropResponse])
def get_crops(
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    crops = db.query(Crop).order_by(Crop.name.asc()).all()
    if not search or not search.strip():
        return [_serialize_crop(crop) for crop in crops]

    query = _normalize_pest_label(search)
    if len(query) < 2:
        return []

    def normalized_names(crop):
        return [
            _normalize_pest_label(name)
            for name in [crop.name, *(crop.aliases or [])]
        ]

    matched = [
        crop
        for crop in crops
        if any(query in name for name in normalized_names(crop))
    ]
    if not matched:
        searchable = {
            name: crop
            for crop in crops
            for name in normalized_names(crop)
            if name
        }
        near_matches = difflib.get_close_matches(
            query,
            list(searchable),
            n=8,
            cutoff=0.55,
        )
        matched = list(dict.fromkeys(searchable[name] for name in near_matches))
    return [_serialize_crop(crop) for crop in matched]


def _serialize_pest_crop_solution(solution, pest, crop) -> dict:
    return {
        "solution_id": solution.solution_id,
        "pest_id": pest.pest_id,
        "pest_name": pest.name,
        "scientific_name": (
            solution.scientific_name or pest.scientific_name
        ),
        "insect_group": next(
            item["insect_group"]
            for item in PEST_DATA
            if item["pest_id"] == pest.pest_id
        ),
        "risk": pest.risk,
        "crop_id": crop.crop_id,
        "crop_name": crop.name,
        "region": solution.region,
        "description": solution.description,
        "identification_signs": solution.identification_signs,
        "crop_damage": solution.crop_damage,
        "recommended_treatment": solution.recommended_treatment,
        "immediate_control_measures": solution.immediate_control_measures,
        "biological_control_options": solution.biological_control_options,
        "cultural_control_methods": solution.cultural_control_methods,
        "mechanical_control_methods": solution.mechanical_control_methods,
        "chemical_control_options": solution.chemical_control_options,
        "prevention": solution.prevention,
        "monitoring": solution.monitoring,
        "safety_precautions": solution.safety_precautions,
        "expert_advice": solution.expert_advice,
        "source_references": solution.source_references or [],
        "reviewed_on": solution.reviewed_on,
    }


@app.get(
    "/api/solutions",
    response_model=PestCropSolutionListResponse,
)
def get_solutions(
    crop_id: str = Query(min_length=1, max_length=100),
    pest_id: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    crop = db.query(Crop).filter(Crop.crop_id == crop_id).first()
    if not crop:
        raise HTTPException(status_code=404, detail="Supported crop not found")

    query = (
        db.query(PestCropSolution, Pest)
        .join(Pest, Pest.pest_id == PestCropSolution.pest_id)
        .filter(
            PestCropSolution.crop_id == crop.crop_id,
            PestCropSolution.status == "VERIFIED",
            PestCropSolution.risk_level.in_(("HIGH", "MEDIUM")),
            PestCropSolution.risk_level == Pest.risk,
            Pest.pest_id.in_(item["pest_id"] for item in PEST_DATA),
        )
    )
    if pest_id:
        query = query.filter(PestCropSolution.pest_id == pest_id)

    records = query.order_by(Pest.name.asc()).all()
    serialized = [
        _serialize_pest_crop_solution(solution, pest, crop)
        for solution, pest in records
        if _is_active_species_label(pest.name)
    ]
    return {
        "crop": _serialize_crop(crop),
        "total": len(serialized),
        "solutions": serialized,
    }

# -------------------------------------------------------------------

# WebSocket

# -------------------------------------------------------------------

@app.websocket("/ws/detections")

async def detection_websocket(websocket: WebSocket):

    await manager.connect(websocket)

    try:

        while True:

            message = await websocket.receive_text()

            if message == "ping":

                await websocket.send_text('{"type":"pong"}')

    except WebSocketDisconnect:

        print("WebSocket client disconnected")

        manager.disconnect(websocket)

    except Exception as error:

        print("WebSocket error:", repr(error))

        manager.disconnect(websocket)

# -------------------------------------------------------------------

# Root endpoint

# -------------------------------------------------------------------

@app.get("/")

def root():

    return {

        "message": "Pest Guard Backend is running",

        "docs": "/docs",

    }
