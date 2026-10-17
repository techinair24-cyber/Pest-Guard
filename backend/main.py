import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import logging

import os

import urllib.error
import urllib.request

import time

from twilio.rest import Client

import json

import numpy as np

import tensorflow as tf

from pathlib import Path

from typing import List, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from sqlalchemy import desc

from sqlalchemy.orm import Session

from database import Base, engine, get_db

from models import (

    Device,

    Detection,

    Pest,

    Solution,

    HighRiskSolutionHistory,

)

from pest_data import PEST_DATA, SOLUTION_DATA

from schemas import (

    DetectionCreate,

    DetectionResponse,

    DeviceHeartbeat,

    HealthResponse,
    PestResponse,
)

logger = logging.getLogger(__name__)

PEST_MODEL = os.getenv("PEST_MODEL", "cnn").strip().lower()
USE_YAMNET = PEST_MODEL == "yamnet"

AI_DIR = Path(__file__).resolve().parent / "ai_model"

if USE_YAMNET:
    import tensorflow_hub as hub

    YAMNET_DIR = AI_DIR / "pest_yamnet_updated_candidate"

    ai_model = tf.keras.models.load_model(
        YAMNET_DIR / "best_candidate.keras",
        compile=False,
    )

    with open(
        YAMNET_DIR / "class_names.json",
        "r",
        encoding="utf-8",
    ) as f:
        class_names = json.load(f)

    yamnet = hub.load("https://tfhub.dev/google/yamnet/1")

elif PEST_MODEL == "new_dataset_candidate":
    CANDIDATE_DIR = AI_DIR / "pest_new_dataset_candidate"

    ai_model = tf.keras.models.load_model(
        CANDIDATE_DIR / "best_candidate.keras",
        compile=False,
    )

    with open(
        CANDIDATE_DIR / "class_names.json",
        "r",
        encoding="utf-8",
    ) as f:
        class_names = json.load(f)

    with open(
        CANDIDATE_DIR / "common_names.json",
        "r",
        encoding="utf-8",
    ) as f:
        common_names = json.load(f)

    if len(common_names) != len(class_names):
        raise RuntimeError(
            "Candidate common names do not match model classes."
        )

    print(
        f"Loaded NEW candidate model: {len(class_names)} species"
    )

else:
    ai_model = tf.keras.models.load_model(
        AI_DIR / "best_cnn_v3.keras",
        compile=False,
    )

    with open(
        AI_DIR / "class_names.json",
        "r",
        encoding="utf-8",
    ) as f:
        class_names = json.load(f)

MEL_MATRIX = tf.signal.linear_to_mel_weight_matrix(

    128, 513, 16000, 50, 8000

)

SAMPLE_RATE = 16000
# One signed-int16 LSB at the PCM amplitude scale; less than this is not resolvable.
PCM16_RMS_FLOOR = 1.0 / 32768.0

PEST_IDENTIFICATION_CONFIDENCE = 0.70


if not isinstance(class_names, list) or not class_names:
    raise RuntimeError("The model class-label list is empty or invalid.")

if ai_model.output_shape[-1] != len(class_names):
    raise RuntimeError("Model output does not match the class labels.")

if not USE_YAMNET and ai_model.input_shape != (None, 155, 128, 1):
    raise RuntimeError(
        f"Unexpected CNN input shape: {ai_model.input_shape}"
    )


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


def prepare_audio(audio):

    audio = np.asarray(audio, dtype=np.float32)

    target_length = 80000

    if len(audio) > target_length:

        audio = audio[:target_length]

    elif len(audio) < target_length:

        padded = np.zeros(target_length, dtype=np.float32)

        padded[:len(audio)] = audio

        audio = padded

    max_value = np.max(np.abs(audio))

    if max_value > 0:

        audio = audio / max_value

    stft = tf.signal.stft(

        audio,

        frame_length=1024,

        frame_step=512,

        fft_length=1024

    )

    spectrogram = tf.abs(stft)

    mel = tf.matmul(

        tf.square(spectrogram),

        MEL_MATRIX,

    )

    mel = tf.math.log(mel + 1e-6)

    mean = tf.reduce_mean(mel)

    std = tf.math.reduce_std(mel)

    mel = (mel - mean) / (std + 1e-6)

    return mel[..., tf.newaxis]

