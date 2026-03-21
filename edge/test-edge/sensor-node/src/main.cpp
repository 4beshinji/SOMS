/**
 * Sensor Node - XIAO ESP32-S3 + BME680
 *
 * Features:
 * - BME680 environmental data (temperature, humidity, pressure, gas)
 * - Wi-Fi/MQTT connection
 * - Per-channel telemetry compatible with WorldModel
 * - MCP tool support (JSON-RPC 2.0) for get_status
 */

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include "esp_wifi.h"

// ==================== Configuration ====================
#if __has_include("generated_config.h")
#include "generated_config.h"
#endif

#ifndef CFG_WIFI_SSID
#define CFG_WIFI_SSID "YOUR_WIFI_SSID"
#endif
#ifndef CFG_WIFI_PASS
#define CFG_WIFI_PASS "YOUR_WIFI_PASSWORD"
#endif
#ifndef CFG_MQTT_SERVER
#define CFG_MQTT_SERVER "192.168.128.161"
#endif
#ifndef CFG_MQTT_PORT
#define CFG_MQTT_PORT 1883
#endif
#ifndef CFG_MQTT_USER
#define CFG_MQTT_USER ""
#endif
#ifndef CFG_MQTT_PASS
#define CFG_MQTT_PASS ""
#endif
#ifndef CFG_DEVICE_ID
#define CFG_DEVICE_ID "sensor_node_01"
#endif
#ifndef CFG_ZONE
#define CFG_ZONE "main"
#endif

const char* WIFI_SSID = CFG_WIFI_SSID;
const char* WIFI_PASS = CFG_WIFI_PASS;
const char* MQTT_SERVER = CFG_MQTT_SERVER;
const int MQTT_PORT = CFG_MQTT_PORT;
const char* MQTT_USER = CFG_MQTT_USER;
const char* MQTT_PASS_STR = CFG_MQTT_PASS;
const char* DEVICE_ID = CFG_DEVICE_ID;
const char* ZONE = CFG_ZONE;

// WiFi CSI configuration
#ifndef CFG_CSI_ENABLED
#define CFG_CSI_ENABLED 0
#endif
#define CSI_PUBLISH_INTERVAL_MS 100   // 10 Hz publish rate
#define CSI_SUBCARRIER_COUNT    52    // LLTF 20 MHz

// MQTT topics (built dynamically in setup())
char topicPrefix[128];
char topicMcpRequest[128];
#if CFG_CSI_ENABLED
char topicCSI[128];
#endif

// I2C pins (XIAO ESP32-S3)
#define SDA_PIN 5
#define SCL_PIN 6

// BME680 I2C address
#define BME680_I2C_ADDR 0x76

// Telemetry interval (milliseconds)
#define TELEMETRY_INTERVAL 10000  // 10 seconds

// ==================== Globals ====================
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
Adafruit_BME680 bme;

unsigned long lastTelemetry = 0;
unsigned long lastStatus = 0;

// ==================== WiFi CSI ====================
#if CFG_CSI_ENABLED
static int8_t csi_raw_buf[CSI_SUBCARRIER_COUNT * 2];
static volatile bool csi_data_ready = false;
static portMUX_TYPE csi_mux = portMUX_INITIALIZER_UNLOCKED;
static unsigned long lastCSI = 0;

static void wifi_csi_cb(void* ctx, wifi_csi_info_t* info) {
  if (!info || !info->buf) return;
  int offset = info->first_word_invalid ? 4 : 0;
  int available = (info->len - offset) / 2;
  if (available < CSI_SUBCARRIER_COUNT) return;

  portENTER_CRITICAL(&csi_mux);
  memcpy((void*)csi_raw_buf, info->buf + offset, CSI_SUBCARRIER_COUNT * 2);
  csi_data_ready = true;
  portEXIT_CRITICAL(&csi_mux);
}

