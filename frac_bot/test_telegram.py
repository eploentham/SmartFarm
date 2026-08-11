#!/usr/bin/env python3
# test_telegram.py - เทสส่งข้อความ + รูป ไปหา M ผ่าน Telegram
# ใช้เช็คว่า token + chat_id ถูกต้อง ส่งถึงจริงไหม

import requests
import sys

# ---------- config ----------
TG_TOKEN   = "8940796280:AAH5b1rk94Ujcj5aEJMfhwMEan5D_Xcaos0"        # ⚠️ ใช้ token ใหม่ (หลัง revoke ตัวเก่า)
TG_CHAT_ID = "8979584153"            # chat_id ของ M (จาก m_worker)
# ----------------------------

def send_text(text):
    """ส่งข้อความธรรมดา"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": text}
    r = requests.post(url, data=data, timeout=10)
    print(f"ส่งข้อความ: status={r.status_code}")
    print(r.json())
    return r.status_code == 200

def send_photo(img_path, caption=""):
    """ส่งรูป + คำบรรยาย"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    with open(img_path, "rb") as f:
        files = {"photo": f}
        data = {"chat_id": TG_CHAT_ID, "caption": caption}
        r = requests.post(url, data=data, files=files, timeout=10)
    print(f"ส่งรูป: status={r.status_code}")
    print(r.json())
    return r.status_code == 200

if __name__ == "__main__":
    print("=== เทสส่ง Telegram หา M ===\n")

    # เทส 1: ส่งข้อความ
    print("[1] ส่งข้อความ...")
    ok1 = send_text("🧪 ทดสอบระบบ - M กำลังจะพ่นยาใช่ไหม?")

    # เทส 2: ส่งรูป (ถ้าใส่ path ภาพมาด้วย)
    if len(sys.argv) > 1:
        print("\n[2] ส่งรูป...")
        ok2 = send_photo(sys.argv[1], caption="🧪 ทดสอบส่งรูป")
    else:
        print("\n[2] ข้ามส่งรูป (ไม่ได้ใส่ path ภาพ)")
        ok2 = True

    print("\n=== ผล ===")
    print(f"ข้อความ: {'✅ สำเร็จ' if ok1 else '❌ ล้มเหลว'}")
    if len(sys.argv) > 1:
        print(f"รูป: {'✅ สำเร็จ' if ok2 else '❌ ล้มเหลว'}")