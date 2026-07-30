// SmartFarm water-pressure node  (TTGO T-Display / ESP32, no display)
// ===========================================================================
// 1 ESP32 -> 2x pressure transducer (0.5-4.5V, 10 bar / 145 psi) -> 2 pumps.
// Publishes each pump to its own topic  smartfarm/pressure/{pump_code}.
// Serial-only status (TFT is NOT used). Shares config.py/.env with the PZEM
// pipeline on the logger side; here it's a standalone sketch.
//
//   Sensor transfer:  0.5V = 0 bar ... 4.5V = full scale (10 bar).
//   Ratiometric -> feed from a CLEAN 5V; unstable 5V = unstable reading.
//
//   Wiring (per sensor):  RED->+5V  BLACK->GND(common w/ ESP32)  BLUE->signal
//   Signal max 4.5V > ESP32 ADC 3.3V, so a 1:1 divider halves it:
//       BLUE --[ R1 4.7k ]--+--> ADC pin      (4.5V -> 2.25V, safe)
//                           |
//                        [ R2 4.7k ]
//                           |
//                          GND        + 100nF from ADC node to GND (motor noise)
//   DIV_FACTOR = (R1+R2)/R2 = 2.0  -> sensor_v = adc_node_v * 2.0
//
//   Sensor1 -> GPIO34 (ADC1_CH6, input-only)   pump_code1
//   Sensor2 -> GPIO35 (ADC1_CH7, input-only)   pump_code2
//   ADC1 chosen so readings work with WiFi on. analogReadMilliVolts() uses the
//   eFuse calibration -> volts, not raw counts.
//
// Setup portal (WiFiManager / tzapu):
//   First boot (or after reset) -> AP "PRESSURE-Setup" (pass 12345678) -> web
//   form asks for WiFi + MQTT + pump_code1/2 + per-sensor calibration v_min/v_max.
//   Config persists in LittleFS.
//   BOOT button (GPIO0) after boot:
//     - short tap (<2s)  -> open config portal, KEEP saved WiFi (edit settings)
//     - hold 5s          -> factory reset: wipe WiFi + config
//
// Calibration: watch the Serial "sensor_v" print with the line at 0 bar -> that
//   is your v_min; apply a known pressure (SUMO gauge) -> note sensor_v -> v_max
//   = extrapolate to full scale, or just set v_min/v_max endpoints in the portal.
//
// Libraries: tzapu/WiFiManager, PubSubClient, ArduinoJson
// ===========================================================================

#include <FS.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <ArduinoOTA.h>        // wireless firmware update (no USB after first flash)
#include <time.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ---- Pins / constants -----------------------------------------------------
#define ADC1_PIN     34        // sensor 1 (pump_code1)  ADC1_CH6, input-only
#define ADC2_PIN     35        // sensor 2 (pump_code2)  ADC1_CH7, input-only
#define BOOT_BTN      0        // GPIO0, INPUT_PULLUP: idle HIGH, pressed LOW
#define DIV_FACTOR   2.0f      // (R1+R2)/R2 = (4700+4700)/4700
#define FS_BAR       10.0f     // full-scale pressure (bar) = 145 psi
#define SAMPLES      20        // software averaging per reading
#define PSI_PER_BAR  14.5037738f

// ---- Scheduled reboot config / ตั้งค่ารีบูตตามเวลา ----
#define REBOOT_HOUR    3      // reboot ตอนตี 3 (03:00)
#define REBOOT_MINUTE  0
bool rebootDone = false;      // flag กันรีบูตซ้ำในนาทีเดียวกัน

static const uint32_t PUBLISH_INTERVAL = 10000;  // ms between publishes
static const uint32_t BTN_HOLD_MS      = 5000;   // hold BOOT this long = full reset
static const uint32_t BTN_TAP_MAX      = 2000;   // release before this = on-demand portal
static const char*    AP_NAME          = "PRESSURE-Setup";
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
char cfg_pump_code1[16] = "";     // sensor 1
char cfg_pump_code2[16] = "";     // sensor 2
char cfg_vmin1[8]       = "0.5";  // per-sensor calibration endpoints (volts)
char cfg_vmax1[8]       = "4.5";
char cfg_vmin2[8]       = "0.5";
char cfg_vmax2[8]       = "4.5";
bool shouldSaveConfig   = false;

