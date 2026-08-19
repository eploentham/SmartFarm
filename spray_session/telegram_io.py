#!/usr/bin/env python3
# telegram_io.py — รันบน PN64 (สมองกลาง SFC2)
# ---------------------------------------------------------------------------
# Part 3: I/O adapter เดียวที่คุยกับ Telegram Bot API แล้ว bridge เข้า MQTT
#
#   getUpdates (long-poll)  ── publish ──▶  sfc2/telegram/incoming   (ข้อความดิบจาก M)
#   sfc2/telegram/send      ── subscribe ─▶  sendMessage / sendPhoto (ส่งออก)
#
# ⚠️ กฎเหล็ก: 1 bot token = getUpdates ได้ตัวเดียว
#    ไฟล์นี้ต้องเป็น poller เดียวในระบบ — ถ้า spray_monitor (wait_for_yes_no)
#    หรือ service อื่นยัง poll getUpdates อยู่ ต้องหยุดก่อน ไม่งั้น update
#    จะถูกแย่งกันดึงแล้วหายแบบสุ่ม (debug ยากมาก)
#
# หน้าที่ "โง่ๆ" ตั้งใจ: ไม่ parse ความหมายภาษาไทยที่นี่ (yes/หมดแล้ว/a1/...)
#    เพราะความหมายขึ้นกับ state ของ session — parse ที่ session_manager.py
# ---------------------------------------------------------------------------

import json
import os
import time
import threading

import requests
import paho.mqtt.client as mqtt

# ---------- config ----------
BROKER, PORT = "192.168.0.254", 1883
MQTT_USER, MQTT_PASS = "pop", "pop1"

TOPIC_INCOMING = "sfc2/telegram/incoming"   # publish: ข้อความดิบจาก Telegram
TOPIC_SEND     = "sfc2/telegram/send"       # subscribe: คำสั่งส่งข้อความ/รูปออก

# Bot token มาจาก env เท่านั้น (ห้าม hardcode) — systemd service ใส่ให้ผ่าน Environment=
#   export TELEGRAM_BOT_TOKEN="123456:ABC-..."
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

POLL_TIMEOUT = 25          # long-poll getUpdates กี่วิ (Telegram แนะนำ <30)
OFFSET_FILE  = os.path.expanduser("~/smartfarm/scripts/.tg_offset")

# DEBUG: mirror สำเนาทุกข้อความที่ส่งออก → ให้พี่เอกเห็นด้วย (เฝ้าดูตอนพัฒนา)
#   ตั้ง None เพื่อปิด (หรือ comment บล็อก mirror ใน on_message ออก) ตอน production
CC_CHAT_ID = 8394445325
# ----------------------------

BASE = f"https://api.telegram.org/bot{TG_TOKEN}"


