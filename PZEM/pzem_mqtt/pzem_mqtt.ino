// SmartFarm PZEM pump-energy node  (TTGO T-Display / ESP32, no display)
// ===========================================================================
// 1 ESP32 -> 2x PZEM-004T v3.0 -> 2 pumps.  Publishes each pump to its own
// topic  smartfarm/pump/{pump_code}.  Serial-only status (TFT is NOT used).
//
//   PZEM1 (UART2/Serial2): TX -> divider -> GPIO27 (RX)   RX -> GPIO26 (TX)
//   PZEM2 (UART1/Serial1): TX -> divider -> GPIO22 (RX)   RX -> GPIO21 (TX)
//   Divider on TX line only: 4.7k top + 9.4k bottom (5V -> 3.33V). RX direct.
//   CT wire passes the clamp CT_TURNS times -> divide I/P/E by CT_TURNS (1 = as-is).
//
// Setup portal (WiFiManager / tzapu):
//   First boot (or after reset) -> AP "PZEM-Setup" (pass 12345678) -> web form
//   asks for WiFi + MQTT broker IP + pump_code1 (PZEM1) + pump_code2 (PZEM2).
//   Config persists in LittleFS.
//   BOOT button (GPIO0) after boot:
//     - short tap (<2s)  -> open config portal, KEEP saved WiFi (edit settings)
//     - hold 5s          -> factory reset: wipe WiFi + config
//
// Libraries: mandulaj/PZEM-004T-v30, tzapu/WiFiManager, PubSubClient, ArduinoJson
// ===========================================================================

#include <FS.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <ArduinoOTA.h>        // wireless firmware update (no USB after first flash)
#include <time.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <PZEM004Tv30.h>
#include <time.h>

// ---- Pins / constants -----------------------------------------------------
#define PZEM1_RX_PIN 27
#define PZEM1_TX_PIN 26
#define PZEM2_RX_PIN 22
#define PZEM2_TX_PIN 21
#define BOOT_BTN      0        // GPIO0, INPUT_PULLUP: idle HIGH, pressed LOW
#define CT_TURNS      1        // CT wire passes clamp once -> no division (I/P/E as-is)
#define RUN_WATTS     200.0    // power_w > this => is_running = 1 (matches DB)

// ---- Scheduled reboot config / ตั้งค่ารีบูตตามเวลา ----
#define REBOOT_HOUR    3      // reboot ตอนตี 3 (03:00)
#define REBOOT_MINUTE  5
bool rebootDone = false;      // flag กันรีบูตซ้ำในนาทีเดียวกัน

static const uint32_t PUBLISH_INTERVAL = 10000;  // ms between publishes
static const uint32_t BTN_HOLD_MS      = 5000;   // hold BOOT this long = full reset
static const uint32_t BTN_TAP_MAX      = 2000;   // release before this = on-demand portal
static const char*    AP_NAME          = "PZEM-Setup";
static const char*    AP_PASS          = "12345678";

// NTP (reading_at is sent as local Thailand time, MySQL DATETIME format)
static const char* NTP1 = "pool.ntp.org";
static const char* NTP2 = "time.google.com";
static const long   TZ_OFFSET_SEC = 7 * 3600;    // Asia/Bangkok, no DST

// ---- Persisted config -----------------------------------------------------
char cfg_mqtt_ip[40]    = "";
char cfg_mqtt_port[6]   = "1883";
char cfg_mqtt_user[32]  = "";     // leave blank if broker allows anonymous
char cfg_mqtt_pass[32]  = "";
char cfg_pump_code1[16] = "";     // PZEM1
char cfg_pump_code2[16] = "";     // PZEM2
bool shouldSaveConfig   = false;

// ---- Globals --------------------------------------------------------------
PZEM004Tv30 pzem1(Serial2, PZEM1_RX_PIN, PZEM1_TX_PIN);
PZEM004Tv30 pzem2(Serial1, PZEM2_RX_PIN, PZEM2_TX_PIN);
WiFiClient   net;
PubSubClient mqtt(net);

uint32_t lastPublish = 0;
uint32_t lastMqttTry = 0;      // throttle reconnect so loop stays responsive
uint32_t btnDownAt   = 0;      // millis when BOOT press started (0 = not pressed)

