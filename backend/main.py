import asyncio

import os

import urllib.error

import urllib.request

from twilio.rest import Client

import json

import numpy as np

import tensorflow as tf

from pathlib import Path

from datetime import datetime, timedelta

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

    128, 513, 16000, 80, 7600

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





class AISolutionRequest(BaseModel):

    pest: str = Field(min_length=1, max_length=200)

    common_name: str = Field(min_length=1, max_length=200)

    risk: Literal["HIGH", "MEDIUM"]

    confidence: float = Field(ge=0, le=1)

    pest_id: str = Field(default="", max_length=200)

    pest_description: str = Field(default="", max_length=2000)

    pest_symptoms: str = Field(default="", max_length=2000)





class AISolutionResponse(BaseModel):

    pest: str

    common_name: str

    risk: Literal["HIGH", "MEDIUM"]

    confidence: float

    about: str

    recommended_action: str

    prevention: str

    precautions: str





def _request_openai_solution(payload: AISolutionRequest) -> dict:

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:

        raise HTTPException(

            status_code=503,

            detail="AI solution generation is not configured.",

        )



    prompt = (

        "You are an agricultural pest-management assistant.\n\n"

        "The Pest Guard sensor detected this insect:\n\n"

        f"Common name: {payload.common_name}\n"

        f"Scientific name: {payload.pest}\n"

        f"Risk: {payload.risk}\n"

        f"AI confidence: {payload.confidence:.2f}\n\n"

        f"Known pest ID: {payload.pest_id or 'unavailable'}\n"

        f"Known description: {payload.pest_description or 'unavailable'}\n"

        f"Known symptoms: {payload.pest_symptoms or 'unavailable'}\n\n"

        "Generate a concise pest-management response with these JSON string "

        "fields: about, recommended_action, prevention, precautions.\n\n"

        "Use the identified pest only. Do not replace it with another species. "

        "Do not claim certainty when confidence is low. Prefer integrated "

        "pest-management guidance. Do not recommend dangerous pesticide "

        "mixing, unsafe dosages, or illegal products. Crop information is "

        "unavailable, so clearly say that exact treatment depends on the crop "

        "and local agricultural guidance. Return valid JSON only."

    )

    request_body = json.dumps(

        {

            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),

            "messages": [{"role": "user", "content": prompt}],

            "response_format": {"type": "json_object"},

            "temperature": 0.2,

        }

    ).encode("utf-8")

    provider_request = urllib.request.Request(

        "https://api.openai.com/v1/chat/completions",

        data=request_body,

        headers={

            "Authorization": f"Bearer {api_key}",

            "Content-Type": "application/json",

        },

        method="POST",

    )



    try:

        with urllib.request.urlopen(provider_request, timeout=25) as response:

            provider_data = json.loads(response.read().decode("utf-8"))

        content = provider_data["choices"][0]["message"]["content"]

        generated = json.loads(content)

    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as error:

        raise RuntimeError("AI solution provider returned an invalid or unavailable response.") from error



    required_fields = (

        "about",

        "recommended_action",

        "prevention",

        "precautions",

    )

    if not isinstance(generated, dict) or any(

        not isinstance(generated.get(field), str) or not generated[field].strip()

        for field in required_fields

    ):

        raise RuntimeError("AI solution provider returned incomplete guidance.")



    return {

        "pest": payload.pest,

        "common_name": payload.common_name,

        "risk": payload.risk,

        "confidence": payload.confidence,

        **{field: generated[field].strip() for field in required_fields},

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

    return {"history": [
        {
            "id": item.id, "detection_id": item.detection_id, "device_id": item.device_id,
            "pest_id": item.pest_id, "pest": item.pest, "common_name": item.common_name,
            "image_url": item.image_url, "risk": item.risk, "confidence": item.confidence,
            "temperature": item.temperature, "humidity": item.humidity,
            "solution_title": item.solution_title, "solution_description": item.solution_description,
            "recommended_action": item.recommended_action, "prevention": item.prevention,
            "detected_at": item.detected_at, "created_at": item.created_at,
        }
        for item in history
    ]}

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

async def ai_predict(request: Request):

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



            audio = np.frombuffer(

                raw_audio,

                dtype="<i2",

            ).astype(np.float32)



        else:

            payload = await request.json()



            if "audio" not in payload:

                raise HTTPException(

                    status_code=400,

                    detail="Audio data is required",

                )



            audio = payload["audio"]



        result = predict_pest(audio)



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



    except HTTPException:

        raise



    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=f"AI prediction failed: {str(error)}",

        )





@app.post("/api/ai/solution", response_model=AISolutionResponse)

