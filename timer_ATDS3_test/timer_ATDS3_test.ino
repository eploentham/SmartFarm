#include <Arduino.h>
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>
#include <time.h>
#include <lvgl.h> // เรียกใช้ LVGL

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
unsigned long valve1Duration = 5000;  // ระยะเวลาเปิดวาล์ว 5 วินาที
unsigned long valve2Duration = 5000;  // ระยะเวลาเปิดวาล์ว 5 วินาที
unsigned long valve3Duration = 5000;  // ระยะเวลาเปิดวาล์ว 5 วินาที
unsigned long valve4Duration = 5000;  // ระยะเวลาเปิดวาล์ว 5 วินาที
unsigned long valve5Duration = 5000;  // ระยะเวลาเปิดวาล์ว 5 วินาที
unsigned long valve6Duration = 5000;  // ระยะเวลาเปิดวาล์ว 5 วินาที
unsigned long valve7Duration = 5000;  // ระยะเวลาเปิดวาล์ว 5 วินาที
unsigned long valve8Duration = 5000;  // ระยะเวลาเปิดวาล์ว 5 วินาที
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
int count = 0;

// WiFi credentials
const char* ssid = "TP-Link_3800";
const char* password = "46284143";

void setup() {
  Serial.begin(115200);
  
}

void loop() {
  delay(1000);
  Serial.printf("** free heap: %" PRIu32 "\n", ESP.getFreeHeap());
}