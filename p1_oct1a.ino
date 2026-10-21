#include <WiFi.h>

#include <HTTPClient.h>

#include <WiFiClientSecure.h>

#include <driver/i2s.h>

#include <esp_heap_caps.h>
#include <math.h>

// =====================================================

// Wi-Fi

// =====================================================

const char* ssid = "Nest living 1st_2.4G";

const char* password = "one@12340";

// =====================================================

// Backend URLs

// =====================================================

const char* aiURL =

  "https://pest-guard-1q36.onrender.com/api/ai/predict";

// PEST_GUARD_DETECTION_CONTROL_URL

const char* controlURL =

  "https://pest-guard-1q36.onrender.com/api/devices/FIELD-UNIT-01/detection-control";

const char* heartbeatURL =

  "https://pest-guard-1q36.onrender.com/api/devices/FIELD-UNIT-01/heartbeat";

// The field unit starts stopped until the website enables detection.

bool detectionEnabled = false;

unsigned long lastControlPollMs = 0;

const unsigned long CONTROL_POLL_INTERVAL_MS = 2500;

const unsigned long DEVICE_HEARTBEAT_INTERVAL_MS = 20000;

// =====================================================

// Device

// =====================================================

const char* deviceID = "FIELD-UNIT-01";

// =====================================================

void sendDeviceHeartbeat() {

  if (WiFi.status() != WL_CONNECTED) {

    return;

  }

  WiFiClientSecure heartbeatClient;

  heartbeatClient.setInsecure();

  HTTPClient heartbeatHttp;

  heartbeatHttp.setTimeout(8000);

  if (!heartbeatHttp.begin(heartbeatClient, heartbeatURL)) {

    Serial.println("Device heartbeat connection setup failed.");

    return;

  }

  heartbeatHttp.addHeader("Content-Type", "application/json");

  int heartbeatCode = heartbeatHttp.POST(

    "{\"status\":\"ONLINE\",\"connection\":\"CONNECTED\"}"

  );

  if (heartbeatCode >= 200 && heartbeatCode < 300) {

    Serial.printf("Device heartbeat accepted: HTTP %d\n", heartbeatCode);

  } else if (heartbeatCode > 0) {

    Serial.printf("Device heartbeat rejected: HTTP %d\n", heartbeatCode);

  } else {

    Serial.printf(

      "Device heartbeat failed: %s\n",

      heartbeatHttp.errorToString(heartbeatCode).c_str()

    );

  }

  heartbeatHttp.end();

}

void deviceHeartbeatTask(void*) {

  for (;;) {

    sendDeviceHeartbeat();

    vTaskDelay(pdMS_TO_TICKS(DEVICE_HEARTBEAT_INTERVAL_MS));

  }

}

// INMP441

// =====================================================

#define I2S_PORT I2S_NUM_0

#define I2S_SCK 12

#define I2S_WS  11

#define I2S_SD  10

// =====================================================

// Piezo

// =====================================================

#define PIEZO_PIN 4

// =====================================================

// Audio

// =====================================================

#define SAMPLE_RATE 16000

#define DURATION 5

#define TOTAL_SAMPLES (SAMPLE_RATE * DURATION)

// One AI prediction per sound event.
// A new event is permitted only after consecutive quiet 5-second windows.
// Tune AUDIO_ACTIVITY_RMS_THRESHOLD from the serial RMS readings if needed.
const double AUDIO_ACTIVITY_RMS_THRESHOLD = 250.0;
const uint8_t QUIET_WINDOWS_TO_REARM = 2;
const bool DIAGNOSTIC_ONLY = false;
bool soundEventLocked = false;
uint8_t quietWindowsAfterEvent = 0;

// =====================================================

// Audio buffer in PSRAM

// =====================================================

int32_t* audioBuffer;
int16_t* pcmBuffer;

// =====================================================
// RGB + active buzzer alerts
// Assumes a common-cathode RGB module (HIGH = ON).
// Confirm GPIOs match your physical wiring.
// =====================================================
// Confirmed physical wiring
#define RGB_RED_PIN   7
#define RGB_GREEN_PIN 15
#define RGB_BLUE_PIN  16
#define BUZZER_PIN    5

void setRGB(bool red, bool green, bool blue) {
  digitalWrite(RGB_RED_PIN, red ? HIGH : LOW);
  digitalWrite(RGB_GREEN_PIN, green ? HIGH : LOW);
  digitalWrite(RGB_BLUE_PIN, blue ? HIGH : LOW);
}

