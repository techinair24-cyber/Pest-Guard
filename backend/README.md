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

## Field-unit detection control

The dashboard's existing `POST` and `GET /api/devices/{device_id}/detection-control`
routes keep command state in the database so separate API workers see the same
request. Each command has a `command_id`; the ESP32 must poll the GET route, apply
`enabled`, and send both `detection_enabled` and that `control_command_id` in its
heartbeat. Only a heartbeat whose command ID matches the latest request can confirm
`RUNNING` or `STOPPED`. Heartbeats without the command ID remain valid device
heartbeats but do not acknowledge a control request.

An online device with no matching report is `REQUESTED` for up to 60 seconds, then
`TIMEOUT`; a missing or stale device heartbeat is `DEVICE_OFFLINE`. The firmware
source is `..\p1_oct1a.ino`; flash the updated firmware before expecting acknowledgements
from a physical device. Build and hardware-test it with the ESP32 board toolchain.

## Hardware event

`POST /api/device/detection` accepts `device_id`, `status`, and optional pest, confidence, risk, temperature, and humidity fields. Unvalidated `HARMFUL_PEST` claims are recorded as `UNKNOWN`, then broadcast on `/api/ws/detections`.

Audio inference uses the CNN embedding and the required four-group hierarchical classifier.
Keep `ai_model\pest_new_dataset_candidate\best_candidate.keras`, `class_names.json`, and
`hierarchical_audio_classifier.joblib` together. The backend refuses to start if the
hierarchical artifact is missing or incompatible; it does not silently fall back to CNN-only
predictions. At startup, check for a `Pest Guard inference ready: path=hierarchical` log
containing the artifact path and `expected_species=47`. SMS credentials and provider
configuration belong in `.env`, based on `.env.example`.

## Audio prediction safety

`POST /api/ai/predict` accepts mono 16 kHz audio as either signed 16-bit PCM in an `application/octet-stream` body (little-endian) or JSON `audio` samples (signed int16 values, or normalized floats in `[-1, 1]`). Inputs shorter than one second, malformed samples, and AC RMS levels at or below one int16 least-significant bit are rejected. CNN features retain the 5-second, 80,000-sample training preprocessing.

The runtime background-gate threshold defaults to `0.15` to accept all 412 labeled insect validation clips; the saved gate artifact's original threshold is `0.25`. On the pilot background holdout, the lower runtime threshold increases false acceptance from 5.0% (3/60) to 8.3% (5/60). Silence is still rejected by the PCM RMS floor. Set `PEST_BACKGROUND_GATE_THRESHOLD` to override the runtime threshold.

The current production checkpoint has no validation-supported identification threshold. The endpoint returns `status: "UNKNOWN"` and `risk: "UNKNOWN"`; `pest` carries the top class only when it matches a trained label, as an unverified suggestion. The existing `confidence` response field is the top model score, not a calibrated probability. Device-reported `HARMFUL_PEST` detections are also stored as `UNKNOWN`. Do not use an uncalibrated score or suggested class for species-specific treatment.

AI detections also include `insect_group` and `group_score`. The group labels come from the class-aligned `group_by_label` mapping in the required hierarchical model bundle. The group score is the sum of the normalized joint species scores for all species in that group; it is an uncalibrated ranking estimate, not a confirmed identification. The response's `top_predictions` remains the three highest-scoring species candidates, including their actual model scores and common names when available. Older rows are assigned a group from their saved species label; their group score remains unavailable unless it was stored.

Run the focused safety tests from this directory:

```powershell
python -m unittest test_prediction_safety -v
python -m unittest test_insect_groups -v
```

To replay the production CNN and hierarchical scores on the 412-recording validation manifest, run `python evaluate_hierarchical_classifier.py` from this directory. It requires the local `ai_model\pest_new_dataset_candidate\split_manifest.json` and `Pest_Guard_New_Datasets` folder; it does not retrain or overwrite artifacts.