def predict_pest(audio):
    waveform = decode_audio_samples(audio)

    if USE_YAMNET:
        # Match the YAMNet training pipeline: 5-second clips at 16 kHz.
        sample_rate = SAMPLE_RATE
        clip_samples = sample_rate * 5
        predictions = []

        for start in range(0, len(waveform), clip_samples):
            clip = waveform[start:start + clip_samples]

            # Ignore a trailing fragment shorter than 1 second.
            if len(clip) < sample_rate:
                continue

            if len(clip) < clip_samples:
                clip = np.pad(clip, (0, clip_samples - len(clip)))

            # Normalize each clip before extracting YAMNet embeddings.
            peak = float(np.max(np.abs(clip)))
            if peak > 0:
                clip = clip / peak

            _, embeddings, _ = yamnet(
                tf.convert_to_tensor(clip, dtype=tf.float32)
            )

            features = tf.reduce_mean(
                embeddings, axis=0
            ).numpy().astype(np.float32)

            scores = ai_model(
                features[np.newaxis, :], training=False
            ).numpy()[0]

            predictions.append(scores)

        if not predictions:
            raise HTTPException(
                status_code=400,
                detail="Audio is too short for pest detection."
            )

        # Average predictions across the available audio clips.
        prediction = np.mean(np.stack(predictions), axis=0)

    else:
        # Preserve the existing production CNN pipeline.
        features = prepare_audio(waveform)
        prediction = ai_model.predict(
            tf.expand_dims(features, 0),
            verbose=0
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
        "confidence": float(prediction[index])
    }

class AISolutionRequest(BaseModel):

    pest: str = Field(min_length=1, max_length=200)

    common_name: str = Field(min_length=1, max_length=200)

    risk: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]

    confidence: float = Field(ge=0, le=1)

    pest_id: str = Field(default="", max_length=200)

    pest_description: str = Field(default="", max_length=2000)

    pest_symptoms: str = Field(default="", max_length=2000)

    crop: str = Field(default="", max_length=100)

class AISolutionResponse(BaseModel):

    pest: str

    common_name: str

    risk: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]

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


def _normalize_pest_label(value: str | None) -> str:
    return "".join(
        character
        for character in (value or "").casefold()
        if character.isalnum()
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


def _request_gemini_solution(payload: AISolutionRequest) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Gemini AI solution generation is not configured.",
        )

    prompt = (
        "You are an agricultural pest-management assistant.\n\n"
        "The Pest Guard sensor detected this insect:\n\n"
        f"Common name: {payload.common_name}\n"
        f"Scientific name: {payload.pest}\n"
        f"Risk: {payload.risk}\n"
        f"AI confidence: {payload.confidence:.2f}\n\n"
        "Crop-specific pesticide data is not verified. Do not name or suggest "
        "any pesticide, medicine, dose, or waiting period.\n\n"
        f"Known pest ID: {payload.pest_id or 'unavailable'}\n"
        f"Known description: {payload.pest_description or 'unavailable'}\n"
        f"Known symptoms: {payload.pest_symptoms or 'unavailable'}\n\n"
        "Generate a concise pest-management response with exactly these JSON "
        "string fields: about, recommended_action, prevention.\n\n"
        "Use the identified pest only. Do not replace it with another species. "
        "Do not claim certainty when confidence is low. Prefer integrated "
        "pest-management guidance. Give short, practical steps based only on "
        "the known pest description and symptoms. Do not invent treatment "
        "claims. Return valid JSON only."
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
                "maxOutputTokens": 1200,
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
        generated = json.loads(content.strip())

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
        "pesticide_recommendation": _pesticide_recommendation(payload.crop),
        **{field: generated[field].strip() for field in required_fields},
        "precautions": _safe_application_instructions(),
    }

