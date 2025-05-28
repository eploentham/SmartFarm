#include <TFT_eSPI.h>

TFT_eSPI tft = TFT_eSPI();
//  script test เต็มหน้าจอ 
void setup() {
  Serial.begin(115200);
  Serial.println("TTGO T-Display Full Screen Test");
  
  // เปิด backlight
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);
  
  // เริ่มต้นจอ
  tft.init();
  
  // ทดสอบการหมุนจอทั้ง 4 แบบ
  for (int rotation = 0; rotation < 4; rotation++) {
    tft.setRotation(rotation);
    
    // ระบายสีเต็มจอ
    tft.fillScreen(TFT_BLACK);
    
    // วาดกรอบสีขาวรอบจอ เพื่อเช็คว่าใช้พื้นที่เต็มจอหรือไม่
    tft.drawRect(0, 0, tft.width(), tft.height(), TFT_WHITE);
    
    // แสดงข้อมูลขนาดและการหมุนจอ
    tft.setTextColor(TFT_GREEN, TFT_BLACK);
    tft.setTextSize(2);
    tft.setCursor(10, 10);
    tft.print("Rotation: ");
    tft.println(rotation);
    
    tft.setCursor(10, 40);
    tft.print("Width: ");
    tft.println(tft.width());
    
    tft.setCursor(10, 70);
    tft.print("Height: ");
    tft.println(tft.height());
    
    delay(2000);
  }
  
  // ตั้งค่าสุดท้าย - หมุนแนวนอน (ค่าที่เหมาะสมที่สุดมักเป็น 1 หรือ 3)
  tft.setRotation(1);
  tft.fillScreen(TFT_ORANGE);
  
  // วาดกรอบขอบจอ
  tft.drawRect(0, 0, tft.width() - 1, tft.height() - 1, TFT_WHITE);
  
  // แสดงข้อความ
  tft.setTextColor(TFT_WHITE);
  tft.setTextSize(2);
  tft.setCursor(10, 10);
  tft.println("TTGO Full Screen");
  
  tft.setCursor(10, 50);
  tft.print("Size: ");
  tft.print(tft.width());
  tft.print("x");
  tft.println(tft.height());
  
  Serial.println("Setup complete");
}

void loop() {
  static unsigned long lastUpdate = 0;
  static bool showStatus = true;
  
  // อัพเดททุก 1 วินาที
  if (millis() - lastUpdate > 1000) {
    lastUpdate = millis();
    
    if (showStatus) {
      // แสดงเวลาทำงาน
      tft.fillRect(10, 90, 220, 30, TFT_ORANGE);
      tft.setTextColor(TFT_WHITE, TFT_ORANGE);
      tft.setCursor(10, 90);
      tft.print("Time: ");
      tft.print(millis() / 1000);
      tft.println("s");
    } else {
      tft.fillRect(10, 90, 220, 30, TFT_ORANGE);
    }
    
    showStatus = !showStatus;
  }
}