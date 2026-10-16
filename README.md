# Pest Guard

Deep Learning-Based Pest Detection System Using Sound Analytics.

Pest Guard connects an ESP32-S3 field unit, INMP441 microphone, DFRobot DFR0052 vibration sensor, AI inference, SQLite, FastAPI, and a React monitoring interface. The project uses sound and vibration only; it has no camera system.

## Frontend

```powershell
npm install
npm run dev
```

Set `VITE_API_BASE_URL` and optionally `VITE_WS_URL` in a root `.env` file using `.env.example`. When the API is unavailable, the frontend displays an unavailable state and does not invent detection data.

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

The backend initializes SQLite and seeds only the pest and solution reference catalogs. It does not create device or detection records at startup.

## API

- `GET /api/health`
- `GET /api/devices`
- `GET /api/devices/{device_id}`
- `POST /api/devices/{device_id}/heartbeat`
- `GET /api/devices/{device_id}/detection-control`
- `POST /api/devices/{device_id}/detection-control`
- `POST /api/ai/predict`
- `POST /api/ai/solution`
- `GET /api/detections`
- `GET /api/detections/latest`
- `POST /api/device/detection`
- `GET /api/pests`
- `GET /api/pests/{pest_id}`
- `GET /api/solutions`
- `GET /api/solutions/{pest_id}`
- `GET /api/solutions/history/high-risk`
- `DELETE /api/solutions/history/high-risk`
- `WS /api/ws/detections`

`POST /api/device/detection` accepts `device_id`, `status`, and optional pest, confidence, risk, temperature, and humidity fields. Device-reported `HARMFUL_PEST` results are stored as `UNKNOWN` until a validation-supported identification threshold is available. Stored events are broadcast to connected browser clients. CNN/YAMNet inference is served by `backend/main.py`; SMS alerts are optional.
