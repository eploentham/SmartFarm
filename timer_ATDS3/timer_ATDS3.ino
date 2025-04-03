#include <Arduino.h>
#include <lvgl.h>
#include <ATD1.47-S3.h>
#include <WiFi.h>
#include <time.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>
#include <SPIFFS.h>
#include <DHTesp.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <AsyncMqttClient.h>
//#include <esp_task_wdt.h>

// MQTT Configuration
const char* mqtt_server = "192.168.100.242";
const int mqtt_port = 1883;
const char* mqtt_client_id = "ESP32_Temperature1";
const char* mqtt_topic = "smartfarm/temperature";
#define MQTT_USERNAME "pop"
#define MQTT_PASSWORD "pop1"
AsyncMqttClient mqttClient;

// Define pins for water valves
const int VALVE1_PIN = 15;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE2_PIN = 16;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE3_PIN = 17;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE4_PIN = 18;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE5_PIN = 42;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE6_PIN = 41;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE7_PIN = 40;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE8_PIN = 39;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
#define DHTPIN 38
#define DHTTYPE DHT22
DHTesp dht;
unsigned long lastReadTime = 0;
const unsigned long READ_INTERVAL = 5000; // อ่านทุก 5 วินาที

// DS18B20 setup
#define DS18B20_PIN 4  // กำหนด pin สำหรับ DS18B20
OneWire oneWire(DS18B20_PIN);
DallasTemperature ds18b20(&oneWire);
// ตัวแปรสำหรับเก็บค่า
float temperature = 0,humidity = 0;
bool useDS18B20 = false;  // ตัวแปรเช็คว่าใช้ DS18B20 หรือไม่

// Timer variables
unsigned long Duration = 600000;		//ระยะเวลาในการเปิดวาล์ว 10 นาที
unsigned long valve1StartTime = 0;
unsigned long valve2StartTime = 0;
unsigned long valve3StartTime = 0;
unsigned long valve4StartTime = 0;
unsigned long valve5StartTime = 0;
unsigned long valve6StartTime = 0;
unsigned long valve7StartTime = 0;
unsigned long valve8StartTime = 0;
unsigned long valve1Duration = Duration;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve2Duration = Duration;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve3Duration = Duration;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve4Duration = Duration;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve5Duration = Duration;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve6Duration = Duration;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve7Duration = Duration;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve8Duration = Duration;  // ระยะเวลาเปิดวาล์ว 10 นาที
bool VALVE1RUNNING = false;
bool VALVE2RUNNING = false;
bool VALVE3RUNNING = false;
bool VALVE4RUNNING = false;
bool VALVE5RUNNING = false;
bool VALVE6RUNNING = false;
bool VALVE7RUNNING = false;
bool VALVE8RUNNING = false;
// Time variables
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 7 * 3600;  // GMT+7
const int daylightOffset_sec = 0;
struct tm timeinfo;
bool valveOpenedToday = false;
String VALVE1NAME="",VALVE2NAME="",VALVE3NAME="",VALVE4NAME="",VALVE5NAME="",VALVE6NAME="",VALVE7NAME="",VALVE8NAME="";
//int temperature=0,humidity=0;
// กำหนด state ของวาล์วแต่ละตัว
enum ValveState {
    IDLE,       // พัก
    OPENING,    // กำลังเปิด
    RUNNING,    // กำลังทำงาน
    CLOSING     // กำลังปิด
};
// ตัวแปรสำหรับวาล์วแต่ละตัว
struct Valve {
    ValveState state;
    unsigned long startTime;
    unsigned long duration;
    bool isRunning;
    int pin;
    const char* name;
};
// สร้างตัวแปรสำหรับวาล์วทั้ง 8 ตัว
Valve VALVES[8] = {
    {IDLE, 0, 0, false, VALVE1_PIN, VALVE1NAME.c_str()},
    {IDLE, 0, 0, false, VALVE2_PIN, VALVE2NAME.c_str()},
    {IDLE, 0, 0, false, VALVE3_PIN, VALVE3NAME.c_str()},
    {IDLE, 0, 0, false, VALVE4_PIN, VALVE4NAME.c_str()},
    {IDLE, 0, 0, false, VALVE5_PIN, VALVE5NAME.c_str()},
    {IDLE, 0, 0, false, VALVE6_PIN, VALVE6NAME.c_str()},
    {IDLE, 0, 0, false, VALVE7_PIN, VALVE7NAME.c_str()},
    {IDLE, 0, 0, false, VALVE8_PIN, VALVE8NAME.c_str()}
};

// Web server
AsyncWebServer server(80);
lv_obj_t *valve1Label;
lv_obj_t *valve2Label;
lv_obj_t *valve3Label;
lv_obj_t *valve4Label;
lv_obj_t *valve5Label;
lv_obj_t *valve6Label;
lv_obj_t *valve7Label;
lv_obj_t *valve8Label;
lv_obj_t *timeLabel;  // Label สำหรับแสดงเวลา
lv_obj_t *ipLabel;  // เพิ่ม label สำหรับแสดง IP
lv_obj_t *lastUpdateLabel;
lv_obj_t *temperatureLabel;
lv_obj_t *mqttLabel;
int count = 0;

// WiFi credentials
// ถ้าหน้าจอ เป็นสีตุ่นๆ ให้ดู ssid กับ password ว่าถูกต้องหรือไม่
//const char* ssid = "TP-Link_3800";
//const char* password = "46284143";
//const char* ssid = "Xiaomi 13";
//const char* password = "11111111";
const char* ssid = "dental";
const char* password = "doctorbng5";
// ตัวอย่างตารางเวลาเปิดวาล์ว
struct Schedule {
    int hour;
    int minute;
    int valveIndex;
    unsigned long duration;
};

