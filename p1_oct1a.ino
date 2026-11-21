// =============================================================
// PEST GUARD FIELD UNIT | ESP32-S3 COMPLETE FIRMWARE
// Dual-Tier Buffered PCM Capture (PSRAM -> Segmented Internal SRAM)
// Pre-Upload Audio Integrity, Non-Blocking AI Upload,
// Fresh Pre-Alert Command Verification, Verified Pest Alerts
// =============================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <driver/i2s.h>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include <limits.h>

// =============================================================
// 1. FORWARD TYPE DECLARATIONS (MUST PRECEDE ALL FUNCTIONS
//    FOR ARDUINO IDE AUTO-PROTOTYPE COMPATIBILITY)
// =============================================================

class PestAudioStream;

enum DetectionCycleOutcome : uint8_t {
  CYCLE_OK = 0,
  CYCLE_STOPPED = 1,
  CYCLE_INVALID_AUDIO = 2,
  CYCLE_MEMORY_SHORTAGE = 3,
  CYCLE_NETWORK_ERROR = 4
};

// =============================================================
// 2. WI-FI CONFIGURATION
// =============================================================

const char* const WIFI_SSID     = "abc";
const char* const WIFI_PASSWORD = "123456789";

// =============================================================
// 3. PEST GUARD BACKEND (PRESERVED)
// =============================================================

const char* const DEVICE_ID   = "FIELD-UNIT-01";
const char* const SERVER_HOST = "pest-guard-1q36.onrender.com";
const uint16_t    SERVER_PORT = 443;
const char* const AI_PATH     = "/api/ai/predict";

const char* const CONTROL_URL =
    "https://pest-guard-1q36.onrender.com/api/devices/FIELD-UNIT-01/detection-control";

const char* const HEARTBEAT_URL =
    "https://pest-guard-1q36.onrender.com/api/devices/FIELD-UNIT-01/heartbeat";

// =============================================================
// 4. HARDWARE PINS (PRESERVED)
// =============================================================

// INMP441 Microphone (I2S, L/R tied to GND -> LEFT channel)
constexpr i2s_port_t MIC_I2S_PORT = I2S_NUM_0;
constexpr int MIC_SCK_PIN = 12;
constexpr int MIC_WS_PIN  = 11;
constexpr int MIC_SD_PIN  = 10;

// Piezo Sensor
constexpr int PIEZO_PIN = 4;

// Common-cathode RGB LED (HIGH = ON) & Active Buzzer (HIGH = ON)
constexpr int RGB_RED_PIN   = 7;
constexpr int RGB_GREEN_PIN = 15;
constexpr int RGB_BLUE_PIN  = 16;
constexpr int BUZZER_PIN    = 5;

// =============================================================
// 5. AUDIO, INTEGRITY & MEMORY SETTINGS
// =============================================================

constexpr uint32_t SAMPLE_RATE       = 16000;
constexpr uint32_t RECORD_SECONDS    = 5;
constexpr uint32_t TOTAL_SAMPLES     = SAMPLE_RATE * RECORD_SECONDS;
constexpr uint32_t PCM_PAYLOAD_BYTES = TOTAL_SAMPLES * sizeof(int16_t);

// Read 256 samples (16 ms) per I2S read for rapid Stop checks.
constexpr size_t AUDIO_CHUNK_SAMPLES = 256;

// Discard 64 ms after restarting I2S clocks so INMP441 bias settles.
constexpr size_t MIC_WARMUP_SAMPLES  = 1024;

// I2S DMA: 16 x 256 x 4 bytes = 16 KB internal DMA RAM (256 ms ring buffer).
constexpr int I2S_DMA_BUF_COUNT = 16;
constexpr int I2S_DMA_BUF_LEN   = 256;

// Pre-upload audio integrity thresholds.
constexpr uint32_t MIN_VALID_CAPTURE_MS    = 4700;
constexpr uint32_t MAX_VALID_CAPTURE_MS    = 5450;
constexpr uint32_t MAX_SAFE_CHUNK_GAP_MS   = 210;   // Below 256 ms (16 x 256 x 4-byte DMA)
constexpr uint32_t MAX_RAW_ZERO_RUN        = 1600;  // 100 ms exact 32-bit zero dropout
constexpr double   MIN_VALID_RMS           = 0.5;
constexpr int32_t  MIN_VALID_PEAK_TO_PEAK  = 4;

// Segmented internal SRAM layout: 40 x 4,000 bytes = 160,000 bytes.
constexpr size_t INTERNAL_CHUNK_BYTES = 4000;
constexpr size_t INTERNAL_CHUNK_COUNT = PCM_PAYLOAD_BYTES / INTERNAL_CHUNK_BYTES;

// Internal DRAM thresholds for safe mbedTLS operation.
constexpr size_t MIN_TLS_FREE_HEAP_BYTES          = 50000;
constexpr size_t RECOMMENDED_TLS_HEAP_BYTES       = 62000;
constexpr size_t MIN_TLS_LARGEST_BLOCK_BYTES      = 22528;

// Higher floor required before opening a 2nd concurrent TLS socket (Core 0 poll
// while Core 1 AI socket waits for FastAPI inference).
constexpr size_t MIN_CONCURRENT_TLS_FREE_HEAP     = 76000;
constexpr size_t MIN_CONCURRENT_TLS_LARGEST_BLOCK = 24576;

// Two-part contiguous guard blocks reserved during segmented allocation.
constexpr size_t TLS_GUARD_A_PRIMARY_BYTES   = 26624;
constexpr size_t TLS_GUARD_B_PRIMARY_BYTES   = 14336;
constexpr size_t TLS_GUARD_A_FALLBACK_BYTES  = 24576;
constexpr size_t TLS_GUARD_B_FALLBACK_BYTES  = 12288;

// Cap AI HTTP response size to prevent malformed pages from exhausting SRAM.
constexpr size_t MAX_AI_RESPONSE_BYTES = 16384;

static_assert(
    PCM_PAYLOAD_BYTES == 160000,
    "Unexpected PCM payload size"
);
static_assert(
    INTERNAL_CHUNK_COUNT * INTERNAL_CHUNK_BYTES == PCM_PAYLOAD_BYTES,
    "Segmented chunk size must divide PCM_PAYLOAD_BYTES evenly"
);
static_assert(
    (INTERNAL_CHUNK_BYTES % sizeof(int16_t)) == 0,
    "Chunk size must be an even number of bytes for 16-bit PCM"
);

// =============================================================
// 6. WEBSITE CONTROL & TIMEOUT SETTINGS
// =============================================================

constexpr uint32_t CONTROL_POLL_INTERVAL_MS  = 2500;
constexpr uint32_t HEARTBEAT_INTERVAL_MS     = 20000;
constexpr uint32_t CONTROL_HTTP_TIMEOUT_MS   = 8000;
constexpr uint32_t AI_CONNECT_TIMEOUT_SEC    = 12;
constexpr uint32_t AI_WRITE_STALL_TIMEOUT_MS = 15000;
constexpr uint32_t AI_RESPONSE_TIMEOUT_MS    = 90000;
constexpr uint32_t AI_MUTEX_WAIT_MS          = 12000;

// =============================================================
// 7. DIAGNOSTIC MODE
// =============================================================

// TRUE  = record and validate microphone locally, no AI upload.
// FALSE = normal Pest Guard detection.
const bool DIAGNOSTIC_ONLY = false;

// =============================================================
// 8. SHARED DEVICE STATE
// =============================================================

// Detection always begins disabled until website Detect arrives.
volatile bool detectionEnabled = false;
char appliedControlCommandId[65] = {0};
volatile bool pendingAckHeartbeat = false;

// Coordinates SRAM-aware concurrent HTTPS access between Core 0 and Core 1.
volatile bool captureInProgress      = false;
volatile bool captureUsesInternalRam = false;
volatile bool aiSocketActive         = false;

portMUX_TYPE detectionControlMux = portMUX_INITIALIZER_UNLOCKED;

// Serializes control/heartbeat HTTPS and peak-RAM AI upload start.
// Released immediately after the 160 KB body finishes uploading so Core 0
// can keep polling Detect/Stop throughout long FastAPI inference waits.
SemaphoreHandle_t controlHttpsMutex = nullptr;

// Synchronizes RGB LED & buzzer GPIO writes between Core 0 and Core 1.
SemaphoreHandle_t alertMutex = nullptr;

bool microphoneReady = false;
volatile bool controlTaskRunning = false;

// =============================================================
// 9. FUNCTION DECLARATIONS
// =============================================================

void setupAlertPins();
void alertsOff();
void applyPestAlert(
    const String& status,
    const String& pest,
    const String& risk,
    float confidence,
    bool verified,
    const char* expectedCommandId = nullptr
);

bool connectWiFi();
bool pollDetectionControl(
    uint32_t mutexWaitMs = 0,
    bool* outRequestSucceeded = nullptr
);
bool sendDeviceHeartbeat(uint32_t mutexWaitMs = 0);
void deviceControlTask(void* parameter);

bool setupMicrophone();
DetectionCycleOutcome runDetectionCycle();

static bool uploadAudioToAI(
    PestAudioStream& audioStream,
    const char* detectionCommandId,
    int& outHttpCode,
    String& outResponseBody,
    bool& outStopped
);

static inline size_t minSize(size_t a, size_t b) {
  return (a < b) ? a : b;
}

static void appendBytesToString(String& dest, const uint8_t* data, size_t len) {
  if (data == nullptr || len == 0) return;
  dest.reserve(dest.length() + len);
  for (size_t i = 0; i < len; i++) {
    dest += static_cast<char>(data[i]);
  }
}

// =============================================================
// SECTION A: THREAD-SAFE SHARED STATE & HEAP HELPERS
// =============================================================

static bool getDetectionState() {
  bool enabled;
  portENTER_CRITICAL(&detectionControlMux);
  enabled = detectionEnabled;
  portEXIT_CRITICAL(&detectionControlMux);
  return enabled;
}

static void getDetectionSnapshot(
    bool& enabledOut,
    char* commandIdOut,
    size_t commandIdCapacity
) {
  portENTER_CRITICAL(&detectionControlMux);
  enabledOut = detectionEnabled;
  if (commandIdOut != nullptr && commandIdCapacity > 0) {
    const size_t copyLen = minSize(
        commandIdCapacity - 1,
        sizeof(appliedControlCommandId) - 1
    );
    memcpy(commandIdOut, appliedControlCommandId, copyLen);
    commandIdOut[copyLen] = '\0';
  }
  portEXIT_CRITICAL(&detectionControlMux);
}

