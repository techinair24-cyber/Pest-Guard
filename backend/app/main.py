import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .database.connection import get_connection, init_db
from .database.seed import seed_reference_data
from .models.schemas import DetectionPayload, DeviceDetectionPayload, DeviceRegistration
from .services.sms import SmsNotConfiguredError, send_sms_alert
from .websocket.manager import manager

app = FastAPI(title='Pest Guard API', version='1.0.0')
origins = [origin.strip() for origin in os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://localhost:5174').split(',') if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])


@app.on_event('startup')
def startup():
    init_db()
    seed_reference_data()


def row_to_dict(row):
    return dict(row) if row else None


def normalize_detection(row):
    detection = row_to_dict(row)
    if detection:
        detection['confidence'] = float(detection['confidence'])
    return detection


@app.get('/')
def root():
    return {'service': 'Pest Guard API', 'status': 'available'}


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'pest-guard-api'}


@app.get('/api/device/status')
def device_status(device_id: Optional[str] = None):
    query = 'SELECT * FROM devices'
    params = ()
    if device_id:
        query += ' WHERE device_id = ?'
        params = (device_id,)
    query += ' ORDER BY last_seen DESC LIMIT 1'
    with get_connection() as connection:
        device = connection.execute(query, params).fetchone()
    if not device:
        return {'available': False, 'message': 'No device has connected yet', 'device': None}
    device_data = row_to_dict(device)
    last_seen = datetime.fromisoformat(device_data['last_seen']) if device_data.get('last_seen') else None
    is_online = bool(last_seen and (datetime.now(timezone.utc) - last_seen).total_seconds() <= 120)
    device_data['connection'] = 'ONLINE' if is_online else 'OFFLINE'
    return {'available': True, 'device': device_data}


@app.get('/api/devices/{device_id}')
def device_by_id(device_id: str):
    return device_status(device_id)


@app.post('/api/device/register')
def register_device(payload: DeviceRegistration):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute('''INSERT INTO devices (device_id, name, last_seen, microphone_status, vibration_status, ai_status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET name=excluded.name, last_seen=excluded.last_seen,
            microphone_status=excluded.microphone_status, vibration_status=excluded.vibration_status, ai_status=excluded.ai_status''',
            (payload.device_id, payload.name, now, payload.microphone_status, payload.vibration_status, payload.ai_status))
        connection.commit()
        device = connection.execute('SELECT * FROM devices WHERE device_id = ?', (payload.device_id,)).fetchone()
    return row_to_dict(device)


@app.get('/api/detection/latest')
def latest_detection():
    with get_connection() as connection:
        detection = connection.execute('SELECT * FROM detections ORDER BY timestamp DESC, id DESC LIMIT 1').fetchone()
    return {'available': bool(detection), 'detection': normalize_detection(detection)}


@app.get('/api/detections')
def detection_history(limit: int = 25):
    limit = max(1, min(limit, 100))
    with get_connection() as connection:
        rows = connection.execute('SELECT * FROM detections ORDER BY timestamp DESC, id DESC LIMIT ?', (limit,)).fetchall()
    return {'detections': [normalize_detection(row) for row in rows]}


@app.get('/api/pests')
def pests():
    with get_connection() as connection:
        rows = connection.execute('SELECT * FROM pests ORDER BY name').fetchall()
    return {'pests': [row_to_dict(row) for row in rows]}


@app.get('/api/pests/{pest_id}')
def pest(pest_id: str):
    with get_connection() as connection:
        row = connection.execute('SELECT * FROM pests WHERE id = ?', (pest_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Pest not found')
    return row_to_dict(row)


@app.get('/api/solutions')
def solutions():
    with get_connection() as connection:
        rows = connection.execute('SELECT * FROM solutions ORDER BY pest_name').fetchall()
    return {'solutions': [row_to_dict(row) for row in rows]}


@app.get('/api/solutions/{pest_id}')
def solution(pest_id: str):
    with get_connection() as connection:
        row = connection.execute('SELECT * FROM solutions WHERE pest_id = ?', (pest_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Solution not found')
    return row_to_dict(row)


async def store_detection(payload: DetectionPayload):
    if payload.status not in {'HARMFUL_PEST', 'NON_PEST', 'UNKNOWN'}:
        raise HTTPException(status_code=422, detail='status must be HARMFUL_PEST, NON_PEST, or UNKNOWN')
    timestamp = (payload.timestamp or datetime.now(timezone.utc)).isoformat()
    with get_connection() as connection:
        connection.execute('''INSERT INTO detections (device_id, pest, confidence, status, risk, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)''', (payload.device_id, payload.pest, payload.confidence, payload.status, payload.risk, timestamp))
        connection.execute('''INSERT INTO devices (device_id, name, last_seen, microphone_status, vibration_status, ai_status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET last_seen=excluded.last_seen''',
            (payload.device_id, payload.device_id, timestamp, 'CONNECTED', 'CONNECTED', 'READY'))
        connection.commit()
        row = connection.execute('SELECT * FROM detections ORDER BY id DESC LIMIT 1').fetchone()
    detection = normalize_detection(row)
    await manager.broadcast(detection)
    if detection['status'] == 'HARMFUL_PEST':
        try:
            send_sms_alert(detection)
        except SmsNotConfiguredError:
            pass
    return detection


@app.post('/api/detection')
async def create_detection(payload: DetectionPayload):
    return await store_detection(payload)


@app.post('/api/device/detection')
async def device_detection(payload: DeviceDetectionPayload):
    prediction = payload.audio_prediction
    detection = DetectionPayload(device_id=payload.device_id, pest=prediction.pest,
        confidence=prediction.confidence, status=prediction.status,
        risk=prediction.risk, timestamp=payload.timestamp)
    return await store_detection(detection)


@app.websocket('/ws/detections')
async def detection_socket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
