/**
 * Camera Node - Freenove ESP32 WROVER v3.0
 * MJPEG HTTP Stream + MCP Control
 *
 * Features:
 * - MJPEG HTTP stream on port 81 (for Perception pipeline)
 * - JSON-RPC 2.0 MCP protocol via MQTT (for Brain control)
 * - Periodic heartbeat
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <base64.h>
#include "esp_camera.h"
#include "esp_http_server.h"

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
#define CFG_DEVICE_ID "camera_node_01"
#endif
#ifndef CFG_ZONE
#define CFG_ZONE "main"
#endif

// Static IP (leave undefined or "" for DHCP)
#ifndef CFG_STATIC_IP
#define CFG_STATIC_IP ""
#endif
#ifndef CFG_GATEWAY
#define CFG_GATEWAY "192.168.128.1"
#endif
#ifndef CFG_SUBNET
#define CFG_SUBNET "255.255.255.0"
#endif

const char* WIFI_SSID = CFG_WIFI_SSID;
const char* WIFI_PASS = CFG_WIFI_PASS;
const char* MQTT_SERVER = CFG_MQTT_SERVER;
const int MQTT_PORT = CFG_MQTT_PORT;
const char* MQTT_USER = CFG_MQTT_USER;
const char* MQTT_PASS_STR = CFG_MQTT_PASS;
const char* DEVICE_ID = CFG_DEVICE_ID;
const char* ZONE = CFG_ZONE;

// MQTT topics (built dynamically in setup())
char topicMcpRequest[128];
char topicStatus[128];

// Camera pins (Freenove ESP32 WROVER v3.0)
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     21
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       19
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       5
#define Y2_GPIO_NUM       4
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
#define LED_PIN           2

// ==================== MJPEG Stream ====================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char *STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static httpd_handle_t stream_httpd = NULL;

static esp_err_t stream_handler(httpd_req_t *req) {
  esp_err_t res = ESP_OK;
  char part_buf[64];

  res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[Stream] Capture failed");
      res = ESP_FAIL;
      break;
    }

    size_t hlen = snprintf(part_buf, sizeof(part_buf), STREAM_PART, fb->len);

    res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
    if (res == ESP_OK)
      res = httpd_resp_send_chunk(req, part_buf, hlen);
    if (res == ESP_OK)
      res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);

    esp_camera_fb_return(fb);

    if (res != ESP_OK) break;  // Client disconnected
  }
  return res;
}

void startStreamServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;
  config.ctrl_port = 32769;
  config.stack_size = 8192;

  httpd_uri_t stream_uri = {
    .uri = "/",
    .method = HTTP_GET,
    .handler = stream_handler,
    .user_ctx = NULL
  };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.printf("MJPEG stream: http://%s:81/\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("Failed to start stream server!");
  }
}

// ==================== Globals ====================
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
sensor_t* cam_sensor = nullptr;

// ==================== Resolution Mapping ====================
framesize_t parseResolution(const char* resStr) {
  if (strcmp(resStr, "QVGA") == 0) return FRAMESIZE_QVGA;   // 320x240
  if (strcmp(resStr, "VGA") == 0) return FRAMESIZE_VGA;      // 640x480
  if (strcmp(resStr, "SVGA") == 0) return FRAMESIZE_SVGA;    // 800x600
  if (strcmp(resStr, "XGA") == 0) return FRAMESIZE_XGA;      // 1024x768
  if (strcmp(resStr, "UXGA") == 0) return FRAMESIZE_UXGA;    // 1600x1200
  return FRAMESIZE_VGA;
}

// ==================== Camera Init ====================
void setupCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 10000000;  // 10MHz: avoids WiFi scan interference on WROVER
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 10;
  config.fb_count = psramFound() ? 2 : 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    ESP.restart();
  }

  cam_sensor = esp_camera_sensor_get();
  Serial.printf("Camera initialized (PSRAM: %s)\n", psramFound() ? "YES" : "NO");
}

// ==================== WiFi ====================
void setupWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setMinSecurity(WIFI_AUTH_OPEN);

  for (int retry = 0; retry < 5; retry++) {
    if (retry > 0) {
      Serial.printf("\nRetry %d/5...\n", retry + 1);
      WiFi.disconnect(true);
      delay(1000);
    }

    // Scan to find BSSID and channel, then connect explicitly
    Serial.println("Scanning for AP...");
    int n = WiFi.scanNetworks();
    int bestIdx = -1;
    int bestRSSI = -999;
    for (int i = 0; i < n; i++) {
      if (WiFi.SSID(i) == WIFI_SSID && WiFi.RSSI(i) > bestRSSI) {
        bestIdx = i;
        bestRSSI = WiFi.RSSI(i);
      }
    }

    if (bestIdx < 0) {
      Serial.printf("SSID '%s' not found in scan (%d networks)\n", WIFI_SSID, n);
      WiFi.scanDelete();
      continue;
    }

    uint8_t* bssid = WiFi.BSSID(bestIdx);
    int32_t channel = WiFi.channel(bestIdx);
    Serial.printf("Found: BSSID=%02X:%02X:%02X:%02X:%02X:%02X CH=%d RSSI=%d\n",
                   bssid[0], bssid[1], bssid[2], bssid[3], bssid[4], bssid[5],
                   channel, bestRSSI);
    WiFi.scanDelete();

    // Static IP config before begin()
    if (strlen(CFG_STATIC_IP) > 0) {
      IPAddress ip, gw, sn;
      ip.fromString(CFG_STATIC_IP);
      gw.fromString(CFG_GATEWAY);
      sn.fromString(CFG_SUBNET);
      WiFi.config(ip, gw, sn, gw);
    }

    // Connect without BSSID/channel lock when using static IP (avoids NO_AP_FOUND)
    if (strlen(CFG_STATIC_IP) > 0) {
      WiFi.begin(WIFI_SSID, WIFI_PASS);
    } else {
      WiFi.begin(WIFI_SSID, WIFI_PASS, channel, bssid);
    }

    Serial.print("Connecting");
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts++ < 40) {
      delay(500);
      Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("\nWiFi connected: %s\n", WiFi.localIP().toString().c_str());
      return;
    }
    Serial.println("\nConnect failed");
  }

  Serial.println("WiFi failed after all retries!");
  ESP.restart();
}

// ==================== MQTT ====================
void mqttCallback(char* topic, byte* payload, unsigned int length);

bool mqttConnect() {
  bool connected;
  if (strlen(MQTT_USER) > 0) {
    connected = mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS_STR);
  } else {
    connected = mqtt.connect(DEVICE_ID);
  }
  if (connected) {
    mqtt.subscribe(topicMcpRequest);
    Serial.printf("MQTT connected, subscribed: %s\n", topicMcpRequest);
  }
  return connected;
}

void setupMQTT() {
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(32768);

  // Try a few times, but don't block forever — stream server must stay alive
  Serial.print("Connecting to MQTT");
  for (int i = 0; i < 5 && !mqtt.connected(); i++) {
    if (mqttConnect()) break;
    Serial.print(".");
    delay(2000);
  }
  if (!mqtt.connected()) {
    Serial.println("\nMQTT not available — stream-only mode");
  }
}

// ==================== MCP Tool Handler ====================
void handleCaptureToolCall(const char* reqId, JsonObject args) {
  const char* resolution = args["resolution"] | "VGA";
  int quality = args["quality"] | 10;

  Serial.printf("Capture: id=%s, res=%s, q=%d\n", reqId, resolution, quality);
  digitalWrite(LED_PIN, LOW);

  // Set resolution
  framesize_t framesize = parseResolution(resolution);
  cam_sensor->set_framesize(cam_sensor, framesize);
  cam_sensor->set_quality(cam_sensor, quality);

  // Capture
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Capture failed!");
    digitalWrite(LED_PIN, HIGH);

    // Send error response
    JsonDocument response;
    response["jsonrpc"] = "2.0";
    response["error"] = "Capture failed";
    response["id"] = reqId;

    char responseTopic[128];
    snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);
    String output;
    serializeJson(response, output);
    mqtt.publish(responseTopic, output.c_str());
    return;
  }

  Serial.printf("Captured: %dx%d, %u bytes\n", fb->width, fb->height, fb->len);

  // Base64 encode
  String base64Image = base64::encode(fb->buf, fb->len);

  // Build JSON-RPC 2.0 response
  JsonDocument response;
  response["jsonrpc"] = "2.0";
  response["id"] = reqId;
  JsonObject result = response["result"].to<JsonObject>();
  result["image"] = base64Image;
  result["width"] = fb->width;
  result["height"] = fb->height;
  result["size_bytes"] = fb->len;
  result["format"] = "jpeg";

  // Publish response
  char responseTopic[128];
  snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);

  String output;
  serializeJson(response, output);

  bool sent = mqtt.publish(responseTopic, output.c_str());
  Serial.printf("Response sent: %s (%s)\n", responseTopic, sent ? "OK" : "FAIL");

  esp_camera_fb_return(fb);
  digitalWrite(LED_PIN, HIGH);
}

void handleGetStatus(const char* reqId) {
  JsonDocument response;
  response["jsonrpc"] = "2.0";
  response["id"] = reqId;
  JsonObject result = response["result"].to<JsonObject>();
  result["device_id"] = DEVICE_ID;
  result["status"] = "online";
  result["uptime_sec"] = millis() / 1000;
  result["free_heap"] = ESP.getFreeHeap();
  result["wifi_rssi"] = WiFi.RSSI();
  result["psram"] = psramFound();

  char responseTopic[128];
  snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);

  String output;
  serializeJson(response, output);
  mqtt.publish(responseTopic, output.c_str());
}

// ==================== MQTT Callback ====================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, payload, length);

  if (error) {
    Serial.printf("JSON parse error: %s\n", error.c_str());
    return;
  }

  // Verify JSON-RPC 2.0 call_tool method
  const char* method = doc["method"] | "";
  if (strcmp(method, "call_tool") != 0) return;

  const char* reqId = doc["id"] | "unknown";
  const char* toolName = doc["params"]["name"] | "";
  JsonObject args = doc["params"]["arguments"].as<JsonObject>();

  Serial.printf("Tool call: %s (id=%s)\n", toolName, reqId);

  if (strcmp(toolName, "capture") == 0) {
    handleCaptureToolCall(reqId, args);
  } else if (strcmp(toolName, "get_status") == 0) {
    handleGetStatus(reqId);
  } else {
    // Unknown tool error
    JsonDocument response;
    response["jsonrpc"] = "2.0";
    response["error"] = "Unknown tool";
    response["id"] = reqId;

    char responseTopic[128];
    snprintf(responseTopic, sizeof(responseTopic), "mcp/%s/response/%s", DEVICE_ID, reqId);
    String output;
    serializeJson(response, output);
    mqtt.publish(responseTopic, output.c_str());
  }
}

// ==================== Heartbeat ====================
void publishStatus() {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["status"] = "online";
  doc["uptime_sec"] = millis() / 1000;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["wifi_rssi"] = WiFi.RSSI();

  String output;
  serializeJson(doc, output);
  mqtt.publish(topicStatus, output.c_str());
}

// ==================== Setup ====================
void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.println("\n=== Camera Node (MCP-compliant) ===");

  // Build MQTT topics dynamically
  snprintf(topicMcpRequest, sizeof(topicMcpRequest), "mcp/%s/request/call_tool", DEVICE_ID);
  snprintf(topicStatus, sizeof(topicStatus), "office/%s/camera/%s/status", ZONE, DEVICE_ID);

  setupCamera();
  setupWiFi();
  startStreamServer();
  setupMQTT();

  digitalWrite(LED_PIN, HIGH);
  publishStatus();

  Serial.println("=== Ready ===\n");
}

// ==================== Main Loop ====================
void loop() {
  // Non-blocking MQTT reconnect (try once per 10s, never block)
  static unsigned long lastMqttRetry = 0;
  if (!mqtt.connected() && millis() - lastMqttRetry > 10000) {
    Serial.println("MQTT reconnecting...");
    mqttConnect();
    lastMqttRetry = millis();
  }
  if (mqtt.connected()) {
    mqtt.loop();
  }

  // Status every 30 seconds (only if MQTT is up)
  static unsigned long lastStatus = 0;
  if (mqtt.connected() && millis() - lastStatus > 30000) {
    publishStatus();
    lastStatus = millis();
  }

  delay(10);
}
