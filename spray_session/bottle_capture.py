#!/usr/bin/env python3
# bottle_capture.py — เจ้าของการ "อ่านฉลากขวด" 1 ใบต่อ 1 คำขอ
# ---------------------------------------------------------------------------
# Part 4:
#   subscribe sfc2/capture/request  {session_id}
#     → หยิบภาพขวด → OCR (Gemini) → publish sfc2/capture/result
#                                     {session_id, image_path, data, ok}
#
# ที่มาของ "ภาพขวด" มี 2 โหมด (เลือกด้วย env):
#
#   MOCK MODE      BOTTLE_MOCK=1 (ค่าเริ่มต้น)
#     ข้ามภาพ+Gemini คืน "fixed text" ไปก่อน — เทส flow เต็มได้ทุกเวลา
#
#   REAL MODE      BOTTLE_MOCK=0
#     MQTT FRAME BRIDGE: subscribe เฟรม JPEG จาก topic กล้อง (BOTTLE_FRAME_TOPIC)
#     เก็บเฟรม "ล่าสุด" ไว้ใน RAM. พอมี capture/request → เอาเฟรมล่าสุดไป Gemini จริง.
#     → เทส Gemini path ได้แม้กลางคืน: publish รูปขวดเข้า topic ด้วย send_bottle.py
#       (ภายหลังจะสลับให้ pi5camera publish เฟรมสดเข้า topic เดียวกันได้เลย)
#
# ⚠️ REAL MODE ต้องมี env GEMINI_API_KEY + import config/gemini_extract ได้
#    (รันจากโฟลเดอร์ detectbottle หรือ PYTHONPATH ชี้ไปที่นั่น)
# ---------------------------------------------------------------------------

import json
import os
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

# ---------- config ----------
BROKER, PORT = "192.168.0.254", 1883
MQTT_USER, MQTT_PASS = "pop", "pop1"

T_REQUEST = "sfc2/capture/request"   # subscribe: ขอถ่าย 1 ใบ
T_RESULT  = "sfc2/capture/result"    # publish: ผล OCR

MOCK = os.environ.get("BOTTLE_MOCK", "1") == "1"   # 1 = mock (ค่าเริ่มต้น)

# real mode: topic เฟรมกล้องขวด (แยกจาก smartfarm/cam1/frame ที่เป็น worker view)
BOTTLE_FRAME_TOPIC = os.environ.get("BOTTLE_FRAME_TOPIC", "smartfarm/bottlecam/frame")
CAPTURE_DIR  = os.path.expanduser(
    os.environ.get("CAPTURE_DIR", "~/smartfarm/detectbottle/captures"))
FRAME_MAX_AGE = int(os.environ.get("BOTTLE_FRAME_MAX_AGE", "300"))  # วิ; เฟรมเก่ากว่านี้ = ไม่รับ
# ----------------------------

# เฟรม JPEG ล่าสุดที่รับจาก topic กล้อง (real mode) — paho เรียก callback ทีละอัน
# แต่กัน race กับ publisher thread ด้วย lock เบาๆ
_frame_lock = threading.Lock()
_latest = {"bytes": None, "ts": 0.0}

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