Schedule schedules[] = {
    {8, 0, VALVE1_PIN, valve1Duration},   // วาล์ว 1 เปิด 8:00 30 นาที
    {12, 0, VALVE2_PIN, valve2Duration},  // วาล์ว 2 เปิด 12:00 45 นาที
    {18, 0, VALVE3_PIN, valve3Duration},   // วาล์ว 3 เปิด 18:00 1 ชั่วโมง
	{19, 0, VALVE4_PIN, valve4Duration},   // วาล์ว 4 เปิด 19:00 1 ชั่วโมง
	{20, 0, VALVE5_PIN, valve5Duration},   // วาล์ว 5 เปิด 20:00 1 ชั่วโมง
	{21, 0, VALVE6_PIN, valve6Duration},   // วาล์ว 6 เปิด 21:00 1 ชั่วโมง
	{22, 0, VALVE7_PIN, valve7Duration},   // วาล์ว 7 เปิด 22:00 1 ชั่วโมง
	{23, 0, VALVE8_PIN, valve8Duration}   // วาล์ว 8 เปิด 23:00 1 ชั่วโมง
};
// API Handlers
void handleGetStatus(AsyncWebServerRequest *request) {
  // Print request details
  Serial.println("GET /api/status");
  Serial.print("From IP: ");
  Serial.println(request->client()->remoteIP());
  
  StaticJsonDocument<200> doc;
  doc["valve1"] = VALVE1RUNNING;
  doc["valve2"] = VALVE2RUNNING;
  doc["valve3"] = VALVE3RUNNING;
  doc["valve4"] = VALVE4RUNNING;
  doc["valve5"] = VALVE5RUNNING;
  doc["valve6"] = VALVE6RUNNING;
  doc["valve7"] = VALVE7RUNNING;
  doc["valve8"] = VALVE8RUNNING;
  doc["time"] = String(timeinfo.tm_hour) + ":" +                 String(timeinfo.tm_min) + ":" +                 String(timeinfo.tm_sec);
  
  String response;
  serializeJson(doc, response);
  request->send(200, "application/json", response);
}

