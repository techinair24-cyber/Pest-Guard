# Pest Guard backend

FastAPI service for the ESP32-S3, AI inference, SQLite storage, browser REST API, WebSocket updates, and optional SMS alerts.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Run the command from the `backend` directory. The service creates `pest_guard.db` on first start and seeds pest and solution reference catalogs. Detection records are created by `POST /api/device/detection`.

## Hardware event

`POST /api/device/detection` accepts `device_id`, `status`, and optional pest, confidence, risk, temperature, and humidity fields. Unvalidated `HARMFUL_PEST` claims are recorded as `UNKNOWN`, then broadcast on `/api/ws/detections`.

The CNN/YAMNet inference endpoint and model loading are in `main.py`. SMS credentials and provider configuration belong in `.env`, based on `.env.example`.

## Audio prediction safety

`POST /api/ai/predict` accepts mono 16 kHz audio as either signed 16-bit PCM in an `application/octet-stream` body (little-endian) or JSON `audio` samples (signed int16 values, or normalized floats in `[-1, 1]`). Inputs shorter than one second, malformed samples, and AC RMS levels at or below one int16 least-significant bit are rejected. CNN features retain the 5-second, 80,000-sample training preprocessing.

The current production checkpoint has no validation-supported identification threshold. The endpoint therefore returns `status: "UNKNOWN"`, `pest: null`, and `risk: "UNKNOWN"`; its existing `confidence` response field contains the top model score, not a calibrated probability. Device-reported `HARMFUL_PEST` detections are also stored as `UNKNOWN` until device-level validation supports a threshold. Do not use an uncalibrated score for species-specific treatment.

Run the focused safety tests from this directory:

```powershell
python -m unittest test_prediction_safety -v
```
