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

Run the command from the `backend` directory. The service creates `pest_guard.db` on first start and seeds pest, crop, and solution-review reference data. Detection records are created by `POST /api/device/detection`.

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

Audio inference uses the eight-group hierarchy in
`pest_guard_hierarchy_inference_8class.py`, loaded by `main.py` from
`ai_model\pest_guard_8class_candidate`. The lightweight background gate runs separately
before insect classification. The hierarchy manifest currently labels this bundle as
experimental; its presence does not establish production validation. SMS credentials
and provider configuration belong in `.env`, based on `.env.example`.

## Audio prediction safety

`POST /api/ai/predict` accepts mono 16 kHz audio as either signed 16-bit PCM in an `application/octet-stream` body (little-endian) or JSON `audio` samples (signed int16 values, or normalized floats in `[-1, 1]`). Inputs shorter than one second, malformed samples, and AC RMS levels at or below one int16 least-significant bit are rejected. The hierarchy uses peak-normalized 5-second, 80,000-sample audio and 128-bin log-mel features.

The background gate uses the threshold stored in its artifact by default. Set `PEST_BACKGROUND_GATE_THRESHOLD` to override it. The gate runs independently of the hierarchy's group and subtype confidence thresholds.

The endpoint returns `status: "UNKNOWN"` and `identification_status: "UNCONFIRMED"`; a matching top class or group is only an unverified suggestion. Confidence values are model scores, not calibrated probabilities. Device-reported `HARMFUL_PEST` detections are also stored as `UNKNOWN`. Do not use an uncalibrated score or suggested class for species-specific treatment.

AI detections also include `insect_group` and `group_score`. Group-only and uncertain subtype results retain the predicted group without claiming a species identification. Confidence values and scores are model outputs and are not calibrated probabilities; do not use them alone for species-specific treatment.

## Solution guidance

The Solutions page uses manually maintained, source-attributed records in `solution_data.py`; it does not generate guidance with an external AI provider. Per-pest research coverage is loaded from the root `pest_crop_evidence_matrix.csv` into `pest_solution_coverage`; it is separate from publishable crop-specific solution records. The crop list in `crop_data.py` defines supported search choices, not pest-to-crop relationships.

`GET /api/crops` lists supported crops. `GET /api/solutions?crop_id={crop_id}` returns only records marked `VERIFIED` that match the crop and catalogue risk, have species identity and crop-damage evidence, and provide field-level sources for each populated recommendation. The endpoint supports HIGH, MEDIUM, and LOW catalogue risks. Unverified management categories remain unavailable rather than being inferred. Internal scientific names are not included in the public solution response.

`GET /api/solutions/history/high-risk` returns persisted history records and a `total` count. It does not attach unverified or legacy solution text to those records. The API response shape is defined in `schemas.py`; source organization, URL, title, and review date are included with each verified crop solution.

Run the focused safety tests from this directory:

```powershell
python -m unittest test_prediction_safety -v
python -m unittest test_insect_groups -v
```