void handleControlValve(AsyncWebServerRequest *request) {
  // Print request details
  Serial.println("POST /api/valve");
  Serial.print("From IP: ");
  Serial.println(request->client()->remoteIP());
  
  // Print all parameters
  Serial.println("Parameters received:");
  int valve = 0;
  String action = "", chkparamvalve = "", chkparamaction = "", chkparamvalvenum = "", chkparamvalvename = "",valvename="",valvenum="";
  for(int i = 0; i < request->params(); i++) {
    const AsyncWebParameter* param = request->getParam(i);  // Changed to const pointer
    bool valveaction = false; // Changed to const pointer
    Serial.print(param->name());
    Serial.print(": ");
    Serial.println(param->value());
    if(param->name() == "valve"){
      valve = param->value().toInt();
      chkparamvalve = "OK";
    }
    if(param->name() == "action"){
      action = param->value();
      valveaction = action == "on" ? true : false;
      chkparamaction = "OK";
    }
    if(param->name() == "valvenum"){
      valvenum = param->value();
      chkparamvalvenum = "OK";
    }
    if(param->name() == "valvename"){
      valvename = param->value();
      chkparamvalvename = "OK";
    }
  }
  if (chkparamvalve == "OK" && chkparamaction == "OK") {
    // Print parameters
    Serial.print("Valve: ");    Serial.println(valve);    Serial.print("Action: ");    Serial.println(action);
    if (valve == 1) {
      if (action == "on") {        openValve(VALVE1_PIN);      } else if (action == "off") {        closeValve(VALVE1_PIN);      }
      Serial.println("Valve 1 turned "+String(VALVE1RUNNING));
    }else if (valve == 2) {
      if (action == "on") {        openValve(VALVE2_PIN);      } else if (action == "off") {        closeValve(VALVE2_PIN);      }
      Serial.println("Valve 2 turned "+String(VALVE2RUNNING));
    }else if (valve == 3) {
      if (action == "on") {        openValve(VALVE3_PIN);      } else if (action == "off") {        closeValve(VALVE3_PIN);      }
      Serial.println("Valve 3 turned "+String(VALVE3RUNNING));
    }else if (valve == 4) {
      if (action == "on") {        openValve(VALVE4_PIN);      } else if (action == "off") {        closeValve(VALVE4_PIN);      }
      Serial.println("Valve 4 turned "+String(VALVE4RUNNING));
    }else if (valve == 5) {
      if (action == "on") {        openValve(VALVE5_PIN);      } else if (action == "off") {        closeValve(VALVE5_PIN);      }
      Serial.println("Valve 5 turned "+String(VALVE5RUNNING));
    }else if (valve == 6) {
      if (action == "on") {         openValve(VALVE6_PIN);      } else if (action == "off") {        closeValve(VALVE6_PIN);      }
      Serial.println("Valve 6 turned "+String(VALVE6RUNNING));
    }else if (valve == 7) {
      if (action == "on") {         openValve(VALVE7_PIN);      } else if (action == "off") {        closeValve(VALVE7_PIN);      }
      Serial.println("Valve 7 turned "+String(VALVE7RUNNING));
    }else if (valve == 8) {
      if (action == "on") {         openValve(VALVE8_PIN);      } else if (action == "off") {        closeValve(VALVE8_PIN);      }
      Serial.println("Valve 8 turned "+String(VALVE8RUNNING));
    }
    request->send(200, "text/plain", "OK");
  }else if (chkparamvalve == "OK" && chkparamaction == "OK"){
    if(valvenum == "1"){      setValveName("1", valvename);
    }else if(valvenum == "2"){      setValveName("2", valvename);
    }else if(valvenum == "3"){      setValveName("3", valvename);
    }else if(valvenum == "4"){      setValveName("4", valvename);
    }else if(valvenum == "5"){      setValveName("5", valvename);
    }else if(valvenum == "6"){      setValveName("6", valvename);
    }else if(valvenum == "7"){      setValveName("7", valvename);
    }else if(valvenum == "8"){      setValveName("8", valvename);
    }
  } else {
    Serial.println("Missing parameters");
    request->send(400, "text/plain", "Missing parameters");
  }
}
void updateTimeDisplay() {
  if(!getLocalTime(&timeinfo)){
    lv_label_set_text(timeLabel, "Time: Error");
    return;
  }
  char timeStr[20];
  sprintf(timeStr, "Time: %02d:%02d:%02d",           timeinfo.tm_hour,           timeinfo.tm_min,           timeinfo.tm_sec);
  lv_label_set_text(timeLabel, timeStr);
}
void openValve(int valvePin) {
  Serial.println("openValve "+String(valvePin));
  //setValveRunning(valvePin, true);
  if(valvePin==VALVE1_PIN){    setValveTimerStart(VALVE1_PIN, Duration);
  }else if(valvePin==VALVE2_PIN){    setValveTimerStart(VALVE2_PIN, Duration);
  }else if(valvePin==VALVE3_PIN){    setValveTimerStart(VALVE3_PIN, Duration);
  }else if(valvePin==VALVE4_PIN){    setValveTimerStart(VALVE4_PIN, Duration);
  }else if(valvePin==VALVE5_PIN){    setValveTimerStart(VALVE5_PIN, Duration);
  }else if(valvePin==VALVE6_PIN){    setValveTimerStart(VALVE6_PIN, Duration);
  }else if(valvePin==VALVE7_PIN){    setValveTimerStart(VALVE7_PIN, Duration);
  }else if(valvePin==VALVE8_PIN){    setValveTimerStart(VALVE8_PIN, Duration);
  }
  setLabel();
}
void closeValve(int valvePin) {
  Serial.println("closeValve "+String(valvePin));
  //setValveRunning(valvePin, false);
	if(valvePin==VALVE1_PIN){    digitalWrite(VALVE1_PIN, LOW);    VALVE1RUNNING = false;VALVES[0].isRunning = false;
	}else if(valvePin==VALVE2_PIN){    digitalWrite(VALVE2_PIN, LOW);    VALVE2RUNNING = false;VALVES[1].isRunning = false;
	}else if(valvePin==VALVE3_PIN){    digitalWrite(VALVE3_PIN, LOW);    VALVE3RUNNING = false;VALVES[2].isRunning = false;
	}else if(valvePin==VALVE4_PIN){    digitalWrite(VALVE4_PIN, LOW);    VALVE4RUNNING = false;VALVES[3].isRunning = false;
	}else if(valvePin==VALVE5_PIN){    digitalWrite(VALVE5_PIN, LOW);    VALVE5RUNNING = false;VALVES[4].isRunning = false;
	}else if(valvePin==VALVE6_PIN){    digitalWrite(VALVE6_PIN, LOW);    VALVE6RUNNING = false;VALVES[5].isRunning = false;
	}else if(valvePin==VALVE7_PIN){    digitalWrite(VALVE7_PIN, LOW);    VALVE7RUNNING = false;VALVES[6].isRunning = false;
	}else if(valvePin==VALVE8_PIN){    digitalWrite(VALVE8_PIN, LOW);    VALVE8RUNNING = false;VALVES[7].isRunning = false;
	}
	setLabel();
}
void setLabel(){
	//ทำแบบนี้ เพราะว่า กดปุ่มที่มีการเปิดปิดวาล์ว จะทำให้ปุ่มนี้มีการกดซ้ำได้ จึงต้องมีการตรวจสอบก่อน  
	if(VALVE1RUNNING){    lv_label_set_text(valve1Label, (VALVE1NAME+"  ON "+String(valve1Duration/60000)+" min").c_str());  }else{    lv_label_set_text(valve1Label, (VALVE1NAME+" OFF").c_str());  }
	if(VALVE2RUNNING){    lv_label_set_text(valve2Label, (VALVE2NAME+"  ON "+String(valve2Duration/60000)+" min").c_str());  }else{    lv_label_set_text(valve2Label, (VALVE2NAME+" OFF").c_str());  }
	if(VALVE3RUNNING){    lv_label_set_text(valve3Label, (VALVE3NAME+"  ON "+String(valve3Duration/60000)+" min").c_str());  }else{    lv_label_set_text(valve3Label, (VALVE3NAME+" OFF").c_str());  }
	if(VALVE4RUNNING){    lv_label_set_text(valve4Label, (VALVE4NAME+"  ON "+String(valve4Duration/60000)+" min").c_str());  }else{    lv_label_set_text(valve4Label, (VALVE4NAME+" OFF").c_str());  }
	if(VALVE5RUNNING){    lv_label_set_text(valve5Label, (VALVE5NAME+"  ON "+String(valve5Duration/60000)+" min").c_str());  }else{    lv_label_set_text(valve5Label, (VALVE5NAME+" OFF").c_str());  }
	if(VALVE6RUNNING){    lv_label_set_text(valve6Label, (VALVE6NAME+"  ON "+String(valve6Duration/60000)+" min").c_str());  }else{    lv_label_set_text(valve6Label, (VALVE6NAME+" OFF").c_str());  }
	if(VALVE7RUNNING){    lv_label_set_text(valve7Label, (VALVE7NAME+"  ON "+String(valve7Duration/60000)+" min").c_str());  }else{    lv_label_set_text(valve7Label, (VALVE7NAME+" OFF").c_str());  }
	if(VALVE8RUNNING){    lv_label_set_text(valve8Label, (VALVE8NAME+"  ON "+String(valve8Duration/60000)+" min").c_str());  }else{    lv_label_set_text(valve8Label, (VALVE8NAME+" OFF").c_str());  }
}
// ฟังก์ชันสำหรับบันทึกค่า config ลงไฟล์
void saveConfig(String saveType = "all") {
  File configFile = SPIFFS.open("/config.json", "r");
  StaticJsonDocument<1024> doc;
  
  // ถ้ามีไฟล์อยู่แล้ว ให้โหลดค่าที่มีอยู่ก่อน
  if(configFile) {
    DeserializationError error = deserializeJson(doc, configFile);
    configFile.close();
    if(error) {
      Serial.println("Failed to parse existing config file");
    }
  }

  // เปิดไฟล์ใหม่สำหรับเขียน
  configFile = SPIFFS.open("/config.json", "w");
  if(!configFile) {
    Serial.println("Failed to open config file for writing");
    return;
  }

  // บันทึกค่าตามประเภทที่ต้องการ
  if(saveType == "all" || saveType == "names") {
    // บันทึกชื่อวาล์ว
    doc["valve1Name"] = VALVE1NAME;
    doc["valve2Name"] = VALVE2NAME;
    doc["valve3Name"] = VALVE3NAME;
    doc["valve4Name"] = VALVE4NAME;
    doc["valve5Name"] = VALVE5NAME;
    doc["valve6Name"] = VALVE6NAME;
    doc["valve7Name"] = VALVE7NAME;
    doc["valve8Name"] = VALVE8NAME;
  }

  if(saveType == "all" || saveType == "durations") {
    // บันทึกระยะเวลาเปิดวาล์ว
    doc["valve1Duration"] = valve1Duration;
    doc["valve2Duration"] = valve2Duration;
    doc["valve3Duration"] = valve3Duration;
    doc["valve4Duration"] = valve4Duration;
    doc["valve5Duration"] = valve5Duration;
    doc["valve6Duration"] = valve6Duration;
    doc["valve7Duration"] = valve7Duration;
    doc["valve8Duration"] = valve8Duration;
  }

  if(saveType == "all" || saveType == "schedules") {
    // บันทึกตารางเวลา
    JsonArray scheduleArray = doc.createNestedArray("schedules");
    for(int i = 0; i < sizeof(schedules)/sizeof(schedules[0]); i++) {
      JsonObject schedule = scheduleArray.createNestedObject();
      schedule["hour"] = schedules[i].hour;
      schedule["minute"] = schedules[i].minute;
      schedule["valveIndex"] = schedules[i].valveIndex;
      schedule["duration"] = schedules[i].duration;
    }
  }

  if(serializeJson(doc, configFile) == 0) {
    Serial.println("Failed to write to config file");
  }
  configFile.close();
  Serial.println("Config saved successfully - " + saveType);
}
void setValveName(String valve, String name) {
  if(valve=="1"){VALVE1NAME=name;}
  else if(valve=="2"){VALVE2NAME=name;}
  else if(valve=="3"){VALVE3NAME=name;}
  else if(valve=="4"){VALVE4NAME=name;}
  else if(valve=="5"){VALVE5NAME=name;}
  else if(valve=="6"){VALVE6NAME=name;}
  else if(valve=="7"){VALVE7NAME=name;}
  else if(valve=="8"){VALVE8NAME=name;}
  
  saveConfig("names"); // บันทึกเฉพาะชื่อวาล์ว
}
void setValveDuration(String valve, String duration) {
  if(valve=="1"){valve1Duration=duration.toInt(); VALVES[0].duration = valve1Duration;}
  else if(valve=="2"){valve2Duration=duration.toInt(); VALVES[1].duration = valve2Duration;}
  else if(valve=="3"){valve3Duration=duration.toInt(); VALVES[2].duration = valve3Duration;}
  else if(valve=="4"){valve4Duration=duration.toInt(); VALVES[3].duration = valve4Duration;}
  else if(valve=="5"){valve5Duration=duration.toInt(); VALVES[4].duration = valve5Duration;}
  else if(valve=="6"){valve6Duration=duration.toInt(); VALVES[5].duration = valve6Duration;}
  else if(valve=="7"){valve7Duration=duration.toInt(); VALVES[6].duration = valve7Duration;}
  else if(valve=="8"){valve8Duration=duration.toInt(); VALVES[7].duration = valve8Duration;}
  
  saveConfig("durations"); // บันทึกเฉพาะระยะเวลา
}
void setValveTimerStart(int valvePin,unsigned long duration) {
  Serial.println("setValveTimerStart "+String(valvePin)+" "+String(duration));
  if(valvePin==VALVE1_PIN){
    valve1StartTime = millis();    valve1Duration = duration;    VALVE1RUNNING = true;    digitalWrite(VALVE1_PIN, HIGH);VALVES[0].isRunning = true;VALVES[0].startTime = millis();VALVES[0].duration = duration;
  }else if(valvePin==VALVE2_PIN){
    valve2StartTime = millis();    valve2Duration = duration;    VALVE2RUNNING = true;    digitalWrite(VALVE2_PIN, HIGH);VALVES[1].isRunning = true;VALVES[1].startTime = millis();VALVES[1].duration = duration;
  }else if(valvePin==VALVE3_PIN){
    valve3StartTime = millis();    valve3Duration = duration;    VALVE3RUNNING = true;    digitalWrite(VALVE3_PIN, HIGH);VALVES[2].isRunning = true;VALVES[2].startTime = millis();VALVES[2].duration = duration;
  }else if(valvePin==VALVE4_PIN){
    valve4StartTime = millis();    valve4Duration = duration;    VALVE4RUNNING = true;    digitalWrite(VALVE4_PIN, HIGH);VALVES[3].isRunning = true;VALVES[3].startTime = millis();VALVES[3].duration = duration;
  }else if(valvePin==VALVE5_PIN){
    valve5StartTime = millis();    valve5Duration = duration;    VALVE5RUNNING = true;    digitalWrite(VALVE5_PIN, HIGH);VALVES[4].isRunning = true;VALVES[4].startTime = millis();VALVES[4].duration = duration;
  }else if(valvePin==VALVE6_PIN){
    valve6StartTime = millis();    valve6Duration = duration;    VALVE6RUNNING = true;    digitalWrite(VALVE6_PIN, HIGH);VALVES[5].isRunning = true;VALVES[5].startTime = millis();VALVES[5].duration = duration;
  }else if(valvePin==VALVE7_PIN){
    valve7StartTime = millis();    valve7Duration = duration;    VALVE7RUNNING = true;    digitalWrite(VALVE7_PIN, HIGH);VALVES[6].isRunning = true;VALVES[6].startTime = millis();VALVES[6].duration = duration;
  }else if(valvePin==VALVE8_PIN){
    valve8StartTime = millis();    valve8Duration = duration;    VALVE8RUNNING = true;    digitalWrite(VALVE8_PIN, HIGH);VALVES[7].isRunning = true;VALVES[7].startTime = millis();VALVES[7].duration = duration;
  }
}
void checkValve1Timer() {
  if (VALVE1RUNNING) {
    unsigned long currentTime = millis();
    if (currentTime - valve1StartTime >= valve1Duration) {
        VALVE1RUNNING = false;
        digitalWrite(VALVE1_PIN, LOW);  // ปิดวาล์ว
    }
  }
  if (VALVE2RUNNING) {
    //Serial.println("checkValve1Timer VALVE2RUNNING");
      unsigned long currentTime = millis();
      if (currentTime - valve2StartTime >= valve2Duration) {
          VALVE2RUNNING = false;
          digitalWrite(VALVE2_PIN, LOW);  // ปิดวาล์ว
      }
  }
  if (VALVE3RUNNING) {
      unsigned long currentTime = millis(); 
      if (currentTime - valve3StartTime >= valve3Duration) {  
          VALVE3RUNNING = false;
          digitalWrite(VALVE3_PIN, LOW);  // ปิดวาล์ว
      }
  }
  if (VALVE4RUNNING) {
      unsigned long currentTime = millis();
      if (currentTime - valve4StartTime >= valve4Duration) {
          VALVE4RUNNING = false;
          digitalWrite(VALVE4_PIN, LOW);  // ปิดวาล์ว
      }
  }
  if (VALVE5RUNNING) {
      unsigned long currentTime = millis();
      if (currentTime - valve5StartTime >= valve5Duration) {
          VALVE5RUNNING = false;
          digitalWrite(VALVE5_PIN, LOW);  // ปิดวาล์ว
      }
  }
  if (VALVE6RUNNING) {
      unsigned long currentTime = millis();
      if (currentTime - valve6StartTime >= valve6Duration) {
          VALVE6RUNNING = false;
          digitalWrite(VALVE6_PIN, LOW);  // ปิดวาล์ว
      }
  }
  if (VALVE7RUNNING) {
      unsigned long currentTime = millis();
      if (currentTime - valve7StartTime >= valve7Duration) {
          VALVE7RUNNING = false;
          digitalWrite(VALVE7_PIN, LOW);  // ปิดวาล์ว
      }
  }
  if (VALVE8RUNNING) {
      unsigned long currentTime = millis();
      if (currentTime - valve8StartTime >= valve8Duration) {
          VALVE8RUNNING = false;
          digitalWrite(VALVE8_PIN, LOW);  // ปิดวาล์ว
      }
  }
}
// ฟังก์ชันอัพเดทสถานะบนจอ
void updateDisplay() {
    for(int i = 0; i < 8; i++) {
        if(VALVES[i].isRunning) {
            unsigned long remainingTime = VALVES[i].duration - ((millis()) - VALVES[i].startTime);
			//Serial.println("updateDisplay "+String(VALVES[i].duration)+" "+String(VALVES[i].startTime)+" "+String(remainingTime));
            int minutes = remainingTime / 60000;
            int seconds = (remainingTime % 60000) / 1000;
            String status = String(VALVES[i].name) + " ON " + String(minutes) + ":" + String(seconds);
            // อัพเดท label ตาม index
            switch(i) {
                case 0: lv_label_set_text(valve1Label, status.c_str()); break;
                case 1: lv_label_set_text(valve2Label, status.c_str()); break;
                case 2: lv_label_set_text(valve3Label, status.c_str()); break;
                case 3: lv_label_set_text(valve4Label, status.c_str()); break;
                case 4: lv_label_set_text(valve5Label, status.c_str()); break;
                case 5: lv_label_set_text(valve6Label, status.c_str()); break;
                case 6: lv_label_set_text(valve7Label, status.c_str()); break;
                case 7: lv_label_set_text(valve8Label, status.c_str()); break;
            }
        } else {
            String status = String(VALVES[i].name) + " OFF";
            // อัพเดท label ตาม index
            switch(i) {
                case 0: lv_label_set_text(valve1Label, status.c_str()); break;
                case 1: lv_label_set_text(valve2Label, status.c_str()); break;
                case 2: lv_label_set_text(valve3Label, status.c_str()); break;
                case 3: lv_label_set_text(valve4Label, status.c_str()); break;
                case 4: lv_label_set_text(valve5Label, status.c_str()); break;
                case 5: lv_label_set_text(valve6Label, status.c_str()); break;
                case 6: lv_label_set_text(valve7Label, status.c_str()); break;
                case 7: lv_label_set_text(valve8Label, status.c_str()); break;
            }
        }
    }
}
void updateDisplay1() {
	if (VALVE1RUNNING) {
		unsigned long remainingTime = valve1Duration - (millis() - valve1StartTime);
		int minutes = remainingTime / 60000;
		int seconds = (remainingTime % 60000) / 1000;
		// แสดงเวลาที่เหลือบนจอ
		lv_label_set_text(valve1Label, (String(VALVE1NAME) + " ON " + String(minutes) + ":" + String(seconds)).c_str());
	} else {
		lv_label_set_text(valve1Label, (String(VALVE1NAME) + " OFF").c_str());
  	}
	if (VALVE2RUNNING) {
		unsigned long remainingTime = valve2Duration - (millis() - valve2StartTime);
		int minutes = remainingTime / 60000;
		int seconds = (remainingTime % 60000) / 1000;
		lv_label_set_text(valve2Label, (String(VALVE2NAME) + " ON " + String(minutes) + ":" + String(seconds)).c_str());
	} else {
		lv_label_set_text(valve2Label, (String(VALVE2NAME) + " OFF").c_str());
	}
	if (VALVE3RUNNING) {
		unsigned long remainingTime = valve3Duration - (millis() - valve3StartTime);
		int minutes = remainingTime / 60000;
		int seconds = (remainingTime % 60000) / 1000;
		lv_label_set_text(valve3Label, (String(VALVE3NAME) + " ON " + String(minutes) + ":" + String(seconds)).c_str());
	} else {
		lv_label_set_text(valve3Label, (String(VALVE3NAME) + " OFF").c_str());	
	}
	if (VALVE4RUNNING) {
		unsigned long remainingTime = valve4Duration - (millis() - valve4StartTime);
		int minutes = remainingTime / 60000;
		int seconds = (remainingTime % 60000) / 1000;
		lv_label_set_text(valve4Label, (String(VALVE4NAME) + " ON " + String(minutes) + ":" + String(seconds)).c_str());
	} else {
		lv_label_set_text(valve4Label, (String(VALVE4NAME) + " OFF").c_str());
	}
	if (VALVE5RUNNING) {
		unsigned long remainingTime = valve5Duration - (millis() - valve5StartTime);
		int minutes = remainingTime / 60000;
		int seconds = (remainingTime % 60000) / 1000;
		lv_label_set_text(valve5Label, (String(VALVE5NAME) + " ON " + String(minutes) + ":" + String(seconds)).c_str());
	} else {
		lv_label_set_text(valve5Label, (String(VALVE5NAME) + " OFF").c_str());
	}
	if (VALVE6RUNNING) {
		unsigned long remainingTime = valve6Duration - (millis() - valve6StartTime);
		int minutes = remainingTime / 60000;
		int seconds = (remainingTime % 60000) / 1000;
		lv_label_set_text(valve6Label, (String(VALVE6NAME) + " ON " + String(minutes) + ":" + String(seconds)).c_str());
	} else {
		lv_label_set_text(valve6Label, (String(VALVE6NAME) + " OFF").c_str());
	}
	if (VALVE7RUNNING) {
		unsigned long remainingTime = valve7Duration - (millis() - valve7StartTime);
		int minutes = remainingTime / 60000;
		int seconds = (remainingTime % 60000) / 1000;
		lv_label_set_text(valve7Label, (String(VALVE7NAME) + " ON " + String(minutes) + ":" + String(seconds)).c_str());
	} else {
		lv_label_set_text(valve7Label, (String(VALVE7NAME) + " OFF").c_str());
	}
	if (VALVE8RUNNING) {
		unsigned long remainingTime = valve8Duration - (millis() - valve8StartTime);
		int minutes = remainingTime / 60000;
		int seconds = (remainingTime % 60000) / 1000;
		lv_label_set_text(valve8Label, (String(VALVE8NAME) + " ON " + String(minutes) + ":" + String(seconds)).c_str());
	} else {
		lv_label_set_text(valve8Label, (String(VALVE8NAME) + " OFF").c_str());
	}
}
void initLabel(){
  lastUpdateLabel = lv_label_create(lv_scr_act());
  lv_label_set_text(lastUpdateLabel, "connect wifi");
  lv_obj_align(lastUpdateLabel, LV_ALIGN_BOTTOM_LEFT, 10, -5);
  lv_obj_set_style_text_color(lastUpdateLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);
  lv_label_set_text(lastUpdateLabel, "2025-04-01");
  
  // Create time display label with larger font
  timeLabel = lv_label_create(lv_scr_act());
  lv_label_set_text(timeLabel, "Time: --:--:--");
  lv_obj_set_style_text_color(timeLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);
  //lv_obj_set_style_text_scale(timeLabel, 200, LV_PART_MAIN | LV_STATE_DEFAULT);  // เพิ่มขนาดตัวอักษรเป็น 2 เท่า
  lv_obj_align(timeLabel, LV_ALIGN_TOP_LEFT, 10, 10);
  
  // Create IP display label
  ipLabel = lv_label_create(lv_scr_act());
  //lv_label_set_text(ipLabel, WiFi.localIP().toString().c_str());    //ต้อง set หลัง WIFI connected
  lv_obj_set_style_text_color(ipLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);
  lv_obj_align(ipLabel, LV_ALIGN_TOP_RIGHT, -10, 10);

  // Create valve control label
  valve1Label = lv_label_create(lv_scr_act());
  lv_label_set_text(valve1Label, "Valve1 Control");
  lv_obj_align(valve1Label, LV_ALIGN_TOP_LEFT, 5, 30);  // เลื่อนขึ้น 20 pixels
  
  valve2Label = lv_label_create(lv_scr_act());
  lv_label_set_text(valve2Label, "Valve2 Control");
  lv_obj_align(valve2Label, LV_ALIGN_TOP_LEFT, 5, 50);  // เลื่อนลง 20 pixels

  valve3Label = lv_label_create(lv_scr_act());
  lv_label_set_text(valve3Label, "Valve3 Control");
  lv_obj_align(valve3Label, LV_ALIGN_TOP_LEFT, 5, 70);  // เลื่อนลง 20 pixels

  valve4Label = lv_label_create(lv_scr_act());
  lv_label_set_text(valve4Label, "Valve4 Control");
  lv_obj_align(valve4Label, LV_ALIGN_TOP_LEFT, 5, 90);  // เลื่อนลง 20 pixels

  valve5Label = lv_label_create(lv_scr_act());
  lv_label_set_text(valve5Label, "Valve5 Control");
  lv_obj_align(valve5Label, LV_ALIGN_TOP_RIGHT, 0, 30);  // เลื่อนลง 20 pixels

  valve6Label = lv_label_create(lv_scr_act());
  lv_label_set_text(valve6Label, "Valve6 Control");
  lv_obj_align(valve6Label, LV_ALIGN_TOP_RIGHT, 0, 50);  // เลื่อนลง 20 pixels

  valve7Label = lv_label_create(lv_scr_act());
  lv_label_set_text(valve7Label, "Valve7 Control");
  lv_obj_align(valve7Label, LV_ALIGN_TOP_RIGHT, 0, 70);  // เลื่อนลง 20 pixels

  valve8Label = lv_label_create(lv_scr_act());
  lv_label_set_text(valve8Label, "Valve8 Control");
  lv_obj_align(valve8Label, LV_ALIGN_TOP_RIGHT, 0, 90);  // เลื่อนลง 20 pixels

  temperatureLabel = lv_label_create(lv_scr_act());
  lv_label_set_text(temperatureLabel, "Temperature: --°C");
  lv_obj_set_style_text_color(temperatureLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);
  lv_obj_align(temperatureLabel, LV_ALIGN_BOTTOM_LEFT, 10, -20);  // เลื่อนลง 20 pixels

  mqttLabel = lv_label_create(lv_scr_act());
  lv_label_set_text(mqttLabel, "MQTT: --");
  lv_obj_set_style_text_color(mqttLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);
  lv_obj_align(mqttLabel, LV_ALIGN_BOTTOM_RIGHT, -40, -5);  // เลื่อนลง 20 pixels
}
void openValveSchedule(){
	// ตัวอย่างการตั้งเวลาเปิดวาล์วตามตารางเวลา
  if(timeinfo.tm_hour == 5 && timeinfo.tm_min == 0) {  // เปิดเวลา 5:00
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
    //setValveTimerStart(1, valve1Duration);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 6 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 7 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 8 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 9 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 10 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 11 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 12 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 13 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 14 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 15 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 16 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 17 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }else if(timeinfo.tm_hour == 18 && timeinfo.tm_min == 0){
    //setValveTimerStart("1", 30 * 60 * 1000);  // เปิด 30 นาที
  }
}
// ฟังก์ชันตั้งเวลาเปิดวาล์ว
void setValveTimer(int valveIndex, unsigned long duration) {
    if(valveIndex >= 0 && valveIndex < 8) {
        VALVES[valveIndex].duration = duration;
        VALVES[valveIndex].startTime = millis();
        VALVES[valveIndex].state = OPENING;
        digitalWrite(VALVES[valveIndex].pin, HIGH);
        VALVES[valveIndex].isRunning = true;
    }
}
// ฟังก์ชันตรวจสอบและควบคุมวาล์ว
void checkValves() {
    unsigned long currentTime = millis();
    for(int i = 0; i < 8; i++) {
        switch(VALVES[i].state) {
            case IDLE:
                // รอคำสั่งเปิด
                break;
            case OPENING:
                // เปิดวาล์ว
                VALVES[i].state = RUNNING;
                break;
            case RUNNING:
                // ตรวจสอบเวลาเปิด
                if(currentTime - VALVES[i].startTime >= VALVES[i].duration) {
                    VALVES[i].state = CLOSING;
                    digitalWrite(VALVES[i].pin, LOW);
                    VALVES[i].isRunning = false;
                }
                break;
            case CLOSING:
                // ปิดวาล์ว
                VALVES[i].state = IDLE;
                break;
        }
    }
}
void setup() {
	// put your setup code here, to run once:
	Serial.begin(115200);
	Display.begin();  Display.useLVGL();  Switch.begin();
	
	// Initialize watchdog timer
	//esp_task_wdt_init(30, true); // 30 seconds timeout
	//esp_task_wdt_add(NULL); // Add current task to watchdog
	
	// Initialize SPIFFS
	if(!SPIFFS.begin(true)){
		Serial.println("An error occurred while mounting SPIFFS");
		return;
	}
	Serial.println("SPIFFS mounted successfully");
	
	// Load configuration
	loadConfig();
	
	// Set background color to orange when WiFi is connected
	lv_obj_set_style_bg_color(lv_scr_act(), lv_color_make(255, 165, 0), LV_PART_MAIN | LV_STATE_DEFAULT);
	initLabel();

	// Setup valve pins as outputs
	pinMode(VALVE1_PIN, OUTPUT);  pinMode(VALVE2_PIN, OUTPUT);  pinMode(VALVE3_PIN, OUTPUT);  pinMode(VALVE4_PIN, OUTPUT);
	pinMode(VALVE5_PIN, OUTPUT);  pinMode(VALVE6_PIN, OUTPUT);  pinMode(VALVE7_PIN, OUTPUT);  pinMode(VALVE8_PIN, OUTPUT);
	digitalWrite(VALVE1_PIN, LOW);  digitalWrite(VALVE2_PIN, LOW);  digitalWrite(VALVE3_PIN, LOW);  digitalWrite(VALVE4_PIN, LOW);
	digitalWrite(VALVE5_PIN, LOW);  digitalWrite(VALVE6_PIN, LOW);  digitalWrite(VALVE7_PIN, LOW);  digitalWrite(VALVE8_PIN, LOW);

	// ตั้งค่า Static IP
	IPAddress local_IP(172, 25, 10, 246);    // IP ที่ต้องการ
	IPAddress gateway(172, 25, 255, 1);       // Gateway (มักเป็น IP ของ router)
	IPAddress subnet(255, 255, 0, 0);      // Subnet mask
	IPAddress primaryDNS(8, 8, 8, 8);        // DNS หลัก (Google DNS)
	IPAddress secondaryDNS(8, 8, 4, 4);      // DNS รอง (Google DNS)

	// ตั้งค่า Static IP
	//if (!WiFi.config(local_IP, gateway, subnet, primaryDNS, secondaryDNS)) {
	//  Serial.println("STA Failed to configure");
	//}
	
	// เชื่อมต่อ WiFi
	WiFi.begin(ssid, password);
	while (WiFi.status() != WL_CONNECTED) {
		delay(500);
		Serial.print("+");
	}
	
	Serial.println("WiFi connected");
	Serial.print("IP address: ");
	Serial.println(WiFi.localIP());
	lv_label_set_text(ipLabel, WiFi.localIP().toString().c_str());
	// Configure time
	configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  // Button handlers
  Switch.onPressed(A, []() {
    //Serial.println("Switch.onPressed A");
    if(VALVE1RUNNING){
      closeValve(VALVE1_PIN);
      Serial.println("Switch.onPressed A false");
    }else{
      openValve(VALVE1_PIN);
      Serial.println("Switch.onPressed A true");
    }
  });
  Switch.onPressed(B, []() {
    if(VALVE2RUNNING){
      closeValve(VALVE2_PIN);
      Serial.println("Switch.onPressed B false");
    }else{
      openValve(VALVE2_PIN);
      Serial.println("Switch.onPressed B true");
    }
  });
  Switch.onPressed(C, []() {
    if(VALVE3RUNNING){
      closeValve(VALVE3_PIN);
      Serial.println("Switch.onPressed C false");
    }else{
      openValve(VALVE3_PIN);
      Serial.println("Switch.onPressed C true");
    }
  });
    // Setup API endpoints
  server.on("/api/status", HTTP_GET, handleGetStatus);
  server.on("/api/valve", HTTP_POST, handleControlValve);
  server.begin();
	setValveName("1", "Valve1");  setValveName("2", "Valve2");  setValveName("3", "Valve3");  setValveName("4", "Valve4");  setValveName("5", "Valve5");  setValveName("6", "Valve6");  setValveName("7", "Valve7");  setValveName("8", "Valve8");
	dht.setup(DHTPIN, DHTesp::DHT22);  // แก้ไขจาก dht.begin() เป็น dht.setup()
	
	// Setup MQTT
	mqttClient.setServer(mqtt_server, mqtt_port);
	mqttClient.setClientId(mqtt_client_id);
	mqttClient.setKeepAlive(5).setWill("smartfarm/status", 2, true, "offline");
	//mqttClient.setCredentials(MQTT_USERNAME, MQTT_PASSWORD);
	
	// Setup MQTT callbacks
	mqttClient.onConnect(onMqttConnect);
	mqttClient.onDisconnect(onMqttDisconnect);
	mqttClient.onPublish(onMqttPublish);
}