// ---- Globals --------------------------------------------------------------
WiFiClient   net;
PubSubClient mqtt(net);

uint32_t lastPublish = 0;
uint32_t lastMqttTry = 0;      // throttle reconnect so loop stays responsive
uint32_t btnDownAt   = 0;      // millis when BOOT press started (0 = not pressed)

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
  strlcpy(cfg_vmin1,      doc["vmin1"]      | cfg_vmin1,      sizeof(cfg_vmin1));
  strlcpy(cfg_vmax1,      doc["vmax1"]      | cfg_vmax1,      sizeof(cfg_vmax1));
  strlcpy(cfg_vmin2,      doc["vmin2"]      | cfg_vmin2,      sizeof(cfg_vmin2));
  strlcpy(cfg_vmax2,      doc["vmax2"]      | cfg_vmax2,      sizeof(cfg_vmax2));
  Serial.printf("Loaded: mqtt=%s:%s user=%s p1=%s p2=%s cal1=[%s..%s] cal2=[%s..%s]\n",
                cfg_mqtt_ip, cfg_mqtt_port, cfg_mqtt_user, cfg_pump_code1, cfg_pump_code2,
                cfg_vmin1, cfg_vmax1, cfg_vmin2, cfg_vmax2);
}

void saveConfig() {
  JsonDocument doc;
  doc["mqtt_ip"]    = cfg_mqtt_ip;
  doc["mqtt_port"]  = cfg_mqtt_port;
  doc["mqtt_user"]  = cfg_mqtt_user;
  doc["mqtt_pass"]  = cfg_mqtt_pass;
  doc["pump_code1"] = cfg_pump_code1;
  doc["pump_code2"] = cfg_pump_code2;
  doc["vmin1"]      = cfg_vmin1;
  doc["vmax1"]      = cfg_vmax1;
  doc["vmin2"]      = cfg_vmin2;
  doc["vmax2"]      = cfg_vmax2;
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
  WiFiManagerParameter p_pc1 ("pump1",    "pump_code sensor1 (e.g. WS1-P1)", cfg_pump_code1, sizeof(cfg_pump_code1) - 1);
  WiFiManagerParameter p_pc2 ("pump2",    "pump_code sensor2 (e.g. WS1-P2)", cfg_pump_code2, sizeof(cfg_pump_code2) - 1);
  WiFiManagerParameter p_vn1 ("vmin1",    "sensor1 V at 0 bar",   cfg_vmin1, sizeof(cfg_vmin1) - 1);
  WiFiManagerParameter p_vx1 ("vmax1",    "sensor1 V at full",    cfg_vmax1, sizeof(cfg_vmax1) - 1);
  WiFiManagerParameter p_vn2 ("vmin2",    "sensor2 V at 0 bar",   cfg_vmin2, sizeof(cfg_vmin2) - 1);
  WiFiManagerParameter p_vx2 ("vmax2",    "sensor2 V at full",    cfg_vmax2, sizeof(cfg_vmax2) - 1);
  wm.addParameter(&p_ip);
  wm.addParameter(&p_port);
  wm.addParameter(&p_user);
  wm.addParameter(&p_pass);
  wm.addParameter(&p_pc1);
  wm.addParameter(&p_pc2);
  wm.addParameter(&p_vn1);
  wm.addParameter(&p_vx1);
  wm.addParameter(&p_vn2);
  wm.addParameter(&p_vx2);

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
    strlcpy(cfg_vmin1,      p_vn1.getValue(),  sizeof(cfg_vmin1));
    strlcpy(cfg_vmax1,      p_vx1.getValue(),  sizeof(cfg_vmax1));
    strlcpy(cfg_vmin2,      p_vn2.getValue(),  sizeof(cfg_vmin2));
    strlcpy(cfg_vmax2,      p_vx2.getValue(),  sizeof(cfg_vmax2));
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
  snprintf(host, sizeof(host), "press-%s", cfg_pump_code1[0] ? cfg_pump_code1 : "node");
  ArduinoOTA.setHostname(host);
  // ArduinoOTA.setPassword("press-ota");   // uncomment to require a password
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
  snprintf(clientId, sizeof(clientId), "press-%s", cfg_pump_code1[0] ? cfg_pump_code1 : "node");
  bool ok = cfg_mqtt_user[0]
              ? mqtt.connect(clientId, cfg_mqtt_user, cfg_mqtt_pass)   // with auth
              : mqtt.connect(clientId);                                // anonymous
  if (ok)
    Serial.printf("MQTT connected to %s:%u\n", cfg_mqtt_ip, port);
  else
    Serial.printf("MQTT connect failed rc=%d\n", mqtt.state());
}

