from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path.cwd()
BACKEND = PROJECT / "backend" / "main.py"
API_JS = PROJECT / "src" / "services" / "api.js"
LIVE_JSX = PROJECT / "src" / "pages" / "LiveMonitoring.jsx"
LIVE_CSS = PROJECT / "src" / "pages" / "LiveMonitoring.css"
FIRMWARE = Path(r"C:\Users\Deepthi MG\Desktop\p1_oct1a\p1_oct1a.ino")

required = [BACKEND, API_JS, LIVE_JSX, LIVE_CSS, FIRMWARE]
missing = [str(path) for path in required if not path.is_file()]
if missing:
    print("STOPPED. These files were not found; no files were changed:")
    for item in missing:
        print(" -", item)
    print("Run this script from the Pest guard project root and verify the firmware path.")
    sys.exit(1)

contents = {path: path.read_text(encoding="utf-8-sig") for path in required}
updated = dict(contents)

# 1) Backend: in-memory desired state. It defaults to OFF after server restart.
backend = updated[BACKEND]
if "# PEST_GUARD_DETECTION_CONTROL_STATE" not in backend:
    app_anchor = re.search(r"(?m)^app\s*=\s*FastAPI\s*\(", backend)
    if not app_anchor:
        raise SystemExit("STOPPED: Could not find FastAPI app declaration; no files written.")
    state_code = (
        "# PEST_GUARD_DETECTION_CONTROL_STATE\n"
        "# Default to stopped after backend restart for fail-safe behavior.\n"
        "DETECTION_CONTROL_STATE = {}\n\n"
    )
    backend = backend[:app_anchor.start()] + state_code + backend[app_anchor.start():]

if "# PEST_GUARD_DETECTION_CONTROL_ENDPOINTS" not in backend:
    predict_anchor = re.search(
        r"(?m)^@app\.post\(\s*['\"]?/api/ai/predict['\"]?\s*,?\s*\)",
        backend,
    )
    if not predict_anchor:
        raise SystemExit("STOPPED: Could not find /api/ai/predict route to anchor new endpoint; no files written.")
    routes = '''# PEST_GUARD_DETECTION_CONTROL_ENDPOINTS
@app.get("/api/devices/{device_id}/detection-control")
def get_detection_control(device_id: str):
    return {
        "device_id": device_id,
        "enabled": bool(DETECTION_CONTROL_STATE.get(device_id, False)),
    }


@app.post("/api/devices/{device_id}/detection-control")
def set_detection_control(device_id: str, payload: dict):
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(
            status_code=422,
            detail="Field 'enabled' must be true or false",
        )

    DETECTION_CONTROL_STATE[device_id] = enabled
    return {"device_id": device_id, "enabled": enabled}


'''
    backend = backend[:predict_anchor.start()] + routes + backend[predict_anchor.start():]
updated[BACKEND] = backend

# 2) Frontend API helpers.
api_js = updated[API_JS]
if "export const getDetectionControl =" not in api_js:
    latest_anchor = "export const getLatestDetection = async () => {"
    if api_js.count(latest_anchor) != 1:
        raise SystemExit("STOPPED: API helper anchor wasn't unique; no files written.")
    get_code = '''export const getDetectionControl = async (deviceId) => {
  return request(`/api/devices/${encodeURIComponent(deviceId)}/detection-control`)
}

'''
    api_js = api_js.replace(latest_anchor, get_code + latest_anchor, 1)
if "export const setDetectionEnabled =" not in api_js:
    latest_anchor = "export const getLatestDetection = async () => {"
    set_code = '''export const setDetectionEnabled = (deviceId, enabled) =>
  request(`/api/devices/${encodeURIComponent(deviceId)}/detection-control`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  })

'''
    api_js = api_js.replace(latest_anchor, set_code + latest_anchor, 1)
updated[API_JS] = api_js

# 3) Live monitoring UI: add state, handler, initial status read, buttons.
live = updated[LIVE_JSX]
import_line = "import { getDetectionControl, setDetectionEnabled } from '../services/api'"
if import_line not in live:
    nav_import = "import { useNavigate } from 'react-router-dom'"
    if live.count(nav_import) != 1:
        raise SystemExit("STOPPED: Couldn't identify LiveMonitoring imports; no files written.")
    live = live.replace(nav_import, nav_import + "\n\n" + import_line, 1)

