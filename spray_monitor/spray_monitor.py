"""Main loop: YOLO detection on cam 1 → Telegram → cam 2 → Gemini → DB."""
import cv2
import time
import logging
import os
from datetime import datetime
from ultralytics import YOLO
from picamera2 import Picamera2

from config import (CAM1_INDEX, YOLO_CONF, TRIGGER_HOLD_SECONDS,
                    COOLDOWN_SECONDS, PHOTO_READY_TIMEOUT_S,
                    TG_ALLOWED_WORKERS, LOG_DIR)
from db_helper        import insert_detection, update_status
from telegram_helper  import send_message, send_photo, wait_for_yes_no
from tts_helper       import speak_th
from gemini_helper    import analyze_chemical
from tv_display       import TvDisplay

# ───── logging ─────
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/spray_monitor.log"),
        logging.StreamHandler(),
    ])
log = logging.getLogger('spray')

# ───── camera 1 (detection) ─────
def init_detection_cam():
    cam = Picamera2(camera_num=CAM1_INDEX)
    cfg = cam.create_preview_configuration(
        main={'format': 'RGB888', 'size': (640, 480)})
    cam.configure(cfg)
    cam.set_controls({'AfMode': 2})
    cam.start()
    return cam

# ───── one full workflow run ─────
def run_workflow(app_id: int, conf: float):
    """Run stages 2-7. Each stage updates DB status."""
    worker = TG_ALLOWED_WORKERS[0]                       # assume M is the main sprayer

    # Stage 2 — voice + Telegram
    log.info(f"app#{app_id} stage 2: voice + telegram")
    speak_th(f"คุณ {worker} คุณกำลังพ่นยาใช่ไหม ถ้าใช่ ตอบ yes ทาง telegram")
    prompt_ts = time.time()
    send_message(f"🌿 Detected possible spraying by worker {worker}.\n"
                 f"Reply *yes* to start chemical logging, *no* to cancel.")
    update_status(app_id, 'awaiting_confirm')

    # Stage 3 — wait for reply
    reply = wait_for_yes_no(prompt_ts)
    if reply != 'yes':
        log.info(f"app#{app_id} cancelled (reply={reply})")
        update_status(app_id, 'cancelled' if reply == 'no' else 'timeout',
                      note=f"telegram_reply={reply}")
        return
    update_status(app_id, 'confirmed',
                  confirmed_at=datetime.now(),
                  telegram_confirm_yn='Y',
                  worker_code=worker)

    # Stage 4-5 — show cam 2, wait for bottle, countdown, capture
    log.info(f"app#{app_id} stage 4: TV display")
    tv = TvDisplay()
    try:
        update_status(app_id, 'awaiting_photo')
        tv.show_live(seconds=8,
                     instruction='Hold the bottle in front of camera')
        speak_th("กรุณาแสดงขวดยา หน้ากล้อง พร้อมแล้วนับถอยหลัง")
        tv.show_live(seconds=5,
                     instruction='Ready... countdown starting')

        photo_path = tv.countdown_and_capture()
        log.info(f"app#{app_id} captured: {photo_path}")
        update_status(app_id, 'captured',
                      captured_at=datetime.now(),
                      chemical_photo_path=photo_path)

        # Stage 6 — Gemini
        tv.show_message(['Analyzing chemical...', 'AI is reading the label'], seconds=2)
        result = analyze_chemical(photo_path)
        parsed = result['parsed']

        update_status(app_id, 'analyzed',
                      analyzed_at=datetime.now(),
                      chemical_name     = parsed.get('chemical_name'),
                      active_ingredient = parsed.get('active_ingredient'),
                      chemical_type     = parsed.get('chemical_type'),
                      frac_code         = parsed.get('frac_code'),
                      irac_code         = parsed.get('irac_code'),
                      gemini_raw_response = result['raw'])

        # Show result on TV + send to Telegram
        chem = parsed.get('chemical_name') or 'Unknown'
        ai_ing = parsed.get('active_ingredient') or '-'
        tv.show_message([f"Identified:", chem, ai_ing, "✅ Saved"], seconds=5)
        send_photo(photo_path,
                   caption=f"✅ Logged: {chem}\nActive: {ai_ing}\nID: {app_id}")

        update_status(app_id, 'completed')

    finally:
        tv.close()

# ───── main detection loop ─────
def main():
    model = YOLO('yolov8n.pt')
    cam   = init_detection_cam()
    log.info("Spray monitor started — watching for worker + tank")

    both_seen_since = None
    last_trigger_at = 0

    try:
        while True:
            frame = cv2.cvtColor(cam.capture_array(), cv2.COLOR_RGB2BGR)
            results = model(frame, conf=YOLO_CONF, imgsz=640, verbose=False)

            seen_person = False
            seen_bag    = False
            bag_conf    = 0.0
            for r in results:
                for box in r.boxes:
                    label = model.names[int(box.cls[0])]
                    c     = float(box.conf[0])
                    if label == 'person'   and c >= YOLO_CONF: seen_person = True
                    if label == 'backpack' and c >= YOLO_CONF:
                        seen_bag = True
                        bag_conf = max(bag_conf, c)

            if seen_person and seen_bag:
                both_seen_since = both_seen_since or time.time()
                held = time.time() - both_seen_since
                cooldown_ok = (time.time() - last_trigger_at) > COOLDOWN_SECONDS
                if held >= TRIGGER_HOLD_SECONDS and cooldown_ok:
                    log.info(f"TRIGGER: person+backpack held {held:.1f}s, conf={bag_conf:.2f}")
                    last