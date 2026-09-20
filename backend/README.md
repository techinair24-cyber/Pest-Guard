# Pest Guard backend

FastAPI service for the ESP32-S3, AI inference, SQLite storage, browser REST API, WebSocket updates, and optional SMS alerts.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The service creates `pest_guard.db` on first start. It seeds only pest and solution reference catalogs. Detection records are created by `POST /api/detection` or `POST /api/device/detection`.

## Hardware event

`POST /api/device/detection` accepts the ESP32 payload with `device_id`, `audio_prediction`, `vibration`, and optional `timestamp`. Harmful results are stored and broadcast on `/api/ws/detections`.

The trained model belongs behind `app/ai/inference.py`. SMS credentials and provider configuration belong in `.env`, based on `.env.example`.
