import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import logging

import os

import urllib.error
import urllib.request

import time

import uuid

from twilio.rest import Client

import json

import numpy as np

from pathlib import Path

from typing import List, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from sqlalchemy import desc, inspect, text

from sqlalchemy.orm import Session

from database import Base, engine, get_db

from models import (

    Device,
    Detection,
    DetectionControlCommand,

    Pest,

    Solution,

    HighRiskSolutionHistory,

)

from pest_data import PEST_DATA, SOLUTION_DATA
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


class AISolutionRequest(BaseModel):

    pest: str = Field(min_length=1, max_length=200)

    common_name: str = Field(min_length=1, max_length=200)

    risk: Literal["HIGH", "MEDIUM", "LOW", "NO_RISK"]

    confidence: float = Field(ge=0, le=1)

    pest_id: str = Field(default="", max_length=200)

    pest_description: str = Field(default="", max_length=2000)

    pest_symptoms: str = Field(default="", max_length=2000)

    crop: str = Field(default="", max_length=100)

class AISolutionResponse(BaseModel):

    pest: str

    common_name: str

    risk: Literal["HIGH", "MEDIUM", "LOW", "NO_RISK"]

    confidence: float

    crop: str

    about: str

    recommended_action: str

    pesticide_recommendation: str

    prevention: str

    precautions: str


def _pesticide_recommendation(crop: str, uncertain: bool = False) -> str:
    if uncertain:
        return (
            "The pest identification is uncertain. Do not choose or apply a "
            "pest-specific pesticide. Confirm the pest and crop with a local "
            "agricultural officer first."
        )

    crop = crop.strip()
    if not crop:
        return (
            "Please verify the pest identification before treatment. "
            "Do not choose or apply a pest-specific pesticide. "
            "Select your crop before seeking crop-specific pesticide advice. "
            "Pest Guard has no verified locally registered product or "
            "crop-specific label dose for this pest. Ask a local agricultural "
            "officer to confirm both."
        )

    return (
        f"Pest Guard has no verified locally registered product or "
        f"crop-specific label dose for this pest on {crop}. Do not guess a "
        "product or dose. Ask a local agricultural officer to confirm a "
        "registered product and its label rate."
    )


def _safe_application_instructions() -> str:
    return (
        "1. Do not apply a pesticide until a locally registered product and "
        "its label are confirmed for this pest and crop.\n"
        "2. If an officer recommends a product, wear the protective equipment "
        "listed on its label. Follow label instructions for mixing, spraying, "
        "re-entry, storage, and disposal. Never mix products.\n"
        "3. Follow the label's pre-harvest waiting period. Pest Guard has no "
        "verified product label or waiting period for this case."
    )


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

    return db.query(Pest).filter(
        (Pest.pest_id == pest_name)
        | (Pest.name == pest_name)
        | (Pest.scientific_name == pest_name)
    ).first()


def _find_pest_record_normalized(db: Session, pest_name: str | None):
    normalized_name = _normalize_pest_label(pest_name)
    if not normalized_name:
        return None

    for pest in db.query(Pest).all():
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
        "risk": risk,
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
        "metadata_is_model_authoritative": False,
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

    risk = (
        resolved["risk"]
        if resolved["metadata_is_model_authoritative"]
        else stored_risk
        if stored_risk in {"HIGH", "MEDIUM", "LOW", "NO_RISK"}
        else resolved["risk"]
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
        "status": detection.status,
        "pest": detection.pest,
        "scientific_name": detection.scientific_name or resolved["scientific_name"],
        "common_name": detection.common_name or resolved["common_name"],
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
        "risk_rationale": detection.risk_rationale or resolved["risk_rationale"],
        "affected_crops": stored_crops or resolved["affected_crops"],
        "metadata_source_name": (
            detection.metadata_source_name or resolved["metadata_source_name"]
        ),
        "metadata_source_url": (
            detection.metadata_source_url or resolved["metadata_source_url"]
        ),
        "temperature": detection.temperature,
        "humidity": detection.humidity,
        "audio_file": detection.audio_file,
        "message": detection.message,
        "detected_at": detection.detected_at,
    }
    response["insect_group"], response["group_score"] = resolve_saved_group_prediction(
        detection.pest,
        getattr(detection, "insect_group", None),
        getattr(detection, "group_score", None),
        MODEL_SPECIES_GROUPS,
    )
    detection_message = str(detection.message or "")
    normalized_message = detection_message.casefold()
    if normalized_message.startswith("inference_error:"):
        response.update(
            {
                "identification_status": "ERROR",
                "identification_label": "Inference error",
                "source": "DEVICE_INFERENCE_ERROR",
            }
        )
    elif (
        "unverified model prediction" in normalized_message
        or "low-confidence model prediction rejected" in normalized_message
    ):
        response.update(
            {
                "identification_status": "UNCONFIRMED",
                "identification_label": (
                    "Possible match" if detection.pest else "Unidentified sound"
                ),
                "source": "AI_MODEL_PREDICTION",
            }
        )
    return response