void loop() {
  // put your main code here, to run repeatedly:
  Display.loop();
  Switch.loop();
  
  // Reset watchdog timer
  //esp_task_wdt_reset();
  
  // Update time display
  updateTimeDisplay();
  openValveSchedule();

  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi connection lost. Reconnecting...");
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
      delay(500);
      Serial.print(".");
    }
    Serial.println("\nReconnected to WiFi");
  }

  // ตรวจสอบเวลาและปิดวาล์ว
  checkValve1Timer();
  // ตรวจสอบและควบคุมวาล์ว
  checkValves();
  // อัพเดทสถานะบนจอ
  updateDisplay();

  unsigned long currentTime = millis();
  if (currentTime - lastReadTime >= READ_INTERVAL) {
    checkTemperature();
    if (mqttClient.connected()) {
      publishTemperature();
    } else {
      connectMQTT();
    }
    lastReadTime = currentTime;
  }
}

// ตัวอย่างการตั้งเวลาเปิดวาล์วตามเงื่อนไข
void checkConditions() {
    // ตัวอย่าง: เปิดวาล์วเมื่ออุณหภูมิสูงเกิน 30°C
    if(temperature > 30) {
        setValveTimer(0, 15 * 60 * 1000);  // เปิดวาล์ว 1 15 นาที
    }
    
    // ตัวอย่าง: เปิดวาล์วเมื่อความชื้นต่ำกว่า 40%
    if(humidity < 40) {
        setValveTimer(1, 20 * 60 * 1000);  // เปิดวาล์ว 2 20 นาที
    }
}

