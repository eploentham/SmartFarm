#!/usr/bin/env python3
# harvest_sprayer_csi_motion.py — รันบน pi5camera01
# ถ่ายภาพ CSI cam1 เฉพาะตอนมีการเคลื่อนไหว "ในโซนแท่นทำงาน" เท่านั้น
# ช่วง 08:00-19:30, ความละเอียด 1920x1080, แยกโฟลเดอร์ตามวัน
# + heartbeat: ถ่าย 1 เฟรมทุก 10 นาที เพื่อเก็บ negative frames (ฉากว่าง) ไว้ด้วย

from picamera2 import Picamera2
import cv2, time, os
from datetime import datetime, time as dtime

# ---------- config (ปรับได้) ----------
CAM_NUM      = 1
OUT_DIR      = os.path.expanduser("~/smartfarm/datasets/sprayer_raw")
CAP_SIZE     = (1920, 1080)     # ความละเอียดภาพที่เก็บจริง
LORES_SIZE   = (640, 360)       # เฟรมเล็กไว้เช็ค motion (เบา CPU)

# ROI เป็นสัดส่วน 0-1 (left, top, right, bottom) — เช็ค motion เฉพาะโซนนี้
# ตัดใบไม้ขวาสุด + พื้นล่างซ้าย(ไก่) + หลังคาออก เหลือแท่น+จุดผสมยา
#ROI = (0.25, 0.35, 0.80, 0.95)
ROI = (0.02, 0.40, 0.80, 1.00)   # ซ้ายเกือบสุด, ตัดหลังคาบน, ขวาจบถังฟ้าใบใกล้
MOTION_AREA  = 3000     # พิกเซลที่เปลี่ยนขั้นต่ำ (ในโซน ROI) ถึงถือว่ามี motion
COOLDOWN_S   = 4        # ถ่ายแล้วพักกี่วิ กันถ่ายรัวซ้ำ
HEARTBEAT_S  = 600      # ถ่ายฉากว่างทุก 10 นาที (เก็บ negative frames)
START_H, START_M = 8, 0        # เริ่ม 08:00
END_H,   END_M   = 19, 30      # หยุด 19:30
# --------------------------------------

def in_window():
    """คืน True ถ้าเวลาปัจจุบันอยู่ในช่วง 08:00-19:30"""
    now = datetime.now().time()
    return dtime(START_H, START_M) <= now <= dtime(END_H, END_M)

def day_folder():
    """โฟลเดอร์ตามวันที่ (สร้างถ้ายังไม่มี)"""
    d = os.path.join(OUT_DIR, datetime.now().strftime("%Y%m%d"))
    os.makedirs(d, exist_ok=True)
    return d

def save_frame(picam, tag):
    """ถ่ายเต็มความละเอียดแล้วเซฟ พร้อม tag บอกที่มา (motion/heartbeat)"""
    ts = datetime.now().strftime("%H%M%S")
    path = os.path.join(day_folder(), f"cam1_{tag}_{ts}.jpg")
    picam.capture_file(path)
    return path

# ---- ตั้งค่ากล้อง: main = ภาพเต็ม, lores = เฟรมเช็ค motion ----
picam = Picamera2(camera_num=CAM_NUM)
#picam.configure(picam.create_still_configuration(    main={"size": CAP_SIZE},    lores={"size": LORES_SIZE},    display=None))
picam.configure(picam.create_still_configuration(    main={"size": CAP_SIZE},    lores={"size": LORES_SIZE, "format": "RGB888"},   # ← เพิ่ม format ให้ lores เป็น 3 ช่อง
    display=None))
#gray = cv2.cvtColor(lo, cv2.COLOR_RGB2GRAY)   # lores เป็น RGB888 แล้ว
picam.start()
time.sleep(2)   # รอ sensor warm up

# แปลง ROI สัดส่วน -> พิกัดพิกเซลบนเฟรม lores
lw, lh = LORES_SIZE
x1, y1 = int(ROI[0]*lw), int(ROI[1]*lh)
x2, y2 = int(ROI[2]*lw), int(ROI[3]*lh)

prev = None
last_shot = 0
last_heartbeat = 0
print("เริ่มทำงาน (motion-gated) — Ctrl+C เพื่อหยุด")

try:
    while True:
        # นอกช่วงเวลา -> พักยาว ไม่ถ่าย ไม่เช็ค motion
        if not in_window():
            prev = None            # รีเซ็ต ป้องกัน motion หลอกตอนเริ่มวันใหม่
            time.sleep(30)
            continue

        # ---- เช็ค motion บนเฟรมเล็ก เฉพาะใน ROI ----
        lo = picam.capture_array("lores")
        gray = cv2.cvtColor(lo, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        roi_gray = gray[y1:y2, x1:x2]      # ตัดเฉพาะโซนที่สนใจ

        now = time.time()
        if prev is not None:
            diff = cv2.absdiff(prev, roi_gray)
            _, th = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            moved = cv2.countNonZero(th)

            # มี motion ในโซน + พ้น cooldown -> ถ่าย
            if moved > MOTION_AREA and (now - last_shot) > COOLDOWN_S:
                save_frame(picam, "motion")
                last_shot = now

        # ---- heartbeat: เก็บฉากว่าง (negative) เป็นระยะ ----
        if (now - last_heartbeat) > HEARTBEAT_S:
            save_frame(picam, "hb")
            last_heartbeat = now

        prev = roi_gray
        time.sleep(0.3)   # เช็ค ~3 ครั้ง/วินาที (CPU เบามาก)

except KeyboardInterrupt:
    print("หยุดแล้ว")
finally:
    picam.stop()