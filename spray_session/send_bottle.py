#!/usr/bin/env python3
# send_bottle.py — publish รูปขวด 1 ใบเข้า topic กล้องขวด (สำหรับเทส real mode)
# ---------------------------------------------------------------------------
# ใช้ตอนกลางคืน/ไม่มีกล้องสด: เอารูปขวดที่ถ่ายไว้ยิงเข้า BOTTLE_FRAME_TOPIC
# แล้ว bottle_capture.py (BOTTLE_MOCK=0) จะเก็บไว้เป็น "เฟรมล่าสุด"
# พอตอบ 'ถ่าย' ทาง Telegram → มันหยิบเฟรมนี้ไป Gemini จริง
#
#   python3 send_bottle.py bottle.jpg
#   BOTTLE_FRAME_TOPIC=smartfarm/bottlecam/frame python3 send_bottle.py bottle.jpg
# ---------------------------------------------------------------------------

import os
import sys

import paho.mqtt.client as mqtt

BROKER, PORT = "192.168.0.254", 1883
USER, PASSWD = "pop", "pop1"
TOPIC = os.environ.get("BOTTLE_FRAME_TOPIC", "smartfarm/bottlecam/frame")

if len(sys.argv) < 2:
    print("วิธีใช้: python3 send_bottle.py <ไฟล์รูปขวด.jpg>")
    sys.exit(1)

img = sys.argv[1]
if not os.path.exists(img):
    print(f"❌ ไม่พบไฟล์: {img}")
    sys.exit(1)

with open(img, "rb") as f:
    data = f.read()

client = mqtt.Client()
client.username_pw_set(USER, PASSWD)
client.connect(BROKER, PORT)
client.loop_start()
client.publish(TOPIC, data).wait_for_publish()
client.loop_stop()
client.disconnect()

print(f"✅ ส่ง {len(data):,} bytes → '{TOPIC}' (เฟรมล่าสุดพร้อมให้ Gemini อ่าน)")
