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
cd ..
python -m uvicorn backend.app.main:app --reload --port 8000
```

The backend initializes SQLite and seeds only the pest and solution reference catalogs. It does not create device or detection records at startup.

## API

- `GET /api/health`
- `GET /api/device/status`
- `POST /api/device/register`
- `GET /api/detection/latest`
- `GET /api/detections`
- `POST /api/detection`
- `POST /api/device/detection`
- `GET /api/pests`
- `GET /api/solutions`
- `GET /api/solutions/{pest_id}`
- `WS /ws/detections`

A hardware-shaped event can be sent to `POST /api/device/detection` with `device_id`, `audio_prediction`, `vibration`, and an optional timestamp. Stored events are broadcast to connected browser clients. SMS delivery and trained CNN inference are integration boundaries in `backend/app/services/sms.py` and `backend/app/ai/inference.py`; credentials and model paths are intentionally not hardcoded.