state_anchor = "const [popup, setPopup] = useState(null)"
if "const [detectionControlEnabled, setDetectionControlEnabled]" not in live:
    if live.count(state_anchor) != 1:
        raise SystemExit("STOPPED: Couldn't identify LiveMonitoring popup state; no files written.")
    live = live.replace(
        state_anchor,
        state_anchor + "\n  const [detectionControlEnabled, setDetectionControlEnabled] = useState(false)\n"
        "  const [detectionControlBusy, setDetectionControlBusy] = useState(false)\n"
        "  const [detectionControlError, setDetectionControlError] = useState('')\n"
        "  const [detectionControlMessage, setDetectionControlMessage] = useState('Detection is stopped.')",
        1,
    )

if "// PEST_GUARD_DETECTION_CONTROL_HANDLERS" not in live:
    device_id_line = re.search(
        r"(?m)^\s*const deviceId = .*\n",
        live,
    )
    if not device_id_line:
        raise SystemExit("STOPPED: Couldn't find deviceId in LiveMonitoring; no files written.")
    handlers = '''

  // PEST_GUARD_DETECTION_CONTROL_HANDLERS
  useEffect(() => {
    let active = true

    getDetectionControl(deviceId)
      .then((result) => {
        if (!active) return
        const enabled = Boolean(result?.enabled)
        setDetectionControlEnabled(enabled)
        setDetectionControlMessage(
          enabled ? 'Detection is running.' : 'Detection is stopped.'
        )
        setDetectionControlError('')
      })
      .catch((controlError) => {
        if (!active) return
        setDetectionControlError(`Unable to read device control: ${controlError.message}`)
      })

    return () => {
      active = false
    }
  }, [deviceId])

  const handleDetectionControl = async (enabled) => {
    setDetectionControlBusy(true)
    setDetectionControlError('')

    try {
      const result = await setDetectionEnabled(deviceId, enabled)
      const accepted = Boolean(result?.enabled)
      setDetectionControlEnabled(accepted)
      setDetectionControlMessage(
        accepted
          ? 'Detect requested. The field unit will start at its next control check.'
          : 'Stop requested. A detection cycle already in progress may finish.'
      )
    } catch (controlError) {
      setDetectionControlError(`Control request failed: ${controlError.message}`)
    } finally {
      setDetectionControlBusy(false)
    }
  }
'''
    live = live[:device_id_line.end()] + handlers + live[device_id_line.end():]

if "<section className=\"detection-control-panel\"" not in live:
    ui_anchor = '<section className="monitoring-grid">'
    if live.count(ui_anchor) != 1:
        raise SystemExit("STOPPED: Couldn't find the monitoring-grid UI anchor; no files written.")
    ui = '''<section className="detection-control-panel" aria-label="Manual detection controls">
        <div className="detection-control-copy">
          <p className="monitoring-card-eyebrow">FIELD UNIT CONTROL</p>
          <h2>Detection Control</h2>
          <p>{detectionControlMessage}</p>
          {detectionControlError && (
            <p className="detection-control-error" role="alert">{detectionControlError}</p>
          )}
        </div>
        <div className="detection-control-actions">
          <span className={`detection-control-state ${detectionControlEnabled ? 'is-running' : 'is-stopped'}`}>
            {detectionControlEnabled ? 'RUNNING' : 'STOPPED'}
          </span>
          <button
            type="button"
            className="detection-control-button detection-control-start"
            onClick={() => handleDetectionControl(true)}
            disabled={detectionControlBusy || detectionControlEnabled}
          >
            {detectionControlBusy ? 'Please wait…' : 'Detect'}
          </button>
          <button
            type="button"
            className="detection-control-button detection-control-stop"
            onClick={() => handleDetectionControl(false)}
            disabled={detectionControlBusy || !detectionControlEnabled}
          >
            {detectionControlBusy ? 'Please wait…' : 'Stop'}
          </button>
        </div>
      </section>

      '''
    live = live.replace(ui_anchor, ui + ui_anchor, 1)
