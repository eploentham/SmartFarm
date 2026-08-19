#!/usr/bin/env python3
# bottle_capture.py — รันบน Pi5 (pi5camera01)
# ---------------------------------------------------------------------------
# Part 4: เจ้าของการถ่ายขวด/ซองสารเคมี 1 ใบต่อ 1 คำขอ
#
#   subscribe sfc2/capture/request  {session_id}
#     → ถ่าย 1 ใบ → OCR (Gemini) → publish sfc2/capture/result
#                                     {session_id, image_path, data, ok}
#
# ⚠️ 1 process = 1 เจ้าของกล้อง (CSI เปิดซ้อน = device busy)
#    real mode reuse pattern ของ capture_and_read.py: tv_display.py เป็นเจ้าของ
#    กล้อง+จอ TV เราขอถ่ายผ่าน HTTP POST /capture (ไม่เปิดกล้องเอง)
#
# MOCK MODE (ค่าเริ่มต้นตอนนี้): ข้ามกล้อง+Gemini คืน "fixed text" ไปก่อน
#    → ทดสอบ flow เต็มได้กลางคืน/ที่มืด แล้วค่อยเปิด real ตอนกลางวัน
#      ตั้ง env BOTTLE_MOCK=0 เพื่อใช้กล้อง+Gemini จริง
# ---------------------------------------------------------------------------

import json
import os
import time

import paho.mqtt.client as mqtt

# ---------- config ----------
BROKER, PORT = "192.168.0.254", 1883
MQTT_USER, MQTT_PASS = "pop", "pop1"

T_REQUEST = "sfc2/capture/request"   # subscribe: ขอถ่าย 1 ใบ
T_RESULT  = "sfc2/capture/result"    # publish: ผล OCR

MOCK = os.environ.get("BOTTLE_MOCK", "1") == "1"   # 1 = mock (ค่าเริ่มต้น)

# real mode เท่านั้น
TV_URL       = os.environ.get("TV_URL", "http://localhost:5000")   # tv_display.py
CAPTURE_DIR  = os.path.expanduser("~/smartfarm/detectbottle/captures")
# ----------------------------

# ---- ข้อมูล mock: ขวดจริงที่พี่เอกถ่ายมาทดสอบ (โมคารอล / kasugamycin) + สลับให้หลากหลาย ----
_MOCK_BOTTLES = [
    {
        "brand_name": "โมคารอล",
        "active_ingredients": [{"name": "kasugamycin hydrochloride hydrate",
                                "concentration_percent": 2.0}],
        "formulation_code": "SL",
        "registration_number": "วอส. 217/2566",
        "batch_number": None,
        "expiry_date": "2027-02-01",
        "chemical_category": "fungicide",
        "application_category": "biological",   # kasugamycin = สารปฏิชีวนะจากจุลินทรีย์
        "confidence": 0.95,
    },
    {
        "brand_name": "ไดเทน เอ็ม-45",
        "active_ingredients": [{"name": "mancozeb", "concentration_percent": 80.0}],
        "formulation_code": "WP",
        "registration_number": "วอส. 45/2560",
        "batch_number": "L2409",
        "expiry_date": "2026-12-31",
        "chemical_category": "fungicide",
        "application_category": "chemical",
        "confidence": 0.92,
    },
    {
        "brand_name": "เซฟวิน 85",
        "active_ingredients": [{"name": "carbaryl", "concentration_percent": 85.0}],
        "formulation_code": "WP",
        "registration_number": "วอส. 88/2558",
        "batch_number": None,
        "expiry_date": "2025-06-30",            # หมดอายุแล้ว → ทดสอบ flag EXPIRED
        "chemical_category": "insecticide",
        "application_category": "chemical",
        "confidence": 0.88,
    },
]
_mock_idx = 0


def mock_capture(session_id):
    """คืนผล mock 1 ใบ (สลับชนิดไปเรื่อยๆ) — ไม่แตะกล้อง/Gemini."""
    global _mock_idx
    data = dict(_MOCK_BOTTLES[_mock_idx % len(_MOCK_BOTTLES)])
    _mock_idx += 1
    image_path = f"/tmp/mock_bottle_{session_id}_{_mock_idx}.jpg"
    print(f"[mock] session {session_id} → {data['brand_name']} "
          f"({data['application_category']})")
    return {"session_id": session_id, "image_path": image_path,
            "data": data, "ok": True}


def real_capture(session_id):
    """ถ่ายจริงผ่าน tv_display (/capture) → blur gate → Gemini OCR.
    reuse pattern capture_and_read.py — ต้องมี tv_display.py รัน + กลางวัน."""
    import urllib.request
    from gemini_extract import extract_label   # import ตอนใช้จริง (ต้องมี key)

    # 1) ขอ tv_display ถ่าย high-res still (เจ้าของกล้อง)
    try:
        req = urllib.request.Request(f"{TV_URL}/capture", method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            cap = json.load(r)
    except Exception as e:
        print(f"[real] เรียก tv_display /capture ไม่ได้: {e}")
        return {"session_id": session_id, "image_path": None,
                "data": None, "ok": False}

    if not cap.get("ok"):
        return {"session_id": session_id, "image_path": cap.get("path"),
                "data": None, "ok": False}
    path = cap["path"]

    # GATE 1 — เบลอ (local ฟรี) อย่าเปลือง Gemini call
    if cap.get("blurry"):
        print("[real] ภาพเบลอ — ให้ถ่ายใหม่")
        return {"session_id": session_id, "image_path": path,
                "data": None, "ok": False}

    # 2) Gemini OCR
    ext = extract_label(path)
    if not ext["ok"]:
        print(f"[real] Gemini ล้มเหลว: {ext['error']}")
        return {"session_id": session_id, "image_path": path,
                "data": None, "ok": False}
    return {"session_id": session_id, "image_path": path,
            "data": ext["data"], "ok": True}


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        mode = "MOCK" if MOCK else "REAL"
        print(f"เชื่อม MQTT สำเร็จ (mode={mode})")
        client.subscribe(T_REQUEST)
    else:
        print(f"เชื่อม MQTT ไม่สำเร็จ rc={rc}")


def on_message(client, userdata, msg):
    try:
        req = json.loads(msg.payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        print(f"[req] payload ไม่ใช่ JSON: {e}")
        return
    session_id = req.get("session_id")
    if session_id is None:
        print("[req] ขาด session_id — ข้าม")
        return

    result = mock_capture(session_id) if MOCK else real_capture(session_id)
    client.publish(T_RESULT, json.dumps(result, ensure_ascii=False))
    print(f"[result] → session {session_id} ok={result['ok']}")


def main():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    print(f"bottle_capture พร้อม (mock={MOCK})")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nปิด bottle_capture")
        client.disconnect()


if __name__ == "__main__":
    main()