void checkSchedules() {
    for(int i = 0; i < 3; i++) {
        if(timeinfo.tm_hour == schedules[i].hour && 
           timeinfo.tm_min == schedules[i].minute) {
            setValveTimer(schedules[i].valveIndex, schedules[i].duration);
        }
    }
}

// Method สำหรับอ่านค่า DHT22
bool checkDHT22() {
    float temp = dht.getTemperature();
    float hum = dht.getHumidity();
    
    if (dht.getStatus() == DHTesp::ERROR_NONE) {
        temperature = temp;
        humidity = hum;
        
        // แสดงผลใน Serial Monitor
        Serial.printf("T: %.1f°C, H: %.1f%%\n", temperature, humidity);
        
        // แสดงผลใน temperatureLabel
        String tempText = "T: " + String(temperature, 1) + "°C, H: " + String(humidity, 1) + "%";
        lv_label_set_text(temperatureLabel, tempText.c_str());
        
        // เปลี่ยนสีข้อความเป็นสีขาว (ปกติ)
        lv_obj_set_style_text_color(temperatureLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);
        return true;  // อ่านค่าได้สำเร็จ
    } else {
        // กรณีอ่านค่าไม่ได้
        Serial.println("DHT22 Error: " + String(dht.getStatusString()));
        lv_label_set_text(temperatureLabel, "DHT22 Error: Sensor not found");
        lv_obj_set_style_text_color(temperatureLabel, lv_color_make(255, 0, 0), LV_PART_MAIN | LV_STATE_DEFAULT);
        return false;  // อ่านค่าไม่สำเร็จ
    }
}