updated[LIVE_JSX] = live

# 4) CSS for the button panel.
css = updated[LIVE_CSS]
if ".detection-control-panel" not in css:
    css_add = '''

/* PEST_GUARD_DETECTION_CONTROL_STYLES */
.detection-control-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  margin: 1.5rem 0;
  padding: clamp(1.1rem, 2.5vw, 1.75rem);
  border: 1px solid rgba(125, 150, 132, 0.28);
  border-radius: 22px;
  background: var(--card, #fff);
  box-shadow: 0 12px 32px rgba(20, 45, 30, 0.06);
}

.detection-control-copy h2 {
  margin: 0.15rem 0 0.45rem;
}

.detection-control-copy > p:not(.monitoring-card-eyebrow) {
  margin: 0;
  max-width: 52rem;
  color: var(--muted, #647067);
  line-height: 1.55;
}

.detection-control-copy .detection-control-error {
  margin-top: 0.55rem !important;
  color: #b42318 !important;
}

.detection-control-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.65rem;
  min-width: max-content;
}

.detection-control-state {
  padding: 0.45rem 0.7rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.detection-control-state.is-running {
  color: #166534;
  background: #dcfce7;
}

.detection-control-state.is-stopped {
  color: #475569;
  background: #e2e8f0;
}

.detection-control-button {
  min-height: 44px;
  padding: 0.7rem 1.1rem;
  border: 0;
  border-radius: 12px;
  font: inherit;
  font-weight: 750;
  cursor: pointer;
  transition: transform 140ms ease, opacity 140ms ease;
}

.detection-control-button:hover:not(:disabled) {
  transform: translateY(-1px);
}

.detection-control-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.detection-control-start {
  color: #fff;
  background: #15803d;
}

.detection-control-stop {
  color: #fff;
  background: #b91c1c;
}

@media (max-width: 720px) {
  .detection-control-panel {
    align-items: stretch;
    flex-direction: column;
  }

  .detection-control-actions {
    justify-content: flex-start;
    min-width: 0;
  }
}
'''
    css = css.rstrip() + css_add + "\n"
updated[LIVE_CSS] = css

# 5) ESP32 firmware: poll backend state between cycles; default OFF.
firmware = updated[FIRMWARE]
url_pat = re.compile(
    r"const\s+char\s*\*\s*detectionURL\s*=\s*\"[^\"]*?/api/device/detection\"\s*;",
    re.S,
)
if "// PEST_GUARD_DETECTION_CONTROL_URL" not in firmware:
    m = url_pat.search(firmware)
    if not m:
        raise SystemExit("STOPPED: Couldn't find detectionURL in firmware; no files written.")
    declaration = m.group(0) + '''

// PEST_GUARD_DETECTION_CONTROL_URL
const char* controlURL =
  "https://pest-guard-1q36.onrender.com/api/devices/FIELD-UNIT-01/detection-control";

// The field unit starts stopped until the website enables detection.
bool detectionEnabled = false;
unsigned long lastControlPollMs = 0;
const unsigned long CONTROL_POLL_INTERVAL_MS = 2500;
'''
    firmware = firmware[:m.start()] + declaration + firmware[m.end():]