void setupCSI() {
  wifi_csi_config_t cfg;
  memset(&cfg, 0, sizeof(cfg));
  cfg.lltf_en = true;
  cfg.htltf_en = true;
  cfg.stbc_htltf2_en = true;
  cfg.ltf_merge_en = true;
  cfg.channel_filter_en = true;
  cfg.manu_scale = false;
  cfg.shift = false;

  ESP_ERROR_CHECK(esp_wifi_set_csi_config(&cfg));
  ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_cb, NULL));
  ESP_ERROR_CHECK(esp_wifi_set_csi(true));
  Serial.printf("WiFi CSI enabled → %s (10 Hz)\n", topicCSI);
}

void publishCSI() {
  int8_t local_buf[CSI_SUBCARRIER_COUNT * 2];

  portENTER_CRITICAL(&csi_mux);
  memcpy(local_buf, (void*)csi_raw_buf, sizeof(local_buf));
  csi_data_ready = false;
  portEXIT_CRITICAL(&csi_mux);

  JsonDocument doc;
  JsonArray amp = doc["amplitudes"].to<JsonArray>();
  for (int i = 0; i < CSI_SUBCARRIER_COUNT; i++) {
    float re = (float)local_buf[2 * i];
    float im = (float)local_buf[2 * i + 1];
    amp.add(sqrtf(re * re + im * im));
  }

  String output;
  serializeJson(doc, output);
  mqtt.publish(topicCSI, output.c_str());
}
#endif

// Forward declarations
void mqttCallback(char* topic, byte* payload, unsigned int length);
void handleToolCall(JsonDocument& doc);
void readAndPublishSensors();
void publishStatus();

// ==================== Setup ====================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=== Sensor Node Starting ===");

  // Build MQTT topics dynamically
  snprintf(topicPrefix, sizeof(topicPrefix), "office/%s/sensor/%s", ZONE, DEVICE_ID);
  snprintf(topicMcpRequest, sizeof(topicMcpRequest), "mcp/%s/request/call_tool", DEVICE_ID);
#if CFG_CSI_ENABLED
  snprintf(topicCSI, sizeof(topicCSI), "office/%s/wifi-csi/%s", ZONE, DEVICE_ID);
#endif

  // I2C init
  Wire.begin(SDA_PIN, SCL_PIN);

  // BME680 init
  Serial.println("Initializing BME680...");
  if (!bme.begin(BME680_I2C_ADDR, &Wire)) {
    Serial.println("Could not find BME680! Check wiring (0x76 or 0x77)");
    while (1) delay(1000);
  }
  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme.setGasHeater(320, 150);
  Serial.println("BME680 initialized");

  // WiFi
  Serial.print("Connecting to WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.setMinSecurity(WIFI_AUTH_WPA_PSK);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWiFi connected: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nWiFi failed!");
    ESP.restart();
  }

  // MQTT
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(2048);

  Serial.print("Connecting to MQTT...");
  attempts = 0;
  while (!mqtt.connected() && attempts < 5) {
    bool connected;
    if (strlen(MQTT_USER) > 0) {
      connected = mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS_STR);
    } else {
      connected = mqtt.connect(DEVICE_ID);
    }
    if (connected) {
      mqtt.subscribe(topicMcpRequest);
      Serial.printf("\nMQTT connected, subscribed: %s\n", topicMcpRequest);
    } else {
      Serial.print(".");
      delay(2000);
      attempts++;
    }
  }
  if (!mqtt.connected()) {
    Serial.println("\nMQTT connection failed!");
  }

  // WiFi CSI collection (after WiFi + MQTT are up)
#if CFG_CSI_ENABLED
  setupCSI();
#endif

  Serial.println("=== Initialization Complete ===\n");
  publishStatus();
}

// ==================== Main Loop ====================
void loop() {
  // MQTT reconnect
  if (!mqtt.connected()) {
    Serial.println("MQTT disconnected, reconnecting...");
    bool connected;
    if (strlen(MQTT_USER) > 0) {
      connected = mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS_STR);
    } else {
      connected = mqtt.connect(DEVICE_ID);
    }
    if (connected) {
      mqtt.subscribe(topicMcpRequest);
      Serial.println("MQTT reconnected");
    } else {
      delay(2000);
      return;
    }
  }
  mqtt.loop();

  // Periodic telemetry
  if (millis() - lastTelemetry > TELEMETRY_INTERVAL) {
    readAndPublishSensors();
    lastTelemetry = millis();
  }

  // Periodic status (every 30s)
  if (millis() - lastStatus > 30000) {
    publishStatus();
    lastStatus = millis();
  }

  // WiFi CSI publish (10 Hz)
