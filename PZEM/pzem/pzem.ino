/*
 * PZEM-004T v3.0 x2 — Bench Test (Debug Version)
 * TTGO T-Display (ESP32)
 *
 * การต่อสาย (ต่อไขว้ TX<->RX เสมอ):
 *   PZEM1 TX -> divider 4.7k/9.4k -> GPIO27 (ESP32 RX, Serial2)
 *   PZEM1 RX -> GPIO26 (ESP32 TX, ต่อตรง)
 *   PZEM2 TX -> divider 4.7k/9.4k -> GPIO22 (ESP32 RX, Serial1)
 *   PZEM2 RX -> GPIO21 (ESP32 TX, ต่อตรง)
 *   5V, GND ใช้ร่วมกันได้ (ต้องมี GND ร่วมเสมอ)
 */

#include <PZEM004Tv30.h>

// ---------- PZEM 1 : Serial2 (UART2) ----------
#define PZEM1_RX 27   // ESP32 รับ <- PZEM1 TX (ผ่าน divider)
#define PZEM1_TX 26   // ESP32 ส่ง -> PZEM1 RX (ตรง)

// สลับเป็น
//#define PZEM1_RX 26
//#define PZEM1_TX 27

// ---------- PZEM 2 : Serial1 (UART1) ----------
#define PZEM2_RX 22   // ESP32 รับ <- PZEM2 TX (ผ่าน divider)
#define PZEM2_TX 21   // ESP32 ส่ง -> PZEM2 RX (ตรง)

#define CT_TURNS 3    // ร้อยสาย CT 3 รอบ -> หาร 3

PZEM004Tv30 pzem1(Serial2, PZEM1_RX, PZEM1_TX);
//PZEM004Tv30 pzem2(Serial1, PZEM2_RX, PZEM2_TX);

// ---------- ฟังก์ชันอ่าน + วินิจฉัย ----------
void readPzem(PZEM004Tv30 &p, const char* name) {
  float v  = p.voltage();
  float i  = p.current();
  float pw = p.power();
  float e  = p.energy();
  float f  = p.frequency();
  float pf = p.pf();

  // แสดงค่าดิบทั้งหมด (NaN จะขึ้น "nan" ให้เห็นชัด)
  Serial.printf("[%s] V=%.1f | I=%.3f | P=%.1f | E=%.3f | F=%.1f | PF=%.2f\n",
                name, v, i, pw, e, f, pf);

  // ---------- วินิจฉัยแยกกรณี ----------
  if (isnan(v) && isnan(f)) {
    Serial.printf("   >> [%s] \xE0\xB8\xAA\xE0\xB8\xB7\xE0\xB9\x88\xE0\xB8\xAD\xE0\xB8\xAA\xE0\xB8\xB2\xE0\xB8\xA3\xE0\xB9\x84\xE0\xB8\xA1\xE0\xB9\x88\xE0\xB8\x95\xE0\xB8\xB4\xE0\xB8\x94: TX/RX, GND, 220V\n", name);
    Serial.printf("      - \xE0\xB8\xAA\xE0\xB8\xA5\xE0\xB8\xB1\xE0\xB8\x9A TX<->RX \xE0\xB8\x94\xE0\xB8\xB9\n");
    Serial.printf("      - GND \xE0\xB8\xA3\xE0\xB9\x88\xE0\xB8\xA7\xE0\xB8\xA1?\n");
  } else if (isnan(v)) {
    Serial.printf("   >> [%s] V=nan: \xE0\xB9\x84\xE0\xB8\xA1\xE0\xB9\x88\xE0\xB8\xA1\xE0\xB8\xB5 220V \xE0\xB9\x80\xE0\xB8\x82\xE0\xB9\x89\xE0\xB8\xB2\xE0\xB8\x82\xE0\xB8\xB1\xE0\xB9\x89\xE0\xB8\xA7\n", name);
  } else if (isnan(i)) {
    Serial.printf("   >> [%s] I=nan (V \xE0\xB8\x9B\xE0\xB8\x81\xE0\xB8\x95\xE0\xB8\xB4): \xE0\xB9\x80\xE0\xB8\x8A\xE0\xB9\x87\xE0\xB8\x84 CT\n", name);
  } else {
    // อ่านได้ครบ -> แสดงค่าที่หาร CT_TURNS แล้ว (ค่าจริง)
    Serial.printf("   >> [%s] OK | I_real=%.3f A | P_real=%.1f W | E_real=%.3f kWh\n",
                  name, i / CT_TURNS, pw / CT_TURNS, e / CT_TURNS);
  }
}

void setup() {
  Serial.begin(115200);
  //delay(1000);
  delay(3000);   // รอ PZEM warm-up นานขึ้น
  Serial.println("\n=== PZEM x2 Bench Test (Debug) ===");
  Serial.println("V/I/P/E/F/PF = raw | I_real/P_real = /CT_TURNS\n");

  // ลองอ่าน address ดูว่า PZEM ตอบไหม
  Serial.printf("PZEM1 addr: 0x%02X\n", pzem1.readAddress());
  //Serial.printf("PZEM2 addr: 0x%02X\n", pzem2.readAddress());
}

void loop() {
  readPzem(pzem1, "PZEM1");
  //readPzem(pzem2, "PZEM2");
  Serial.println("--------------------------------------------------");
  delay(2000);   // PZEM refresh 1Hz อย่าถี่กว่านี้
}