// Method สำหรับอ่านค่า DS18B20
bool checkDS18B20() {
    ds18b20.requestTemperatures();
    float temp = ds18b20.getTempCByIndex(0);
    if (temp != DEVICE_DISCONNECTED_C) {
        temperature = temp;
        // แสดงผลใน Serial Monitor
        Serial.printf("Temperature (DS18B20): %.1f°C\n", temperature);
        // แสดงผลใน temperatureLabel
        String tempText = "T: " + String(temperature, 1) + "°C";
        lv_label_set_text(temperatureLabel, tempText.c_str());
        // เปลี่ยนสีข้อความเป็นสีขาว (ปกติ)
        lv_obj_set_style_text_color(temperatureLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);
        return true;  // อ่านค่าได้สำเร็จ
    } else {
        // กรณีอ่านค่าไม่ได้
        Serial.println("DS18B20 Error: Could not read temperature");
        lv_label_set_text(temperatureLabel, "DS18B20 Error: Sensor not found");
        lv_obj_set_style_text_color(temperatureLabel, lv_color_make(255, 0, 0), LV_PART_MAIN | LV_STATE_DEFAULT);
        return false;  // อ่านค่าไม่สำเร็จ
    }
}

// Method หลักสำหรับตรวจสอบอุณหภูมิ
void checkTemperature() {
    if (!useDS18B20) {
        // ลองอ่านค่า DHT22 ก่อน
        if (!checkDHT22()) {
            // ถ้า DHT22 ไม่ทำงาน ให้ลองใช้ DS18B20
            Serial.println("DHT22 Error, trying DS18B20");
            useDS18B20 = true;
            checkDS18B20();
        }
    } else {
        // ใช้ DS18B20
        checkDS18B20();
    }
}