#if CFG_CSI_ENABLED
  if (csi_data_ready && millis() - lastCSI >= CSI_PUBLISH_INTERVAL_MS) {
    publishCSI();
    lastCSI = millis();
  }
#endif

  delay(10);
}

// ==================== MQTT Callback ====================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error) {
    Serial.printf("JSON parse error: %s\n", error.c_str());
    return;
  }

  // MCP tool call
  if (strcmp(topic, topicMcpRequest) == 0) {
    handleToolCall(doc);
  }
}

// ==================== MCP Tool Handler ====================
void handleToolCall(JsonDocument& doc) {
  const char* reqId = doc["id"] | "unknown";
  const char* method = doc["method"] | "";

  if (strcmp(method, "call_tool") != 0) return;

  const char* toolName = doc["params"]["name"] | "";
  Serial.printf("Tool call: %s (id=%s)\n", toolName, reqId);

  // Build response
  JsonDocument response;
  response["jsonrpc"] = "2.0";
  response["id"] = reqId;

  if (strcmp(toolName, "get_status") == 0) {
    // Read sensors and return
    if (bme.performReading()) {
      JsonObject result = response["result"].to<JsonObject>();
      result["temperature"] = bme.temperature;
      result["humidity"] = bme.humidity;
      result["pressure"] = bme.pressure / 100.0;
      result["gas_resistance"] = bme.gas_resistance / 1000.0;
      result["uptime_sec"] = millis() / 1000;
      result["free_heap"] = ESP.getFreeHeap();
    } else {
      response["error"] = "Failed to read BME680";
    }
  } else {
    response["error"] = "Unknown tool";
  }

  // Publish response
  char responseTopic[128];
  snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);

  String output;
  serializeJson(response, output);
  mqtt.publish(responseTopic, output.c_str());
  Serial.printf("Response sent: %s\n", responseTopic);
}

// ==================== Sensor Read & Publish ====================
void readAndPublishSensors() {
  if (!bme.performReading()) {
    Serial.println("Failed to perform reading");
    return;
  }

  float temperature = bme.temperature;
  float humidity = bme.humidity;
  float pressure = bme.pressure / 100.0;  // Pa to hPa
  float gas = bme.gas_resistance / 1000.0;  // Ohms to kOhms

  Serial.printf("T=%.1f°C H=%.1f%% P=%.1fhPa G=%.1fkΩ\n",
                temperature, humidity, pressure, gas);

  // Per-channel telemetry with {"value": X} format for WorldModel
  char topic[128];
  char payload[64];

  snprintf(topic, sizeof(topic), "%s/temperature", topicPrefix);
  snprintf(payload, sizeof(payload), "{\"value\":%.2f}", temperature);
  mqtt.publish(topic, payload);

  snprintf(topic, sizeof(topic), "%s/humidity", topicPrefix);
  snprintf(payload, sizeof(payload), "{\"value\":%.2f}", humidity);
  mqtt.publish(topic, payload);

  snprintf(topic, sizeof(topic), "%s/pressure", topicPrefix);
  snprintf(payload, sizeof(payload), "{\"value\":%.2f}", pressure);
  mqtt.publish(topic, payload);

  snprintf(topic, sizeof(topic), "%s/gas", topicPrefix);
  snprintf(payload, sizeof(payload), "{\"value\":%.2f}", gas);
  mqtt.publish(topic, payload);
}

// ==================== Status Publish ====================
void publishStatus() {
  char topic[128];
  snprintf(topic, sizeof(topic), "%s/heartbeat", topicPrefix);

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["status"] = "online";
  doc["uptime_sec"] = millis() / 1000;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["wifi_rssi"] = WiFi.RSSI();

  String output;
  serializeJson(doc, output);
  mqtt.publish(topic, output.c_str());
}