async def generate_ai_solution(payload: AISolutionRequest):

    try:

        return await asyncio.to_thread(_request_openai_solution, payload)

    except HTTPException:

        raise

    except Exception as error:

        print("AI solution generation failed:", repr(error))

        raise HTTPException(

            status_code=502,

            detail="AI solution generation is temporarily unavailable. Please try again.",

        ) from error





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
    db.flush()

    # Save every HIGH-risk detection together with the solution that was
    # available at detection time. If curated guidance is unavailable and
    # OpenAI is unavailable, keep a safe built-in fallback so the history
    # record is never saved without solution content.
    if payload.risk == "HIGH":
        pest_record = None

        if payload.pest:
            pest_record = (
                db.query(Pest)
                .filter(
                    (Pest.pest_id == payload.pest)
                    | (Pest.name == payload.pest)
                    | (Pest.scientific_name == payload.pest)
                )
                .first()
            )

        # Also try the seeded pest data directly. This keeps the resolver
        # useful even if the database does not yet contain a matching row.
        if not pest_record and payload.pest:
            for item in PEST_DATA:
                if (
                    item.get("pest_id") == payload.pest
                    or item.get("name") == payload.pest
                    or item.get("scientific_name") == payload.pest
                ):
                    pest_record = Pest(
                        pest_id=item.get("pest_id"),
                        name=item.get("name") or payload.pest,
                        scientific_name=item.get("scientific_name"),
                        description=item.get("description"),
                        risk=item.get("risk"),
                        symptoms=item.get("symptoms"),
                    )
                    break

        common_name = pest_record.name if pest_record else (payload.pest or "Unknown pest")
        pest_id = pest_record.pest_id if pest_record else None

        solution_record = None
        if pest_id:
            solution_record = (
                db.query(Solution)
                .filter(Solution.pest_id == pest_id)
                .first()
            )

        solution_title = None
        solution_description = None
        recommended_action = None
        prevention = None

        if solution_record:
            # Preferred path: use the curated solution already stored in DB.
            solution_title = solution_record.title
            solution_description = solution_record.description
            recommended_action = solution_record.recommended_action
            prevention = solution_record.prevention
        else:
            # Second path: generate the same type of guidance used by the
            # Solutions page.
            try:
                ai_solution_payload = AISolutionRequest(
                    pest=payload.pest or common_name,
                    common_name=common_name,
                    risk="HIGH",
                    confidence=payload.confidence or 0.0,
                    pest_id=pest_id or "",
                    pest_description=(
                        pest_record.description if pest_record else ""
                    ),
                    pest_symptoms=(
                        pest_record.symptoms if pest_record else ""
                    ),
                )

                generated_solution = await asyncio.to_thread(
                    _request_openai_solution,
                    ai_solution_payload,
                )

                solution_title = f"{common_name} HIGH Risk Solution"
                solution_description = generated_solution.get("about")
                recommended_action = generated_solution.get(
                    "recommended_action"
                )
                prevention = generated_solution.get("prevention")

            except Exception as error:
                # Final fallback: do not leave the saved HIGH-risk alert
                # without guidance just because the external AI provider
                # is temporarily unavailable.
                print(
                    "HIGH-risk AI solution generation failed; "
                    "using built-in fallback:",
                    repr(error),
                )

                solution_title = f"{common_name} HIGH Risk Safety Guidance"
                solution_description = (
                    f"A HIGH-risk detection was recorded for {common_name}. "
                    "Confirm the pest in the field before treatment and "
                    "inspect affected plants for feeding damage or visible "
                    "insects."
                )
                recommended_action = (
                    "Isolate the affected area if practical, inspect nearby "
                    "plants, remove heavily affected plant material where "
                    "appropriate, and use an integrated pest-management "
                    "method recommended for the crop and confirmed pest."
                )
                prevention = (
                    "Continue field monitoring, remove suitable pest habitat "
                    "where practical, maintain crop hygiene, and follow local "
                    "agricultural guidance for the confirmed pest and crop."
                )

        db.add(
            HighRiskSolutionHistory(
                detection_id=detection.id,
                device_id=payload.device_id,
                pest_id=pest_id,
                pest=payload.pest,
                common_name=common_name,
                # Pest images are owned by the Vercel frontend asset mapping.
                # The Solutions page resolves the correct image from the
                # stored pest/model name when image_url is not present.
                image_url=None,
                risk="HIGH",
                confidence=payload.confidence,
                temperature=payload.temperature,
                humidity=payload.humidity,
                solution_title=solution_title,
                solution_description=solution_description,
                recommended_action=recommended_action,
                prevention=prevention,
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