// ฟังก์ชันสำหรับโหลดค่า config จากไฟล์
void loadConfig() {
  if(SPIFFS.exists("/config.json")) {
    File configFile = SPIFFS.open("/config.json", "r");
    if(!configFile) {
      Serial.println("Failed to open config file");
      return;
    }

    StaticJsonDocument<1024> doc;
    DeserializationError error = deserializeJson(doc, configFile);
    configFile.close();

    if(error) {
      Serial.println("Failed to parse config file");
      return;
    }

    // โหลดค่าต่างๆ จาก config
    if(doc.containsKey("valve1Name")) VALVE1NAME = doc["valve1Name"].as<String>();
    if(doc.containsKey("valve2Name")) VALVE2NAME = doc["valve2Name"].as<String>();
    if(doc.containsKey("valve3Name")) VALVE3NAME = doc["valve3Name"].as<String>();
    if(doc.containsKey("valve4Name")) VALVE4NAME = doc["valve4Name"].as<String>();
    if(doc.containsKey("valve5Name")) VALVE5NAME = doc["valve5Name"].as<String>();
    if(doc.containsKey("valve6Name")) VALVE6NAME = doc["valve6Name"].as<String>();
    if(doc.containsKey("valve7Name")) VALVE7NAME = doc["valve7Name"].as<String>();
    if(doc.containsKey("valve8Name")) VALVE8NAME = doc["valve8Name"].as<String>();

    if(doc.containsKey("valve1Duration")) valve1Duration = doc["valve1Duration"];
    if(doc.containsKey("valve2Duration")) valve2Duration = doc["valve2Duration"];
    if(doc.containsKey("valve3Duration")) valve3Duration = doc["valve3Duration"];
    if(doc.containsKey("valve4Duration")) valve4Duration = doc["valve4Duration"];
    if(doc.containsKey("valve5Duration")) valve5Duration = doc["valve5Duration"];
    if(doc.containsKey("valve6Duration")) valve6Duration = doc["valve6Duration"];
    if(doc.containsKey("valve7Duration")) valve7Duration = doc["valve7Duration"];
    if(doc.containsKey("valve8Duration")) valve8Duration = doc["valve8Duration"];

    Serial.println("Config loaded successfully");
  } else {
    Serial.println("Config file not found, using default values");
    saveConfig("all"); // สร้างไฟล์ config ใหม่ด้วยค่าเริ่มต้น
  }
}