if "bool pollDetectionControl()" not in firmware:
    loop_match = re.search(r"(?m)^void\s+loop\s*\(\s*\)\s*\{", firmware)
    if not loop_match:
        raise SystemExit("STOPPED: Couldn't find firmware loop(); no files written.")
    poll_code = '''

// PEST_GUARD_REMOTE_DETECTION_CONTROL
bool pollDetectionControl() {
  bool previousState = detectionEnabled;
  WiFiClientSecure controlClient;
  controlClient.setInsecure();

  HTTPClient controlHttp;
  controlHttp.setTimeout(8000);

  if (!controlHttp.begin(controlClient, controlURL)) {
    detectionEnabled = false;
    Serial.println("Detection control unavailable. Failing safe to STOPPED.");
    return false;
  }

  int controlCode = controlHttp.GET();
  if (controlCode == 200) {
    String body = controlHttp.getString();
    int keyPosition = body.indexOf("\\\"enabled\\\"");
    int colonPosition = keyPosition >= 0 ? body.indexOf(':', keyPosition) : -1;

    if (colonPosition >= 0) {
      String value = body.substring(colonPosition + 1);
      value.trim();
      detectionEnabled = value.startsWith("true");
    } else {
      detectionEnabled = false;
    }
  } else {
    Serial.printf("Detection control HTTP status: %d\\n", controlCode);
    detectionEnabled = false;
  }

  controlHttp.end();

  if (previousState != detectionEnabled) {
    Serial.println(detectionEnabled
      ? "Remote command: DETECT enabled"
      : "Remote command: STOP detection");
  }

  return detectionEnabled;
}

'''
    firmware = firmware[:loop_match.start()] + poll_code + firmware[loop_match.start():]

# Replace loop only if the control polling isn't wired in yet.
loop_start = re.search(r"(?m)^void\s+loop\s*\(\s*\)\s*\{", firmware)
if not loop_start:
    raise SystemExit("STOPPED: Firmware loop anchor disappeared; no files written.")
if "if (!detectionEnabled)" not in firmware[loop_start.start():]:
    loop_tail = '''void loop() {
  if (audioBuffer == NULL) {
    Serial.println("Audio buffer unavailable; retrying in 5 seconds.");
    delay(5000);
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected. Reconnecting...");
    WiFi.disconnect();
    WiFi.begin(ssid, password);
    unsigned long reconnectStart = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - reconnectStart < 15000) {
      delay(500);
      Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("Wi-Fi reconnect failed. Retrying next cycle.");
      delay(3000);
      return;
    }
    Serial.print("Wi-Fi reconnected. IP: ");
    Serial.println(WiFi.localIP());
  }

  const unsigned long now = millis();
  if (lastControlPollMs == 0 || now - lastControlPollMs >= CONTROL_POLL_INTERVAL_MS) {
    lastControlPollMs = now;
    pollDetectionControl();
  }

  if (!detectionEnabled) {
    delay(100);
    return;
  }

  runDetectionCycle();
  Serial.println("Detection cycle finished. Checking Detect/Stop command before the next cycle.");
  delay(200);
}
'''
    firmware = firmware[:loop_start.start()] + loop_tail
updated[FIRMWARE] = firmware

# Safety checks on all proposed versions before writing anything.
if "@app.get(\"/api/devices/{device_id}/detection-control\")" not in updated[BACKEND]:
    raise SystemExit("STOPPED: Backend GET control route missing after patch preparation.")
if "@app.post(\"/api/devices/{device_id}/detection-control\")" not in updated[BACKEND]:
    raise SystemExit("STOPPED: Backend POST control route missing after patch preparation.")
if "<section className=\"detection-control-panel\"" not in updated[LIVE_JSX]:
    raise SystemExit("STOPPED: Control buttons missing after patch preparation.")
if "pollDetectionControl();" not in updated[FIRMWARE] or "if (!detectionEnabled)" not in updated[FIRMWARE]:
    raise SystemExit("STOPPED: Firmware control polling missing after patch preparation.")

# Backup every file that will change, including the ino outside project root.
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_root = PROJECT / f".pest_guard_controls_backup_{stamp}"
backup_root.mkdir(parents=True, exist_ok=False)
for path in required:
    try:
        relative = path.relative_to(PROJECT)
    except ValueError:
        relative = Path("external_firmware") / path.name
    target = backup_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

for path in required:
    if updated[path] != contents[path]:
        path.write_text(updated[path], encoding="utf-8", newline="")

print("Detect/Stop control patch applied.")
print(f"Backup folder: {backup_root}")
print("Updated files:")
for path in required:
    if updated[path] != contents[path]:
        print(" -", path)
print("Behavior: device defaults to STOPPED; Detect enables repeated cycles; Stop prevents the next cycle.")
print("Limit: a cycle already recording or awaiting the backend may finish before Stop takes effect.")
print("Next: run npm run build, inspect git diff, then compile the ESP32 firmware before upload.")