// ---- Sensor ---------------------------------------------------------------
// Read the ADC pin SAMPLES times (calibrated millivolts), average, and undo
// the 1:1 divider to recover the transducer's own voltage (0.5-4.5V).
float readSensorVolts(uint8_t pin) {
  uint32_t sum_mv = 0;
  for (int i = 0; i < SAMPLES; i++) {
    sum_mv += analogReadMilliVolts(pin);   // eFuse-calibrated node voltage (mV)
    delayMicroseconds(200);
  }
  float node_v = (sum_mv / (float)SAMPLES) / 1000.0f;
  return node_v * DIV_FACTOR;              // sensor_v before the divider
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

void publishSensor(uint8_t pin, const char* pump_code, float vmin, float vmax) {
  if (!pump_code[0]) return;               // unconfigured slot -> skip
  float sensor_v = readSensorVolts(pin);
  float span = (vmax - vmin);
  float bar = (span > 0.01f) ? (sensor_v - vmin) * FS_BAR / span : 0.0f;
  if (bar < 0) bar = 0;                     // clamp noise at 0 bar
  float psi = bar * PSI_PER_BAR;

  JsonDocument doc;
  doc["pump_id"]      = pump_code;
  doc["voltage_raw"]  = round(sensor_v * 1000) / 1000.0;  // 3 dp -> decimal(4,3)
  doc["pressure_bar"] = round(bar * 100) / 100.0;         // 2 dp -> decimal(5,2)
  doc["pressure_psi"] = round(psi * 100) / 100.0;         // 2 dp -> decimal(6,2)
  char ts[24];
  if (nowString(ts, sizeof(ts))) doc["reading_at"] = ts;  // logger fills if absent

  char topic[52], payload[256];
  snprintf(topic, sizeof(topic), "smartfarm/pressure/%s", pump_code);
  size_t len = serializeJson(doc, payload, sizeof(payload));
  bool sent = mqtt.publish(topic, (const uint8_t*)payload, len, false);
  Serial.printf("PUB %s %s [%s]  sensor_v=%.3f bar=%.2f\n",
                topic, payload, sent ? "ok" : "FAIL", sensor_v, bar);
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
  analogSetPinAttenuation(ADC1_PIN, ADC_11db);   // full ~0-3.1V range on ADC node
  analogSetPinAttenuation(ADC2_PIN, ADC_11db);
  Serial.println("\nPressure node booting...");

  loadConfig();
  runPortal(false);                        // connect WiFi (or open portal if needed)

  configTime(TZ_OFFSET_SEC, 0, NTP1, NTP2);
  mqtt.setBufferSize(512);
  setupOTA();
  Serial.printf("Online. IP=%s  topics: p1=%s p2=%s\n",
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
      publishSensor(ADC1_PIN, cfg_pump_code1, atof(cfg_vmin1), atof(cfg_vmax1));
      publishSensor(ADC2_PIN, cfg_pump_code2, atof(cfg_vmin2), atof(cfg_vmax2));
    } else {
      Serial.println("MQTT down, skip publish cycle");
    }
  }
  checkScheduledReboot();   // ← เพิ่มบรรทัดนี้
}