# ---------------------------------------------------------------------------
# offset persistence — กัน reprocess ข้อความเดิมหลัง restart
# (Telegram ยืนยัน update เมื่อเราขอ offset ถัดไป แต่เก็บไฟล์ไว้กันพลาดตอน crash)
# ---------------------------------------------------------------------------
def load_offset():
    try:
        with open(OFFSET_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def save_offset(offset: int):
    try:
        os.makedirs(os.path.dirname(OFFSET_FILE), exist_ok=True)
        with open(OFFSET_FILE, "w") as f:
            f.write(str(offset))
    except OSError as e:
        print(f"[offset] เขียนไฟล์ไม่ได้: {e}")


# ---------------------------------------------------------------------------
# ส่งออก Telegram (เรียกจาก MQTT callback thread)
# ---------------------------------------------------------------------------
def tg_send_message(chat_id, text):
    try:
        r = requests.post(f"{BASE}/sendMessage",
                          json={"chat_id": chat_id, "text": text},
                          timeout=15)
        if not r.ok:
            print(f"[send] sendMessage error {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print(f"[send] sendMessage ล้มเหลว: {e}")


def tg_send_photo(chat_id, image_path, caption=""):
    try:
        with open(image_path, "rb") as f:
            r = requests.post(f"{BASE}/sendPhoto",
                              data={"chat_id": chat_id, "caption": caption},
                              files={"photo": f},
                              timeout=30)
        if not r.ok:
            print(f"[send] sendPhoto error {r.status_code}: {r.text[:120]}")
    except FileNotFoundError:
        print(f"[send] ไม่เจอรูป {image_path} — ส่งเป็นข้อความแทน")
        if caption:
            tg_send_message(chat_id, caption)
    except Exception as e:
        print(f"[send] sendPhoto ล้มเหลว: {e}")


# ---------------------------------------------------------------------------
# MQTT — subscribe sfc2/telegram/send
#   payload: {"chat_id": <int|str>, "text": "...", "image_path": "/path.jpg"?}
# ---------------------------------------------------------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("เชื่อม MQTT สำเร็จ")
        client.subscribe(TOPIC_SEND)
    else:
        print(f"เชื่อม MQTT ไม่สำเร็จ rc={rc}")


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        print(f"[send] payload ไม่ใช่ JSON: {e}")
        return

    chat_id = data.get("chat_id")
    if chat_id is None:
        print("[send] ขาด chat_id — ข้าม")
        return

    image_path = data.get("image_path")
    text = data.get("text", "")
    if image_path:
        tg_send_photo(chat_id, image_path, caption=text)
    else:
        tg_send_message(chat_id, text)

    # ── DEBUG mirror: ส่งสำเนาให้พี่เอกดูทุกข้อความ (comment ทั้งบล็อกออกตอน production) ──
    if CC_CHAT_ID and str(CC_CHAT_ID) != str(chat_id):
        cc = f"[→{chat_id}] {text}" if text else f"[→{chat_id}] (รูป)"
        if image_path:
            tg_send_photo(CC_CHAT_ID, image_path, caption=cc)
        else:
            tg_send_message(CC_CHAT_ID, cc)
    # ── end mirror ──


# ---------------------------------------------------------------------------
# getUpdates long-poll loop (main thread) → publish sfc2/telegram/incoming
# ---------------------------------------------------------------------------
def extract_photo_file_id(msg: dict):
    """รูปใน Telegram มาเป็น array หลายขนาด — เอา file_id ของขนาดใหญ่สุด."""
    photos = msg.get("photo") or []
    if not photos:
        return None
    return photos[-1].get("file_id")   # ตัวสุดท้าย = ความละเอียดสูงสุด


def poll_loop(client):
    offset = load_offset()
    print(f"เริ่ม poll getUpdates (offset={offset})")
    while True:
        params = {"timeout": POLL_TIMEOUT}
        if offset is not None:
            params["offset"] = offset
        try:
            r = requests.get(f"{BASE}/getUpdates", params=params,
                             timeout=POLL_TIMEOUT + 10)
            updates = r.json().get("result", [])
        except Exception as e:
            print(f"[poll] error: {e}")
            time.sleep(3)
            continue

        for upd in updates:
            offset = upd["update_id"] + 1
            save_offset(offset)

            msg = upd.get("message") or upd.get("edited_message") or {}
            chat = msg.get("chat") or {}
            file_id = extract_photo_file_id(msg)
            payload = {
                "chat_id":    chat.get("id"),
                "text":       msg.get("text") or msg.get("caption") or "",
                "has_photo":  file_id is not None,
                "file_id":    file_id,
                "message_id": msg.get("message_id"),
                "ts":         msg.get("date"),
            }
            client.publish(TOPIC_INCOMING, json.dumps(payload, ensure_ascii=False))
            preview = payload["text"][:40] or ("[photo]" if file_id else "[?]")
            print(f"[in] chat={payload['chat_id']} → {preview}")


def main():
    if not TG_TOKEN:
        raise SystemExit("❌ ไม่มี TELEGRAM_BOT_TOKEN ใน env — ตั้งค่าก่อนรัน")

    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_start()   # MQTT ทำงานใน thread เบื้องหลัง (รับ TOPIC_SEND)

    try:
        poll_loop(client)   # getUpdates วนใน main thread
    except KeyboardInterrupt:
        print("\nปิด telegram_io")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
