#!/usr/bin/env python3
# mqtt_yolo_receiver.py - รันบน PN64
# รับ JPEG จาก MQTT -> decode (RAM) -> YOLO (OpenVINO/iGPU) -> print ผล
# เก็บภาพ conf ต่ำ (จุดอ่อนโมเดล) ไว้ review/ สำหรับเทรนรอบหน้า

import cv2, numpy as np, os
import paho.mqtt.client as mqtt
from ultralytics import YOLO
from datetime import datetime

# ---------- config ----------
BROKER     = "192.168.0.254"
PORT       = 1883
USER, PASSWD = "pop", "pop1"
TOPIC      = "smartfarm/cam1/frame"
MODEL      = "/home/ekapop/smartfarm/best_openvino_model"
CONF       = 0.25                    # ต่ำ เพื่อเห็น detection อ่อน ๆ ด้วย
REVIEW_DIR = os.path.expanduser("~/smartfarm/review")
LOW_MIN, LOW_MAX = 0.25, 0.50        # ช่วง conf ที่ถือว่า "อ่อน ควรเก็บ"
# ----------------------------

os.makedirs(REVIEW_DIR, exist_ok=True)

# เช็ค path โมเดลก่อน (กัน error path ผิด)
if not os.path.exists(MODEL):
    print(f"❌ ไม่เจอโมเดลที่: {MODEL}")
    os.system("ls -d ~/smartfarm/*openvino*/ 2>/dev/null")
    exit(1)

print("โหลดโมเดล...")
model = YOLO(MODEL)
print("โหลดเสร็จ รอรับภาพจาก MQTT...")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("เชื่อม MQTT สำเร็จ")
        client.subscribe(TOPIC)
    else:
        print(f"เชื่อม MQTT ไม่สำเร็จ rc={rc}")

def on_message(client, userdata, msg):
    # decode ภาพใน RAM (ไม่แตะ disk)
    arr = np.frombuffer(msg.payload, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        print("decode ภาพไม่ได้ (payload เสีย?)")
        return

    # รัน YOLO บน Intel iGPU
    results = model.predict(frame, device="intel:gpu", imgsz=640, conf=CONF, verbose=False)
    boxes = results[0].boxes

    if len(boxes) == 0:
        print("ไม่เจออะไร")
        return

    found = [f"{model.names[int(b.cls)]}({float(b.conf):.2f})" for b in boxes]
    print("เจอ:", ", ".join(found))

    # เก็บเฉพาะภาพที่มี detection conf อ่อน (จุดที่โมเดลยังไม่แข็ง)
    has_low = any(LOW_MIN <= float(b.conf) < LOW_MAX for b in boxes)
    if has_low:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(REVIEW_DIR, f"lowconf_{ts}.jpg")
        cv2.imwrite(out, results[0].plot())     # ภาพวาดกรอบ+conf
        print(f"  -> เก็บไว้ review (มี conf อ่อน): {out}")

client = mqtt.Client()
client.username_pw_set(USER, PASSWD)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()