struct Reading { float v, i, p, e, f, pf; bool ok; };

// ---- Config file I/O ------------------------------------------------------
void saveConfigCallback() { shouldSaveConfig = true; }

void loadConfig() {
  if (!LittleFS.begin(true)) { Serial.println("LittleFS mount failed"); return; }
  if (!LittleFS.exists("/config.json")) { Serial.println("No config yet"); return; }
  File f = LittleFS.open("/config.json", "r");
  if (!f) return;
  JsonDocument doc;
  if (deserializeJson(doc, f)) { f.close(); Serial.println("config parse error"); return; }
  f.close();
  strlcpy(cfg_mqtt_ip,    doc["mqtt_ip"]    | cfg_mqtt_ip,    sizeof(cfg_mqtt_ip));
  strlcpy(cfg_mqtt_port,  doc["mqtt_port"]  | cfg_mqtt_port,  sizeof(cfg_mqtt_port));
  strlcpy(cfg_mqtt_user,  doc["mqtt_user"]  | cfg_mqtt_user,  sizeof(cfg_mqtt_user));
  strlcpy(cfg_mqtt_pass,  doc["mqtt_pass"]  | cfg_mqtt_pass,  sizeof(cfg_mqtt_pass));
  strlcpy(cfg_pump_code1, doc["pump_code1"] | cfg_pump_code1, sizeof(cfg_pump_code1));
  strlcpy(cfg_pump_code2, doc["pump_code2"] | cfg_pump_code2, sizeof(cfg_pump_code2));
  Serial.printf("Loaded: mqtt=%s:%s user=%s p1=%s p2=%s\n",
                cfg_mqtt_ip, cfg_mqtt_port, cfg_mqtt_user, cfg_pump_code1, cfg_pump_code2);
}

void saveConfig() {
  JsonDocument doc;
  doc["mqtt_ip"]    = cfg_mqtt_ip;
  doc["mqtt_port"]  = cfg_mqtt_port;
  doc["mqtt_user"]  = cfg_mqtt_user;
  doc["mqtt_pass"]  = cfg_mqtt_pass;
  doc["pump_code1"] = cfg_pump_code1;
  doc["pump_code2"] = cfg_pump_code2;
  File f = LittleFS.open("/config.json", "w");
  if (!f) { Serial.println("config write failed"); return; }
  serializeJson(doc, f);
  f.close();
  Serial.println("Config saved");
}

// ---- WiFiManager portal ---------------------------------------------------
// forcePortal=false: normal boot (open portal only if WiFi won't connect).
// forcePortal=true : on-demand — always open the portal, keeping saved WiFi.
void runPortal(bool forcePortal) {
  WiFiManager wm;
  wm.setSaveConfigCallback(saveConfigCallback);

  WiFiManagerParameter p_ip  ("mqtt_ip",  "MQTT broker IP", cfg_mqtt_ip,    sizeof(cfg_mqtt_ip) - 1);
  WiFiManagerParameter p_port("mqtt_port","MQTT port",      cfg_mqtt_port,  sizeof(cfg_mqtt_port) - 1);
  WiFiManagerParameter p_user("mqtt_user","MQTT user (blank if none)", cfg_mqtt_user, sizeof(cfg_mqtt_user) - 1);
  WiFiManagerParameter p_pass("mqtt_pass","MQTT password",  cfg_mqtt_pass,  sizeof(cfg_mqtt_pass) - 1);
  WiFiManagerParameter p_pc1 ("pump1",    "pump_code PZEM1 (e.g. WS1-P1)", cfg_pump_code1, sizeof(cfg_pump_code1) - 1);
  WiFiManagerParameter p_pc2 ("pump2",    "pump_code PZEM2 (e.g. WS1-P2)", cfg_pump_code2, sizeof(cfg_pump_code2) - 1);
  wm.addParameter(&p_ip);
  wm.addParameter(&p_port);
  wm.addParameter(&p_user);
  wm.addParameter(&p_pass);
  wm.addParameter(&p_pc1);
  wm.addParameter(&p_pc2);

  wm.setConfigPortalTimeout(180);
  bool ok = forcePortal ? wm.startConfigPortal(AP_NAME, AP_PASS)   // keeps saved creds
                        : wm.autoConnect(AP_NAME, AP_PASS);

  if (shouldSaveConfig) {
    strlcpy(cfg_mqtt_ip,    p_ip.getValue(),   sizeof(cfg_mqtt_ip));
    strlcpy(cfg_mqtt_port,  p_port.getValue(), sizeof(cfg_mqtt_port));
    strlcpy(cfg_mqtt_user,  p_user.getValue(), sizeof(cfg_mqtt_user));
    strlcpy(cfg_mqtt_pass,  p_pass.getValue(), sizeof(cfg_mqtt_pass));
    strlcpy(cfg_pump_code1, p_pc1.getValue(),  sizeof(cfg_pump_code1));
    strlcpy(cfg_pump_code2, p_pc2.getValue(),  sizeof(cfg_pump_code2));
    saveConfig();
    shouldSaveConfig = false;
  }
  if (!ok) { Serial.println("WiFi failed, restart"); delay(2000); ESP.restart(); }
}

