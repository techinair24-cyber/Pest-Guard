// =============================================================
// PEST GUARD ESP32-S3 | SECTION 1 OF 5
// Libraries, hardware pins, settings and shared state
// =============================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <driver/i2s.h>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>
#include <math.h>
#include <string.h>

// =============================================================
// 1. WI-FI CONFIGURATION
// =============================================================

const char* const WIFI_SSID = "abc";
const char* const WIFI_PASSWORD = "123456789";

// =============================================================
// 2. PEST GUARD BACKEND
// =============================================================

const char* const DEVICE_ID = "FIELD-UNIT-01";

const char* const SERVER_HOST =
    "pest-guard-1q36.onrender.com";

const uint16_t SERVER_PORT = 443;

const char* const AI_PATH = "/api/ai/predict";

const char* const CONTROL_URL =
    "https://pest-guard-1q36.onrender.com/api/devices/FIELD-UNIT-01/detection-control";

const char* const HEARTBEAT_URL =
    "https://pest-guard-1q36.onrender.com/api/devices/FIELD-UNIT-01/heartbeat";

// =============================================================
// 3. INMP441 MICROPHONE
// =============================================================

constexpr i2s_port_t MIC_I2S_PORT = I2S_NUM_0;

constexpr int MIC_SCK_PIN = 12;
constexpr int MIC_WS_PIN  = 11;
constexpr int MIC_SD_PIN  = 10;

// =============================================================
// 4. PIEZO SENSOR
// =============================================================

constexpr int PIEZO_PIN = 4;

// =============================================================
// 5. RGB LED AND BUZZER
// =============================================================

constexpr int RGB_RED_PIN   = 7;
constexpr int RGB_GREEN_PIN = 15;
constexpr int RGB_BLUE_PIN  = 16;

constexpr int BUZZER_PIN = 5;

// =============================================================
// 6. AUDIO SETTINGS
// =============================================================

constexpr uint32_t SAMPLE_RATE = 16000;

constexpr uint32_t RECORD_SECONDS = 5;

constexpr uint32_t TOTAL_SAMPLES =
    SAMPLE_RATE * RECORD_SECONDS;

constexpr uint32_t PCM_PAYLOAD_BYTES =
    TOTAL_SAMPLES * sizeof(int16_t);

// Process audio in small chunks.
constexpr size_t AUDIO_CHUNK_SAMPLES = 256;

static_assert(
    PCM_PAYLOAD_BYTES == 160000,
    "Unexpected PCM payload size"
);

// =============================================================
// 7. WEBSITE CONTROL SETTINGS
// =============================================================

constexpr uint32_t CONTROL_POLL_INTERVAL_MS = 2500;

constexpr uint32_t HEARTBEAT_INTERVAL_MS = 20000;

constexpr uint32_t CONTROL_HTTP_TIMEOUT_MS = 8000;

constexpr uint32_t AI_RESPONSE_TIMEOUT_MS = 90000;

// =============================================================
// 8. DIAGNOSTIC MODE
// =============================================================

// TRUE  = record and inspect microphone, no AI upload.
// FALSE = normal Pest Guard detection.

const bool DIAGNOSTIC_ONLY = false;

// =============================================================
// 9. SHARED DEVICE STATE
// =============================================================

// Detection must begin disabled.
// Website Start command enables it.

volatile bool detectionEnabled = false;

char appliedControlCommandId[65] = {0};

portMUX_TYPE detectionControlMux =
    portMUX_INITIALIZER_UNLOCKED;

// Prevent overlapping HTTPS connections.
SemaphoreHandle_t httpsMutex = nullptr;

// Becomes true only after I2S initialization succeeds.
bool microphoneReady = false;

// =============================================================
// 10. FUNCTION DECLARATIONS
// =============================================================

void setupAlertPins();

void alertsOff();

void applyPestAlert(
    const String& status,
    const String& pest,
    const String& risk,
    float confidence,
    bool verified
);

bool connectWiFi();

bool pollDetectionControl();

void sendDeviceHeartbeat();

void deviceControlTask(void* parameter);

bool setupMicrophone();

void runDetectionCycle();

// ================= END OF SECTION 1 =================

// =============================================================
// PEST GUARD ESP32-S3 | SECTION 2 OF 5
// RGB LED, buzzer and verified pest alerts
// =============================================================

// Assumes common-cathode RGB LED: HIGH = ON.
// Assumes active buzzer: HIGH = ON.

// -------------------------------------------------------------
// 1. READ WEBSITE DETECTION STATE SAFELY
// -------------------------------------------------------------

static bool alertDetectionEnabled() {
  bool enabled;

  portENTER_CRITICAL(&detectionControlMux);
  enabled = detectionEnabled;
  portEXIT_CRITICAL(&detectionControlMux);

  return enabled;
}

// -------------------------------------------------------------
// 2. SET RGB LED COLOR
// -------------------------------------------------------------

static void setAlertRGB(
    bool red,
    bool green,
    bool blue
) {
  digitalWrite(RGB_RED_PIN, red ? HIGH : LOW);
  digitalWrite(RGB_GREEN_PIN, green ? HIGH : LOW);
  digitalWrite(RGB_BLUE_PIN, blue ? HIGH : LOW);
}

// -------------------------------------------------------------
// 3. SWITCH OFF ALL ALERTS
// -------------------------------------------------------------

void alertsOff() {
  setAlertRGB(false, false, false);
  digitalWrite(BUZZER_PIN, LOW);
}

// -------------------------------------------------------------
// 4. INITIALIZE HARDWARE OUTPUTS
// -------------------------------------------------------------