void beepBuzzer(uint8_t count, uint16_t beepMs = 500, uint16_t gapMs = 200) {
  for (uint8_t i = 0; i < count; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(beepMs);
    digitalWrite(BUZZER_PIN, LOW);

    if (i + 1 < count) {
      delay(gapMs);
    }
  }
}
void initializeAlerts() {
  pinMode(RGB_RED_PIN, OUTPUT);
  pinMode(RGB_GREEN_PIN, OUTPUT);
  pinMode(RGB_BLUE_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  setRGB(false, false, false);
  setRGB(false, true, false);
  beepBuzzer(1, 120, 100);
  delay(250);
  setRGB(false, false, false);
  Serial.println("RGB module and active buzzer ready.");
}

bool isNoDetectionStatus(String status) {
  status.trim();
  status.toUpperCase();
  return status == "NO DETECTION" || status == "NO_DETECTION" ||
         status == "NO PEST DETECTED" || status == "NO_PEST_DETECTED" ||
         status == "NOT_DETECTED" || status == "NOT DETECTED" ||
         status == "NONE" || status == "NO_PEST" || status == "NO PEST";
}


void updatePestAlerts(String risk, String status, String pest,
                      float confidence) {
  risk.trim();
  risk.toUpperCase();
  status.trim();
  status.toUpperCase();
  pest.trim();
  pest.toUpperCase();

  bool noPestName = pest.length() == 0 || pest == "NONE" ||
                    pest == "NO PEST" || pest == "NO_PEST" ||
                    pest == "NO DETECTION" || pest == "NO_DETECTION" ||
                    pest == "NOT DETECTED" || pest == "NOT_DETECTED";

  if (noPestName || isNoDetectionStatus(status) ||
      !isfinite(confidence) || confidence < 0.40f ||
      confidence > 1.0f) {
    setRGB(false, false, false);
    digitalWrite(BUZZER_PIN, LOW);
    Serial.println("Uncertain/no detection: alerts OFF");
    return;
  }

  if (confidence < 0.70f) {
    setRGB(false, false, true);
    digitalWrite(BUZZER_PIN, LOW);
    Serial.println("Possible match: BLUE, no buzzer");
    return;
  }

  if (risk == "LOW") {
    setRGB(false, true, false);
    Serial.println("Supported match, LOW risk: GREEN + 1 beep");
    beepBuzzer(1);
  } else if (risk == "MEDIUM" || risk == "MODERATE") {
    setRGB(true, true, false);
    Serial.println("Supported match, MEDIUM risk: YELLOW + 2 beeps");
    beepBuzzer(2);
  } else if (risk == "HIGH" || risk == "CRITICAL" || risk == "SEVERE") {
    setRGB(true, false, false);
    Serial.println("Supported match, HIGH risk: RED + 3 beeps");
    beepBuzzer(3);
  } else {
    setRGB(false, false, false);
    digitalWrite(BUZZER_PIN, LOW);
    Serial.println("Unknown risk: alerts OFF");
  }
}



// =====================================================

// SETUP

// =====================================================

void setup() {

  Serial.begin(115200);

  delay(1000);
  initializeAlerts();

  Serial.println();

  Serial.println("====================================");

  Serial.println("       PEST GUARD FIELD UNIT");

  Serial.println("====================================");

  // ===================================================

  // PSRAM

  // ===================================================

  if (!psramFound()) {

    Serial.println("ERROR: PSRAM NOT FOUND!");

    return;

  }

  Serial.println("PSRAM detected.");

  audioBuffer =

    (int32_t*)ps_malloc(

      TOTAL_SAMPLES * sizeof(int32_t)

    );

  if (audioBuffer == NULL) {

    Serial.println(

      "ERROR: AUDIO BUFFER ALLOCATION FAILED!"

    );

    return;

  }

  Serial.println("Audio buffer allocated.");

  pcmBuffer = (int16_t*)ps_malloc(TOTAL_SAMPLES * sizeof(int16_t));
  if (pcmBuffer == NULL) {
    Serial.println("ERROR: PCM BUFFER ALLOCATION FAILED!");
    return;
  }
  Serial.println("Compact PCM buffer allocated.");

  // ===================================================

  // Piezo

  // ===================================================

  pinMode(PIEZO_PIN, INPUT);

  Serial.println("Piezo sensor ready.");

  // ===================================================

  // Wi-Fi

  // ===================================================

  Serial.println();

  Serial.println("Connecting to Wi-Fi...");

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {

    delay(500);

    Serial.print(".");

  }

  Serial.println();

  Serial.println("Wi-Fi CONNECTED!");

  Serial.print("ESP32 IP: ");

  Serial.println(WiFi.localIP());

  // ===================================================

  // I2S CONFIGURATION

  // ===================================================

  i2s_config_t i2s_config = {

    .mode = (i2s_mode_t)(

      I2S_MODE_MASTER |

      I2S_MODE_RX

    ),

    .sample_rate = SAMPLE_RATE,

    .bits_per_sample =

      I2S_BITS_PER_SAMPLE_32BIT,

    .channel_format =

      I2S_CHANNEL_FMT_ONLY_LEFT,

    .communication_format =

      I2S_COMM_FORMAT_STAND_I2S,

    .intr_alloc_flags =

      ESP_INTR_FLAG_LEVEL1,

    .dma_buf_count = 8,

    .dma_buf_len = 256,

    .use_apll = false,

    .tx_desc_auto_clear = false,

    .fixed_mclk = 0

  };

  i2s_pin_config_t pin_config = {

    .bck_io_num = I2S_SCK,

    .ws_io_num = I2S_WS,

    .data_out_num =

      I2S_PIN_NO_CHANGE,

    .data_in_num = I2S_SD

  };

  i2s_driver_install(

    I2S_PORT,

    &i2s_config,

    0,

    NULL

  );

  i2s_set_pin(

    I2S_PORT,

    &pin_config

  );

  i2s_zero_dma_buffer(I2S_PORT);

  Serial.println("INMP441 ready.");

  BaseType_t heartbeatTaskResult = xTaskCreate(

    deviceHeartbeatTask,

    "deviceHeartbeat",

    8192,

    nullptr,

    1,

    nullptr

  );

  if (heartbeatTaskResult != pdPASS) {

    Serial.println("Unable to start device heartbeat task.");

  }

  // ===================================================

}

void runDetectionCycle() {

  // Initial Piezo state

  // ===================================================

  Serial.println();

  Serial.print("Initial vibration: ");

  Serial.println(

    digitalRead(PIEZO_PIN)

  );

  Serial.println();
  Serial.println("Starting live detection cycle immediately...");

  // ===================================================

  // Read Piezo

  // ===================================================

  int vibration =

    digitalRead(PIEZO_PIN);

  Serial.println();

  Serial.print("Vibration detected: ");

  Serial.println(vibration);

  // ===================================================

  // RECORD AUDIO WITH I2S READ VALIDATION

  // ===================================================

  Serial.println();

  Serial.println("Recording 5 seconds...");

  size_t totalCaptured = 0;

  size_t totalBytesRead = 0;

  uint32_t failedReads = 0;

  while (totalCaptured < TOTAL_SAMPLES) {

    size_t bytesRead = 0;

    size_t remaining = TOTAL_SAMPLES - totalCaptured;

    size_t samplesToRead = min((size_t)256, remaining);

    size_t requestedBytes = samplesToRead * sizeof(int32_t);

    esp_err_t result = i2s_read(

      I2S_PORT,

      audioBuffer + totalCaptured,

      requestedBytes,

      &bytesRead,

      portMAX_DELAY

    );

    if (result != ESP_OK) {

      failedReads++;

      Serial.printf("I2S read error: %d\n", result);

      continue;

    }

    if (bytesRead == 0 || bytesRead % sizeof(int32_t) != 0) {

      failedReads++;

      Serial.printf("Invalid I2S byte count: %u\n",

                    (unsigned int)bytesRead);

      continue;

    }

    size_t samplesRead = bytesRead / sizeof(int32_t);

    if (samplesRead > remaining) {

      Serial.println("ERROR: More samples returned than requested.");

      break;

    }

    totalCaptured += samplesRead;

    totalBytesRead += bytesRead;

  }

  Serial.println();

  Serial.println("Recording complete.");

  Serial.printf("Samples captured: %u / %u\n",

                (unsigned int)totalCaptured,

                (unsigned int)TOTAL_SAMPLES);

  Serial.printf("Bytes captured: %u\n",

                (unsigned int)totalBytesRead);

  Serial.printf("Failed reads: %u\n",

                (unsigned int)failedReads);

  if (totalCaptured != TOTAL_SAMPLES) {

    Serial.println("ERROR: Recording incomplete. Stopping this test.");

    return;

  }

  Serial.println("I2S capture count verified.");

int16_t sampleMin = 32767;

int16_t sampleMax = -32768;

double sumSquares = 0.0;

uint32_t zeroSamples = 0;

for (size_t i = 0; i < TOTAL_SAMPLES; i++) {

  int16_t sample = (int16_t)(audioBuffer[i] >> 16);
  pcmBuffer[i] = sample;

  if (sample < sampleMin) sampleMin = sample;

  if (sample > sampleMax) sampleMax = sample;

  sumSquares += (double)sample * sample;

  if (sample == 0) zeroSamples++;

}

double rms = sqrt(sumSquares / TOTAL_SAMPLES);

double zeroPercent = 100.0 * zeroSamples / TOTAL_SAMPLES;

Serial.println("----- MICROPHONE SIGNAL CHECK -----");

Serial.printf("Minimum sample: %d\n", sampleMin);

Serial.printf("Maximum sample: %d\n", sampleMax);

Serial.printf("RMS level: %.2f\n", rms);

Serial.printf("Zero samples: %u (%.2f%%)\n",

              (unsigned int)zeroSamples, zeroPercent);

Serial.println("-----------------------------------");

  if (DIAGNOSTIC_ONLY) {
    Serial.println("DIAGNOSTIC ONLY: no AI request sent.");
    return;
  }

  // Suppress silent windows and prevent repeat predictions from one continuing sound.
  const bool audioActive = rms >= AUDIO_ACTIVITY_RMS_THRESHOLD;

  if (soundEventLocked) {
    if (audioActive) {
      quietWindowsAfterEvent = 0;
      Serial.printf(
        "Sound event remains active (RMS %.2f). Suppressing another AI prediction.\n",
        rms
      );
    } else {
      quietWindowsAfterEvent++;
      Serial.printf(
        "Quiet window %u/%u (RMS %.2f).\n",
        (unsigned int)quietWindowsAfterEvent,
        (unsigned int)QUIET_WINDOWS_TO_REARM,
        rms
      );

      if (quietWindowsAfterEvent >= QUIET_WINDOWS_TO_REARM) {
        soundEventLocked = false;
        quietWindowsAfterEvent = 0;
        Serial.println("Silence confirmed. Ready for the next sound event.");
      }
    }

    Serial.println("Skipping AI request for this audio window.");
    return;
  }

  if (!audioActive) {
    Serial.printf(
      "Audio is below the activity threshold (RMS %.2f < %.2f). No AI request sent.\n",
      rms,
      AUDIO_ACTIVITY_RMS_THRESHOLD
    );
    return;
  }

  // Send signed 16-bit little-endian PCM directly. The backend accepts
  // application/octet-stream, avoiding a huge JSON array of 80,000 numbers.
  Serial.println();
  Serial.println("Preparing compact PCM audio...");
  const size_t pcmBytes = TOTAL_SAMPLES * sizeof(int16_t);
  Serial.printf("Binary PCM payload size: %u bytes\n", (unsigned int)pcmBytes);

  // ===================================================

  // SEND AUDIO TO CNN V3

  // ===================================================

  Serial.println();

  Serial.println("Sending compact audio to AI backend...");

  Serial.println("Please wait...");

  WiFiClientSecure aiClient;

  aiClient.setInsecure();

  HTTPClient aiHttp;

  aiHttp.setTimeout(120000);

  if (!aiHttp.begin(

        aiClient,

        aiURL

      )) {

    Serial.println(

      "ERROR: AI HTTP connection failed!"

    );

    return;

  }

  aiHttp.addHeader(
    "Content-Type",
    "application/octet-stream"
  );

  int aiCode = aiHttp.POST(
    (uint8_t*)pcmBuffer,
    pcmBytes
  );

  Serial.println();

  Serial.print(

    "AI HTTP Response Code: "

  );

  Serial.println(aiCode);

  // ===================================================

  // IMPORTANT:

  // READ THE RESPONSE ONLY ONCE

  // ===================================================

  String aiResponse = "";

  if (aiCode > 0) {

    aiResponse =

      aiHttp.getString();

    Serial.println();

    Serial.println("====================================");

    Serial.println("             AI PREDICTION RESULT");

    Serial.println("====================================");

    Serial.println(aiResponse);

    Serial.println("====================================");

  } else {

    Serial.print(

      "AI request failed: "

    );

    Serial.println(

      aiHttp.errorToString(aiCode)

    );

    aiHttp.end();

    return;

  }

  aiHttp.end();

  if (aiCode >= 200 && aiCode < 300) {
    soundEventLocked = true;
    quietWindowsAfterEvent = 0;
    Serial.println(
      "Sound event handled. Further predictions paused until two quiet windows are detected."
    );
  }

  // ===================================================

  // PARSE AI RESPONSE

  // ===================================================

  String status = "UNKNOWN";

  String pest = "";

  String risk = "UNKNOWN";

  float confidence = 0.0;

  int start;

  int end;

  // ---------------------------------------------------

  // STATUS

  // ---------------------------------------------------

  start =

    aiResponse.indexOf("\"status\":\"");

  if (start >= 0) {

    start += 10;

    end =

      aiResponse.indexOf(

        "\"",

        start

      );

    if (end >= 0) {

      status =

        aiResponse.substring(

          start,

          end

        );

    }

  }

  // ---------------------------------------------------

  // PEST

  // ---------------------------------------------------

  start =

    aiResponse.indexOf("\"pest\":\"");

  if (start >= 0) {

    start += 8;

    end =

      aiResponse.indexOf(

        "\"",

        start

      );

    if (end >= 0) {

      pest =

        aiResponse.substring(

          start,

          end

        );

    }

  }

  // ---------------------------------------------------

  // CONFIDENCE

  // ---------------------------------------------------

  start =

    aiResponse.indexOf(

      "\"confidence\":"

    );

  if (start >= 0) {

    start += 13;

    end =

      aiResponse.indexOf(

        ",",

        start

      );

    if (end < 0) {

      end =

        aiResponse.indexOf(

          "}",

          start

        );

    }

    if (end >= 0) {

      confidence =

        aiResponse.substring(

          start,

          end

        ).toFloat();

    }

  }

  // ---------------------------------------------------

  // RISK

  // ---------------------------------------------------

  start =

    aiResponse.indexOf("\"risk\":\"");

  if (start >= 0) {

    start += 8;

    end =

      aiResponse.indexOf(

        "\"",

        start

      );

    if (end >= 0) {

      risk =

        aiResponse.substring(

          start,

          end

        );

    }

  }

  // ===================================================

  // DISPLAY PARSED RESULT

  // ===================================================

  Serial.println();

  Serial.println("====================================");

  Serial.println("        PARSED AI RESULT");

  Serial.println("====================================");

  Serial.print("Status: ");

  Serial.println(status);

  Serial.print("Pest: ");

  Serial.println(pest);

  Serial.print("Confidence: ");

  Serial.println(confidence, 6);

  Serial.print("Risk: ");

  Serial.println(risk);

  Serial.print("Vibration: ");

  Serial.println(vibration);

  Serial.println("====================================");

  // ===================================================

  // Apply alert pattern from the parsed AI response.
  updatePestAlerts(risk, status, pest, confidence);

  // /api/ai/predict already persists and broadcasts this unconfirmed prediction.
  // Do not POST the same event to /api/device/detection again: that creates a
  // duplicate history row and may overwrite the resolved catalogue risk.
  Serial.println();
  Serial.println("AI prediction saved and broadcast by backend; duplicate POST skipped.");


  // ===================================================

  // FREE AUDIO BUFFER

  // ===================================================

  // ===================================================

  // COMPLETE

  // ===================================================

  Serial.println();

  Serial.println("====================================");

  Serial.println(

    "     FULL PEST GUARD TEST COMPLETE"

  );

  Serial.println("====================================");

}

// =====================================================

// LOOP

// =====================================================

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

    int keyPosition = body.indexOf("\"enabled\"");

    int colonPosition = keyPosition >= 0 ? body.indexOf(':', keyPosition) : -1;

    if (colonPosition >= 0) {

      String value = body.substring(colonPosition + 1);

      value.trim();

      detectionEnabled = value.startsWith("true");

    } else {

      detectionEnabled = false;

    }

  } else {

    Serial.printf(

      "Control HTTP error: %d (%s) | WiFi RSSI: %d dBm | Free heap: %u bytes\n",

      controlCode,

      controlHttp.errorToString(controlCode).c_str(),

      WiFi.RSSI(),

      ESP.getFreeHeap()

    );

    detectionEnabled = false;

  }

  controlHttp.end();

  if (previousState != detectionEnabled) {

    if (detectionEnabled) {
      // A new Detect session starts ready to recognize its first sound event.
      soundEventLocked = false;
      quietWindowsAfterEvent = 0;
    }

    Serial.println(detectionEnabled

      ? "Remote command: DETECT enabled"

      : "Remote command: STOP detection");

  }

  return detectionEnabled;

}

void loop() {

  if (audioBuffer == NULL || pcmBuffer == NULL) {
    Serial.println("Audio/PCM buffer unavailable; retrying in 5 seconds.");

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