#include <Arduino.h>
#include <lvgl.h>
#include <ATD1.47-S3.h>
#include <WiFi.h>
#include <time.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>

// Define pins for water valves
const int VALVE1_PIN = 15;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE2_PIN = 16;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE3_PIN = 17;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE4_PIN = 18;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE5_PIN = 42;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE6_PIN = 41;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE7_PIN = 40;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
const int VALVE8_PIN = 39;  // เปลี่ยนเป็น PIN ที่ต้องการ ขา GPIO ที่ใช้งานได้สมบูรณ์ ไม่ชนกับอุปกรณ์อื่น ๆ
// Timer variables
unsigned long valve1StartTime = 0;
unsigned long valve2StartTime = 0;
unsigned long valve3StartTime = 0;
unsigned long valve4StartTime = 0;
unsigned long valve5StartTime = 0;
unsigned long valve6StartTime = 0;
unsigned long valve7StartTime = 0;
unsigned long valve8StartTime = 0;
unsigned long valve1Duration = 600000;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve2Duration = 600000;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve3Duration = 600000;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve4Duration = 600000;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve5Duration = 600000;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve6Duration = 600000;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve7Duration = 600000;  // ระยะเวลาเปิดวาล์ว 10 นาที
unsigned long valve8Duration = 600000;  // ระยะเวลาเปิดวาล์ว 10 นาที
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

int count = 0;