static bool controlCommandStillActive(const char* expectedCommandId) {
  if (expectedCommandId == nullptr || expectedCommandId[0] == '\0') {
    return false;
  }

  bool enabled = false;
  char currentId[65] = {0};
  getDetectionSnapshot(enabled, currentId, sizeof(currentId));

  return enabled && (strcmp(currentId, expectedCommandId) == 0);
}

static void setCaptureMemoryState(bool active, bool usesInternalRam) {
  portENTER_CRITICAL(&detectionControlMux);
  captureInProgress = active;
  captureUsesInternalRam = active ? usesInternalRam : false;
  portEXIT_CRITICAL(&detectionControlMux);
}

static void getCaptureMemoryState(bool& activeOut, bool& usesInternalRamOut) {
  portENTER_CRITICAL(&detectionControlMux);
  activeOut = captureInProgress;
  usesInternalRamOut = captureUsesInternalRam;
  portEXIT_CRITICAL(&detectionControlMux);
}

static void setAiSocketActive(bool active) {
  portENTER_CRITICAL(&detectionControlMux);
  aiSocketActive = active;
  portEXIT_CRITICAL(&detectionControlMux);
}

static bool isAiSocketActive() {
  bool active;
  portENTER_CRITICAL(&detectionControlMux);
  active = aiSocketActive;
  portEXIT_CRITICAL(&detectionControlMux);
  return active;
}

static bool hasEnoughHeapForTls(bool concurrentWithAi) {
  const size_t freeInternal =
      heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  const size_t largestInternal =
      heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);

  if (concurrentWithAi) {
    return (freeInternal >= MIN_CONCURRENT_TLS_FREE_HEAP) &&
           (largestInternal >= MIN_CONCURRENT_TLS_LARGEST_BLOCK);
  }

  return (freeInternal >= MIN_TLS_FREE_HEAP_BYTES) &&
         (largestInternal >= MIN_TLS_LARGEST_BLOCK_BYTES);
}

static void stopAwareDelayMs(uint32_t totalMs) {
  const uint32_t startMs = millis();
  while ((uint32_t)(millis() - startMs) < totalMs) {
    if (!getDetectionState()) {
      alertsOff();
      return;
    }
    const uint32_t elapsed = (uint32_t)(millis() - startMs);
    const uint32_t remaining = (elapsed < totalMs) ? (totalMs - elapsed) : 0;
    delay((remaining > 50UL) ? 50UL : remaining);
  }
}

// =============================================================
// SECTION B: RGB LED, BUZZER AND VERIFIED PEST ALERTS
// =============================================================

static bool isAlertAllowed(const char* expectedCommandId) {
  if (expectedCommandId != nullptr && expectedCommandId[0] != '\0') {
    return controlCommandStillActive(expectedCommandId);
  }
  return getDetectionState();
}

static void writeAlertPinsRaw(bool red, bool green, bool blue, bool buzzer) {
  digitalWrite(RGB_RED_PIN, red ? HIGH : LOW);
  digitalWrite(RGB_GREEN_PIN, green ? HIGH : LOW);
  digitalWrite(RGB_BLUE_PIN, blue ? HIGH : LOW);
  digitalWrite(BUZZER_PIN, buzzer ? HIGH : LOW);
}

