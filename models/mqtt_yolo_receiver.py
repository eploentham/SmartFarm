#!/usr/bin/env python3
# mqtt_yolo_receiver.py - รันบน PN64
# รับ JPEG -> YOLO -> เก็บ conf ต่ำ (review) + ส่ง Telegram เมื่อ worker+sprayer พร้อมกัน
#
# Part 1: ตรวจเจอ worker + sprayer ในเฟรมเดียว (conf >= 0.50 ทั้งคู่)
#         -> ส่ง Telegram "M กำลังจะพ่นยาใช่ไหม?" + รูป annotated
#         -> throttle 15 นาที (in-memory, restart แล้วเริ่มใหม่)
#         -> ส่งใน background thread (ไม่บล็อก loop รับ MQTT)

import cv2, numpy as np, os, time, requests, threading
import paho.mqtt.client as mqtt
from ultralytics import YOLO
from datetime import datetime

# ---------- config ----------
BROKER, PORT = "192.168.0.254", 1883
USER, PASSWD = "pop", "pop1"
TOPIC        = "smartfarm/cam1/frame"
MODEL        = "/home/ekapop/smartfarm/best_openvino_model"
CONF         = 0.25
REVIEW_DIR   = os.path.expanduser("~/smartfarm/review")
LOW_MIN, LOW_MAX = 0.25, 0.50

# --- Telegram ---
TG_TOKEN     = "8940796280:AAH5b1rk94Ujcj5aEJMfhwMEan5D_Xcaos0"          # ⚠️ ต้องใส่ (ใช้ตัวเดิมจาก detectbottle ได้)
TG_CHAT_ID   = "8979584153"                    # พี่เอก (ทดสอบ) — สลับเป็น chat_id ของ M ทีหลัง
TG_CHAT_ID_CHK   = "8394445325"                 #pop
TG_COOLDOWN  = 900                             # throttle 15 นาที (900 วิ) กันสแปม
TG_MIN_CONF  = 0.50                            # ต้อง conf >= 0.5 ถึงนับ (มั่นใจจริง)

# --- ชื่อ class ที่ใช้ trigger (match แบบ case-insensitive) ---
CLS_WORKER   = "worker"                        # ถ้าโมเดลสะกดต่าง แก้ตรงนี้
CLS_SPRAYER  = "sprayer"
# ----------------------------

os.makedirs(REVIEW_DIR, exist_ok=True)
if not os.path.exists(MODEL):
    print(f"❌ ไม่เจอโมเดล: {MODEL}"); exit(1)

print("โหลดโมเดล...")
model = YOLO(MODEL)
print("classes:", model.names)                # <-- ดูชื่อ class จริง ครั้งแรกที่รัน
print("โหลดเสร็จ รอรับภาพ...")

last_alert_ts = 0   # เวลาส่ง Telegram ครั้งล่าสุด (สำหรับ throttle)


def send_telegram(text, img_bgr):
    """ส่งข้อความ + รูปไป Telegram (ทำงานใน background thread — ช้าได้ ไม่บล็อก loop)"""
    try:
        # encode รูปเป็น JPEG ใน RAM (ไม่เขียน disk — ตรงกฎ retention)
        ok, jpg = cv2.imencode(".jpg", img_bgr)
        if not ok:
            return
        url   = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        files = {"photo": ("detect.jpg", jpg.tobytes(), "image/jpeg")}
        data  = {"chat_id": TG_CHAT_ID, "caption": text}
        r = requests.post(url, data=data, files=files, timeout=20)
        if r.status_code == 200:
            print("  -> ส่ง Telegram แล้ว")
        else:
            print(f"  -> Telegram error {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  -> Telegram ส่งไม่ได้: {e}")
def send_telegram_checker(text, img_bgr):
    """ส่งข้อความ + รูปไป Telegram (ทำงานใน background thread — ช้าได้ ไม่บล็อก loop)"""
    try:
        # encode รูปเป็น JPEG ใน RAM (ไม่เขียน disk — ตรงกฎ retention)
        ok, jpg = cv2.imencode(".jpg", img_bgr)
        if not ok:
            return
        url   = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        files = {"photo": ("detect.jpg", jpg.tobytes(), "image/jpeg")}
        data  = {"chat_id": TG_CHAT_ID_CHK, "caption": text}
        r = requests.post(url, data=data, files=files, timeout=20)
        if r.status_code == 200:
            print("  -> ส่ง Telegram แล้ว")
        else:
            print(f"  -> Telegram error {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  -> Telegram ส่งไม่ได้: {e}")
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("เชื่อม MQTT สำเร็จ")
        client.subscribe(TOPIC)
    else:
        print(f"เชื่อม MQTT ไม่สำเร็จ rc={rc}")

def on_message(client, userdata, msg):
    global last_alert_ts
    arr = np.frombuffer(msg.payload, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        print("decode ภาพไม่ได้"); return

    results = model.predict(frame, device="intel:gpu", imgsz=640, conf=CONF, verbose=False)
    boxes = results[0].boxes
    if len(boxes) == 0:
        print("ไม่เจออะไร"); return

    found = [f"{model.names[int(b.cls)]}({float(b.conf):.2f})" for b in boxes]
    print("เจอ:", ", ".join(found))

    annotated = results[0].plot()   # ภาพวาดกรอบ (ใช้ทั้ง Telegram + review)

    # --- เก็บ conf ต่ำไว้ review (active learning) ---
    has_low = any(LOW_MIN <= float(b.conf) < LOW_MAX for b in boxes)
    if has_low:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(os.path.join(REVIEW_DIR, f"lowconf_{ts}.jpg"), annotated)
        print("  -> เก็บ review (conf อ่อน)")

    # --- ตรวจ worker + sprayer พร้อมกันในเฟรมเดียว (spray intent) ---
    worker_ok = any(
        model.names[int(b.cls)].lower() == CLS_WORKER and float(b.conf) >= TG_MIN_CONF
        for b in boxes
    )
    sprayer_ok = any(
        model.names[int(b.cls)].lower() == CLS_SPRAYER and float(b.conf) >= TG_MIN_CONF
        for b in boxes
    )

    now = time.time()
    if worker_ok and sprayer_ok and (now - last_alert_ts) > TG_COOLDOWN:
        ts_str  = datetime.now().strftime("%H:%M:%S")
        caption = f"M กำลังจะพ่นยาใช่ไหม? 🌿\n{ts_str} | เจอ: {', '.join(found)}"
        # ส่งใน background thread -> loop รับ MQTT ทำงานต่อได้ทันที
        threading.Thread(
            target=send_telegram,
            args=(caption, annotated.copy()),   # copy กัน main loop เขียนทับระหว่างส่ง
            daemon=True                          # ปิด service ได้แม้ upload ค้าง
        ).start()
        threading.Thread(
                    target=send_telegram_checker,
                    args=(caption, annotated.copy()),   # copy กัน main loop เขียนทับระหว่างส่ง
                    daemon=True                          # ปิด service ได้แม้ upload ค้าง
                ).start()
        last_alert_ts = now
        print("  -> worker+sprayer! ส่ง Telegram (thread)")

client = mqtt.Client()
client.username_pw_set(USER, PASSWD)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()