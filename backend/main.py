import json
import numpy as np
import tensorflow as tf
from pathlib import Path
from datetime import datetime, timedelta
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Device, Detection, Pest, Solution
from pest_data import PEST_DATA, SOLUTION_DATA
from schemas import (
    DetectionCreate,
    DetectionResponse,
    DeviceHeartbeat,
    DeviceResponse,
    HealthResponse,
    PestResponse,
    SolutionResponse,
)
# -------------------------------------------------------------------
# AI MODEL
# -------------------------------------------------------------------

AI_DIR = Path(__file__).resolve().parent / "ai_model"

ai_model = tf.keras.models.load_model(
    AI_DIR / "best_cnn_v3.keras"
)

with open(AI_DIR / "class_names.json", "r", encoding="utf-8") as f:
    class_names = json.load(f)

MEL_MATRIX = tf.signal.linear_to_mel_weight_matrix(
    128, 513, 16000, 50, 8000
)


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

    magnitude = tf.abs(stft)

    mel = tf.matmul(magnitude, MEL_MATRIX)
    mel = tf.math.log(mel + 1e-6)

    mean = tf.reduce_mean(mel)
    std = tf.math.reduce_std(mel)

    mel = (mel - mean) / (std + 1e-6)

    return mel[..., tf.newaxis]


def predict_pest(audio):
    features = prepare_audio(audio)
    prediction = ai_model.predict(
        tf.expand_dims(features, 0),
        verbose=0
    )[0]

    index = int(np.argmax(prediction))

    return {
        "pest": class_names[index],
        "confidence": float(prediction[index])
    }

# -------------------------------------------------------------------
# Database
# -------------------------------------------------------------------

Base.metadata.create_all(bind=engine)


# -------------------------------------------------------------------
# FastAPI application
# -------------------------------------------------------------------

app = FastAPI(
    title="Pest Guard API",
    description="Backend API for the Pest Guard AI pest detection system.",
    version="1.0.0",
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


@app.on_event("startup")
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

@app.get("/api/devices")
def get_devices(db: Session = Depends(get_db)):
    devices = db.query(Device).order_by(Device.id.asc()).all()

    return {
        "devices": [
            {
                "device_id": device.device_id,
                "name": device.name,
                "status": device.status,
                "connection": device.connection,
                "last_seen": device.last_seen,
                "temperature": device.temperature,
                "humidity": device.humidity,
            }
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
        "device": {
            "device_id": device.device_id,
            "name": device.name,
            "status": device.status,
            "connection": device.connection,
            "last_seen": device.last_seen,
            "temperature": device.temperature,
            "humidity": device.humidity,
        }
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
    device.temperature = payload.temperature
    device.humidity = payload.humidity
    device.last_seen = datetime.utcnow()

    db.commit()
    db.refresh(device)

    return {
        "message": "Heartbeat received",
        "device": {
            "device_id": device.device_id,
            "name": device.name,
            "status": device.status,
            "connection": device.connection,
            "last_seen": device.last_seen,
            "temperature": device.temperature,
            "humidity": device.humidity,
        },
    }
@app.post("/api/ai/predict")
async def ai_predict(payload: dict):
    if "audio" not in payload:
        raise HTTPException(status_code=400, detail="Audio data is required")

    try:
        result = predict_pest(payload["audio"])

        confidence = result["confidence"]

        if confidence >= 0.70:
            risk = "HIGH"
            status = "HARMFUL_PEST"
        elif confidence >= 0.40:
            risk = "MEDIUM"
            status = "UNKNOWN"
        else:
            risk = "LOW"
            status = "UNKNOWN"

        return {
            "status": status,
            "pest": result["pest"],
            "confidence": confidence,
            "risk": risk,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"AI prediction failed: {str(error)}",
        )

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
        if payload.confidence < 0 or payload.confidence > 1:
            raise HTTPException(
                status_code=400,
                detail="Confidence must be between 0 and 1",
            )

    detected_time = payload.detected_at or datetime.utcnow()

    detection = Detection(
        device_id=payload.device_id,
        status=payload.status,
        pest=payload.pest,
        confidence=payload.confidence,
        risk=payload.risk,
        temperature=payload.temperature,
        humidity=payload.humidity,
        audio_file=payload.audio_file,
        message=payload.message,
        detected_at=detected_time,
    )

    db.add(detection)

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
    device.last_seen = datetime.utcnow()

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
        "detected_at": detection.detected_at,
    }

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
            # Keep the connection alive.
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)

    except Exception:
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