void setupAlertPins() {
  pinMode(RGB_RED_PIN, OUTPUT);
  pinMode(RGB_GREEN_PIN, OUTPUT);
  pinMode(RGB_BLUE_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  alertsOff();

  Serial.println("RGB LED initialized.");
  Serial.println("Active buzzer initialized.");
  Serial.println("Alerts start OFF.");
}

// -------------------------------------------------------------
// 5. CONTROL BUZZER SAFELY
// -------------------------------------------------------------

static void beepAlert(
    uint8_t count,
    uint16_t beepDurationMs = 250,
    uint16_t gapDurationMs = 150
) {
  for (uint8_t i = 0; i < count; i++) {

    // Stop immediately between alert phases
    // if website detection has been disabled.
    if (!alertDetectionEnabled()) {
      alertsOff();
      return;
    }

    digitalWrite(BUZZER_PIN, HIGH);
    delay(beepDurationMs);
    digitalWrite(BUZZER_PIN, LOW);

    if (!alertDetectionEnabled()) {
      alertsOff();
      return;
    }

    if (i + 1 < count) {
      delay(gapDurationMs);
    }
  }
}

// -------------------------------------------------------------
// 6. VALIDATE PEST NAME
// -------------------------------------------------------------

static bool isValidAlertPestName(String pest) {
  pest.trim();
  pest.toUpperCase();

  if (pest.isEmpty()) return false;

  if (pest == "NULL" ||
      pest == "NONE" ||
      pest == "UNKNOWN" ||
      pest == "UNCONFIRMED" ||
      pest == "NO PEST" ||
      pest == "NO_PEST" ||
      pest == "NO DETECTION" ||
      pest == "NO_DETECTION" ||
      pest == "UNIDENTIFIED SOUND") {
    return false;
  }

  return true;
}

// -------------------------------------------------------------
// 7. APPLY VERIFIED AI PEST ALERT
// -------------------------------------------------------------

void applyPestAlert(
    const String& status,
    const String& pest,
    const String& risk,
    float confidence,
    bool verified
) {
  // Never retain the previous pest alert.
  alertsOff();

  if (!alertDetectionEnabled()) {
    Serial.println("Detection disabled: alerts OFF.");
    return;
  }

  String normalizedStatus = status;
  normalizedStatus.trim();
  normalizedStatus.toUpperCase();

  String normalizedRisk = risk;
  normalizedRisk.trim();
  normalizedRisk.toUpperCase();

  // Backend must explicitly accept the detection.
  if (normalizedStatus != "HARMFUL_PEST") {
    Serial.println(
      "No confirmed pest: alerts OFF."
    );
    return;
  }

  // Never trust top-three candidate predictions.
  if (!verified || !isValidAlertPestName(pest)) {
    Serial.println(
      "Pest unverified or missing: alerts OFF."
    );
    return;
  }

  // Reject invalid confidence values.
  if (!isfinite(confidence) ||
      confidence < 0.40f ||
      confidence > 1.0f) {
    Serial.println(
      "Invalid/low confidence: alerts OFF."
    );
    return;
  }

  // Validate risk before giving any alert.
  if (normalizedRisk != "LOW" &&
      normalizedRisk != "MEDIUM" &&
      normalizedRisk != "MODERATE" &&
      normalizedRisk != "HIGH" &&
      normalizedRisk != "CRITICAL" &&
      normalizedRisk != "SEVERE") {
    Serial.println(
      "Unknown risk level: alerts OFF."
    );
    return;
  }

  // Verified but below the stronger alert threshold.
  if (confidence < 0.70f) {
    setAlertRGB(false, false, true);
    digitalWrite(BUZZER_PIN, LOW);

    Serial.println(
      "Verified possible match: BLUE, no buzzer."
    );
    return;
  }

  // Stop may have arrived while processing.
  if (!alertDetectionEnabled()) {
    alertsOff();
    return;
  }

  if (normalizedRisk == "LOW") {
    setAlertRGB(false, true, false);
    Serial.println(
      "Verified LOW risk: GREEN + 1 beep."
    );
    beepAlert(1);

  } else if (normalizedRisk == "MEDIUM" ||
             normalizedRisk == "MODERATE") {
    setAlertRGB(true, true, false);
    Serial.println(
      "Verified MEDIUM risk: YELLOW + 2 beeps."
    );
    beepAlert(2);

  } else {
    setAlertRGB(true, false, false);
    Serial.println(
      "Verified HIGH risk: RED + 3 beeps."
    );
    beepAlert(3);
  }

  if (!alertDetectionEnabled()) {
    alertsOff();
  }
}

// ================= END OF SECTION 2 =================

// =============================================================
// PEST GUARD ESP32-S3 | SECTION 3 OF 5
// Wi-Fi, Remote Detection Control and Device Heartbeat
// =============================================================

// -------------------------------------------------------------
// 1. CONNECT TO WI-FI
// -------------------------------------------------------------

bool connectWiFi() {

  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.println();
  Serial.println("Connecting to Wi-Fi...");

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long startMs = millis();
  const unsigned long timeoutMs = 15000;

  while (WiFi.status() != WL_CONNECTED &&
         millis() - startMs < timeoutMs) {

    delay(250);
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi connection failed.");
    return false;
  }

  Serial.println("Wi-Fi CONNECTED.");

  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  Serial.printf(
    "Wi-Fi RSSI: %d dBm\n",
    WiFi.RSSI()
  );

  return true;
}

// -------------------------------------------------------------
// 2. READ CURRENT DETECTION STATE
// -------------------------------------------------------------

static bool getDetectionState() {

  bool enabled;

  portENTER_CRITICAL(&detectionControlMux);
  enabled = detectionEnabled;
  portEXIT_CRITICAL(&detectionControlMux);

  return enabled;
}

// -------------------------------------------------------------
// 3. SEND DEVICE HEARTBEAT
// -------------------------------------------------------------

void sendDeviceHeartbeat() {

  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  if (httpsMutex == nullptr) {
    Serial.println("HTTPS mutex not initialized.");
    return;
  }

  // Do not start a second HTTPS operation
  // while another operation is using the network.

  if (xSemaphoreTake(httpsMutex, 0) != pdTRUE) {
    return;
  }

  bool currentEnabled = false;
  char currentCommandId[65] = {0};

  portENTER_CRITICAL(&detectionControlMux);

  currentEnabled = detectionEnabled;

  memcpy(
    currentCommandId,
    appliedControlCommandId,
    sizeof(currentCommandId)
  );

  portEXIT_CRITICAL(&detectionControlMux);

  // Build a small JSON request body.

  JsonDocument heartbeatDoc;

  heartbeatDoc["status"] = "ONLINE";
  heartbeatDoc["connection"] = "CONNECTED";
  heartbeatDoc["detection_enabled"] = currentEnabled;

  heartbeatDoc["control_command_id"] = currentCommandId;

  String payload;
  serializeJson(heartbeatDoc, payload);

  {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;

    http.setTimeout(CONTROL_HTTP_TIMEOUT_MS);
    http.setConnectTimeout(CONTROL_HTTP_TIMEOUT_MS);
    http.setReuse(false);

    if (!http.begin(client, HEARTBEAT_URL)) {

      Serial.println(
        "Heartbeat connection setup failed."
      );

    } else {

      http.addHeader(
        "Content-Type",
        "application/json"
      );

      int responseCode = http.POST(payload);

      if (responseCode >= 200 &&
          responseCode < 300) {

        Serial.printf(
          "Device heartbeat accepted: HTTP %d\n",
          responseCode
        );

      } else {

        Serial.printf(
          "Heartbeat failed: %d (%s)\n",
          responseCode,
          http.errorToString(responseCode).c_str()
        );
      }

      http.end();
    }
  }

  xSemaphoreGive(httpsMutex);
}

// -------------------------------------------------------------
// 4. POLL WEBSITE START / STOP COMMAND
// -------------------------------------------------------------

bool pollDetectionControl() {

  bool previousEnabled = getDetectionState();

  if (WiFi.status() != WL_CONNECTED) {
    return previousEnabled;
  }

  if (httpsMutex == nullptr) {
    Serial.println("HTTPS mutex not initialized.");
    return previousEnabled;
  }

  // Skip polling while an AI upload or another HTTPS
  // operation is in progress, rather than opening
  // simultaneous TLS connections.

  if (xSemaphoreTake(httpsMutex, 0) != pdTRUE) {
    return previousEnabled;
  }

  bool validResponse = false;
  bool requestedEnabled = previousEnabled;
  char receivedCommandId[65] = {0};

  {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;

    http.setTimeout(CONTROL_HTTP_TIMEOUT_MS);
    http.setConnectTimeout(CONTROL_HTTP_TIMEOUT_MS);
    http.setReuse(false);

    if (!http.begin(client, CONTROL_URL)) {

      Serial.println(
        "Control connection setup failed."
      );

    } else {

      int responseCode = http.GET();

      if (responseCode == HTTP_CODE_OK) {

        String responseBody = http.getString();

        JsonDocument controlDoc;

        DeserializationError jsonError =
            deserializeJson(controlDoc, responseBody);

        if (jsonError) {

          Serial.print("Invalid control JSON: ");
          Serial.println(jsonError.c_str());

        } else if (!controlDoc["enabled"].is<bool>()) {

          Serial.println(
            "Control response missing valid enabled value."
          );

        } else {

          requestedEnabled =
              controlDoc["enabled"].as<bool>();

          const char* commandId =
              controlDoc["command_id"] | "";

          const size_t commandLength =
              strlen(commandId);

          // The backend may return no command ID
          // before the first Start/Stop command.
          // In that case, only accept the safe
          // initial disabled state.

          if (commandLength >= sizeof(receivedCommandId)) {

            Serial.println(
              "Invalid control command ID length."
            );

          } else if (
              requestedEnabled &&
              commandLength == 0
          ) {

            Serial.println(
              "Enabled command missing command ID."
            );

          } else {

            memcpy(
              receivedCommandId,
              commandId,
              commandLength
            );

            receivedCommandId[commandLength] = '\0';

            validResponse = true;
          }
        }

      } else {

        Serial.printf(
          "Control HTTP error: %d (%s)\n",
          responseCode,
          http.errorToString(responseCode).c_str()
        );

        Serial.printf(
          "Free heap: %u bytes\n",
          (unsigned int)ESP.getFreeHeap()
        );
      }

      http.end();
    }
  }

  // Release the network before changing state
  // or sending an acknowledgement.

  xSemaphoreGive(httpsMutex);

  if (!validResponse) {

    Serial.println(
      "Control request failed. Keeping last confirmed state."
    );

    return previousEnabled;
  }

  char oldCommandId[65] = {0};

  portENTER_CRITICAL(&detectionControlMux);

  memcpy(
    oldCommandId,
    appliedControlCommandId,
    sizeof(oldCommandId)
  );

  detectionEnabled = requestedEnabled;

  memcpy(
    appliedControlCommandId,
    receivedCommandId,
    sizeof(appliedControlCommandId)
  );

  portEXIT_CRITICAL(&detectionControlMux);

  const bool stateChanged =
      previousEnabled != requestedEnabled;

  const bool commandChanged =
      strcmp(oldCommandId, receivedCommandId) != 0;

  if (!requestedEnabled) {

    // Important: STOP must clear an older LED alert.
    alertsOff();
  }

  if (stateChanged || commandChanged) {

    Serial.println();

    if (requestedEnabled) {

      Serial.println(
        "REMOTE COMMAND: DETECTION STARTED"
      );

    } else {

      Serial.println(
        "REMOTE COMMAND: DETECTION STOPPED"
      );
    }

    // Acknowledge the exact website command.
    sendDeviceHeartbeat();
  }

  return requestedEnabled;
}

// -------------------------------------------------------------
// 5. BACKGROUND WEBSITE CONTROL TASK
// -------------------------------------------------------------

void deviceControlTask(void* parameter) {

  (void)parameter;

  unsigned long lastControlPoll = 0;
  unsigned long lastHeartbeat = 0;

  for (;;) {

    if (WiFi.status() == WL_CONNECTED) {

      unsigned long now = millis();

      // Poll the remote Start / Stop state.

      if (lastControlPoll == 0 ||
          now - lastControlPoll >=
              CONTROL_POLL_INTERVAL_MS) {

        lastControlPoll = now;
        pollDetectionControl();
      }

      now = millis();

      // Periodically report that the device
      // is connected and operational.

      if (lastHeartbeat == 0 ||
          now - lastHeartbeat >=
              HEARTBEAT_INTERVAL_MS) {

        lastHeartbeat = now;
        sendDeviceHeartbeat();
      }
    }

    // Give other FreeRTOS tasks time to run.
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}

// ================= END OF SECTION 3 ==========================

// =============================================================
// PEST GUARD ESP32-S3 | SECTION 4 OF 5
// INMP441, PSRAM-buffered PCM capture and AI response
// =============================================================

// -------------------------------------------------------------
// 1. INITIALIZE INMP441 MICROPHONE
// -------------------------------------------------------------

bool setupMicrophone() {

  microphoneReady = false;

  i2s_config_t config = {};

  config.mode = (i2s_mode_t)(
      I2S_MODE_MASTER | I2S_MODE_RX
  );

  config.sample_rate = SAMPLE_RATE;

  config.bits_per_sample =
      I2S_BITS_PER_SAMPLE_32BIT;

  config.channel_format =
      I2S_CHANNEL_FMT_ONLY_LEFT;

  config.communication_format =
      I2S_COMM_FORMAT_STAND_I2S;

  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;

  // Larger DMA queue helps tolerate short network delays.
  config.dma_buf_count = 16;
  config.dma_buf_len = 512;

  config.use_apll = false;
  config.tx_desc_auto_clear = false;
  config.fixed_mclk = 0;

  esp_err_t result = i2s_driver_install(
      MIC_I2S_PORT,
      &config,
      0,
      nullptr
  );

  if (result != ESP_OK) {
    Serial.printf(
        "I2S driver installation failed: %d\n",
        (int)result
    );
    return false;
  }

  i2s_pin_config_t pins = {};

  // ESP32-S3 Arduino cores use ESP-IDF 4.4 or later.
  // INMP441 does not require an MCLK output.
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = MIC_SCK_PIN;
  pins.ws_io_num = MIC_WS_PIN;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = MIC_SD_PIN;

  result = i2s_set_pin(MIC_I2S_PORT, &pins);

  if (result != ESP_OK) {
    Serial.printf(
        "I2S pin configuration failed: %d\n",
        (int)result
    );

    i2s_driver_uninstall(MIC_I2S_PORT);
    return false;
  }

  microphoneReady = true;

  Serial.println("INMP441 driver initialized.");
  Serial.println("Configured I2S receive channel: LEFT.");
  Serial.println("Audio: 16000 Hz, mono, 16-bit PCM.");

  return true;
}

// -------------------------------------------------------------
// 2. PSRAM-BUFFERED AUDIO STREAM
// -------------------------------------------------------------

// Captures the full clip before HTTPS transmission so network stalls
// cannot change which microphone samples are included in the payload.

class PestAudioStream : public Stream {

private:

  int32_t rawSamples[AUDIO_CHUNK_SAMPLES];
  uint8_t pcmBytes[AUDIO_CHUNK_SAMPLES * 2];
  uint8_t* recordingBuffer = nullptr;

  uint32_t capturedSamples = 0;
  uint32_t consumedBytes = 0;
  uint32_t zeroSamples = 0;
  uint32_t currentZeroRun = 0;
  uint32_t longestZeroRun = 0;
  uint32_t clippedSamples = 0;
  uint32_t rawZeroWords = 0;
  uint32_t failedReads = 0;

  uint32_t captureStartMs = 0;
  uint32_t captureEndMs = 0;

  int16_t sampleMin = 32767;
  int16_t sampleMax = -32768;
  int32_t rawMin = INT32_MAX;
  int32_t rawMax = INT32_MIN;

  double sumSquares = 0.0;

  bool failed = false;
  bool started = false;
  bool captureReady = false;

  bool loadNextChunk() {

    if (failed) return false;

    if (recordingBuffer == nullptr) {
      Serial.println("PCM capture buffer is unavailable.");
      failed = true;
      return false;
    }

    if (capturedSamples >= TOTAL_SAMPLES) {
      return false;
    }

    // Start a fresh recording before opening the HTTPS request.
    if (!started) {

      if (i2s_stop(MIC_I2S_PORT) != ESP_OK ||
          i2s_start(MIC_I2S_PORT) != ESP_OK) {

        Serial.println("Cannot restart I2S recording.");
        failed = true;
        return false;
      }

      started = true;
      captureStartMs = millis();
    }

    if (millis() - captureStartMs > 15000UL) {
      Serial.println("Audio capture exceeded timeout.");
      failed = true;
      return false;
    }

    size_t remaining =
        TOTAL_SAMPLES - capturedSamples;

    size_t requestSamples =
        min(AUDIO_CHUNK_SAMPLES, remaining);

    size_t bytesRead = 0;

    esp_err_t result = i2s_read(
        MIC_I2S_PORT,
        rawSamples,
        requestSamples * sizeof(int32_t),
        &bytesRead,
        pdMS_TO_TICKS(1000)
    );

    if (result != ESP_OK ||
        bytesRead == 0 ||
        bytesRead > requestSamples * sizeof(int32_t) ||
        (bytesRead % sizeof(int32_t)) != 0) {

      failedReads++;

      Serial.printf(
          "Invalid I2S read: error=%d bytes=%u\n",
          (int)result,
          (unsigned int)bytesRead
      );

      failed = true;
      return false;
    }

    size_t count = bytesRead / sizeof(int32_t);
    const size_t chunkStartSample = capturedSamples;

    for (size_t i = 0; i < count; i++) {

      const int32_t rawSample = rawSamples[i];
      const int16_t sample =
          (int16_t)(rawSample >> 16);

      if (rawSample < rawMin) rawMin = rawSample;
      if (rawSample > rawMax) rawMax = rawSample;
      if (rawSample == 0) rawZeroWords++;

      // Explicit little-endian PCM encoding.
      uint16_t value = (uint16_t)sample;

      pcmBytes[i * 2] =
          (uint8_t)(value & 0xFF);

      pcmBytes[i * 2 + 1] =
          (uint8_t)((value >> 8) & 0xFF);

      if (sample < sampleMin) sampleMin = sample;
      if (sample > sampleMax) sampleMax = sample;

      if (sample == 0) {
        zeroSamples++;
        currentZeroRun++;
        if (currentZeroRun > longestZeroRun) {
          longestZeroRun = currentZeroRun;
        }
      } else {
        currentZeroRun = 0;
      }

      if (sample == INT16_MIN || sample == INT16_MAX) {
        clippedSamples++;
      }

      sumSquares +=
          (double)sample * (double)sample;
    }

    const size_t chunkBytes = count * sizeof(int16_t);

    memcpy(
        recordingBuffer + chunkStartSample * sizeof(int16_t),
        pcmBytes,
        chunkBytes
    );

    capturedSamples += count;

    if (capturedSamples == TOTAL_SAMPLES) {
      captureEndMs = millis();
    }

    return true;
  }

public:

  bool capture() {

    if (failed || recordingBuffer != nullptr) {
      return false;
    }

    if (!psramFound()) {
      Serial.println(
          "Audio capture aborted: PSRAM is not available."
      );
      failed = true;
      return false;
    }

    const size_t largestPsramBlock =
        heap_caps_get_largest_free_block(
            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
        );

    if (largestPsramBlock < PCM_PAYLOAD_BYTES) {
      Serial.printf(
          "Audio capture aborted: PSRAM block too small (%u bytes available, %u required).\n",
          (unsigned int)largestPsramBlock,
          (unsigned int)PCM_PAYLOAD_BYTES
      );
      failed = true;
      return false;
    }

    recordingBuffer = (uint8_t*)heap_caps_malloc(
        PCM_PAYLOAD_BYTES,
        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
    );

    if (recordingBuffer == nullptr) {
      Serial.println(
          "Audio capture aborted: PSRAM allocation failed."
      );
      failed = true;
      return false;
    }

    Serial.printf(
        "Free PSRAM after PCM buffer: %u bytes\n",
        (unsigned int)ESP.getFreePsram()
    );

    while (capturedSamples < TOTAL_SAMPLES) {
      if (!getDetectionState()) {
        Serial.println("Audio capture stopped.");
        failed = true;
        releaseCaptureBuffer();
        return false;
      }

      if (!loadNextChunk()) {
        releaseCaptureBuffer();
        return false;
      }
    }

    if (failed || capturedSamples != TOTAL_SAMPLES) {
      failed = true;
      releaseCaptureBuffer();
      return false;
    }

    consumedBytes = 0;
    captureReady = true;
    return true;
  }

  void releaseCaptureBuffer() {
    if (recordingBuffer != nullptr) {
      heap_caps_free(recordingBuffer);
      recordingBuffer = nullptr;
    }
    captureReady = false;
  }

  void resetCapture() {

    releaseCaptureBuffer();

    capturedSamples = 0;
    consumedBytes = 0;
    zeroSamples = 0;
    currentZeroRun = 0;
    longestZeroRun = 0;
    clippedSamples = 0;
    rawZeroWords = 0;
    failedReads = 0;

    captureStartMs = 0;
    captureEndMs = 0;

    sampleMin = 32767;
    sampleMax = -32768;
    rawMin = INT32_MAX;
    rawMax = INT32_MIN;

    sumSquares = 0.0;

    failed = false;
    started = false;
    captureReady = false;
  }

  int available() override {

    if (failed) return -1;

    if (!captureReady ||
        recordingBuffer == nullptr ||
        consumedBytes >= PCM_PAYLOAD_BYTES) {
      return 0;
    }

    const uint32_t remainingBytes =
        PCM_PAYLOAD_BYTES - consumedBytes;
    const uint32_t streamChunkBytes =
        AUDIO_CHUNK_SAMPLES * sizeof(int16_t);
    return (int)min(remainingBytes, streamChunkBytes);
  }

  int read() override {

    if (available() <= 0) return -1;

    return recordingBuffer[consumedBytes++];
  }

  int peek() override {

    if (available() <= 0) return -1;

    return recordingBuffer[consumedBytes];
  }

  size_t write(uint8_t value) override {

    (void)value;
    return 0;
  }

  bool complete() const {

    return captureReady &&
           !failed &&
           capturedSamples == TOTAL_SAMPLES &&
           consumedBytes == PCM_PAYLOAD_BYTES;
  }

  bool signalConstant() const {

    return capturedSamples > 0 &&
           sampleMin == sampleMax;
  }

  uint32_t captureDuration() const {

    if (!started || captureEndMs == 0) return 0;

    return captureEndMs - captureStartMs;
  }

  void printDiagnostics() const {

    Serial.println();
    Serial.println("===== MICROPHONE DIAGNOSTICS =====");

    Serial.printf(
        "Samples: %u / %u\n",
        (unsigned int)capturedSamples,
        (unsigned int)TOTAL_SAMPLES
    );

    Serial.printf(
        "PCM bytes consumed: %u / %u\n",
        (unsigned int)consumedBytes,
        (unsigned int)PCM_PAYLOAD_BYTES
    );

    Serial.printf(
        "Minimum: %d\n",
        (int)sampleMin
    );

    Serial.printf(
        "Maximum: %d\n",
        (int)sampleMax
    );

    Serial.printf(
        "Raw I2S min/max: %ld / %ld\n",
        (long)rawMin,
        (long)rawMax
    );

    Serial.printf(
        "Raw I2S zero words: %u\n",
        (unsigned int)rawZeroWords
    );

    if (capturedSamples > 0) {

      double rms = sqrt(
          sumSquares / (double)capturedSamples
      );

      double zeroPercentage =
          (100.0 * zeroSamples) /
          (double)capturedSamples;

      Serial.printf("RMS: %.2f\n", rms);

      Serial.printf(
          "Zero samples: %.2f%%\n",
          zeroPercentage
      );

      Serial.printf(
          "Longest consecutive PCM zero run: %u samples\n",
          (unsigned int)longestZeroRun
      );

      Serial.printf(
          "PCM full-scale samples: %u (%.4f%%)\n",
          (unsigned int)clippedSamples,
          (100.0 * clippedSamples) / (double)capturedSamples
      );
    }

    Serial.printf(
        "Capture duration: %u ms\n",
        (unsigned int)captureDuration()
    );

    Serial.printf(
        "Failed I2S reads: %u\n",
        (unsigned int)failedReads
    );

    if (signalConstant()) {
      Serial.println(
          "WARNING: Constant microphone signal."
      );
    }

    if (captureDuration() > 6500UL) {
      Serial.println(
          "WARNING: Microphone capture took longer than expected."
      );
    }

    Serial.println("==================================");
  }
};

// -------------------------------------------------------------
// 3. RECORD AUDIO AND REQUEST AI PREDICTION
// -------------------------------------------------------------

void runDetectionCycle() {

  if (!microphoneReady) {
    Serial.println("Microphone unavailable.");
    alertsOff();
    return;
  }

  if (!getDetectionState()) {
    alertsOff();
    return;
  }

  Serial.println();
  Serial.println("===== PEST GUARD DETECTION =====");

  Serial.printf(
      "Piezo vibration state: %d\n",
      digitalRead(PIEZO_PIN)
  );

  // The working buffers are static; the full PCM recording is allocated
  // from PSRAM only after a runtime capacity check.

  static PestAudioStream audioStream;
  audioStream.resetCapture();

  // Diagnostic mode does not contact the AI backend.
  if (DIAGNOSTIC_ONLY) {

    Serial.println(
        "Diagnostic mode: microphone capture only."
    );

    if (!audioStream.capture()) {
      audioStream.printDiagnostics();
      audioStream.releaseCaptureBuffer();
      alertsOff();
      return;
    }

    while (!audioStream.complete()) {

      if (!getDetectionState()) {
        Serial.println("Capture stopped.");
        audioStream.releaseCaptureBuffer();
        alertsOff();
        return;
      }

      int count = audioStream.available();

      if (count <= 0) break;

      while (count-- > 0) {
        if (audioStream.read() < 0) break;
      }
    }

    audioStream.printDiagnostics();
    audioStream.releaseCaptureBuffer();

    Serial.println("No AI request sent.");
    alertsOff();
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("AI skipped: Wi-Fi disconnected.");
    alertsOff();
    return;
  }

  if (httpsMutex == nullptr) {
    Serial.println("HTTPS mutex unavailable.");
    alertsOff();
    return;
  }

  // Only one HTTPS operation at a time.
  if (xSemaphoreTake(
          httpsMutex,
          pdMS_TO_TICKS(2000)
      ) != pdTRUE) {

    Serial.println("Network busy. Skipping this cycle.");
    return;
  }

  bool commandEnabled = false;
  char detectionCommandId[65] = {0};

  portENTER_CRITICAL(&detectionControlMux);
  commandEnabled = detectionEnabled;
  memcpy(
      detectionCommandId,
      appliedControlCommandId,
      sizeof(detectionCommandId)
  );
  portEXIT_CRITICAL(&detectionControlMux);

  if (!commandEnabled || detectionCommandId[0] == '\0') {
    Serial.println(
        "AI skipped: no active website Detect command."
    );
    xSemaphoreGive(httpsMutex);
    alertsOff();
    return;
  }

  if (!audioStream.capture()) {
    audioStream.printDiagnostics();
    audioStream.releaseCaptureBuffer();
    xSemaphoreGive(httpsMutex);
    alertsOff();
    return;
  }

  String responseBody;
  int httpCode = -1;

  Serial.printf(
      "Free heap after PCM capture: %u\n",
      (unsigned int)ESP.getFreeHeap()
  );

  {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;

    // ESP32 HTTPClient timeout is 16-bit.
    const uint16_t responseTimeout =
        (AI_RESPONSE_TIMEOUT_MS > 60000UL)
        ? 60000
        : (uint16_t)AI_RESPONSE_TIMEOUT_MS;

    http.setTimeout(responseTimeout);
    http.setConnectTimeout(10000);
    http.setReuse(false);

    String url =
        String("https://") +
        SERVER_HOST +
        AI_PATH;

    if (!http.begin(client, url)) {

      Serial.println("AI connection setup failed.");

    } else {

      http.addHeader(
          "Content-Type",
          "application/octet-stream"
      );
      http.addHeader(
          "X-Detection-Control-Command-Id",
          detectionCommandId
      );

      Serial.println("Sending captured PCM to AI...");

      // Fixed 160000-byte Content-Length.
      // HTTPClient reads audioStream in small blocks.
      httpCode = http.sendRequest(
          "POST",
          &audioStream,
          PCM_PAYLOAD_BYTES
      );

      Serial.printf(
          "AI HTTP response: %d\n",
          httpCode
      );

      if (httpCode > 0) {
        responseBody = http.getString();
      } else {
        Serial.print("AI request error: ");
        Serial.println(
            http.errorToString(httpCode)
        );
      }

      http.end();
    }
  }

  // Release HTTPS before polling website control.
  xSemaphoreGive(httpsMutex);

  audioStream.printDiagnostics();
  const bool audioComplete = audioStream.complete();
  const bool constantAudio = audioStream.signalConstant();
  audioStream.releaseCaptureBuffer();

  Serial.printf(
      "Free heap after AI request: %u\n",
      (unsigned int)ESP.getFreeHeap()
  );

  if (!audioComplete) {

    Serial.println(
        "Audio incomplete. Ignoring AI result."
    );

    alertsOff();
    return;
  }

  if (httpCode != HTTP_CODE_OK) {

    Serial.println("AI request unsuccessful.");

    if (!responseBody.isEmpty()) {
      Serial.println(responseBody);
    }

    alertsOff();
    return;
  }

  // Read website Stop command before applying alerts.
  pollDetectionControl();

  if (!getDetectionState()) {

    Serial.println("Detection stopped by website.");
    alertsOff();
    return;
  }

  // -----------------------------------------------------------
  // 4. PARSE ONLY TOP-LEVEL AI RESPONSE FIELDS
  // -----------------------------------------------------------

  JsonDocument result;

  DeserializationError jsonError =
      deserializeJson(result, responseBody);

  if (jsonError) {

    Serial.printf(
        "Invalid AI JSON: %s\n",
        jsonError.c_str()
    );

    alertsOff();
    return;
  }

  if (!result["status"].is<const char*>() ||
      !result["pest_verified"].is<bool>()) {

    Serial.println(
        "AI response missing required safety fields."
    );

    alertsOff();
    return;
  }

  String status = result["status"] | "";
  String pest = result["pest"] | "";
  String risk = result["risk"] | "UNKNOWN";

  bool verified =
      result["pest_verified"].as<bool>();

  float confidence =
      result["confidence"] | 0.0f;

  status.trim();
  status.toUpperCase();

  // A top-three candidate is NOT a confirmed pest.
  // Do not use top_predictions for hardware alerts.

  bool accepted =
      status == "HARMFUL_PEST" &&
      verified &&
      !pest.isEmpty() &&
      !constantAudio;

  if (!accepted) {

    pest = "";
    verified = false;

    Serial.println();
    Serial.println("NO VERIFIED PEST DETECTED");

  } else {

    Serial.println();
    Serial.println("VERIFIED PEST DETECTED");
    Serial.print("Pest: ");
    Serial.println(pest);
  }

  Serial.print("Status: ");
  Serial.println(status);

  Serial.print("Risk: ");
  Serial.println(risk);

  Serial.print("Confidence: ");
  Serial.println(confidence, 6);

  Serial.print("Verified: ");
  Serial.println(verified ? "YES" : "NO");

  // Final LED/buzzer safety checks are in Section 2.
  applyPestAlert(
      status,
      pest,
      risk,
      confidence,
      verified
  );

  // Backend already saves and broadcasts /api/ai/predict.
  // Do not send a second duplicate detection POST.

  Serial.println("Detection cycle complete.");
}

// ================= END OF SECTION 4 =========================

// =============================================================
// PEST GUARD ESP32-S3 | SECTION 5 OF 5
// System startup, main loop and memory diagnostics
// =============================================================

// -------------------------------------------------------------
// 1. PRINT MEMORY INFORMATION
// -------------------------------------------------------------

static void printMemoryStatus() {

  Serial.println();
  Serial.println("===== ESP32-S3 MEMORY STATUS =====");

  Serial.printf(
      "Free internal heap: %u bytes\n",
      (unsigned int)ESP.getFreeHeap()
  );

  Serial.printf(
      "Minimum free heap: %u bytes\n",
      (unsigned int)ESP.getMinFreeHeap()
  );

  Serial.printf(
      "Largest internal block: %u bytes\n",
      (unsigned int)heap_caps_get_largest_free_block(
          MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
      )
  );

  Serial.printf(
      "PSRAM detected: %s\n",
      psramFound() ? "YES" : "NO"
  );

  Serial.printf(
      "Total PSRAM: %u bytes\n",
      (unsigned int)ESP.getPsramSize()
  );

  Serial.printf(
      "Free PSRAM: %u bytes\n",
      (unsigned int)ESP.getFreePsram()
  );

  Serial.println("================================");
}

// -------------------------------------------------------------
// 2. MAIN SETUP
// -------------------------------------------------------------

void setup() {

  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("====================================");
  Serial.println("       PEST GUARD FIELD UNIT");
  Serial.println("             ESP32-S3");
  Serial.println("====================================");

  // Initialize alerts safely.
  setupAlertPins();

  // Initialize piezo sensor.
  pinMode(PIEZO_PIN, INPUT);

  Serial.println("Piezo sensor initialized.");

  // Detection begins disabled.
  portENTER_CRITICAL(&detectionControlMux);

  detectionEnabled = false;

  memset(
      appliedControlCommandId,
      0,
      sizeof(appliedControlCommandId)
  );

  portEXIT_CRITICAL(&detectionControlMux);

  alertsOff();

  // Print initial memory status.
  printMemoryStatus();

  // -----------------------------------------------------------
  // INITIALIZE HTTPS MUTEX
  // -----------------------------------------------------------

  httpsMutex = xSemaphoreCreateMutex();

  if (httpsMutex == nullptr) {

    Serial.println(
        "FATAL: HTTPS mutex creation failed."
    );

    alertsOff();

    // Cannot safely continue networking.
    while (true) {
      delay(1000);
    }
  }

  Serial.println("HTTPS mutex initialized.");

  // -----------------------------------------------------------
  // INITIALIZE MICROPHONE
  // -----------------------------------------------------------

  if (setupMicrophone()) {

    Serial.println(
        "Microphone driver ready."
    );

  } else {

    Serial.println(
        "ERROR: Microphone initialization failed."
    );

    Serial.println(
        "AI recording will remain disabled."
    );
  }

  // -----------------------------------------------------------
  // CONNECT WI-FI
  // -----------------------------------------------------------

  if (!connectWiFi()) {

    Serial.println(
        "Wi-Fi unavailable at startup."
    );

    Serial.println(
        "The main loop will retry."
    );
  }

  // -----------------------------------------------------------
  // START WEBSITE CONTROL TASK
  // -----------------------------------------------------------

  BaseType_t taskResult = xTaskCreate(
      deviceControlTask,
      "PestGuardControl",
      8192,
      nullptr,
      1,
      nullptr
  );

  if (taskResult == pdPASS) {

    Serial.println(
        "Website control task started."
    );

  } else {

    Serial.println(
        "ERROR: Website control task failed."
    );

    // Do not allow unmanaged detection.
    portENTER_CRITICAL(&detectionControlMux);
    detectionEnabled = false;
    portEXIT_CRITICAL(&detectionControlMux);

    alertsOff();
  }

  printMemoryStatus();

  Serial.println();
  Serial.println("====================================");
  Serial.println("       INITIALIZATION COMPLETE");
  Serial.println("====================================");

  Serial.println(
      "Waiting for website Detect command..."
  );
}

// -------------------------------------------------------------
// 3. MAIN LOOP
// -------------------------------------------------------------

void loop() {

  static unsigned long lastWiFiRetryMs = 0;
  static unsigned long lastMemoryPrintMs = 0;
  static unsigned long lastIdlePrintMs = 0;

  unsigned long now = millis();

  // -----------------------------------------------------------
  // CHECK MICROPHONE
  // -----------------------------------------------------------

  if (!microphoneReady) {

    alertsOff();

    delay(1000);
    return;
  }

  // -----------------------------------------------------------
  // CHECK WI-FI CONNECTION
  // -----------------------------------------------------------

  if (WiFi.status() != WL_CONNECTED) {

    alertsOff();

    // Avoid repeated connection attempts every loop.
    if (lastWiFiRetryMs == 0 ||
        now - lastWiFiRetryMs >= 15000UL) {

      lastWiFiRetryMs = now;

      Serial.println();
      Serial.println("Wi-Fi disconnected.");

      connectWiFi();
    }

    delay(250);
    return;
  }

  // -----------------------------------------------------------
  // PERIODIC MEMORY MONITORING
  // -----------------------------------------------------------

  if (lastMemoryPrintMs == 0 ||
      now - lastMemoryPrintMs >= 30000UL) {

    lastMemoryPrintMs = now;

    printMemoryStatus();
  }

  // -----------------------------------------------------------
  // WAIT FOR WEBSITE START COMMAND
  // -----------------------------------------------------------

  if (!getDetectionState()) {

    alertsOff();

    if (lastIdlePrintMs == 0 ||
        now - lastIdlePrintMs >= 10000UL) {

      lastIdlePrintMs = now;

      Serial.println();
      Serial.println(
          "Detection OFF. Waiting for website..."
      );
    }

    delay(250);
    return;
  }

  // -----------------------------------------------------------
  // DETECTION IS ENABLED
  // -----------------------------------------------------------

  Serial.println();
  Serial.println("====================================");
  Serial.println("         DETECTION ENABLED");
  Serial.println("====================================");

  // Runs the microphone and AI workflow
  // implemented in Section 4.
  runDetectionCycle();

  // -----------------------------------------------------------
  // CHECK STOP COMMAND AFTER EACH CYCLE
  // -----------------------------------------------------------

  if (!getDetectionState()) {

    alertsOff();

    Serial.println(
        "Detection stopped. Alerts OFF."
    );

  } else {

    Serial.println(
        "Detection cycle finished."
    );
  }

  // Avoid a busy loop.
  delay(500);
}

// ================= END OF SECTION 5 =========================
