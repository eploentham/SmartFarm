/*
 * ============================================================
 *  Pressure Transducer TEST / DEBUG sketch
 *  โค้ดทดสอบเซ็นเซอร์แรงดันน้ำ (เป่าเทสที่บ้าน)
 * ------------------------------------------------------------
 *  Sensor  : 0.5-4.5V ratiometric, 0-10 bar (145 PSI), 5V supply
 *  Wiring  : สายน้ำเงิน -> R1(4.7k) -> ADC pin -> R2(4.7k) -> GND
 *            (voltage divider หาร 2 : 4.5V -> 2.25V ปลอดภัยกับ ADC)
 *  Purpose : เป่าเบา ๆ แล้วดูค่า "Sensor V" / "bar" ขยับขึ้น
 *            ปล่อยแล้วต้องกลับมา ~0.5V / ~0 bar
 *  Output  : print ออก Serial Monitor @ 115200 ทุก 1 วินาที
 * ============================================================
 */

// ---------- CONFIG : แก้ตรงนี้ให้ตรงกับบอร์ด/การต่อสาย ----------
#define PRESSURE_PIN   36      // GPIO36 = ใช้ได้ทั้ง DevKit และ T-Display
                               //   DevKit : 34/35/36/39 ใช้ได้
                               //   T-Display : 36/39 (ไม่มี 34/35)

const float DIV_FACTOR = 2.0;  // R1=R2=4.7k -> หาร 2 -> ต้องคูณกลับ 2
const float V_MIN      = 2.5;  // แรงดัน sensor ที่ 0 bar (ตอนนิ่ง)
const float V_MAX      = 4.5;  // แรงดัน sensor ที่ full scale (10 bar)
const float FS_BAR     = 10.0; // full scale = 10 bar (145 PSI)
const int   SAMPLES    = 20;   // เฉลี่ยกี่ครั้งต่อ 1 ค่า (ช่วยกรอง noise)
// -----------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(500);

  analogReadResolution(12);                         // ADC 12-bit (0-4095)
  analogSetPinAttenuation(PRESSURE_PIN, ADC_11db);  // อ่านช่วง ~0-3.3V

  Serial.println();
  Serial.println("=== Pressure Transducer TEST ===");
  Serial.printf("Pin: GPIO%d | Divider x%.1f\n", PRESSURE_PIN, DIV_FACTOR);
  Serial.println("นิ่ง ๆ ควรได้ ~0.50 V / ~0 bar");
  Serial.println("เป่า -> ค่าขึ้น | ปล่อย -> กลับ ~0");
  Serial.println("------------------------------------------------");
}

void loop() {
  // --- อ่านหลายครั้งแล้วเฉลี่ย (หน่วย mV ที่ขา ADC) ---
  long sum_mv = 0;
  for (int i = 0; i < SAMPLES; i++) {
    sum_mv += analogReadMilliVolts(PRESSURE_PIN);   // อ่านเป็น mV (ชดเชย non-linear ให้แล้ว)
    delay(2);
  }
  float adc_mv = sum_mv / (float)SAMPLES;           // mV เฉลี่ยที่ขา ADC

  // --- คำนวณย้อนกลับเป็นแรงดันจริงจาก sensor ---
  float adc_v    = adc_mv / 1000.0;                 // mV -> V ที่ขา ADC
  float sensor_v = adc_v * DIV_FACTOR;              // คูณกลับ (เพราะ divider หารมา)

  // --- แปลงเป็น bar ---
  float bar = (sensor_v - V_MIN) / (V_MAX - V_MIN) * FS_BAR;
  if (bar < 0) bar = 0;                             // กันค่าติดลบตอนนิ่ง (จูน V_MIN ทีหลัง)

  // --- print ออก Serial Monitor ---
  Serial.printf("ADC: %6.1f mV | Sensor: %5.3f V | Pressure: %5.2f bar\n",
                adc_mv, sensor_v, bar);

  delay(1000);  // 1 ค่า ต่อ 1 วินาที
}