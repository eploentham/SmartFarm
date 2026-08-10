#!/usr/bin/env python3
# mqtt_sender_pi5.py - รันบน pi5camera01
# motion จับ -> capture 1920x1080 -> ส่ง MQTT ไป PN64 + เขียนไฟล์ dataset (positive)
# heartbeat ทุก 10 นาที -> เขียนไฟล์อย่างเดียว (negative, ไม่ส่ง MQTT)
# แทนที่ detect_spray.py เดิม (ครึ่ง capture/motion)

from picamera2 import Picamera2
import cv2, time, os
from datetime import datetime
import paho.mqtt.client as mqtt

# ---------- config ----------
CAM_NUM      = 1
BROKER       = "192.168.0.254"
PORT         = 1883
USER, PASSWD = "pop", "pop1"
TOPIC        = "smartfarm/cam1/frame"

CAP_SIZE     = (1920, 1080)          # เฟรมเต็ม (ส่ง MQTT + เก็บ dataset)
LORES_SIZE   = (640, 360)            # เฟรมเล็กไว้เช็ค motion (เบา)
ROI          = (0.02, 0.28, 0.90, 1.00)   # มุมใหม่ที่ล็อกแล้ว (left,top,right,bottom)

MIN_BLOB     = 2500                  # ก้อนใหญ่กว่านี้ถึงถือว่ามี motion (กรองกล้องสั่น/ลม)
COOLDOWN_S   = 4                     # ถ่ายแล้วพักกี่วิ กันถ่ายรัวซ้ำ
HEARTBEAT_S  = 600                   # เก็บ negative (ฉากว่าง) ทุก 10 นาที

DATASET_DIR  = os.path.expanduser("~/smartfarm/datasets/sprayer_raw")
# ----------------------------

def day_folder():
    """โฟลเดอร์ตามวันที่ (สร้างถ้ายังไม่มี)"""
    d = os.path.join(DATASET_DIR, datetime.now().strftime("%Y%m%d"))
    os.makedirs(d, exist_ok=True)
    return d

# ---- ต่อ MQTT ----
client = mqtt.Client()
client.username_pw_set(USER, PASSWD)
client.connect(BROKER, PORT, 60)
client.loop_start()                  # เปิด network thread (ให้ publish ส่งได้จริง)

# ---- ตั้งกล้อง: main = เฟรมเต็ม, lores = เช็ค motion ----
picam = Picamera2(camera_num=CAM_NUM)
picam.configure(picam.create_still_configuration(
    main={"size": CAP_SIZE},
    lores={"size": LORES_SIZE},
    display=None))
picam.start()
time.sleep(2)                        # รอ sensor warm up

# แปลง ROI สัดส่วน -> พิกัดพิกเซลบนเฟรม lores
lw, lh = LORES_SIZE
x1, y1 = int(ROI[0]*lw), int(ROI[1]*lh)
x2, y2 = int(ROI[2]*lw), int(ROI[3]*lh)

prev = None
last_shot = 0
last_hb = 0
print("mqtt_sender เริ่มทำงาน... (Ctrl+C หยุด)")

def capture_bgr():
    """ถ่ายเฟรมเต็ม แปลงเป็น BGR (OpenCV ใช้ BGR)"""
    frame = picam.capture_array("main")
    # picamera2 main มักได้ RGB -> แปลงเป็น BGR ให้ cv2
    # ** ถ้าสีเพี้ยน (ฟ้า<->แดงสลับ) ให้ลบบรรทัด cvtColor นี้ทิ้ง **
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

try:
    while True:
        # ---- เช็ค motion บนเฟรมเล็ก เฉพาะใน ROI ----
        lo = picam.capture_array("lores")
        gray = lo[:lh, :lw]                        # Y-plane (YUV420) = grayscale
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        roi = gray[y1:y2, x1:x2]

        now = time.time()

        if prev is not None:
            diff = cv2.absdiff(prev, roi)
            _, th = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            th = cv2.erode(th, None, iterations=2)   # ลบเส้นบาง (กล้องสั่น/ใบไม้)
            th = cv2.dilate(th, None, iterations=4)  # เชื่อมก้อนที่เหลือ
            cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            biggest = max((cv2.contourArea(c) for c in cnts), default=0)

            # ---- มี motion จริง (ก้อนใหญ่พอ) + พ้น cooldown ----
            if biggest > MIN_BLOB and (now - last_shot) > COOLDOWN_S:
                frame = capture_bgr()
                ts = datetime.now().strftime("%H%M%S")

                # (1) ส่ง MQTT ไป PN64 ก่อน (real-time detection)
                ok, jpg = cv2.imencode(".jpg", frame)   # encode ใน RAM
                if ok:
                    client.publish(TOPIC, jpg.tobytes())

                # (2) เขียนไฟล์ dataset (positive - เก็บ label เทรนรอบหน้า)
                path = os.path.join(day_folder(), f"cam1_motion_{ts}.jpg")
                cv2.imwrite(path, frame)

                print(f"[motion] blob={int(biggest)} -> ส่ง MQTT + เก็บ {path}")
                last_shot = now

        # ---- heartbeat: เก็บ negative (ฉากว่าง) อย่างเดียว ไม่ส่ง MQTT ----
        if (now - last_hb) > HEARTBEAT_S:
            frame = capture_bgr()
            ts = datetime.now().strftime("%H%M%S")
            path = os.path.join(day_folder(), f"cam1_hb_{ts}.jpg")
            cv2.imwrite(path, frame)
            print(f"[heartbeat] เก็บ negative {path}")
            last_hb = now

        prev = roi
        time.sleep(0.3)              # เช็ค ~3 ครั้ง/วินาที (CPU เบา)

except KeyboardInterrupt:
    print("หยุด")
finally:
    picam.stop()
    client.loop_stop()
    client.disconnect()