// MQTT Callback functions
void onMqttConnect(bool sessionPresent) {
  Serial.println("Connected to MQTT");
  lv_label_set_text(mqttLabel, "MQTT: OK");
}

void onMqttDisconnect(AsyncMqttClientDisconnectReason reason) {
  Serial.println("Disconnected from MQTT");
  if (WiFi.isConnected()) {
    Serial.println("Reconnecting to MQTT...");
    mqttClient.connect();
  }
}

void onMqttPublish(uint16_t packetId) {
  Serial.println("Publish acknowledged");
}

// ฟังก์ชันเชื่อมต่อ MQTT
void connectMQTT() {
  if (!mqttClient.connected()) {
    Serial.println("Connecting to MQTT...");
    mqttClient.connect();
  }
}

// ฟังก์ชันส่งข้อมูลอุณหภูมิผ่าน MQTT
void publishTemperature() {
  StaticJsonDocument<200> doc;
  doc["temperature"] = temperature;
  doc["humidity"] = humidity;
  doc["sensor"] = useDS18B20 ? "DS18B20" : "DHT22";
  
  String jsonString;
  serializeJson(doc, jsonString);
  
  uint16_t packetId = mqttClient.publish(mqtt_topic, 1, true, jsonString.c_str());
  Serial.printf("Publishing on topic %s at QoS 1, packetId: %i\n", mqtt_topic, packetId);
}