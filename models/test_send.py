#!/usr/bin/env python3
# test_send.py - ส่งภาพเข้า MQTT เพื่อเทส pipeline
# ใช้งาน: python3 test_send.py <ชื่อไฟล์ภาพ>
# เช่น:   python3 test_send.py test.jpg
#         python3 test_send.py cam1_motion_090340.jpg

import paho.mqtt.client as mqtt
import sys
import os

# ---------- config ----------
BROKER = "192.168.0.254"
PORT   = 1883
USER   = "pop"
PASSWD = "pop1"
TOPIC  = "smartfarm/cam1/frame"
# ----------------------------

# รับชื่อภาพจาก argument
if len(sys.argv) < 2:
    print("วิธีใช้: python3 test_send.py <ชื่อไฟล์ภาพ>")
    print("เช่น:   python3 test_send.py test.jpg")
    sys.exit(1)

IMG = sys.argv[1]   # ชื่อภาพที่พิมพ์ต่อท้ายคำสั่ง

# เช็คว่าไฟล์มีจริง (กัน error เงียบ)
if not os.path.exists(IMG):
    print(f"❌ ไม่พบไฟล์: {IMG}")
    sys.exit(1)

size = os.path.getsize(IMG)
print(f"ไฟล์: {IMG} ({size:,} bytes)")

# เชื่อม + ส่ง
client = mqtt.Client()
client.username_pw_set(USER, PASSWD)
client.connect(BROKER, PORT)
client.loop_start()                        # เริ่ม network loop

with open(IMG, "rb") as f:
    data = f.read()
    result = client.publish(TOPIC, data)
    result.wait_for_publish()              # รอส่งเสร็จจริงก่อนปิด

print(f"✅ ส่ง {len(data):,} bytes ไปที่ topic '{TOPIC}' เสร็จ")

client.loop_stop()
client.disconnect()