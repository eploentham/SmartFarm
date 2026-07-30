// Pure display test for THIS board — no PZEM.
// Cycles bright full-screen colors so we can see if the panel works at all.
#include <TFT_eSPI.h>

#define TFT_BL_PIN 4

TFT_eSPI tft = TFT_eSPI();

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== TFT TEST ===");

  pinMode(TFT_BL_PIN, OUTPUT);
  digitalWrite(TFT_BL_PIN, HIGH);   // backlight ON

  tft.init();
  tft.setRotation(1);
  Serial.println("init done");
}

void loop() {
  tft.fillScreen(TFT_WHITE);  Serial.println("WHITE");  delay(1000);
  tft.fillScreen(TFT_RED);    Serial.println("RED");    delay(1000);
  tft.fillScreen(TFT_GREEN);  Serial.println("GREEN");  delay(1000);
  tft.fillScreen(TFT_BLUE);   Serial.println("BLUE");   delay(1000);

  // Backlight blink test — screen should visibly go dark then bright
  digitalWrite(TFT_BL_PIN, LOW);  Serial.println("BL OFF"); delay(700);
  digitalWrite(TFT_BL_PIN, HIGH); Serial.println("BL ON");  delay(700);
}