void resetConfig() {
  Serial.println("BOOT held 5s -> clearing config & WiFi, restarting...");
  WiFiManager wm;
  wm.resetSettings();
  LittleFS.remove("/config.json");
  delay(500);
  ESP.restart();
}

// ---- OTA (wireless firmware update) --------------------------------------
void setupOTA() {
  char host[32];
  snprintf(host, sizeof(host), "pzem-%s", cfg_pump_code1[0] ? cfg_pump_code1 : "node");
  ArduinoOTA.setHostname(host);
  // ArduinoOTA.setPassword("pzem-ota");   // uncomment to require a password
  ArduinoOTA.onStart([]() { Serial.println("OTA: update starting..."); });
  ArduinoOTA.onEnd([]()   { Serial.println("\nOTA: done, rebooting"); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("OTA error %u\n", e); });
  ArduinoOTA.begin();
  Serial.printf("OTA ready: host='%s.local' ip=%s\n",
                host, WiFi.localIP().toString().c_str());
}

// ---- MQTT -----------------------------------------------------------------
void mqttEnsure() {
  if (mqtt.connected()) return;
  // Don't hammer a failing broker every loop — it blocks button/OTA handling.
  if (lastMqttTry != 0 && millis() - lastMqttTry < 5000) return;
  lastMqttTry = millis();
  uint16_t port = (uint16_t) atoi(cfg_mqtt_port);
  mqtt.setServer(cfg_mqtt_ip, port ? port : 1883);
  char clientId[40];
  snprintf(clientId, sizeof(clientId), "pzem-%s", cfg_pump_code1[0] ? cfg_pump_code1 : "node");
  bool ok = cfg_mqtt_user[0]
              ? mqtt.connect(clientId, cfg_mqtt_user, cfg_mqtt_pass)   // with auth
              : mqtt.connect(clientId);                                // anonymous
  if (ok)
    Serial.printf("MQTT connected to %s:%u\n", cfg_mqtt_ip, port);
  else
    Serial.printf("MQTT connect failed rc=%d\n", mqtt.state());
}

// ---- PZEM -----------------------------------------------------------------
Reading readPzem(PZEM004Tv30 &z) {
  Reading r;
  r.v = z.voltage(); r.i = z.current(); r.p = z.power();
  r.e = z.energy();  r.f = z.frequency(); r.pf = z.pf();
  r.ok = !isnan(r.v);
  if (r.ok) { r.i /= CT_TURNS; r.p /= CT_TURNS; r.e /= CT_TURNS; }
  return r;
}

// Fill "YYYY-MM-DD HH:MM:SS" from NTP-synced clock. Returns false if not synced.
bool nowString(char* out, size_t n) {
  time_t t = time(nullptr);
  if (t < 100000) return false;            // clock not set yet
  struct tm tm_local;
  localtime_r(&t, &tm_local);
  strftime(out, n, "%Y-%m-%d %H:%M:%S", &tm_local);
  return true;
}

