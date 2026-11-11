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

The backend initializes SQLite and seeds the pest catalog, supported crop list, and solution-review coverage. It does not create device or detection records at startup.

## API

- `GET /api/health`
- `GET /api/devices`
- `GET /api/devices/{device_id}`
- `POST /api/devices/{device_id}/heartbeat`
- `GET /api/devices/{device_id}/detection-control`
- `POST /api/devices/{device_id}/detection-control`
- `POST /api/ai/predict`
- `GET /api/detections`
- `GET /api/detections/latest`
- `POST /api/device/detection`
- `GET /api/pests`
- `GET /api/pests/{pest_id}`
- `GET /api/crops`
- `GET /api/crops?search={query}`
- `GET /api/solutions?crop_id={crop_id}`
- `GET /api/solutions?crop_id={crop_id}&pest_id={pest_id}`
- `GET /api/solutions/history/high-risk`
- `DELETE /api/solutions/history/high-risk`
- `WS /ws/detections`

`POST /api/device/detection` accepts `device_id`, `status`, and optional pest, confidence, risk, temperature, and humidity fields. Device-reported `HARMFUL_PEST` results are stored as `UNKNOWN` until a validation-supported identification threshold is available. Stored events are broadcast to connected browser clients. CNN/YAMNet inference is served by `backend/main.py`; SMS alerts are optional.

The Solutions page uses manually maintained, source-attributed pest/crop/risk records. `GET /api/solutions` requires a supported `crop_id` and returns only complete `VERIFIED` records whose risk matches the pest catalog. Unreviewed or unsupported mappings are not returned; an empty result is expected until the relevant record has been verified.