def _request_gemini_solution(payload: AISolutionRequest) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Gemini AI solution generation is not configured.",
        )

    prompt = (
        "You are an agricultural pest-management assistant. Return valid JSON only.\n\n"
        f"Common name: {payload.common_name}\n"
        f"Scientific name: {payload.pest}\n"
        f"Risk level: {payload.risk}\n"
        f"AI model score: {payload.confidence:.1%} (uncalibrated; not verified confidence)\n"
        f"Crop: {payload.crop or 'not supplied'}\n"
        f"Pest ID: {payload.pest_id or 'unavailable'}\n"
        f"Known description: {payload.pest_description or 'unavailable'}\n"
        f"Known symptoms: {payload.pest_symptoms or 'unavailable'}\n\n"
        "Return exactly these five non-empty JSON string fields: about, recommended_action, "
        "pesticide_recommendation, precautions, prevention.\n"
        "about: explain likely pest and crop damage and observable symptoms; be explicit that "
        "this is a candidate identification, not confirmation.\n"
        "recommended_action: give practical crop-protection measures, prioritizing integrated "
        "pest management and suitable non-chemical controls.\n"
        "pesticide_recommendation: discuss a registered pesticide or medicine only when reliable "
        "information applicable to this exact pest and crop is available. Never invent a product, "
        "registration status, or dose. Give an exact dose only when supported by a verified product "
        "label applicable to this crop and pest. If no such label is provided or verified, say that "
        "the exact product and dose cannot be verified and advise checking the registered label or "
        "consulting a qualified local agricultural expert.\n"
        "precautions: describe label-based protective equipment and application precautions, "
        "prohibition on unsafe mixing, and following the product label for storage, disposal, "
        "re-entry, and pre-harvest intervals. Do not invent label intervals.\n"
        "prevention: give practical monitoring, sanitation, prevention, and follow-up steps.\n\n"
        "Use only the supplied pest candidate; do not substitute another species. The model score is "
        "uncalibrated and does not prove identification. If identification is otherwise "
        "uncertain, do not recommend applying a pest-specific pesticide until the pest is confirmed. "
        "If crop information is missing, say that crop-specific treatment cannot be confirmed. "
        "Do not invent facts, label details, or treatment claims."
    )

    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    print("Gemini solution request model:", model)

    request_body = json.dumps(
        {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 2500,
            },
        }
    ).encode("utf-8")

    provider_request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=request_body,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    provider_data = None
    last_provider_error = None

    for attempt in range(3):
        try:
            with urllib.request.urlopen(provider_request, timeout=30) as response:
                response_status = response.status
                response_content_type = response.headers.get("Content-Type", "")
                response_body = response.read()

            if not response_body.strip():
                logger.error(
                    "Gemini provider returned an empty response "
                    "(status=%s, content_type=%r)",
                    response_status,
                    response_content_type,
                )
                raise RuntimeError(
                    "Gemini solution provider returned an empty response."
                )

            if "json" not in response_content_type.lower():
                logger.error(
                    "Gemini provider returned a non-JSON response "
                    "(status=%s, content_type=%r, bytes=%s)",
                    response_status,
                    response_content_type,
                    len(response_body),
                )
                raise RuntimeError(
                    "Gemini solution provider returned a non-JSON response."
                )

            try:
                provider_data = json.loads(response_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                logger.error(
                    "Gemini provider returned invalid JSON "
                    "(status=%s, content_type=%r, bytes=%s, error=%s)",
                    response_status,
                    response_content_type,
                    len(response_body),
                    type(error).__name__,
                )
                raise RuntimeError(
                    "Gemini solution provider returned invalid JSON."
                ) from error
            break
        except urllib.error.HTTPError as error:
            logger.error(
                "Gemini provider HTTP error (status=%s, content_type=%r)",
                error.code,
                error.headers.get("Content-Type", "") if error.headers else "",
            )
            last_provider_error = error
            error.close()

            if error.code == 503 and attempt < 2:
                retry_seconds = 2 ** (attempt + 1)
                print(f"Gemini 503 received. Retrying in {retry_seconds} seconds...")
                time.sleep(retry_seconds)
                continue

            raise RuntimeError(
                f"Gemini solution provider HTTP error {error.code}."
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            print("Gemini solution provider error:", repr(error))
            last_provider_error = error
            if attempt < 2:
                retry_seconds = 2 ** (attempt + 1)
                print(f"Gemini connection error. Retrying in {retry_seconds} seconds...")
                time.sleep(retry_seconds)
                continue
            raise RuntimeError(
                "Gemini solution provider returned an invalid or unavailable response."
            ) from error

    if provider_data is None:
        raise RuntimeError("Gemini solution provider did not return a response.") from last_provider_error

    if not isinstance(provider_data, dict):
        logger.error("Gemini provider JSON response was not an object")
        raise RuntimeError("Gemini solution provider returned an invalid response.")

    try:
        candidates = provider_data.get("candidates") or []
        if not candidates:
            logger.error("Gemini provider response contained no candidates")
            raise RuntimeError("Gemini returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        content = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and part.get("text")
        ).strip()

        if not content:
            logger.error("Gemini provider response contained empty content")
            raise RuntimeError("Gemini returned empty content.")

        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        logger.error("Gemini response text (first 2000 chars): %r", content[:2000])
        generated = json.loads(content)

    except (KeyError, IndexError, TypeError, ValueError) as error:
        logger.error(
            "Gemini solution response could not be parsed (%s)",
            type(error).__name__,
        )
        raise RuntimeError(
            "Gemini solution provider returned an invalid or unavailable response."
        ) from error




    required_fields = (
        "about",
        "recommended_action",
        "pesticide_recommendation",
        "precautions",
        "prevention",
    )

    if not isinstance(generated, dict) or any(
        not isinstance(generated.get(field), str) or not generated[field].strip()
        for field in required_fields
    ):
        raise RuntimeError("Gemini solution provider returned incomplete guidance.")

    return {
        "pest": payload.pest,
        "common_name": payload.common_name,
        "risk": payload.risk,
        "confidence": payload.confidence,
        "crop": payload.crop,
        **{field: generated[field].strip() for field in required_fields},
    }
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

    Add curated pest and solution information only when the

    corresponding records do not already exist.

    """

    for item in PEST_DATA:

        existing = (

            db.query(Pest)

            .filter(Pest.pest_id == item["pest_id"])

            .first()

        )

        if not existing:

            db.add(Pest(**item))

    for item in SOLUTION_DATA:

        existing = (

            db.query(Solution)

            .filter(Solution.pest_id == item["pest_id"])

            .first()

        )

        if not existing:

            db.add(Solution(**item))

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

        # Preserve the model's top trained class for display.
        # The model score is not a verified probability.
        model_confidence = float(result["confidence"])
        top_predictions = result.get("top_predictions", [])
        raw_predicted_pest = result.get("pest")
        predicted_pest = raw_predicted_pest if _is_active_prediction_label(raw_predicted_pest) else None
        insect_group = str(result.get("insect_group") or UNKNOWN_INSECT_GROUP)
        if insect_group not in _ACTIVE_HIERARCHICAL_GROUP_NAMES:
            insect_group = UNKNOWN_INSECT_GROUP
        group_score = result.get("group_score") if insect_group != UNKNOWN_INSECT_GROUP else None
        rejection_reason = result.get("rejection_reason")
        prediction_message = (
            f"Low-confidence model prediction rejected: {rejection_reason}"
            if rejection_reason
            else "Unverified model prediction"
        )
        species_metadata = _resolve_species_metadata(predicted_pest, db)
        common_name = species_metadata["common_name"] if predicted_pest else None
        if predicted_pest is not None:
            common_name = next(
                (
                    str(item.get("common_name") or "").strip()
                    for item in top_predictions
                    if _normalize_pest_label(item.get("pest") or item.get("species"))
                    == _normalize_pest_label(predicted_pest)
                ),
                common_name or str(predicted_pest),
            )
        resolved_risk = (
            species_metadata["risk"] if predicted_pest else "LOW"
        )
        prediction_is_accepted = bool(
            predicted_pest
            and insect_group != UNKNOWN_INSECT_GROUP
            and not rejection_reason
        )
        prediction_status = (
            "HARMFUL_PEST" if prediction_is_accepted else "UNKNOWN"
        )
        identification_status = (
            "MODEL_PREDICTED" if prediction_is_accepted else "UNCONFIRMED"
        )

        # The top-scoring class is only a candidate, not a verified identity.
        prediction_data = {

            "status": prediction_status,

            "identification_status": identification_status,
            "identification_label": (
                str(result.get("identification_label") or ("Possible match" if predicted_pest else "Unidentified sound"))
            ),

            "pest": predicted_pest,
            "common_name": common_name,
            "scientific_name": (
                species_metadata["scientific_name"] if predicted_pest else None
            ),

            "confidence": model_confidence,
            "insect_group": insect_group,
            "group_score": group_score,
            "top_predictions": top_predictions,
            "broad_group_prediction": result.get("broad_group_prediction"),
            "broad_group_confidence": result.get("broad_group_confidence"),
            "broad_group_top_predictions": result.get("broad_group_top_predictions", []),

            "risk": resolved_risk,
            "risk_rationale": (
                species_metadata["risk_rationale"] if predicted_pest else None
            ),
            "affected_crops": (
                species_metadata["affected_crops"] if predicted_pest else []
            ),
            "metadata_source_name": (
                species_metadata["metadata_source_name"] if predicted_pest else None
            ),
            "metadata_source_url": (
                species_metadata["metadata_source_url"] if predicted_pest else None
            ),

            "message": prediction_message,
            "source": "AI_MODEL_PREDICTION",
            "detected_at": datetime.now(timezone.utc).isoformat(),

        }

        # Persist the AI result as an unconfirmed detection.
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
        prediction_data.update(_serialize_detection(detection, None))
        prediction_data["status"] = prediction_status
        prediction_data["identification_status"] = identification_status
        prediction_data["identification_label"] = (
            str(result.get("identification_label") or ("Possible match" if predicted_pest else "Unidentified sound"))
        )
        prediction_data["insect_group"] = insect_group
        prediction_data["group_score"] = group_score
        prediction_data["top_predictions"] = top_predictions
        prediction_data["broad_group_prediction"] = result.get("broad_group_prediction")
        prediction_data["broad_group_confidence"] = result.get("broad_group_confidence")
        prediction_data["broad_group_top_predictions"] = result.get(
            "broad_group_top_predictions", []
        )
        prediction_data["source"] = "AI_MODEL_PREDICTION"
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

def _fallback_ai_solution(payload: AISolutionRequest) -> dict:
    return {
        "pest": payload.pest,
        "common_name": payload.common_name,
        "risk": payload.risk,
        "confidence": payload.confidence,
        "crop": payload.crop,
        "about": (
            f"The Pest Guard catalog identifies this as {payload.common_name} "
            f"({payload.pest}). Signs to check: {payload.pest_symptoms or 'compare the insect and crop damage with the field.'}"
        ),
        "recommended_action": (
            f"1. Inspect affected and nearby plants for "
            f"{payload.pest_symptoms or 'the damage described above'}.\n"
            "2. Mark where the damage is present and record what you see.\n"
            "3. Ask a local agricultural officer which non-chemical steps fit this pest and crop, especially if damage spreads."
        ),
        "prevention": (
            "1. Check the affected and nearby plants again in 2–3 days.\n"
            "2. Keep a simple note or photo record so you can see whether damage is spreading.\n"
            "3. Ask a local agricultural officer for a crop-specific prevention plan."
        ),
        "pesticide_recommendation": _pesticide_recommendation(payload.crop),
        "precautions": _safe_application_instructions(),
    }


def _fallback_uncertain_solution(payload: AISolutionRequest) -> dict:
    return {
        "pest": "Unconfirmed insect",
        "common_name": "Uncertain identification",
        "risk": "LOW",
        "confidence": payload.confidence,
        "crop": payload.crop,
        "about": (
            "The audio result is not a verified species identification. "
            "Treat the model output as an uncertain candidate, not a confirmed pest."
        ),
        "recommended_action": (
            "Inspect the crop and document visible damage, affected plants, and where it occurs. "
            "Seek identification from a local agricultural extension service or qualified adviser "
            "before choosing any species-specific treatment."
        ),
        "prevention": (
            "Continue regular field monitoring and use general integrated pest-management "
            "practices appropriate to the crop."
        ),
        "pesticide_recommendation": _pesticide_recommendation(
            payload.crop,
            uncertain=True,
        ),
        "precautions": (
            "1. Do not apply a pesticide based on this uncertain audio result.\n"
            "2. If a product is later recommended by a local agricultural "
            "officer, wear the label-required protective equipment and follow "
            "all label instructions.\n"
            "3. Follow the product label's pre-harvest waiting period; no "
            "product-specific waiting period is verified here."
        ),
    }


def _high_risk_solution_history_response(item, db: Session) -> dict:
    fallback = _fallback_uncertain_solution(
        AISolutionRequest(
            pest=item.pest or "Unconfirmed insect",
            common_name="Unconfirmed insect",
            risk="HIGH",
            confidence=item.confidence or 0.0,
        )
    )
    return {
        "id": item.id,
        "detection_id": item.detection_id,
        "device_id": item.device_id,
        "pest_verified": False,
        "pest_id": item.pest_id,
        "pest": item.pest,
        "common_name": "Unconfirmed insect",
        "pest_description": "",
        "pest_symptoms": "",
        "image_url": item.image_url,
        "risk": "LOW",
        "confidence": item.confidence,
        "temperature": item.temperature,
        "humidity": item.humidity,
        "solution_title": "General Integrated Pest Management Guidance",
        "solution_description": fallback["about"],
        "recommended_action": fallback["recommended_action"],
        "prevention": fallback["prevention"],
        "detected_at": item.detected_at,
        "created_at": item.created_at,
    }


@app.post("/api/ai/solution", response_model=AISolutionResponse)
async def generate_ai_solution(
    payload: AISolutionRequest,
    db: Session = Depends(get_db),
):
    # Only labels produced by the currently active classifier may be used.
    # A candidate label is never proof that the insect was identified correctly.
    if not _is_active_prediction_label(payload.pest):
        return _fallback_uncertain_solution(payload)

    pest_record = _find_verified_pest_record(
        db,
        payload.pest,
        payload.pest_id,
    )

    if pest_record:
        candidate_pest = pest_record.scientific_name or pest_record.name
        candidate_common_name = pest_record.name
        candidate_pest_id = pest_record.pest_id
        candidate_description = pest_record.description or payload.pest_description
        candidate_symptoms = pest_record.symptoms or payload.pest_symptoms
        candidate_risk = payload.risk
    else:
        # Keep general advice available, but use LOW as a precautionary
        # risk default until the insect identity is verified.
        candidate_pest = payload.pest
        active_common_name = MODEL_COMMON_NAMES.get(
            _normalize_pest_label(payload.pest),
            "",
        )
        candidate_common_name = (
            active_common_name
            or payload.common_name
            or payload.pest
            or 'Unconfirmed insect'
        )
        candidate_pest_id = ''
        candidate_description = payload.pest_description
        candidate_symptoms = payload.pest_symptoms
        candidate_risk = 'LOW'

    gemini_payload = AISolutionRequest(
        pest=candidate_pest,
        common_name=candidate_common_name,
        risk=candidate_risk,
        confidence=payload.confidence,
        pest_id=candidate_pest_id,
        pest_description=candidate_description,
        pest_symptoms=candidate_symptoms,
        crop=payload.crop,
    )

    try:
        generated = await asyncio.to_thread(_request_gemini_solution, gemini_payload)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception(
            "Gemini solution generation failed for model_class=%s",
            payload.pest,
        )
        raise HTTPException(
            status_code=502,
            detail="Gemini could not generate the pest solution. Please try again.",
        ) from error

    # No verified pesticide-label data source exists in this backend. Keep the
    # pesticide/dose field guarded in code rather than trusting an LLM to invent
    # an exact registered product rate. Low-score or catalogue-unmatched labels
    # also require confirmation before any pest-specific pesticide is considered.
    uncertain_identification = (
        not pest_record
        or payload.confidence < PEST_IDENTIFICATION_CONFIDENCE
    )
    generated["pest"] = candidate_pest
    generated["common_name"] = candidate_common_name
    generated["risk"] = "LOW" if uncertain_identification else candidate_risk
    generated["confidence"] = payload.confidence
    generated["crop"] = payload.crop
    generated["pesticide_recommendation"] = _pesticide_recommendation(
        payload.crop,
        uncertain=uncertain_identification,
    )
    generated["precautions"] = (
        (generated.get("precautions") or "").strip()
        + "\n\n"
        + _safe_application_instructions()
    ).strip()
    return generated


# -------------------------------------------------------------------

# SMS ALERT

# -------------------------------------------------------------------

def send_high_risk_sms(detection):

    """

    Send a Twilio trial SMS for HIGH-risk pest detections.

    """

    if detection.get("risk") != "HIGH":

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

    detection_status = payload.status
    detection_pest = payload.pest if _is_active_prediction_label(payload.pest) else None

    if detection_status in {"UNKNOWN", "HARMFUL_PEST"}:
        # Keep the persisted risk consistent with the matching model metadata;
        # ignore any risk sent by the device for model predictions.
        detection_risk = (
            _resolve_species_metadata(detection_pest)["risk"]
            if detection_pest
            else "LOW"
        )
    else:
        detection_pest = None
        detection_risk = "LOW"

    detected_time = payload.detected_at or datetime.now(timezone.utc).replace(
        tzinfo=None
    )

    detection = Detection(

        device_id=payload.device_id,

        status=detection_status,

        pest=detection_pest,

        confidence=payload.confidence,
        insect_group=_active_group_for_label(detection_pest),
        group_score=None,

        risk=detection_risk,

        temperature=payload.temperature,

        humidity=payload.humidity,

        audio_file=payload.audio_file,

        message=payload.message,

        detected_at=detected_time,

    )

    db.add(detection)

    db.flush()

    # Save HIGH-risk detections with the solution available at detection time.

    if detection.status == "HARMFUL_PEST" and detection.risk == "HIGH":

        pest_record = _find_verified_pest_record(db, payload.pest or "")

        common_name = (
            pest_record.name
            if pest_record
            else "Unconfirmed insect"
        )

        pest_id = pest_record.pest_id if pest_record else None

        solution_record = None

        if pest_id:

            solution_record = db.query(Solution).filter(Solution.pest_id == pest_id).first()

        solution_title = None

        solution_description = None

        recommended_action = None

        prevention = None

        if solution_record:

            solution_title = solution_record.title

            solution_description = solution_record.description

            recommended_action = solution_record.recommended_action

            prevention = solution_record.prevention

        elif pest_record and (
            payload.confidence is not None
            and payload.confidence >= PEST_IDENTIFICATION_CONFIDENCE
        ):

            try:

                ai_solution_payload = AISolutionRequest(

                    pest=pest_record.scientific_name or pest_record.name,

                    common_name=pest_record.name,

                    risk="HIGH",

                    confidence=payload.confidence or 0.0,

                    pest_id=pest_record.pest_id,

                    pest_description=pest_record.description if pest_record else "",

                    pest_symptoms=pest_record.symptoms if pest_record else "",

                )

                generated_solution = await asyncio.to_thread(_request_gemini_solution, ai_solution_payload)

                solution_title = f"{common_name} HIGH Risk AI Solution"

                solution_description = generated_solution.get("about")

                recommended_action = generated_solution.get("recommended_action")

                prevention = generated_solution.get("prevention")

            except Exception as error:

                print("HIGH-risk solution generation failed:", repr(error))

        else:

            solution = _fallback_uncertain_solution(
                AISolutionRequest(
                    pest=payload.pest or "Unknown insect",
                    common_name="Unconfirmed insect",
                    risk="HIGH",
                    confidence=payload.confidence or 0.0,
                )
            )
            solution_title = "General Integrated Pest Management Guidance"
            solution_description = solution["about"]
            recommended_action = solution["recommended_action"]
            prevention = solution["prevention"]

        db.add(HighRiskSolutionHistory(

            detection_id=detection.id, device_id=payload.device_id, pest_id=pest_id,

            pest=payload.pest, common_name=common_name, image_url=None, risk="HIGH",

            confidence=payload.confidence, temperature=payload.temperature,

            humidity=payload.humidity, solution_title=solution_title,

            solution_description=solution_description, recommended_action=recommended_action,

            prevention=prevention, detected_at=detected_time,

        ))

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

    detection_data = _serialize_detection(detection, None)
    if detection.detected_at:
        detection_data["detected_at"] = detection.detected_at.isoformat()

    # Send SMS only for HIGH-risk detections.

    send_high_risk_sms(detection_data)

    # Send the new detection immediately to connected website clients.

    await manager.broadcast(detection_data)

    return detection

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

@app.get(

    "/api/pests",

)

def get_pests(

    db: Session = Depends(get_db),

):

    pests = (

        db.query(Pest)

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

@app.get(

    "/api/pests/{pest_id}",

    response_model=PestResponse,

)

def get_pest(

    pest_id: str,

    db: Session = Depends(get_db),

):

    pest = (

        db.query(Pest)

        .filter(Pest.pest_id == pest_id)

        .first()

    )

    if not pest:

        raise HTTPException(

            status_code=404,

            detail="Pest not found",

        )

    return pest

# -------------------------------------------------------------------

# Solution API

# -------------------------------------------------------------------

@app.get(

    "/api/solutions",

)

def get_solutions(

    db: Session = Depends(get_db),

):

    solutions = (

        db.query(Solution)

        .order_by(Solution.title.asc())

        .all()

    )

    return {

        "solutions": [

            {

                "pest_id": solution.pest_id,

                "title": solution.title,

                "description": solution.description,

                "recommended_action": solution.recommended_action,

                "prevention": solution.prevention,

            }

            for solution in solutions

        ]

    }

@app.get(

    "/api/solutions/{pest_id}",

)

def get_solution(

    pest_id: str,

    db: Session = Depends(get_db),

):

    solution = (

        db.query(Solution)

        .filter(Solution.pest_id == pest_id)

        .first()

    )

    if not solution:

        raise HTTPException(

            status_code=404,

            detail="Solution not found for this pest",

        )

    return {

        "solution": {

            "pest_id": solution.pest_id,

            "title": solution.title,

            "description": solution.description,

            "recommended_action": solution.recommended_action,

            "prevention": solution.prevention,

        }

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