void alertsOff() {
  if (alertMutex != nullptr &&
      xSemaphoreTake(alertMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
    writeAlertPinsRaw(false, false, false, false);
    xSemaphoreGive(alertMutex);
    return;
  }
  writeAlertPinsRaw(false, false, false, false);
}

static bool setAlertRGBIfAllowed(
    bool red,
    bool green,
    bool blue,
    const char* expectedCommandId
) {
  bool applied = false;

  if (alertMutex != nullptr &&
      xSemaphoreTake(alertMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
    if (isAlertAllowed(expectedCommandId)) {
      digitalWrite(RGB_RED_PIN, red ? HIGH : LOW);
      digitalWrite(RGB_GREEN_PIN, green ? HIGH : LOW);
      digitalWrite(RGB_BLUE_PIN, blue ? HIGH : LOW);
      applied = true;
    } else {
      writeAlertPinsRaw(false, false, false, false);
    }
    xSemaphoreGive(alertMutex);
    return applied;
  }

  if (isAlertAllowed(expectedCommandId)) {
    digitalWrite(RGB_RED_PIN, red ? HIGH : LOW);
    digitalWrite(RGB_GREEN_PIN, green ? HIGH : LOW);
    digitalWrite(RGB_BLUE_PIN, blue ? HIGH : LOW);
    applied = true;
  } else {
    writeAlertPinsRaw(false, false, false, false);
  }
  return applied;
}

static bool setBuzzerIfAllowed(bool on, const char* expectedCommandId) {
  bool applied = false;

  if (alertMutex != nullptr &&
      xSemaphoreTake(alertMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
    if (on && isAlertAllowed(expectedCommandId)) {
      digitalWrite(BUZZER_PIN, HIGH);
      applied = true;
    } else if (!isAlertAllowed(expectedCommandId)) {
      writeAlertPinsRaw(false, false, false, false);
    } else {
      digitalWrite(BUZZER_PIN, LOW);
      applied = true;
    }
    xSemaphoreGive(alertMutex);
    return applied;
  }

  if (on && isAlertAllowed(expectedCommandId)) {
    digitalWrite(BUZZER_PIN, HIGH);
    applied = true;
  } else if (!isAlertAllowed(expectedCommandId)) {
    writeAlertPinsRaw(false, false, false, false);
  } else {
    digitalWrite(BUZZER_PIN, LOW);
    applied = true;
  }
  return applied;
}

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

static bool delayCheckingAlertAllowed(
    uint16_t durationMs,
    const char* expectedCommandId
) {
  const uint32_t startMs = millis();
  while ((uint32_t)(millis() - startMs) < durationMs) {
    if (!isAlertAllowed(expectedCommandId)) {
      alertsOff();
      return false;
    }
    const uint32_t elapsed = (uint32_t)(millis() - startMs);
    const uint32_t remaining = (elapsed < durationMs) ? (durationMs - elapsed) : 0;
    delay((remaining > 20UL) ? 20UL : remaining);
  }
  return isAlertAllowed(expectedCommandId);
}

static void beepAlert(
    uint8_t count,
    const char* expectedCommandId,
    uint16_t beepDurationMs,
    uint16_t gapDurationMs
) {
  for (uint8_t i = 0; i < count; i++) {
    if (!setBuzzerIfAllowed(true, expectedCommandId)) {
      alertsOff();
      return;
    }

    if (!delayCheckingAlertAllowed(beepDurationMs, expectedCommandId)) {
      alertsOff();
      return;
    }

    setBuzzerIfAllowed(false, expectedCommandId);

    if (!isAlertAllowed(expectedCommandId)) {
      alertsOff();
      return;
    }

    if (i + 1 < count) {
      if (!delayCheckingAlertAllowed(gapDurationMs, expectedCommandId)) {
        alertsOff();
        return;
      }
    }
  }
}

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

void applyPestAlert(
    const String& status,
    const String& pest,
    const String& risk,
    float confidence,
    bool verified,
    const char* expectedCommandId
) {
  // Never retain a previous pest alert.
  alertsOff();

  if (!isAlertAllowed(expectedCommandId)) {
    Serial.println("Detection disabled or command changed: alerts OFF.");
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
    Serial.println("No confirmed pest: alerts OFF.");
    return;
  }

  // Never trust unverified or top-three candidate predictions.
  if (!verified || !isValidAlertPestName(pest)) {
    Serial.println("Pest unverified or missing: alerts OFF.");
    return;
  }

  // Reject invalid or below-floor confidence values.
  if (!isfinite(confidence) ||
      confidence < 0.40f ||
      confidence > 1.0f) {
    Serial.println("Invalid/low confidence: alerts OFF.");
    return;
  }

  // Validate risk before triggering any hardware alert.
  if (normalizedRisk != "LOW" &&
      normalizedRisk != "MEDIUM" &&
      normalizedRisk != "MODERATE" &&
      normalizedRisk != "HIGH" &&
      normalizedRisk != "CRITICAL" &&
      normalizedRisk != "SEVERE") {
    Serial.println("Unknown risk level: alerts OFF.");
    return;
  }

  // Verified possible match below strong-alert threshold.
  if (confidence < 0.70f) {
    if (setAlertRGBIfAllowed(false, false, true, expectedCommandId)) {
      setBuzzerIfAllowed(false, expectedCommandId);
      Serial.println("Verified possible match: BLUE, no buzzer.");
    } else {
      alertsOff();
    }
    return;
  }

  if (!isAlertAllowed(expectedCommandId)) {
    alertsOff();
    return;
  }

  if (normalizedRisk == "LOW") {
    if (setAlertRGBIfAllowed(false, true, false, expectedCommandId)) {
      Serial.println("Verified LOW risk: GREEN + 1 beep.");
      beepAlert(1, expectedCommandId, 250, 150);
    }
  } else if (normalizedRisk == "MEDIUM" ||
             normalizedRisk == "MODERATE") {
    if (setAlertRGBIfAllowed(true, true, false, expectedCommandId)) {
      Serial.println("Verified MEDIUM risk: YELLOW + 2 beeps.");
      beepAlert(2, expectedCommandId, 250, 150);
    }
  } else {
    if (setAlertRGBIfAllowed(true, false, false, expectedCommandId)) {
      Serial.println("Verified HIGH risk: RED + 3 beeps.");
      beepAlert(3, expectedCommandId, 250, 150);
    }
  }

  if (!isAlertAllowed(expectedCommandId)) {
    alertsOff();
  }
}

// =============================================================
// SECTION C: WI-FI, REMOTE CONTROL AND HEARTBEAT (HTTPClient)
// =============================================================

bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.println();
  Serial.println("Connecting to Wi-Fi...");

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);  // Disable modem sleep to avoid TLS latency spikes.

  WiFi.disconnect(false);
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const uint32_t startMs = millis();
  const uint32_t timeoutMs = 15000UL;

  while (WiFi.status() != WL_CONNECTED &&
         (uint32_t)(millis() - startMs) < timeoutMs) {
    delay(250);
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi connection failed.");
    return false;
  }

  Serial.println("Wi-Fi CONNECTED.");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
  Serial.printf("Wi-Fi RSSI: %d dBm\n", WiFi.RSSI());

  return true;
}

static bool sendDeviceHeartbeatInternal(
    bool callerHoldsMutex,
    uint32_t mutexWaitMs
) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  if (!callerHoldsMutex) {
    if (controlHttpsMutex == nullptr) {
      Serial.println("Control HTTPS mutex not initialized.");
      return false;
    }

    const TickType_t waitTicks =
        (mutexWaitMs == 0) ? 0 : pdMS_TO_TICKS(mutexWaitMs);
    if (xSemaphoreTake(controlHttpsMutex, waitTicks) != pdTRUE) {
      return false;
    }
  }

  const bool concurrent = isAiSocketActive();
  if (!hasEnoughHeapForTls(concurrent)) {
    Serial.printf(
        "Heartbeat deferred: internal heap %u free / %u largest (concurrent=%s).\n",
        (unsigned int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        (unsigned int)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        concurrent ? "YES" : "NO"
    );
    if (!callerHoldsMutex) {
      xSemaphoreGive(controlHttpsMutex);
    }
    return false;
  }

  bool currentEnabled = false;
  char currentCommandId[65] = {0};
  getDetectionSnapshot(
      currentEnabled,
      currentCommandId,
      sizeof(currentCommandId)
  );

  JsonDocument heartbeatDoc;
  heartbeatDoc["status"] = "ONLINE";
  heartbeatDoc["connection"] = "CONNECTED";
  heartbeatDoc["detection_enabled"] = currentEnabled;
  heartbeatDoc["control_command_id"] = currentCommandId;

  String payload;
  serializeJson(heartbeatDoc, payload);

  bool accepted = false;

  {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.setTimeout((uint16_t)CONTROL_HTTP_TIMEOUT_MS);
    http.setConnectTimeout((int32_t)CONTROL_HTTP_TIMEOUT_MS);
    http.setReuse(false);

    if (!http.begin(client, HEARTBEAT_URL)) {
      Serial.println("Heartbeat connection setup failed.");
    } else {
      http.addHeader("Content-Type", "application/json");
      const int responseCode = http.POST(payload);

      if (responseCode >= 200 && responseCode < 300) {
        accepted = true;
        Serial.printf("Device heartbeat accepted: HTTP %d\n", responseCode);
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

  if (!callerHoldsMutex) {
    xSemaphoreGive(controlHttpsMutex);
  }

  return accepted;
}

bool sendDeviceHeartbeat(uint32_t mutexWaitMs) {
  return sendDeviceHeartbeatInternal(false, mutexWaitMs);
}

bool pollDetectionControl(
    uint32_t mutexWaitMs,
    bool* outRequestSucceeded
) {
  if (outRequestSucceeded != nullptr) {
    *outRequestSucceeded = false;
  }

  const bool previousEnabled = getDetectionState();

  if (WiFi.status() != WL_CONNECTED) {
    return previousEnabled;
  }

  if (controlHttpsMutex == nullptr) {
    Serial.println("Control HTTPS mutex not initialized.");
    return previousEnabled;
  }

  const TickType_t waitTicks =
      (mutexWaitMs == 0) ? 0 : pdMS_TO_TICKS(mutexWaitMs);
  if (xSemaphoreTake(controlHttpsMutex, waitTicks) != pdTRUE) {
    return previousEnabled;
  }

  const bool concurrent = isAiSocketActive();
  if (!hasEnoughHeapForTls(concurrent)) {
    Serial.printf(
        "Control poll deferred: internal heap %u free / %u largest (concurrent=%s).\n",
        (unsigned int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        (unsigned int)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        concurrent ? "YES" : "NO"
    );
    xSemaphoreGive(controlHttpsMutex);
    return previousEnabled;
  }

  bool validResponse = false;
  bool requestedEnabled = previousEnabled;
  char receivedCommandId[65] = {0};

  {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.setTimeout((uint16_t)CONTROL_HTTP_TIMEOUT_MS);
    http.setConnectTimeout((int32_t)CONTROL_HTTP_TIMEOUT_MS);
    http.setReuse(false);

    if (!http.begin(client, CONTROL_URL)) {
      Serial.println("Control connection setup failed.");
    } else {
      const int responseCode = http.GET();

      if (responseCode == HTTP_CODE_OK) {
        String responseBody = http.getString();

        JsonDocument controlDoc;
        DeserializationError jsonError =
            deserializeJson(controlDoc, responseBody);

        if (jsonError) {
          Serial.print("Invalid control JSON: ");
          Serial.println(jsonError.c_str());
        } else if (!controlDoc["enabled"].is<bool>()) {
          Serial.println("Control response missing valid enabled value.");
        } else {
          requestedEnabled = controlDoc["enabled"].as<bool>();
          const char* commandId = controlDoc["command_id"] | "";
          const size_t commandLength = strlen(commandId);

          // Backend may return empty command_id before first Start/Stop;
          // accept empty command_id only when disabled.
          if (commandLength >= sizeof(receivedCommandId)) {
            Serial.println("Invalid control command ID length.");
          } else if (requestedEnabled && commandLength == 0) {
            Serial.println("Enabled command missing command ID.");
          } else {
            memcpy(receivedCommandId, commandId, commandLength);
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
            "Free internal heap: %u bytes\n",
            (unsigned int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
        );
      }

      http.end();
    }
  }  // Destroy GET TLS socket before any acknowledgement heartbeat.

  if (!validResponse) {
    xSemaphoreGive(controlHttpsMutex);
    Serial.println("Control request failed. Keeping last confirmed state.");
    return previousEnabled;
  }

  char oldCommandId[65] = {0};
  bool oldEnabled = false;

  portENTER_CRITICAL(&detectionControlMux);
  oldEnabled = detectionEnabled;
  memcpy(oldCommandId, appliedControlCommandId, sizeof(oldCommandId));

  detectionEnabled = requestedEnabled;
  memcpy(
      appliedControlCommandId,
      receivedCommandId,
      sizeof(appliedControlCommandId)
  );

  const bool stateChanged = (oldEnabled != requestedEnabled);
  const bool commandChanged = (strcmp(oldCommandId, receivedCommandId) != 0);
  if (stateChanged || commandChanged) {
    pendingAckHeartbeat = true;
  }
  portEXIT_CRITICAL(&detectionControlMux);

  if (outRequestSucceeded != nullptr) {
    *outRequestSucceeded = true;
  }

  if (!requestedEnabled) {
    // STOP immediately clears any active LED or buzzer alert.
    alertsOff();
  }

  if (stateChanged || commandChanged) {
    Serial.println();
    if (requestedEnabled) {
      Serial.printf(
          "REMOTE COMMAND: DETECTION STARTED (ID: %s)\n",
          receivedCommandId
      );
    } else {
      Serial.printf(
          "REMOTE COMMAND: DETECTION STOPPED (ID: %s)\n",
          receivedCommandId
      );
    }

    // Acknowledge while still holding controlHttpsMutex so the AI loop
    // cannot starve or drop the website confirmation.
    if (sendDeviceHeartbeatInternal(true, 0)) {
      portENTER_CRITICAL(&detectionControlMux);
      pendingAckHeartbeat = false;
      portEXIT_CRITICAL(&detectionControlMux);
    }
  }

  xSemaphoreGive(controlHttpsMutex);
  return requestedEnabled;
}

void deviceControlTask(void* parameter) {
  (void)parameter;

  uint32_t lastControlPoll = 0;
  uint32_t lastHeartbeat = 0;

  for (;;) {
    if (WiFi.status() == WL_CONNECTED) {
      uint32_t now = millis();

      // 1. Poll website Detect/Stop state every 2.5 seconds.
      if (lastControlPoll == 0 ||
          (uint32_t)(now - lastControlPoll) >= CONTROL_POLL_INTERVAL_MS) {
        lastControlPoll = now;
        pollDetectionControl(0, nullptr);
      }

      // 2. Retry any pending command-ID ack, or send periodic heartbeat.
      bool needAck = false;
      portENTER_CRITICAL(&detectionControlMux);
      needAck = pendingAckHeartbeat;
      portEXIT_CRITICAL(&detectionControlMux);

      bool capturing = false;
      bool usingInternal = false;
      getCaptureMemoryState(capturing, usingInternal);

      now = millis();
      const bool periodicDue =
          (lastHeartbeat == 0) ||
          ((uint32_t)(now - lastHeartbeat) >= HEARTBEAT_INTERVAL_MS);

      // Pause non-urgent periodic heartbeats during internal-SRAM capture
      // to keep DMA timing jitter low; always send urgent command acks.
      if (needAck || (periodicDue && !(capturing && usingInternal))) {
        if (sendDeviceHeartbeat(0)) {
          lastHeartbeat = millis();
          if (needAck) {
            portENTER_CRITICAL(&detectionControlMux);
            pendingAckHeartbeat = false;
            portEXIT_CRITICAL(&detectionControlMux);
          }
        }
      }
    }

    vTaskDelay(pdMS_TO_TICKS(100));
  }
}

// =============================================================
// SECTION D: INMP441 MICROPHONE & DUAL-TIER AUDIO STREAM
// =============================================================

bool setupMicrophone() {
  microphoneReady = false;

  i2s_config_t config = {};
  config.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  config.sample_rate = SAMPLE_RATE;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;

  // 16 x 256 x 4 bytes = 16 KB DMA RAM (256 ms cushion at 16 kHz).
  config.dma_buf_count = I2S_DMA_BUF_COUNT;
  config.dma_buf_len   = I2S_DMA_BUF_LEN;

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
    Serial.printf("I2S driver installation failed: %d\n", (int)result);
    return false;
  }

  i2s_pin_config_t pins = {};
  pins.mck_io_num   = I2S_PIN_NO_CHANGE;
  pins.bck_io_num   = MIC_SCK_PIN;
  pins.ws_io_num    = MIC_WS_PIN;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num  = MIC_SD_PIN;

  result = i2s_set_pin(MIC_I2S_PORT, &pins);
  if (result != ESP_OK) {
    Serial.printf("I2S pin configuration failed: %d\n", (int)result);
    i2s_driver_uninstall(MIC_I2S_PORT);
    return false;
  }

  // Keep I2S stopped while idle to avoid unnecessary DMA interrupt load.
  i2s_stop(MIC_I2S_PORT);
  i2s_zero_dma_buffer(MIC_I2S_PORT);

  microphoneReady = true;

  Serial.println("INMP441 driver initialized.");
  Serial.println("Configured I2S receive channel: LEFT.");
  Serial.println("Audio: 16000 Hz, mono, 16-bit PCM (160,000 bytes).");

  return true;
}

class PestAudioStream : public Stream {
private:
  enum StorageMode : uint8_t {
    STORAGE_NONE = 0,
    STORAGE_PSRAM = 1,
    STORAGE_INTERNAL_SEGMENTED = 2,
    STORAGE_FLASH = 3
  };

  int32_t rawSamples[AUDIO_CHUNK_SAMPLES];

  StorageMode storageMode = STORAGE_NONE;
  uint8_t* psramBuffer = nullptr;
  uint8_t* internalChunks[INTERNAL_CHUNK_COUNT] = {nullptr};
  File flashFile;
  uint8_t flashWriteBuf[INTERNAL_CHUNK_BYTES] = {0};

  uint32_t capturedSamples       = 0;
  uint32_t consumedBytes         = 0;
  uint32_t zeroSamples           = 0;
  uint32_t currentZeroRun        = 0;
  uint32_t longestZeroRun        = 0;
  uint32_t clippedSamples        = 0;
  uint32_t rawZeroWords          = 0;
  uint32_t currentRawZeroRun     = 0;
  uint32_t longestRawZeroRun     = 0;
  uint32_t failedReads           = 0;
  uint32_t overrunSuspectedCount = 0;
  uint32_t maxChunkGapMs         = 0;
  uint32_t lastChunkEndMs        = 0;

  uint32_t captureStartMs = 0;
  uint32_t captureEndMs   = 0;

  int16_t sampleMin = 32767;
  int16_t sampleMax = -32768;
  int32_t rawMin    = INT32_MAX;
  int32_t rawMax    = INT32_MIN;

  double sumSquares = 0.0;

  bool failed         = false;
  bool memoryShortage = false;
  bool abortedByStop  = false;
  bool started        = false;
  bool captureReady   = false;

  bool allocateStorage() {
    // ---------------------------------------------------------
    // TIER 1: PSRAM (used automatically whenever available)
    // ---------------------------------------------------------
    if (psramFound()) {
      const size_t largestPsram = heap_caps_get_largest_free_block(
          MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
      );
      if (largestPsram >= PCM_PAYLOAD_BYTES) {
        psramBuffer = (uint8_t*)heap_caps_malloc(
            PCM_PAYLOAD_BYTES,
            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
        );
        if (psramBuffer != nullptr) {
          storageMode = STORAGE_PSRAM;
          Serial.printf(
              "Audio buffer: PSRAM (%u bytes). Free PSRAM: %u bytes.\n",
              (unsigned int)PCM_PAYLOAD_BYTES,
              (unsigned int)ESP.getFreePsram()
          );
          return true;
        }
      }
      Serial.println("PSRAM found but allocation failed; falling back to internal SRAM.");
    }

    // ---------------------------------------------------------
    // FLASH FALLBACK: Store PCM in an existing LittleFS partition.
    // This avoids keeping 160 KB of PCM in internal RAM during TLS.
    // Never format automatically: formatting destroys that partition's data.
    // ---------------------------------------------------------
    static bool fsChecked = false;
    static bool fsReady = false;
    if (!fsChecked) {
      fsChecked = true;
      fsReady = LittleFS.begin(true);
      Serial.println(fsReady ? "LittleFS mounted." :
                     "LittleFS unavailable/unformatted; preserving existing flash data.");
    }
    if (fsReady) {
      // Clean up a partial recording left by an earlier power loss.
      if (LittleFS.exists("/pest_guard_audio.pcm")) {
        LittleFS.remove("/pest_guard_audio.pcm");
      }
      const size_t total = LittleFS.totalBytes();
      const size_t used = LittleFS.usedBytes();
      if (total >= used && total - used >= PCM_PAYLOAD_BYTES + 32768UL) {
        flashFile = LittleFS.open("/pest_guard_audio.pcm", FILE_WRITE);
        if (flashFile) {
          storageMode = STORAGE_FLASH;
          Serial.println("Audio storage: LittleFS flash (160 KB temporary recording).");
          return true;
        }
        Serial.println("Cannot open LittleFS recording file.");
      } else {
        Serial.println("LittleFS mounted but insufficient free space for PCM recording.");
      }
    }

    // ---------------------------------------------------------
    // TIER 2: Segmented Internal SRAM (40 x 4,000 bytes)
    // Temporarily holds two contiguous guard blocks so mbedTLS
    // retains clean contiguous buffers after chunk allocation.
    // ---------------------------------------------------------
    const size_t freeBefore =
        heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    const size_t largestBefore =
        heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    const size_t minRequiredTotal =
        PCM_PAYLOAD_BYTES + MIN_TLS_FREE_HEAP_BYTES;

    if (freeBefore < minRequiredTotal ||
        largestBefore < MIN_TLS_LARGEST_BLOCK_BYTES) {
      memoryShortage = true;
      Serial.println("====================================================");
      Serial.println("HARDWARE MEMORY LIMIT REACHED (NO PSRAM AVAILABLE)");
      Serial.printf("Free internal SRAM : %u bytes\n", (unsigned int)freeBefore);
      Serial.printf(
          "Required minimum   : %u bytes (160,000 PCM + %u TLS)\n",
          (unsigned int)minRequiredTotal,
          (unsigned int)MIN_TLS_FREE_HEAP_BYTES
      );
      Serial.printf(
          "Largest free block : %u bytes (min %u)\n",
          (unsigned int)largestBefore,
          (unsigned int)MIN_TLS_LARGEST_BLOCK_BYTES
      );
      Serial.println("Action: Enable Tools -> PSRAM (OPI or QSPI) if your");
      Serial.println("ESP32-S3 module has PSRAM, or use a PSRAM module.");
      Serial.println("====================================================");
      return false;
    }

    void* guardA = heap_caps_malloc(
        TLS_GUARD_A_PRIMARY_BYTES,
        MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
    );
    void* guardB = heap_caps_malloc(
        TLS_GUARD_B_PRIMARY_BYTES,
        MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
    );

    if (guardA == nullptr) {
      guardA = heap_caps_malloc(
          TLS_GUARD_A_FALLBACK_BYTES,
          MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
      );
    }
    if (guardB == nullptr) {
      guardB = heap_caps_malloc(
          TLS_GUARD_B_FALLBACK_BYTES,
          MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
      );
    }

    bool allAllocated = true;
    for (size_t i = 0; i < INTERNAL_CHUNK_COUNT; i++) {
      internalChunks[i] = (uint8_t*)heap_caps_malloc(
          INTERNAL_CHUNK_BYTES,
          MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
      );
      if (internalChunks[i] == nullptr) {
        allAllocated = false;
        break;
      }
    }

    // Immediately release both temporary TLS guard blocks.
    if (guardB != nullptr) {
      heap_caps_free(guardB);
      guardB = nullptr;
    }
    if (guardA != nullptr) {
      heap_caps_free(guardA);
      guardA = nullptr;
    }

    if (!allAllocated) {
      memoryShortage = true;
      releaseCaptureBuffer();
      Serial.println("Audio capture aborted: internal SRAM chunk allocation failed.");
      return false;
    }

    storageMode = STORAGE_INTERNAL_SEGMENTED;

    const size_t freeAfter =
        heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    const size_t largestAfter =
        heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);

    Serial.printf(
        "Audio buffer: Internal SRAM (%u x %u bytes). Free: %u bytes, Largest block: %u bytes.\n",
        (unsigned int)INTERNAL_CHUNK_COUNT,
        (unsigned int)INTERNAL_CHUNK_BYTES,
        (unsigned int)freeAfter,
        (unsigned int)largestAfter
    );

    if (freeAfter < MIN_TLS_FREE_HEAP_BYTES ||
        largestAfter < MIN_TLS_LARGEST_BLOCK_BYTES) {
      memoryShortage = true;
      Serial.println("Audio capture aborted: insufficient TLS headroom after PCM allocation.");
      releaseCaptureBuffer();
      return false;
    }

    if (freeAfter < RECOMMENDED_TLS_HEAP_BYTES) {
      Serial.println("WARNING: Tight internal SRAM headroom for TLS; enabling PSRAM is recommended.");
    }

    return true;
  }

  inline void storeSampleLE(uint32_t sampleIndex, int16_t sample) {
    const uint16_t encoded = (uint16_t)sample;
    const uint8_t lo = (uint8_t)(encoded & 0xFF);
    const uint8_t hi = (uint8_t)((encoded >> 8) & 0xFF);
    const uint32_t byteOffset = sampleIndex * sizeof(int16_t);

    if (storageMode == STORAGE_PSRAM) {
      psramBuffer[byteOffset]     = lo;
      psramBuffer[byteOffset + 1] = hi;
    } else if (storageMode == STORAGE_FLASH) {
      const size_t pos = byteOffset % INTERNAL_CHUNK_BYTES;
      flashWriteBuf[pos] = lo;
      flashWriteBuf[pos + 1] = hi;
      if (pos + 2 == INTERNAL_CHUNK_BYTES) {
        if (!flashFile ||
            flashFile.write(flashWriteBuf, INTERNAL_CHUNK_BYTES) != INTERNAL_CHUNK_BYTES) {
          failed = true;
          Serial.println("LittleFS flash write failed; discarding recording.");
        }
      }
    } else {
      const size_t chunkIdx = byteOffset / INTERNAL_CHUNK_BYTES;
      const size_t offsetInChunk = byteOffset % INTERNAL_CHUNK_BYTES;
      uint8_t* chunk = internalChunks[chunkIdx];
      chunk[offsetInChunk]     = lo;
      chunk[offsetInChunk + 1] = hi;
    }
  }

  bool discardWarmupSamples(const char* activeCommandId) {
    size_t discarded = 0;
    const uint32_t warmupStartMs = millis();

    while (discarded < MIC_WARMUP_SAMPLES) {
      if (activeCommandId != nullptr) {
        if (!controlCommandStillActive(activeCommandId)) {
          abortedByStop = true;
          return false;
        }
      } else if (!getDetectionState()) {
        abortedByStop = true;
        return false;
      }

      if ((uint32_t)(millis() - warmupStartMs) > 2000UL) {
        Serial.println("INMP441 warm-up read timeout.");
        return false;
      }

      const size_t requestSamples = minSize(
          AUDIO_CHUNK_SAMPLES,
          MIC_WARMUP_SAMPLES - discarded
      );
      size_t bytesRead = 0;

      const esp_err_t res = i2s_read(
          MIC_I2S_PORT,
          rawSamples,
          requestSamples * sizeof(int32_t),
          &bytesRead,
          pdMS_TO_TICKS(500)
      );

      if (res != ESP_OK || bytesRead == 0 || (bytesRead % sizeof(int32_t)) != 0) {
        failedReads++;
        Serial.printf(
            "Invalid warm-up I2S read: error=%d bytes=%u\n",
            (int)res,
            (unsigned int)bytesRead
        );
        return false;
      }

      discarded += bytesRead / sizeof(int32_t);
    }

    return true;
  }

  bool loadNextChunk() {
    if (failed || storageMode == STORAGE_NONE) {
      return false;
    }

    if (capturedSamples >= TOTAL_SAMPLES) {
      return false;
    }

    if ((uint32_t)(millis() - captureStartMs) > 10000UL) {
      Serial.println("Audio capture exceeded timeout.");
      failed = true;
      return false;
    }

    const size_t remaining = TOTAL_SAMPLES - capturedSamples;
    const size_t requestSamples = minSize(AUDIO_CHUNK_SAMPLES, remaining);
    size_t bytesRead = 0;

    const esp_err_t result = i2s_read(
        MIC_I2S_PORT,
        rawSamples,
        requestSamples * sizeof(int32_t),
        &bytesRead,
        pdMS_TO_TICKS(1000)
    );

    const uint32_t nowMs = millis();

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

    if (lastChunkEndMs != 0) {
      const uint32_t gapMs = (uint32_t)(nowMs - lastChunkEndMs);
      if (gapMs > maxChunkGapMs) {
        maxChunkGapMs = gapMs;
      }
      if (gapMs >= MAX_SAFE_CHUNK_GAP_MS) {
        overrunSuspectedCount++;
      }
    }
    lastChunkEndMs = nowMs;

    const size_t count = bytesRead / sizeof(int32_t);

    for (size_t i = 0; i < count; i++) {
      const int32_t rawSample = rawSamples[i];
      const int16_t sample = (int16_t)(rawSample >> 16);

      if (rawSample < rawMin) rawMin = rawSample;
      if (rawSample > rawMax) rawMax = rawSample;
      if (rawSample == 0) {
        rawZeroWords++;
        currentRawZeroRun++;
        if (currentRawZeroRun > longestRawZeroRun) {
          longestRawZeroRun = currentRawZeroRun;
        }
      } else {
        currentRawZeroRun = 0;
      }

      storeSampleLE(capturedSamples + i, sample);

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

      sumSquares += (double)sample * (double)sample;
    }

    capturedSamples += count;

    if (capturedSamples == TOTAL_SAMPLES) {
      captureEndMs = nowMs;
    }

    return true;
  }

public:
  ~PestAudioStream() {
    releaseCaptureBuffer();
  }

  bool capture(const char* activeCommandId) {
    if (failed || storageMode != STORAGE_NONE) {
      return false;
    }

    if (!allocateStorage()) {
      failed = true;
      return false;
    }

    setCaptureMemoryState(true, storageMode == STORAGE_INTERNAL_SEGMENTED);

    if (i2s_stop(MIC_I2S_PORT) != ESP_OK ||
        i2s_zero_dma_buffer(MIC_I2S_PORT) != ESP_OK ||
        i2s_start(MIC_I2S_PORT) != ESP_OK) {
      Serial.println("Cannot start I2S recording.");
      failed = true;
      i2s_stop(MIC_I2S_PORT);
      releaseCaptureBuffer();
      return false;
    }

    if (!discardWarmupSamples(activeCommandId)) {
      Serial.println("Audio warm-up stopped or failed.");
      failed = true;
      i2s_stop(MIC_I2S_PORT);
      releaseCaptureBuffer();
      return false;
    }

    started = true;
    captureStartMs = millis();
    lastChunkEndMs = captureStartMs;

    while (capturedSamples < TOTAL_SAMPLES) {
      if (activeCommandId != nullptr) {
        if (!controlCommandStillActive(activeCommandId)) {
          Serial.println("Audio capture stopped by website command.");
          abortedByStop = true;
          failed = true;
          i2s_stop(MIC_I2S_PORT);
          releaseCaptureBuffer();
          return false;
        }
      } else if (!getDetectionState()) {
        Serial.println("Audio capture stopped.");
        abortedByStop = true;
        failed = true;
        i2s_stop(MIC_I2S_PORT);
        releaseCaptureBuffer();
        return false;
      }

      if (!loadNextChunk()) {
        i2s_stop(MIC_I2S_PORT);
        releaseCaptureBuffer();
        return false;
      }
    }

    // Stop I2S immediately after capture completes.
    i2s_stop(MIC_I2S_PORT);

    if (storageMode == STORAGE_FLASH && !failed) {
      flashFile.flush();
      const size_t fileBytes = flashFile.size();
      flashFile.close();
      if (fileBytes == PCM_PAYLOAD_BYTES) {
        flashFile = LittleFS.open("/pest_guard_audio.pcm", FILE_READ);
        if (!flashFile || flashFile.size() != PCM_PAYLOAD_BYTES) {
          failed = true;
          Serial.println("LittleFS PCM file could not be reopened for upload.");
        }
      } else {
        failed = true;
        Serial.printf("LittleFS PCM size mismatch: %u / %u.\n",
                      (unsigned)fileBytes, (unsigned)PCM_PAYLOAD_BYTES);
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

  // Must run BEFORE uploading to reject incomplete, invalid, or overrun audio.
  bool validateCapturedAudio(const char** outReason = nullptr) const {
    auto failWith = [&](const char* reason) -> bool {
      if (outReason != nullptr) *outReason = reason;
      return false;
    };

    if (failed || !captureReady || storageMode == STORAGE_NONE) {
      return failWith("Capture did not complete cleanly.");
    }

    if (capturedSamples != TOTAL_SAMPLES) {
      return failWith("Incomplete PCM sample count.");
    }

    if (failedReads > 0) {
      return failWith("I2S read errors occurred during capture.");
    }

    const uint32_t durationMs = captureDuration();
    if (durationMs < MIN_VALID_CAPTURE_MS || durationMs > MAX_VALID_CAPTURE_MS) {
      return failWith("Capture timing outside valid 5-second window (clock or DMA sample loss).");
    }

    if (overrunSuspectedCount > 0) {
      return failWith("Potential I2S DMA overrun / sample loss detected.");
    }

    if (rawMin == rawMax || sampleMin == sampleMax) {
      return failWith("Constant microphone signal (stuck or disconnected INMP441).");
    }

    if (rawZeroWords >= (TOTAL_SAMPLES * 95UL) / 100UL) {
      return failWith("Microphone data line mostly zero (check SD/SCK/WS/L-R wiring).");
    }

    if (longestRawZeroRun >= MAX_RAW_ZERO_RUN) {
      return failWith("Long digital zero dropout detected in raw I2S stream.");
    }

    const int32_t peakToPeak = (int32_t)sampleMax - (int32_t)sampleMin;
    if (peakToPeak < MIN_VALID_PEAK_TO_PEAK) {
      return failWith("Microphone peak-to-peak amplitude too small (dead signal).");
    }

    const double rms = sqrt(sumSquares / (double)capturedSamples);
    if (!isfinite(rms) || rms < MIN_VALID_RMS) {
      return failWith("Microphone RMS invalid or near zero.");
    }

    if (clippedSamples > (TOTAL_SAMPLES / 2UL)) {
      return failWith("Excessive full-scale clipping (microphone data line stuck high/low).");
    }

    if (outReason != nullptr) {
      *outReason = "OK";
    }
    return true;
  }

  void releaseCaptureBuffer() {
    if (flashFile) flashFile.close();
    if (storageMode == STORAGE_FLASH) {
      LittleFS.remove("/pest_guard_audio.pcm");
    }
    if (psramBuffer != nullptr) {
      heap_caps_free(psramBuffer);
      psramBuffer = nullptr;
    }

    for (size_t i = 0; i < INTERNAL_CHUNK_COUNT; i++) {
      if (internalChunks[i] != nullptr) {
        heap_caps_free(internalChunks[i]);
        internalChunks[i] = nullptr;
      }
    }

    storageMode = STORAGE_NONE;
    captureReady = false;
    setCaptureMemoryState(false, false);
  }

  void resetCapture() {
    releaseCaptureBuffer();

    capturedSamples       = 0;
    consumedBytes         = 0;
    zeroSamples           = 0;
    currentZeroRun        = 0;
    longestZeroRun        = 0;
    clippedSamples        = 0;
    rawZeroWords          = 0;
    currentRawZeroRun     = 0;
    longestRawZeroRun     = 0;
    failedReads           = 0;
    overrunSuspectedCount = 0;
    maxChunkGapMs         = 0;
    lastChunkEndMs        = 0;

    captureStartMs = 0;
    captureEndMs   = 0;

    sampleMin = 32767;
    sampleMax = -32768;
    rawMin    = INT32_MAX;
    rawMax    = INT32_MIN;

    sumSquares = 0.0;

    failed         = false;
    memoryShortage = false;
    abortedByStop  = false;
    started        = false;
    captureReady   = false;
  }

  // Always return >= 0 (never -1) for safe compatibility with HTTPClient.
  int available() override {
    if (failed || !captureReady || consumedBytes >= PCM_PAYLOAD_BYTES) {
      return 0;
    }

    const uint32_t remainingBytes = PCM_PAYLOAD_BYTES - consumedBytes;
    const uint32_t maxBlock = 4096UL;
    return (int)((remainingBytes > maxBlock) ? maxBlock : remainingBytes);
  }

  // Block transfer: frees each 4,000-byte internal SRAM chunk immediately once read.
  size_t readBytes(char* buffer, size_t length) {
    if (buffer == nullptr || length == 0 || failed || !captureReady) {
      return 0;
    }

    uint8_t* dest = reinterpret_cast<uint8_t*>(buffer);
    size_t totalCopied = 0;

    while (totalCopied < length && consumedBytes < PCM_PAYLOAD_BYTES) {
      if (storageMode == STORAGE_PSRAM) {
        if (psramBuffer == nullptr) {
          failed = true;
          break;
        }
        const size_t remaining = PCM_PAYLOAD_BYTES - consumedBytes;
        const size_t toCopy = minSize(length - totalCopied, remaining);
        memcpy(dest + totalCopied, psramBuffer + consumedBytes, toCopy);
        consumedBytes += toCopy;
        totalCopied += toCopy;
      } else if (storageMode == STORAGE_FLASH) {
        if (!flashFile) {
          failed = true;
          break;
        }
        const size_t remaining = PCM_PAYLOAD_BYTES - consumedBytes;
        const size_t want = minSize(length - totalCopied, remaining);
        const int got = flashFile.read(dest + totalCopied, want);
        if (got <= 0) {
          failed = true;
          break;
        }
        consumedBytes += (size_t)got;
        totalCopied += (size_t)got;
      } else if (storageMode == STORAGE_INTERNAL_SEGMENTED) {
        const size_t chunkIdx = consumedBytes / INTERNAL_CHUNK_BYTES;
        const size_t offsetInChunk = consumedBytes % INTERNAL_CHUNK_BYTES;

        if (chunkIdx >= INTERNAL_CHUNK_COUNT ||
            internalChunks[chunkIdx] == nullptr) {
          failed = true;
          break;
        }

        const size_t chunkRemaining = INTERNAL_CHUNK_BYTES - offsetInChunk;
        const size_t totalRemaining = PCM_PAYLOAD_BYTES - consumedBytes;
        const size_t toCopy = minSize(
            length - totalCopied,
            minSize(chunkRemaining, totalRemaining)
        );

        memcpy(
            dest + totalCopied,
            internalChunks[chunkIdx] + offsetInChunk,
            toCopy
        );
        consumedBytes += toCopy;
        totalCopied += toCopy;

        if ((offsetInChunk + toCopy) == INTERNAL_CHUNK_BYTES) {
          heap_caps_free(internalChunks[chunkIdx]);
          internalChunks[chunkIdx] = nullptr;
        }
      } else {
        failed = true;
        break;
      }
    }

    return totalCopied;
  }

  size_t readBytes(uint8_t* buffer, size_t length) {
    return readBytes(reinterpret_cast<char*>(buffer), length);
  }

  int read() override {
    uint8_t byteVal = 0;
    if (readBytes(&byteVal, 1) != 1) {
      return -1;
    }
    return (int)byteVal;
  }

  int peek() override {
    if (available() <= 0) {
      return -1;
    }

    if (storageMode == STORAGE_PSRAM) {
      if (psramBuffer == nullptr) return -1;
      return (int)psramBuffer[consumedBytes];
    }

    if (storageMode == STORAGE_FLASH) {
      return flashFile ? flashFile.peek() : -1;
    }

    if (storageMode == STORAGE_INTERNAL_SEGMENTED) {
      const size_t chunkIdx = consumedBytes / INTERNAL_CHUNK_BYTES;
      const size_t offsetInChunk = consumedBytes % INTERNAL_CHUNK_BYTES;
      if (chunkIdx >= INTERNAL_CHUNK_COUNT ||
          internalChunks[chunkIdx] == nullptr) {
        return -1;
      }
      return (int)internalChunks[chunkIdx][offsetInChunk];
    }

    return -1;
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

  bool hadMemoryShortage() const { return memoryShortage; }
  bool wasAbortedByStop() const  { return abortedByStop; }
  bool usesPsram() const         { return storageMode == STORAGE_PSRAM; }
  uint32_t bytesConsumed() const { return consumedBytes; }

  uint32_t captureDuration() const {
    if (!started || captureEndMs == 0) return 0;
    return (uint32_t)(captureEndMs - captureStartMs);
  }

  const char* storageModeName() const {
    if (storageMode == STORAGE_PSRAM) return "PSRAM";
    if (storageMode == STORAGE_INTERNAL_SEGMENTED) return "INTERNAL_SRAM_SEGMENTED";
    if (storageMode == STORAGE_FLASH) return "FLASH_LITTLEFS";
    return "NONE";
  }

  void printDiagnostics() const {
    Serial.println();
    Serial.println("===== MICROPHONE DIAGNOSTICS =====");
    Serial.printf("Storage mode          : %s\n", storageModeName());
    Serial.printf(
        "Samples               : %u / %u\n",
        (unsigned int)capturedSamples,
        (unsigned int)TOTAL_SAMPLES
    );
    Serial.printf(
        "PCM bytes consumed    : %u / %u\n",
        (unsigned int)consumedBytes,
        (unsigned int)PCM_PAYLOAD_BYTES
    );
    Serial.printf("PCM min / max         : %d / %d\n", (int)sampleMin, (int)sampleMax);
    Serial.printf("Raw I2S min / max     : %ld / %ld\n", (long)rawMin, (long)rawMax);
    Serial.printf("Raw I2S zero words    : %u\n", (unsigned int)rawZeroWords);
    Serial.printf("Longest raw zero run  : %u samples\n", (unsigned int)longestRawZeroRun);

    if (capturedSamples > 0) {
      const double rms = sqrt(sumSquares / (double)capturedSamples);
      const double zeroPercentage =
          (100.0 * zeroSamples) / (double)capturedSamples;

      Serial.printf("RMS                   : %.2f\n", rms);
      Serial.printf("Zero PCM samples      : %.2f%%\n", zeroPercentage);
      Serial.printf("Longest PCM zero run  : %u samples\n", (unsigned int)longestZeroRun);
      Serial.printf(
          "Full-scale samples    : %u (%.4f%%)\n",
          (unsigned int)clippedSamples,
          (100.0 * clippedSamples) / (double)capturedSamples
      );
    }

    Serial.printf("Capture duration      : %u ms\n", (unsigned int)captureDuration());
    Serial.printf("Max I2S chunk gap     : %u ms\n", (unsigned int)maxChunkGapMs);
    Serial.printf("Suspected DMA overruns: %u\n", (unsigned int)overrunSuspectedCount);
    Serial.printf("Failed I2S reads      : %u\n", (unsigned int)failedReads);
    Serial.println("==================================");
  }
};

// =============================================================
// SECTION E: NON-BLOCKING HTTPS AI UPLOAD & FRESH PRE-ALERT CHECK
// =============================================================

static bool acquireControlMutexStopAware(
    const char* activeCommandId,
    uint32_t maxWaitMs
) {
  const uint32_t startMs = millis();

  while ((uint32_t)(millis() - startMs) < maxWaitMs) {
    if (!controlCommandStillActive(activeCommandId)) {
      return false;
    }
    if (xSemaphoreTake(controlHttpsMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
      return true;
    }
  }

  return false;
}

static bool writeAllStopAware(
    WiFiClientSecure& client,
    const uint8_t* data,
    size_t len,
    const char* activeCommandId,
    bool& outStopped
) {
  size_t totalWritten = 0;
  uint32_t lastProgressMs = millis();

  while (totalWritten < len) {
    if (!controlCommandStillActive(activeCommandId)) {
      outStopped = true;
      return false;
    }
    if (!client.connected()) {
      return false;
    }

    const size_t written = client.write(data + totalWritten, len - totalWritten);
    if (written > 0) {
      totalWritten += written;
      lastProgressMs = millis();
    } else {
      if ((uint32_t)(millis() - lastProgressMs) >= AI_WRITE_STALL_TIMEOUT_MS) {
        Serial.println("AI socket write stalled.");
        return false;
      }
      vTaskDelay(pdMS_TO_TICKS(5));
    }
  }

  return true;
}

static bool readHttpLineNonBlocking(
    WiFiClientSecure& client,
    String& outLine,
    uint32_t startMs,
    uint32_t timeoutMs,
    const char* activeCommandId,
    bool& outStopped,
    bool& outTimedOut
) {
  outLine = "";
  outLine.reserve(128);

  while (true) {
    if (!controlCommandStillActive(activeCommandId)) {
      outStopped = true;
      return false;
    }

    if (client.available() > 0) {
      const int ch = client.read();
      if (ch < 0) {
        continue;
      }
      if (ch == '\r') {
        continue;
      }
      if (ch == '\n') {
        return true;
      }
      if (outLine.length() < 1024) {
        outLine += (char)ch;
      }
      continue;
    }

    if (!client.connected()) {
      return outLine.length() > 0;
    }

    if ((uint32_t)(millis() - startMs) >= timeoutMs) {
      outTimedOut = true;
      return false;
    }

    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

static bool readHttpExactBytesNonBlocking(
    WiFiClientSecure& client,
    String& outBody,
    size_t bytesToRead,
    uint32_t startMs,
    uint32_t timeoutMs,
    const char* activeCommandId,
    bool& outStopped,
    bool& outTimedOut,
    bool& outOverflow
) {
  if (outBody.length() + bytesToRead > MAX_AI_RESPONSE_BYTES) {
    outOverflow = true;
    return false;
  }

  uint8_t buf[256];
  size_t remaining = bytesToRead;

  while (remaining > 0) {
    if (!controlCommandStillActive(activeCommandId)) {
      outStopped = true;
      return false;
    }

    const int avail = client.available();
    if (avail > 0) {
      const size_t want = minSize(remaining, minSize((size_t)avail, sizeof(buf)));
      const int got = client.read(buf, want);
      if (got > 0) {
        appendBytesToString(outBody, buf, (size_t)got);
        remaining -= (size_t)got;
      }
      continue;
    }

    if (!client.connected()) {
      return false;
    }

    if ((uint32_t)(millis() - startMs) >= timeoutMs) {
      outTimedOut = true;
      return false;
    }

    vTaskDelay(pdMS_TO_TICKS(20));
  }

  return true;
}

static bool uploadAudioToAI(
    PestAudioStream& audioStream,
    const char* detectionCommandId,
    int& outHttpCode,
    String& outResponseBody,
    bool& outStopped
) {
  outHttpCode = -1;
  outResponseBody = "";
  outStopped = false;

  // Serialize briefly against any in-flight Core 0 GET/POST so we never
  // overlap two TLS handshakes while 160 KB occupies internal SRAM.
  if (!acquireControlMutexStopAware(detectionCommandId, AI_MUTEX_WAIT_MS)) {
    if (!controlCommandStillActive(detectionCommandId)) {
      outStopped = true;
    } else {
      Serial.println("Control mutex busy before AI upload.");
    }
    return false;
  }

  bool holdingControlMutex = true;
  auto releaseControlMutexIfHeld = [&]() {
    if (holdingControlMutex) {
      xSemaphoreGive(controlHttpsMutex);
      holdingControlMutex = false;
    }
  };

  if (!controlCommandStillActive(detectionCommandId)) {
    outStopped = true;
    releaseControlMutexIfHeld();
    return false;
  }

  if (!hasEnoughHeapForTls(false)) {
    Serial.printf(
        "AI upload aborted: insufficient internal SRAM for TLS (%u free / %u largest).\n",
        (unsigned int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        (unsigned int)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
    );
    releaseControlMutexIfHeld();
    return false;
  }

  bool success = false;
  bool timedOut = false;
  bool overflow = false;

  {
    WiFiClientSecure client;
    client.setInsecure();
    client.setHandshakeTimeout(AI_CONNECT_TIMEOUT_SEC);
    client.setTimeout(AI_CONNECT_TIMEOUT_SEC);

    setAiSocketActive(true);

    Serial.println("Connecting to Pest Guard AI endpoint...");
    if (!client.connect(SERVER_HOST, SERVER_PORT)) {
      Serial.println("AI TLS connection failed.");
      setAiSocketActive(false);
      releaseControlMutexIfHeld();
      return false;
    }

    // In PSRAM mode (or whenever concurrent SRAM headroom already exists),
    // release controlHttpsMutex immediately so Core 0 never waits on upload.
    if (audioStream.usesPsram() && hasEnoughHeapForTls(true)) {
      releaseControlMutexIfHeld();
    }

    // Send HTTP/1.1 request headers preserving exact Pest Guard backend API.
    String reqHeaders;
    reqHeaders.reserve(320);
    reqHeaders += "POST ";
    reqHeaders += AI_PATH;
    reqHeaders += " HTTP/1.1\r\nHost: ";
    reqHeaders += SERVER_HOST;
    reqHeaders += "\r\nUser-Agent: PestGuard-ESP32S3\r\n";
    reqHeaders += "Accept: application/json\r\n";
    reqHeaders += "Content-Type: application/octet-stream\r\n";
    reqHeaders += "Content-Length: ";
    reqHeaders += String(PCM_PAYLOAD_BYTES);
    reqHeaders += "\r\nX-Detection-Control-Command-Id: ";
    reqHeaders += detectionCommandId;
    reqHeaders += "\r\nConnection: close\r\n\r\n";

    Serial.println("Sending validated 160,000-byte PCM to AI...");
    if (!writeAllStopAware(
            client,
            reinterpret_cast<const uint8_t*>(reqHeaders.c_str()),
            reqHeaders.length(),
            detectionCommandId,
            outStopped
        )) {
      Serial.println(outStopped ? "AI upload cancelled by Stop." : "Failed sending AI headers.");
      client.stop();
      setAiSocketActive(false);
      releaseControlMutexIfHeld();
      return false;
    }

    // Stream 160,000 bytes in 4,000-byte chunks (freeing each internal SRAM chunk).
    static uint8_t txBuf[INTERNAL_CHUNK_BYTES];
    while (audioStream.available() > 0) {
      if (!controlCommandStillActive(detectionCommandId)) {
        outStopped = true;
        break;
      }

      const size_t n = audioStream.readBytes(txBuf, sizeof(txBuf));
      if (n == 0) {
        break;
      }

      if (!writeAllStopAware(client, txBuf, n, detectionCommandId, outStopped)) {
        break;
      }

      // As progressive freeing restores internal SRAM >= 76 KB, immediately
      // unlock Core 0 control polling even before the final chunk finishes.
      if (holdingControlMutex && hasEnoughHeapForTls(true)) {
        releaseControlMutexIfHeld();
      }

      vTaskDelay(1);
    }

    // Ensure controlHttpsMutex is ALWAYS released before entering the
    // potentially long FastAPI inference wait.
    releaseControlMutexIfHeld();

    if (outStopped) {
      Serial.println("AI upload cancelled by website Stop command.");
      client.stop();
      setAiSocketActive(false);
      return false;
    }

    if (!audioStream.complete()) {
      Serial.printf(
          "AI upload incomplete (%u / %u bytes sent).\n",
          (unsigned int)audioStream.bytesConsumed(),
          (unsigned int)PCM_PAYLOAD_BYTES
      );
      client.stop();
      setAiSocketActive(false);
      return false;
    }

    // Wait non-blockingly for FastAPI response while Core 0 continues
    // polling Detect/Stop every 2.5 seconds.
    const uint32_t waitStartMs = millis();
    String statusLine;
    if (!readHttpLineNonBlocking(
            client,
            statusLine,
            waitStartMs,
            AI_RESPONSE_TIMEOUT_MS,
            detectionCommandId,
            outStopped,
            timedOut
        )) {
      if (outStopped) {
        Serial.println("AI response wait cancelled by website Stop command.");
      } else if (timedOut) {
        Serial.println("AI response timed out waiting for backend.");
      } else {
        Serial.println("AI connection closed before HTTP status line.");
      }
      client.stop();
      setAiSocketActive(false);
      return false;
    }

    // Parse "HTTP/1.x <code> ..."
    const int firstSpace = statusLine.indexOf(' ');
    if (firstSpace > 0) {
      outHttpCode = atoi(statusLine.c_str() + firstSpace + 1);
    }

    // Parse response headers.
    bool isChunked = false;
    int32_t contentLength = -1;
    String headerLine;
    while (readHttpLineNonBlocking(
        client,
        headerLine,
        waitStartMs,
        AI_RESPONSE_TIMEOUT_MS,
        detectionCommandId,
        outStopped,
        timedOut
    )) {
      if (headerLine.length() == 0) {
        break;  // Blank line ends headers.
      }
      const int colon = headerLine.indexOf(':');
      if (colon > 0) {
        String key = headerLine.substring(0, colon);
        String val = headerLine.substring(colon + 1);
        key.trim();
        key.toLowerCase();
        val.trim();

        if (key == "content-length") {
          contentLength = (int32_t)strtol(val.c_str(), nullptr, 10);
        } else if (key == "transfer-encoding") {
          String lowerVal = val;
          lowerVal.toLowerCase();
          if (lowerVal.indexOf("chunked") >= 0) {
            isChunked = true;
          }
        }
      }
    }

    if (outStopped || timedOut) {
      Serial.println(outStopped ? "AI header read cancelled by Stop." : "AI header read timed out.");
      client.stop();
      setAiSocketActive(false);
      return false;
    }

    // Parse response body (chunked, Content-Length, or EOF-delimited).
    if (isChunked) {
      while (true) {
        String sizeLine;
        if (!readHttpLineNonBlocking(
                client,
                sizeLine,
                waitStartMs,
                AI_RESPONSE_TIMEOUT_MS,
                detectionCommandId,
                outStopped,
                timedOut
            )) {
          break;
        }
        const int semi = sizeLine.indexOf(';');
        if (semi >= 0) {
          sizeLine = sizeLine.substring(0, semi);
        }
        sizeLine.trim();
        if (sizeLine.length() == 0) {
          continue;
        }

        char* endPtr = nullptr;
        const unsigned long chunkLen = strtoul(sizeLine.c_str(), &endPtr, 16);
        if (endPtr == sizeLine.c_str()) {
          Serial.println("Malformed chunked AI response size.");
          break;
        }
        if (chunkLen == 0) {
          success = true;
          break;
        }

        if (!readHttpExactBytesNonBlocking(
                client,
                outResponseBody,
                (size_t)chunkLen,
                waitStartMs,
                AI_RESPONSE_TIMEOUT_MS,
                detectionCommandId,
                outStopped,
                timedOut,
                overflow
            )) {
          break;
        }

        // Consume trailing CRLF after chunk data.
        String crlf;
        if (!readHttpLineNonBlocking(
                client,
                crlf,
                waitStartMs,
                AI_RESPONSE_TIMEOUT_MS,
                detectionCommandId,
                outStopped,
                timedOut
            )) {
          break;
        }
      }
    } else if (contentLength >= 0) {
      success = readHttpExactBytesNonBlocking(
          client,
          outResponseBody,
          (size_t)contentLength,
          waitStartMs,
          AI_RESPONSE_TIMEOUT_MS,
          detectionCommandId,
          outStopped,
          timedOut,
          overflow
      );
    } else {
      // Connection: close EOF-delimited body.
      uint8_t buf[256];
      while (true) {
        if (!controlCommandStillActive(detectionCommandId)) {
          outStopped = true;
          break;
        }
        const int avail = client.available();
        if (avail > 0) {
          const size_t want = minSize((size_t)avail, sizeof(buf));
          const int got = client.read(buf, want);
          if (got > 0) {
            if (outResponseBody.length() + (size_t)got > MAX_AI_RESPONSE_BYTES) {
              overflow = true;
              break;
            }
            appendBytesToString(outResponseBody, buf, (size_t)got);
          }
          continue;
        }
        if (!client.connected()) {
          success = true;
          break;
        }
        if ((uint32_t)(millis() - waitStartMs) >= AI_RESPONSE_TIMEOUT_MS) {
          timedOut = true;
          break;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
      }
    }

    client.stop();
    setAiSocketActive(false);
  }  // AI WiFiClientSecure fully destroyed here, freeing all TLS RAM.

  releaseControlMutexIfHeld();

  if (overflow) {
    Serial.println("AI response exceeded maximum safe buffer size.");
    return false;
  }
  if (timedOut) {
    Serial.println("AI response body timed out.");
    return false;
  }
  if (outStopped) {
    Serial.println("AI response aborted by website Stop.");
    return false;
  }

  return success;
}

static bool verifyFreshCommandBeforeAlert(const char* expectedCommandId) {
  for (int attempt = 1; attempt <= 2; attempt++) {
    if (!controlCommandStillActive(expectedCommandId)) {
      return false;
    }

    bool freshOk = false;
    pollDetectionControl(6000, &freshOk);

    if (freshOk) {
      return controlCommandStillActive(expectedCommandId);
    }

    Serial.printf(
        "Fresh pre-alert control check attempt %d/2 failed.\n",
        attempt
    );

    if (attempt < 2) {
      delay(250);
    }
  }

  return false;
}

DetectionCycleOutcome runDetectionCycle() {
  if (!microphoneReady) {
    Serial.println("Microphone unavailable.");
    alertsOff();
    return CYCLE_INVALID_AUDIO;
  }

  if (!getDetectionState()) {
    alertsOff();
    return CYCLE_STOPPED;
  }

  Serial.println();
  Serial.println("===== PEST GUARD DETECTION =====");
  Serial.printf("Piezo vibration state: %d\n", digitalRead(PIEZO_PIN));

  static PestAudioStream audioStream;
  audioStream.resetCapture();

  // -----------------------------------------------------------
  // DIAGNOSTIC-ONLY PATH (NO AI UPLOAD)
  // -----------------------------------------------------------
  if (DIAGNOSTIC_ONLY) {
    Serial.println("Diagnostic mode: microphone capture & validation only.");

    if (!audioStream.capture(nullptr)) {
      audioStream.printDiagnostics();
      const bool memErr = audioStream.hadMemoryShortage();
      const bool stopped = audioStream.wasAbortedByStop();
      audioStream.releaseCaptureBuffer();
      alertsOff();
      if (stopped) return CYCLE_STOPPED;
      return memErr ? CYCLE_MEMORY_SHORTAGE : CYCLE_INVALID_AUDIO;
    }

    const char* validationReason = nullptr;
    const bool audioValid = audioStream.validateCapturedAudio(&validationReason);

    uint8_t drainBuf[512];
    while (!audioStream.complete()) {
      if (!getDetectionState()) {
        Serial.println("Capture stopped.");
        audioStream.releaseCaptureBuffer();
        alertsOff();
        return CYCLE_STOPPED;
      }
      const int avail = audioStream.available();
      if (avail <= 0) break;
      const size_t toRead = minSize((size_t)avail, sizeof(drainBuf));
      if (audioStream.readBytes(drainBuf, toRead) == 0) break;
    }

    audioStream.printDiagnostics();
    Serial.printf(
        "Pre-upload audio integrity verdict: %s (%s)\n",
        audioValid ? "PASS" : "REJECT",
        validationReason != nullptr ? validationReason : ""
    );
    audioStream.releaseCaptureBuffer();
    Serial.println("No AI request sent.");
    alertsOff();
    return audioValid ? CYCLE_OK : CYCLE_INVALID_AUDIO;
  }

  // -----------------------------------------------------------
  // 1. VALIDATE NETWORK & ACTIVE COMMAND BEFORE RECORDING
  // -----------------------------------------------------------
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("AI skipped: Wi-Fi disconnected.");
    alertsOff();
    return CYCLE_NETWORK_ERROR;
  }

  if (controlHttpsMutex == nullptr) {
    Serial.println("Control HTTPS mutex unavailable.");
    alertsOff();
    return CYCLE_NETWORK_ERROR;
  }

  bool commandEnabled = false;
  char detectionCommandId[65] = {0};
  getDetectionSnapshot(
      commandEnabled,
      detectionCommandId,
      sizeof(detectionCommandId)
  );

  if (!commandEnabled || detectionCommandId[0] == '\0') {
    Serial.println("AI skipped: no active website Detect command.");
    alertsOff();
    return CYCLE_STOPPED;
  }

  // -----------------------------------------------------------
  // 2. CAPTURE 5 SECONDS OF PCM WITHOUT BLOCKING CONTROL POLLS
  // -----------------------------------------------------------
  if (!audioStream.capture(detectionCommandId)) {
    audioStream.printDiagnostics();
    const bool memErr = audioStream.hadMemoryShortage();
    const bool stopped = audioStream.wasAbortedByStop();
    audioStream.releaseCaptureBuffer();
    alertsOff();
    if (stopped) return CYCLE_STOPPED;
    return memErr ? CYCLE_MEMORY_SHORTAGE : CYCLE_INVALID_AUDIO;
  }

  if (!controlCommandStillActive(detectionCommandId)) {
    Serial.println("Detection stopped during audio capture.");
    audioStream.releaseCaptureBuffer();
    alertsOff();
    return CYCLE_STOPPED;
  }

  // -----------------------------------------------------------
  // 3. VALIDATE AUDIO INTEGRITY *BEFORE* UPLOADING TO BACKEND
  // -----------------------------------------------------------
  const char* integrityReason = nullptr;
  const bool audioValid = audioStream.validateCapturedAudio(&integrityReason);
  audioStream.printDiagnostics();

  if (!audioValid) {
    Serial.printf(
        "AUDIO REJECTED BEFORE UPLOAD: %s\n",
        integrityReason != nullptr ? integrityReason : "Invalid audio."
    );
    audioStream.releaseCaptureBuffer();
    alertsOff();
    return CYCLE_INVALID_AUDIO;
  }

  Serial.println("Audio integrity check PASSED. Ready for AI upload.");
  Serial.printf(
      "Free internal heap before AI upload: %u bytes (largest: %u)\n",
      (unsigned int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
      (unsigned int)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
  );

  // -----------------------------------------------------------
  // 4. STREAM VALIDATED 160,000-BYTE PCM TO AI BACKEND
  // -----------------------------------------------------------
  int httpCode = -1;
  String responseBody;
  bool stoppedDuringUpload = false;

  const bool transferOk = uploadAudioToAI(
      audioStream,
      detectionCommandId,
      httpCode,
      responseBody,
      stoppedDuringUpload
  );

  const bool audioComplete = audioStream.complete();
  audioStream.releaseCaptureBuffer();

  Serial.printf("AI HTTP response: %d\n", httpCode);
  Serial.printf(
      "Free internal heap after AI request: %u bytes\n",
      (unsigned int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
  );

  if (stoppedDuringUpload) {
    alertsOff();
    return CYCLE_STOPPED;
  }

  if (!transferOk || !audioComplete) {
    Serial.println("AI transfer incomplete or failed. Ignoring result.");
    alertsOff();
    return CYCLE_NETWORK_ERROR;
  }

  if (httpCode != HTTP_CODE_OK) {
    Serial.println("AI request unsuccessful.");
    if (!responseBody.isEmpty()) {
      Serial.println(responseBody.substring(0, minSize(responseBody.length(), 300)));
    }
    alertsOff();
    return CYCLE_NETWORK_ERROR;
  }

  // -----------------------------------------------------------
  // 5. MANDATORY FRESH WEBSITE CONTROL CHECK BEFORE ALERTS
  //    Rejects stale/outdated command IDs and failed polls.
  // -----------------------------------------------------------
  if (!verifyFreshCommandBeforeAlert(detectionCommandId)) {
    Serial.println(
        "Fresh pre-alert control verification failed, stopped, or command ID changed: alerts OFF."
    );
    alertsOff();
    return getDetectionState() ? CYCLE_NETWORK_ERROR : CYCLE_STOPPED;
  }

  // -----------------------------------------------------------
  // 6. PARSE ONLY TOP-LEVEL AI RESPONSE FIELDS
  // -----------------------------------------------------------
  JsonDocument result;
  DeserializationError jsonError = deserializeJson(result, responseBody);

  if (jsonError) {
    Serial.printf("Invalid AI JSON: %s\n", jsonError.c_str());
    alertsOff();
    return CYCLE_NETWORK_ERROR;
  }

  if (!result["status"].is<const char*>() ||
      !result["pest_verified"].is<bool>()) {
    Serial.println("AI response missing required safety fields.");
    alertsOff();
    return CYCLE_NETWORK_ERROR;
  }

  String status = result["status"] | "";
  String pest   = result["pest"] | "";
  String risk   = result["risk"] | "UNKNOWN";

  bool verified = result["pest_verified"].as<bool>();
  float confidence = result["confidence"] | 0.0f;

  status.trim();
  status.toUpperCase();

  // Never use top_predictions for hardware alerts.
  const bool accepted =
      (status == "HARMFUL_PEST") &&
      verified &&
      !pest.isEmpty();

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

  applyPestAlert(
      status,
      pest,
      risk,
      confidence,
      verified,
      detectionCommandId
  );

  // Backend already saves and broadcasts /api/ai/predict.
  Serial.println("Detection cycle complete.");
  return CYCLE_OK;
}

// =============================================================
// SECTION F: MEMORY DIAGNOSTICS, SETUP AND MAIN LOOP
// =============================================================

static void printMemoryStatus() {
  Serial.println();
  Serial.println("===== ESP32-S3 MEMORY STATUS =====");
  Serial.printf(
      "Free internal heap : %u bytes\n",
      (unsigned int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
  );
  Serial.printf(
      "Minimum free heap  : %u bytes\n",
      (unsigned int)ESP.getMinFreeHeap()
  );
  Serial.printf(
      "Largest int block  : %u bytes\n",
      (unsigned int)heap_caps_get_largest_free_block(
          MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
      )
  );
  Serial.printf("PSRAM detected     : %s\n", psramFound() ? "YES" : "NO");
  Serial.printf("Total PSRAM        : %u bytes\n", (unsigned int)ESP.getPsramSize());
  Serial.printf("Free PSRAM         : %u bytes\n", (unsigned int)ESP.getFreePsram());
  Serial.println("==================================");
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("====================================");
  Serial.println("       PEST GUARD FIELD UNIT");
  Serial.println("             ESP32-S3");
  Serial.println("====================================");

  controlHttpsMutex = xSemaphoreCreateMutex();
  alertMutex        = xSemaphoreCreateMutex();

  if (controlHttpsMutex == nullptr || alertMutex == nullptr) {
    Serial.println("FATAL: Mutex creation failed.");
    pinMode(RGB_RED_PIN, OUTPUT);
    pinMode(RGB_GREEN_PIN, OUTPUT);
    pinMode(RGB_BLUE_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    writeAlertPinsRaw(false, false, false, false);
    while (true) {
      delay(1000);
    }
  }

  setupAlertPins();

  pinMode(PIEZO_PIN, INPUT);
  Serial.println("Piezo sensor initialized.");

  // Detection always starts disabled.
  portENTER_CRITICAL(&detectionControlMux);
  detectionEnabled = false;
  memset(appliedControlCommandId, 0, sizeof(appliedControlCommandId));
  pendingAckHeartbeat = false;
  captureInProgress = false;
  captureUsesInternalRam = false;
  aiSocketActive = false;
  portEXIT_CRITICAL(&detectionControlMux);

  alertsOff();
  printMemoryStatus();

  if (setupMicrophone()) {
    Serial.println("Microphone driver ready.");
  } else {
    Serial.println("ERROR: Microphone initialization failed.");
    Serial.println("AI recording will remain disabled.");
  }

  if (!connectWiFi()) {
    Serial.println("Wi-Fi unavailable at startup. Main loop will retry.");
  }

  // Pin background control task to Core 0 (Wi-Fi core); loop() runs on Core 1.
  const BaseType_t taskResult = xTaskCreatePinnedToCore(
      deviceControlTask,
      "PestGuardControl",
      8192,
      nullptr,
      1,
      nullptr,
      0
  );

  if (taskResult == pdPASS) {
    controlTaskRunning = true;
    Serial.println("Website control task started on Core 0.");
  } else {
    controlTaskRunning = false;
    Serial.println("ERROR: Website control task failed.");
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
  Serial.println("Waiting for website Detect command...");
}

void loop() {
  static uint32_t lastWiFiRetryMs   = 0;
  static uint32_t lastMemoryPrintMs = 0;
  static uint32_t lastIdlePrintMs   = 0;

  const uint32_t now = millis();

  if (!microphoneReady || !controlTaskRunning) {
    alertsOff();
    delay(1000);
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    alertsOff();
    if (lastWiFiRetryMs == 0 ||
        (uint32_t)(now - lastWiFiRetryMs) >= 15000UL) {
      lastWiFiRetryMs = now;
      Serial.println();
      Serial.println("Wi-Fi disconnected.");
      connectWiFi();
    }
    delay(250);
    return;
  }

  if (lastMemoryPrintMs == 0 ||
      (uint32_t)(now - lastMemoryPrintMs) >= 30000UL) {
    lastMemoryPrintMs = now;
    printMemoryStatus();
  }

  if (!getDetectionState()) {
    alertsOff();
    if (lastIdlePrintMs == 0 ||
        (uint32_t)(now - lastIdlePrintMs) >= 10000UL) {
      lastIdlePrintMs = now;
      Serial.println();
      Serial.println("Detection OFF. Waiting for website...");
    }
    delay(250);
    return;
  }

  Serial.println();
  Serial.println("====================================");
  Serial.println("         DETECTION ENABLED");
  Serial.println("====================================");

  const DetectionCycleOutcome outcome = runDetectionCycle();

  if (!getDetectionState() || outcome == CYCLE_STOPPED) {
    alertsOff();
    Serial.println("Detection stopped. Alerts OFF.");
    delay(250);
    return;
  }

  if (outcome == CYCLE_MEMORY_SHORTAGE) {
    Serial.println("Backing off 5s due to internal SRAM shortage.");
    stopAwareDelayMs(5000);
  } else if (outcome == CYCLE_INVALID_AUDIO) {
    Serial.println("Backing off 1.5s after rejected audio.");
    stopAwareDelayMs(1500);
  } else if (outcome == CYCLE_NETWORK_ERROR) {
    Serial.println("Backing off 2s after network error.");
    stopAwareDelayMs(2000);
  } else {
    Serial.println("Detection cycle finished.");
    stopAwareDelayMs(500);
  }
}