# -------------------------------------------------------------------

# Database

# -------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

# -------------------------------------------------------------------

# FastAPI application

# -------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    startup_event()
    yield


# PEST_GUARD_DETECTION_CONTROL_STATE
# Default to stopped after backend restart for fail-safe behavior.
DETECTION_CONTROL_STATE = {}

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
    if isinstance(last_seen, datetime):
        if last_seen.tzinfo is None or last_seen.utcoffset() is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        else:
            last_seen = last_seen.astimezone(timezone.utc)
        age_seconds = (
            datetime.now(timezone.utc) - last_seen
        ).total_seconds()
        is_online = 0 <= age_seconds <= DEVICE_STALE_SECONDS
    return {
        "device_id": device.device_id,
        "name": device.name,
        "status": "ONLINE" if is_online else "OFFLINE",
        "connection": "CONNECTED" if is_online else "DISCONNECTED",
        "last_seen": device.last_seen,
        "temperature": device.temperature,
        "humidity": device.humidity,
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

    for f in payload.model_fields_set & {"temperature", "humidity"}:
        setattr(device, f, getattr(payload, f))

    device.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(device)
    return {
        "message": "Heartbeat received",
        "device": _device_response(device),
    }

# PEST_GUARD_DETECTION_CONTROL_ENDPOINTS
@app.get("/api/devices/{device_id}/detection-control")
def get_detection_control(device_id: str):
    return {
        "device_id": device_id,
        "enabled": bool(DETECTION_CONTROL_STATE.get(device_id, False)),
    }


@app.post("/api/devices/{device_id}/detection-control")
def set_detection_control(device_id: str, payload: dict):
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(
            status_code=422,
            detail="Field 'enabled' must be true or false",
        )

    DETECTION_CONTROL_STATE[device_id] = enabled
    return {"device_id": device_id, "enabled": enabled}


@app.post("/api/ai/predict")
async def ai_predict(request: Request):
    try:
        content_type = request.headers.get("content-type", "")

        # Compact ESP32 transport: signed 16-bit little-endian PCM samples.
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
        predicted_pest = (
            result["pest"] if result["pest"] in class_names else None
        )
        common_name = None
        if (
            PEST_MODEL == "new_dataset_candidate"
            and predicted_pest is not None
        ):
            common_name = common_names[class_names.index(predicted_pest)]

        # The top-scoring class is only a candidate, not a verified identity.
        # Risk remains UNKNOWN until a reviewed species-to-risk mapping exists.
        prediction_data = {
            "status": "UNKNOWN",
            "identification_status": "UNCONFIRMED",
            "identification_label": (
                "Possible match" if predicted_pest else "Unidentified sound"
            ),
            "pest": predicted_pest,
            "common_name": common_name,
            "confidence": result["confidence"],
            "risk": "UNKNOWN",
            "message": "Unverified model prediction",
            "source": "AI_MODEL_PREDICTION",
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

        # Push the candidate to the open Live Monitoring page. This is not
        # saved as a confirmed field detection in the database.
        await manager.broadcast(prediction_data)
        return prediction_data

    except HTTPException:
        raise
    except Exception as error:
        logger.exception(
            "AI prediction failed (model=%s)",
            "yamnet" if USE_YAMNET else "cnn",
        )
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
        "risk": "UNKNOWN",
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
        "risk": "UNKNOWN",
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
    # Match the requested candidate against the database catalog.
    # A match provides candidate-specific guidance, not proof of identity.
    pest_record = _find_verified_pest_record(
        db,
        payload.pest,
        payload.pest_id,
    )

    # If the candidate cannot be matched safely, keep generic guidance.
    if not pest_record:
        return _fallback_uncertain_solution(payload)

    # Fetch the curated solution belonging to this exact pest ID.
    solution_record = (
        db.query(Solution)
        .filter(Solution.pest_id == pest_record.pest_id)
        .first()
    )

    description = (
        pest_record.description
        or "No catalog description is available."
    )
    symptoms = (
        pest_record.symptoms
        or "No catalog symptoms are available."
    )

    # Explain the catalog match without claiming the AI confirmed it.
    about = (
        f"Unverified AI candidate: {pest_record.name} "
        f"({pest_record.scientific_name or pest_record.name}). "
        f"This catalog match does not confirm the insect's identity. "
        f"Catalog description: {description} "
        f"Signs to check in the field: {symptoms}"
    )

    # Use this pest's saved recommendations when available.
    if solution_record:
        recommended_action = (
            solution_record.recommended_action
            or (
                f"Inspect affected plants for these signs: {symptoms} "
                "and confirm the insect before choosing pest-specific control."
            )
        )
        prevention = (
            solution_record.prevention
            or "Monitor affected plants regularly and record changes in crop damage."
        )
    else:
        recommended_action = (
            f"Inspect affected plants for these signs: {symptoms} "
            "and document any damage. Confirm the insect with a qualified "
            "agricultural adviser before choosing pest-specific control."
        )
        prevention = (
            "Monitor affected and nearby plants regularly. Record changes "
            "in crop damage and seek crop-specific advice when needed."
        )

    return {
        "pest": pest_record.scientific_name or pest_record.name,
        "common_name": pest_record.name,
        "risk": "UNKNOWN",
        "confidence": payload.confidence,
        "crop": payload.crop,
        "about": about,
        "recommended_action": recommended_action,
        "pesticide_recommendation": _pesticide_recommendation(
            payload.crop,
            uncertain=True,
        ),
        "prevention": prevention,
        "precautions": (
            "Do not apply a pesticide based on this unverified audio result. "
            "Confirm the pest and crop with a local agricultural officer. "
            "If a product is recommended, follow its registered label, "
            "protective-equipment requirements, and pre-harvest waiting period."
        ),
    }

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
    detection_pest = payload.pest if payload.pest in class_names else None
    detection_risk = payload.risk
    if detection_status == "HARMFUL_PEST":
        # Keep a trained class only as an unverified suggestion.
        detection_status = "UNKNOWN"
        detection_risk = "UNKNOWN"
    elif detection_status == "UNKNOWN":
        detection_risk = "UNKNOWN"
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

    detection_data = {

        "id": detection.id,

        "device_id": detection.device_id,

        "status": detection.status,

        "pest": detection.pest,

        "confidence": detection.confidence,

        "risk": detection.risk,

        "temperature": detection.temperature,

        "humidity": detection.humidity,

        "audio_file": detection.audio_file,

        "message": detection.message,

        "detected_at": (

            detection.detected_at.isoformat()

            if detection.detected_at

            else None

        ),

    }

    # Send SMS only for HIGH-risk detections.

    send_high_risk_sms(detection_data)

    # Send the new detection immediately to connected website clients.

    await manager.broadcast(detection_data)

    return detection

@app.get(

    "/api/detections/latest",

)

def get_latest_detection(

    db: Session = Depends(get_db),

):

    detection = (

        db.query(Detection)

        .order_by(desc(Detection.detected_at))

        .first()

    )

    if not detection:

        return {

            "detection": None

        }

    return {

        "detection": {

            "id": detection.id,

            "device_id": detection.device_id,

            "status": detection.status,

            "pest": detection.pest,

            "confidence": detection.confidence,

            "risk": detection.risk,

            "temperature": detection.temperature,

            "humidity": detection.humidity,

            "audio_file": detection.audio_file,

            "message": detection.message,

            "detected_at": detection.detected_at,

        }

    }

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

        "detections": [

            {

                "id": item.id,

                "device_id": item.device_id,

                "status": item.status,

                "pest": item.pest,

                "confidence": item.confidence,

                "risk": item.risk,

                "temperature": item.temperature,

                "humidity": item.humidity,

                "audio_file": item.audio_file,

                "message": item.message,

                "detected_at": item.detected_at,

            }

            for item in detections

        ]

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
