#!/usr/bin/env python3
# test_yolo_pi5.py - วัดว่า Pi5 รัน YOLO ไหวไหม (ความเร็ว + ความร้อน)
# รันบน pi5camera01 - ต้องมี best.pt อยู่ในโฟลเดอร์เดียวกัน

from ultralytics import YOLO
import time, subprocess, os

# ---------- config ----------
PT_MODEL   = "best.pt"          # โมเดล PyTorch ที่ export มาจาก Colab
TEST_IMG   = "cam1_motion_090051.jpg"   # ภาพทดสอบ (เอาภาพจริงจากกล้อง)
IMGSZ      = 640
WARMUP     = 5                  # รอบอุ่นเครื่อง (ไม่นับเวลา)
SPEED_RUNS = 30                 # รอบวัดความเร็ว
THERMAL_S  = 90                 # วินาทีที่รันต่อเนื่องเพื่อดูความร้อนสะสม
# ----------------------------

def get_temp():
    """อ่านอุณหภูมิ CPU (องศา C)"""
    out = subprocess.getoutput("vcgencmd measure_temp")   # temp=54.0'C
    return float(out.split("=")[1].split("'")[0])

def get_throttle():
    """เช็ค throttle/under-voltage (0x0 = ปกติ)"""
    return subprocess.getoutput("vcgencmd get_throttled").split("=")[1]

print("=" * 50)
print("ทดสอบ YOLO บน Pi5")
print("=" * 50)

# ---- 1. export เป็น NCNN (รูปแบบที่เหมาะกับ ARM/Pi5) ----
ncnn_dir = PT_MODEL.replace(".pt", "_ncnn_model")
if not os.path.exists(ncnn_dir):
    print("\n[1] กำลัง export NCNN (ครั้งแรกครั้งเดียว)...")
    YOLO(PT_MODEL).export(format="ncnn", imgsz=IMGSZ)
else:
    print(f"\n[1] มี NCNN อยู่แล้ว: {ncnn_dir}")

model = YOLO(ncnn_dir)   # โหลดตัว NCNN (เร็วกว่า .pt บน Pi5)

# ---- 2. อุณหภูมิก่อนเริ่ม ----
temp_start = get_temp()
print(f"\n[2] อุณหภูมิก่อนเริ่ม: {temp_start:.1f}°C")
print(f"    throttle: {get_throttle()}  (0x0 = ปกติ)")

# ---- 3. warm up (ไม่นับเวลา) ----
print(f"\n[3] อุ่นเครื่อง {WARMUP} รอบ...")
for _ in range(WARMUP):
    model.predict(TEST_IMG, imgsz=IMGSZ, verbose=False)

# ---- 4. วัดความเร็ว ----
print(f"\n[4] วัดความเร็ว {SPEED_RUNS} รอบ...")
times = []
for _ in range(SPEED_RUNS):
    t = time.time()
    model.predict(TEST_IMG, imgsz=IMGSZ, verbose=False)
    times.append(time.time() - t)
    print(f"    รอบ {_+1}/{SPEED_RUNS} | {times[-1]*1000:.0f} ms/เฟรม")

avg = sum(times) / len(times)
fps = 1 / avg
print(f"    เฉลี่ย: {avg*1000:.0f} ms/เฟรม")
print(f"    = {fps:.1f} FPS")

# ---- 5. ทดสอบความร้อนสะสม (รันต่อเนื่อง) ----
print(f"\n[5] รันต่อเนื่อง {THERMAL_S} วินาที ดูความร้อนสะสม...")
t_end = time.time() + THERMAL_S
peak_temp = temp_start
n = 0
while time.time() < t_end:
    model.predict(TEST_IMG, imgsz=IMGSZ, verbose=False)
    n += 1
    if n % 20 == 0:                        # เช็คอุณหภูมิเป็นระยะ
        temp = get_temp()
        peak_temp = max(peak_temp, temp)
        print(f"    ผ่านไป {n} เฟรม | temp: {temp:.1f}°C | throttle: {get_throttle()}")

# ---- 6. สรุปผล ----
temp_end = get_temp()
throttle_end = get_throttle()
print("\n" + "=" * 50)
print("สรุปผล")
print("=" * 50)
print(f"ความเร็ว     : {fps:.1f} FPS ({avg*1000:.0f} ms/เฟรม)")
print(f"อุณหภูมิ     : {temp_start:.1f}°C -> {temp_end:.1f}°C (peak {peak_temp:.1f}°C)")
print(f"throttle     : {throttle_end}")
print("-" * 50)

# ---- ตีความให้เลย ----
print("ตีความ:")
if fps >= 2 and peak_temp < 75 and throttle_end == "0x0":
    print("  ✅ Pi5 รัน YOLO ไหว (สำหรับงาน motion-gated ที่ไม่ต้องการ FPS สูง)")
elif throttle_end != "0x0":
    print("  ❌ เจอ throttle/under-voltage - Pi5 ร้อนเกิน/ไฟตก ไม่ควรรัน YOLO ต่อเนื่อง")
elif peak_temp >= 80:
    print(f"  ⚠️ ร้อนถึง {peak_temp:.1f}°C - เสี่ยง throttle ถ้ารันนานกว่านี้")
elif fps < 1:
    print("  ❌ ช้าเกินไป (<1 FPS) - ควรส่งไป PN64 แทน")
else:
    print("  ⚠️ ก้ำกึ่ง - ดูตัวเลขประกอบการตัดสินใจ")