#include <WiFi.h>

#include <HTTPClient.h>

#include <WiFiClientSecure.h>

#include <driver/i2s.h>
#include <esp_heap_caps.h>
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



const char* detectionURL =

  "https://pest-guard-1q36.onrender.com/api/device/detection";

// =====================================================

// Device

// =====================================================

const char* deviceID = "FIELD-UNIT-01";

// =====================================================

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

// =====================================================

// Audio buffer in PSRAM

// =====================================================



int32_t* audioBuffer;



// =====================================================

// SETUP

// =====================================================



void setup() {



  Serial.begin(115200);

  delay(1000);



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



  // ===================================================

  // Countdown

  // ===================================================



  Serial.println();

  Serial.println("Starting detection...");



  Serial.println("3...");

  delay(1000);



  Serial.println("2...");

  delay(1000);



  Serial.println("1...");

  delay(1000);



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



  // ===================================================

  // CREATE JSON AUDIO

  // ===================================================



  Serial.println();

  Serial.println("Preparing audio...");



  String json;



  json.reserve(900000);



  json = "{\"audio\":[";



  for (int i = 0; i < TOTAL_SAMPLES; i++) {



    int16_t sample =

      (int16_t)(audioBuffer[i] >> 16);



    json += String(sample);



    if (i < TOTAL_SAMPLES - 1) {



      json += ",";

    }

  }



  json += "]}";



  Serial.print("Payload size: ");



  Serial.println(json.length());



  // ===================================================

  // SEND AUDIO TO CNN V3

  // ===================================================



  Serial.println();

  Serial.println("Sending to CNN V3...");

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

    "application/json"

  );



  int aiCode =

    aiHttp.POST(json);



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

    Serial.println("             CNN V3 RESULT");

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



  // ===================================================

  // PARSE AI RESPONSE

  // ===================================================



  String status = "UNKNOWN";

  String pest = "";

  String risk = "LOW";



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

  // CREATE DATABASE JSON

  // ===================================================



  String detectionJson;



  detectionJson =
    "{\"device_id\":\"" +
    String(deviceID) +
    "\","
    "\"status\":\"" +
    status +
    "\","
    "\"pest\":\"" +
    pest +
    "\","
    "\"confidence\":" +
    String(confidence, 6) +
    ","
    "\"risk\":\"" +
    risk +
    "\"}";



  Serial.println();

  Serial.println("Detection JSON:");



  Serial.println(detectionJson);



  // ===================================================

  // SEND DETECTION TO DATABASE

  // ===================================================



  Serial.println();

  Serial.println(

    "Sending detection to database..."

  );



  WiFiClientSecure detectionClient;



  detectionClient.setInsecure();



  HTTPClient detectionHttp;



  detectionHttp.setTimeout(60000);



  if (!detectionHttp.begin(

        detectionClient,

        detectionURL

      )) {



    Serial.println(

      "ERROR: Detection API connection failed!"

    );






    return;

  }



  detectionHttp.addHeader(

    "Content-Type",

    "application/json"

  );



  int detectionCode =

    detectionHttp.POST(

      detectionJson

    );



  Serial.println();



  Serial.print(

    "Detection API Response: "

  );



  Serial.println(detectionCode);



  if (detectionCode > 0) {



    String detectionResponse =

      detectionHttp.getString();



    Serial.println();



    Serial.println(

      "Database Response:"

    );



    Serial.println(

      detectionResponse

    );



  } else {



    Serial.print(

      "Detection request failed: "

    );



    Serial.println(

      detectionHttp.errorToString(

        detectionCode

      )

    );

  }



  detectionHttp.end();



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



void loop() {
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

  runDetectionCycle();
  Serial.println("Next detection cycle starts in 2 seconds...");
  delay(2000);
}