// WiFi credentials
// ถ้าหน้าจอ เป็นสีตุ่นๆ ให้ดู ssid กับ password ว่าถูกต้องหรือไม่
const char* ssid = "TP-Link_3800";
const char* password = "46284143";
//const char* ssid = "Xiaomi 13";
//const char* password = "11111111";
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
  if(valvePin==VALVE1_PIN){    digitalWrite(VALVE1_PIN, HIGH);    VALVE1RUNNING = true;
  }else if(valvePin==VALVE2_PIN){    digitalWrite(VALVE2_PIN, HIGH);    VALVE2RUNNING = true;
  }else if(valvePin==VALVE3_PIN){    digitalWrite(VALVE3_PIN, HIGH);    VALVE3RUNNING = true;
  }else if(valvePin==VALVE4_PIN){    digitalWrite(VALVE4_PIN, HIGH);    VALVE4RUNNING = true;
  }else if(valvePin==VALVE5_PIN){    digitalWrite(VALVE5_PIN, HIGH);    VALVE5RUNNING = true;
  }else if(valvePin==VALVE6_PIN){    digitalWrite(VALVE6_PIN, HIGH);    VALVE6RUNNING = true;
  }else if(valvePin==VALVE7_PIN){    digitalWrite(VALVE7_PIN, HIGH);    VALVE7RUNNING = true;
  }else if(valvePin==VALVE8_PIN){    digitalWrite(VALVE8_PIN, HIGH);    VALVE8RUNNING = true;
  }
  setLabel();
}
void closeValve(int valvePin) {
  Serial.println("closeValve "+String(valvePin));
  //setValveRunning(valvePin, false);
  if(valvePin==VALVE1_PIN){    digitalWrite(VALVE1_PIN, LOW);    VALVE1RUNNING = false;
  }else if(valvePin==VALVE2_PIN){    digitalWrite(VALVE2_PIN, LOW);    VALVE2RUNNING = false;
  }else if(valvePin==VALVE3_PIN){    digitalWrite(VALVE3_PIN, LOW);    VALVE3RUNNING = false;
  }else if(valvePin==VALVE4_PIN){    digitalWrite(VALVE4_PIN, LOW);    VALVE4RUNNING = false;
  }else if(valvePin==VALVE5_PIN){    digitalWrite(VALVE5_PIN, LOW);    VALVE5RUNNING = false;
  }else if(valvePin==VALVE6_PIN){    digitalWrite(VALVE6_PIN, LOW);    VALVE6RUNNING = false;
  }else if(valvePin==VALVE7_PIN){    digitalWrite(VALVE7_PIN, LOW);    VALVE7RUNNING = false;
  }else if(valvePin==VALVE8_PIN){    digitalWrite(VALVE8_PIN, LOW);    VALVE8RUNNING = false;
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
void setValveName(String valve,String name){
  if(valve=="1"){VALVE1NAME=name;}
  else if(valve=="2"){VALVE2NAME=name;}
  else if(valve=="3"){VALVE3NAME=name;}
  else if(valve=="4"){VALVE4NAME=name;}
  else if(valve=="5"){VALVE5NAME=name;}
  else if(valve=="6"){VALVE6NAME=name;}
  else if(valve=="7"){VALVE7NAME=name;}
  else if(valve=="8"){VALVE8NAME=name;}
}
void setValveDuration(String valve,String duration){
  if(valve=="1"){valve1Duration=duration.toInt();}
  else if(valve=="2"){valve2Duration=duration.toInt();}
  else if(valve=="3"){valve3Duration=duration.toInt();}
  else if(valve=="4"){valve4Duration=duration.toInt();}
  else if(valve=="5"){valve5Duration=duration.toInt();}
  else if(valve=="6"){valve6Duration=duration.toInt();}
  else if(valve=="7"){valve7Duration=duration.toInt();}
  else if(valve=="8"){valve8Duration=duration.toInt();}
}

void setup() {
  // put your setup code here, to run once:
  Serial.begin(115200);
  Display.begin();
  Display.useLVGL();
  Switch.begin();
  // Set background color to orange when WiFi is connected
  lv_obj_set_style_bg_color(lv_scr_act(), lv_color_make(255, 165, 0), LV_PART_MAIN | LV_STATE_DEFAULT);
  lastUpdateLabel = lv_label_create(lv_scr_act());
  lv_label_set_text(lastUpdateLabel, "connect wifi");
  lv_obj_align(lastUpdateLabel, LV_ALIGN_BOTTOM_LEFT, 10, 0);
  lv_obj_set_style_text_color(lastUpdateLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);

  // Setup valve pins as outputs
  pinMode(VALVE1_PIN, OUTPUT);  pinMode(VALVE2_PIN, OUTPUT);  pinMode(VALVE3_PIN, OUTPUT);  pinMode(VALVE4_PIN, OUTPUT);
  pinMode(VALVE5_PIN, OUTPUT);  pinMode(VALVE6_PIN, OUTPUT);  pinMode(VALVE7_PIN, OUTPUT);  pinMode(VALVE8_PIN, OUTPUT);
  digitalWrite(VALVE1_PIN, LOW);  digitalWrite(VALVE2_PIN, LOW);  digitalWrite(VALVE3_PIN, LOW);  digitalWrite(VALVE4_PIN, LOW);
  digitalWrite(VALVE5_PIN, LOW);  digitalWrite(VALVE6_PIN, LOW);  digitalWrite(VALVE7_PIN, LOW);  digitalWrite(VALVE8_PIN, LOW);

  // Connect to WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting WIFI");
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print("+");
  }
  lv_label_set_text(lastUpdateLabel, "2025-03-31");
  Serial.println("\nConnected to WiFi");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // Configure time
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  
  // Create time display label with larger font
  timeLabel = lv_label_create(lv_scr_act());
  lv_label_set_text(timeLabel, "Time: --:--:--");
  lv_obj_set_style_text_color(timeLabel, lv_color_make(255, 255, 255), LV_PART_MAIN | LV_STATE_DEFAULT);
  //lv_obj_set_style_text_scale(timeLabel, 200, LV_PART_MAIN | LV_STATE_DEFAULT);  // เพิ่มขนาดตัวอักษรเป็น 2 เท่า
  lv_obj_align(timeLabel, LV_ALIGN_TOP_LEFT, 10, 10);
  
  // Create IP display label
  ipLabel = lv_label_create(lv_scr_act());
  lv_label_set_text(ipLabel, WiFi.localIP().toString().c_str());
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
}

void loop() {
  // put your main code here, to run repeatedly:
  Display.loop();
  Switch.loop();
  // Update time display
  updateTimeDisplay();

  // Reset valveOpenedToday flag at midnight
  if(timeinfo.tm_hour == 0 && timeinfo.tm_min == 0) {
    valveOpenedToday = false;
  }
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
}