void publishPump(PZEM004Tv30 &z, const char* pump_code) {
  if (!pump_code[0]) return;               // unconfigured slot -> skip
  Reading r = readPzem(z);
  if (!r.ok) { Serial.printf("[%s] NaN, skip publish\n", pump_code); return; }

  JsonDocument doc;
  doc["pump_id"]      = pump_code;
  doc["voltage_v"]    = round(r.v  * 10) / 10.0;
  doc["current_a"]    = round(r.i  * 1000) / 1000.0;
  doc["power_w"]      = round(r.p  * 10) / 10.0;
  doc["energy_kwh"]   = round(r.e  * 1000) / 1000.0;
  doc["frequency_hz"] = round(r.f  * 10) / 10.0;
  doc["power_factor"] = round(r.pf * 100) / 100.0;
  doc["is_running"]   = (r.p > RUN_WATTS) ? 1 : 0;
  char ts[24];
  if (nowString(ts, sizeof(ts))) doc["reading_at"] = ts;   // logger fills if absent

  char topic[48], payload[320];
  snprintf(topic, sizeof(topic), "smartfarm/pump/%s", pump_code);
  size_t len = serializeJson(doc, payload, sizeof(payload));
  bool sent = mqtt.publish(topic, (const uint8_t*)payload, len, false);
  Serial.printf("PUB %s %s [%s]\n", topic, payload, sent ? "ok" : "FAIL");
}
// เช็กเวลา ถ้าถึงตี 3 ให้รีบูต / reboot at 03:00 daily to clear memory leak
void checkScheduledReboot() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) return;   // ยังไม่ได้เวลา ข้ามไป
  if (timeinfo.tm_year < (2020 - 1900)) return;  // เวลายังไม่ sync ข้ามไป
  if (timeinfo.tm_hour == REBOOT_HOUR && timeinfo.tm_min == REBOOT_MINUTE) {
    if (!rebootDone) {                    // รีบูตแค่ครั้งเดียวในนาทีนั้น
      rebootDone = true;
      Serial.println("Scheduled reboot at 03:00 / รีบูตตามเวลาตี 3...");
      delay(200);
      ESP.restart();
    }
  } else {
    rebootDone = false;                   // พ้นนาที 03:00 แล้ว รีเซ็ต flag
  }
}

// ---- Setup / Loop ---------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(BOOT_BTN, INPUT_PULLUP);
  Serial.println("\nPZEM pump-energy node booting...");

  loadConfig();
  runPortal(false);                        // connect WiFi (or open portal if needed)

  configTime(TZ_OFFSET_SEC, 0, NTP1, NTP2);
  mqtt.setBufferSize(512);
  setupOTA();
  Serial.printf("Online. IP=%s  topics: pump1=%s pump2=%s\n",
                WiFi.localIP().toString().c_str(),
                cfg_pump_code1[0] ? cfg_pump_code1 : "(none)",
                cfg_pump_code2[0] ? cfg_pump_code2 : "(none)");
  // ตั้งเวลาจาก NTP (โซนไทย UTC+7) / sync time for scheduled reboot
  configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");
}

void loop() {
  ArduinoOTA.handle();          // service wireless-update requests

  // BOOT button: short tap = edit config (keep WiFi), hold 5s = factory reset
  if (digitalRead(BOOT_BTN) == LOW) {
    if (btnDownAt == 0) btnDownAt = millis();
    else if (millis() - btnDownAt >= BTN_HOLD_MS) resetConfig();     // long hold
  } else if (btnDownAt != 0) {
    uint32_t held = millis() - btnDownAt;
    btnDownAt = 0;
    if (held >= 50 && held < BTN_TAP_MAX) {                          // short tap
      Serial.println("BOOT tapped -> config portal (WiFi kept)");
      runPortal(true);
      ESP.restart();                        // reboot to apply new settings cleanly
    }
  }

  mqttEnsure();
  mqtt.loop();

  uint32_t now = millis();
  if (now - lastPublish >= PUBLISH_INTERVAL) {
    lastPublish = now;
    if (mqtt.connected()) {
      publishPump(pzem1, cfg_pump_code1);
      publishPump(pzem2, cfg_pump_code2);
    } else {
      Serial.println("MQTT down, skip publish cycle");
    }
  }
  checkScheduledReboot();   // ← เพิ่มบรรทัดนี้
}
