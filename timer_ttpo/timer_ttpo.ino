#include <WiFi.h>
#include <ATD1.47-S3.h>
#include <PubSubClient.h>
#define WIFI_STA_NAME "bng5 IT"           //Floor1 MRI
#define WIFI_STA_PASS "bng5linux"
// DHT22 data pin
#define WATER_VALVE1 37      // Water valve 1
#define WATER_VALVE2 38      // Water valve 2
#define WATER_VALVE3 39      // Water valve 3
#define WATER_VALVE4 40      // Water valve 4
#define WATER_VALVE5 41      // Water valve 5
#define WATER_VALVE6 42      // Water valve 6
#define WATER_VALVE7 43      // Water valve 7
#define WATER_VALVE8 44      // Water valve 8

#define MQTT_SERVER   "172.25.10.13"
#define MQTT_PORT     1883
#define MQTT_USERNAME "pop"
#define MQTT_PASSWORD "pop1"
String MQTT_NAME ="1-MRI-01";
const char* mqtt_topic = "mqtt_refrigerator";
int loopwificonne,loopwificonnect=0;
String statusWIFI = "",ipaddress = "", statusMQTT="";
IPAddress ip;
WiFiClient client;
PubSubClient clientMqtt(MQTT_SERVER, MQTT_PORT,client);
String color = "";
void setup() {
  // put your setup code here, to run once:
  Serial.begin(250000); // Debug only
  Display.begin();
  Display.fillScreen(Display.color24to16(0x000000)); // เทสีหน้าจอสีดำ

}

void loop() {
  // put your main code here, to run repeatedly:
  

  
  delay(1000);
}