def _blur_variance(jpg_bytes):
    """Laplacian variance ของภาพ (ยิ่งต่ำ = ยิ่งเบลอ). คืน None ถ้าไม่มี cv2."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    arr = np.frombuffer(jpg_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def real_capture(session_id):
    """เอาเฟรมล่าสุดจาก MQTT (BOTTLE_FRAME_TOPIC) → blur gate → Gemini OCR.
    ไม่เปิดกล้องเอง — ใครก็ได้ publish JPEG เข้า topic (send_bottle.py / pi5camera)."""
    from gemini_extract import extract_label   # import ตอนใช้จริง (ต้องมี key)
    try:
        from config import BLUR_THRESHOLD
    except Exception:
        BLUR_THRESHOLD = 100.0

    # 1) หยิบเฟรมล่าสุด
    with _frame_lock:
        jpg = _latest["bytes"]
        age = time.time() - _latest["ts"] if _latest["ts"] else None
    if not jpg:
        print(f"[real] ยังไม่ได้รับภาพจาก {BOTTLE_FRAME_TOPIC} — ให้กล้องส่งภาพก่อน")
        return {"session_id": session_id, "image_path": None,
                "data": None, "ok": False,
                "error": "no_frame"}
    if age is not None and age > FRAME_MAX_AGE:
        print(f"[real] เฟรมเก่าเกินไป ({age:.0f}s > {FRAME_MAX_AGE}s) — ให้ถ่ายใหม่")
        return {"session_id": session_id, "image_path": None,
                "data": None, "ok": False, "error": "stale_frame"}

    # 2) เซฟลงดิสก์ (evidence)
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(CAPTURE_DIR, f"bottle_{session_id}_{ts}.jpg")
    with open(path, "wb") as f:
        f.write(jpg)

    # GATE 1 — เบลอ (local ฟรี) อย่าเปลือง Gemini call
    var = _blur_variance(jpg)
    if var is not None and var < BLUR_THRESHOLD:
        print(f"[real] ภาพเบลอ (var={var:.0f} < {BLUR_THRESHOLD}) — ให้ถ่ายใหม่")
        return {"session_id": session_id, "image_path": path,
                "data": None, "ok": False, "error": "blurry"}

    # 3) Gemini OCR
    print(f"[real] session {session_id}: ส่ง {path} เข้า Gemini "
          f"(var={var if var is not None else 'n/a'})…")
    ext = extract_label(path)
    if not ext["ok"]:
        print(f"[real] Gemini ล้มเหลว: {ext['error']}")
        return {"session_id": session_id, "image_path": path,
                "data": None, "ok": False, "error": ext["error"]}

    # กันไว้: real Gemini อาจไม่คืน application_category / active_ingredients ครบ
    data = dict(ext["data"] or {})
    data.setdefault("application_category", "chemical")
    data.setdefault("active_ingredients", [])

    # GATE 2 — readability: ภาพชัดแต่ไม่เห็นขวด/ฉลาก → ให้ถ่ายใหม่ (อย่าบันทึกขวดเปล่า)
    if not _readable(data):
        print("[real] ไม่เห็นขวด/อ่านฉลากไม่ได้ — ให้ถ่ายใหม่")
        return {"session_id": session_id, "image_path": path,
                "data": None, "ok": False, "error": "no_label"}

    print(f"[real] อ่านได้: {data.get('brand_name')} "
          f"({data.get('application_category')})")
    return {"session_id": session_id, "image_path": path,
            "data": data, "ok": True}


def _readable(data):
    """True ถ้า Gemini เจอขวด/ฉลากจริง (ไม่ใช่เฟรมเปล่า/เสื้อคนงาน).
    reuse logic จาก capture_and_read._readable."""
    ings = data.get("active_ingredients") or []
    has_ingredient = bool(ings and ings[0].get("name"))
    has_brand = bool(data.get("brand_name"))
    conf = data.get("confidence") or 0
    return has_ingredient or (has_brand and conf >= 0.4)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        mode = "MOCK" if MOCK else "REAL"
        print(f"เชื่อม MQTT สำเร็จ (mode={mode})")
        client.subscribe(T_REQUEST)
        if not MOCK:
            client.subscribe(BOTTLE_FRAME_TOPIC)
            print(f"  subscribe เฟรมกล้อง: {BOTTLE_FRAME_TOPIC}")
    else:
        print(f"เชื่อม MQTT ไม่สำเร็จ rc={rc}")


def on_message(client, userdata, msg):
    # --- เฟรมกล้อง (real mode): payload = JPEG bytes ดิบ ไม่ใช่ JSON ---
    if msg.topic == BOTTLE_FRAME_TOPIC:
        with _frame_lock:
            _latest["bytes"] = msg.payload
            _latest["ts"] = time.time()
        print(f"[frame] รับเฟรมล่าสุด {len(msg.payload):,} bytes")
        return

    # --- คำขอถ่าย (JSON) ---
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
