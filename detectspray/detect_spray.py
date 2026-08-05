#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_spray.py  (Pi 5 / CSI Camera Module 3)
ตรวจ "คนสวนถือถังพ่นยา" ที่จุดวางถัง แล้ว log ลง t_person_detection
(sprayer_detected=1). เขียนใหม่ให้ Pi 5 ไม่ร้อน.

ทำไมเวอร์ชันเดิมร้อน:
  - while True + model() ทุกเฟรม ไม่มี sleep/motion gate -> CPU 100% ตลอด
  - imgsz=640 หนักมากบน Pi 5 (ไม่มี GPU/NPU, รันบน CPU ล้วน)
  - r.plot() + cv2.imwrite ทุกเฟรม -> เปลือง CPU/disk เปล่า

วิธีทำให้เย็น (เรียงตามผลกระทบ):
  1) MOTION GATE  - รัน YOLO เฉพาะตอนภาพขยับ  <- ตัวช่วยใหญ่สุด
  2) NCNN model   - เร็ว+เย็นกว่า .pt บน Pi 5 เยอะ
  3) imgsz=320    - ครึ่งภาระของ 640
  4) throttle     - ประมวลผล 1 เฟรมทุก ~3 วิ ไม่รันรัว
  5) จำกัด thread - torch.set_num_threads(2) ไม่ยึด CPU ทุก core
  6) active hours - ทำงานเฉพาะช่วงพ่นยา (07:00-17:00) ไม่ใช่ 24 ชม.
  7) ไม่ r.plot()  - ไม่แสดงภาพก็ไม่ต้องวาดกรอบ

หมายเหตุ: 'person'/'backpack' เป็น COCO class ชั่วคราว (placeholder) —
'backpack' ใช้แทนถังพ่นยาสะพายหลังแบบหยาบๆ ยังไม่แม่น ควรเทรน custom
knapsack-sprayer model ทีหลังแล้วเปลี่ยน MODEL_PATH + TARGET_LABELS.
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path
from datetime import datetime, time as dtime

import cv2
import torch
import numpy as np
import mysql.connector
from dotenv import load_dotenv
from ultralytics import YOLO
from picamera2 import Picamera2

# ---- limit CPU threads BEFORE heavy libs spin up (keeps Pi 5 cooler) ----
torch.set_num_threads(2)
cv2.setNumThreads(2)

# ---- load .env (works for both flat ~/smartfarm/ and scripts/ layouts) ----
for _cand in (Path(__file__).resolve().parent / ".env",
              Path(__file__).resolve().parent.parent / ".env"):
    if _cand.exists():
        load_dotenv(_cand)
        break


def _env(*keys, default=None):
    for k in keys:
        v = os.getenv(k)
        if v not in (None, ""):
            return v
    return default


# ======================================================================
# CONFIG
# ======================================================================
CAMERA_CODE = "CSI-SPRAY-01"     # <=20 chars; distinguishes this CSI cam
PLOT_ID     = "DURIAN-A1"        # plot the spray station belongs to

# --- CSI camera (Camera Module 3), lens LOCKED on the tank spot ---
# Pi 5 has 2 CSI cameras connected. Pick which one points at the spray tank.
# Find the numbers with:  rpicam-hello --list-cameras
CAMERA_NUM   = 1                 # 0 = first CSI, 1 = second CSI (spray tank cam)
CAPTURE_SIZE = (640, 480)        # capture res; YOLO downsizes to IMG_SIZE
LENS_POSITION = 0.12             # fixed focus ~0.1-0.15 m (tank placement)

# --- YOLO model: NCNN export for Pi 5 speed/coolness ---
# Export once on the Pi:  yolo export model=yolov8n.pt format=ncnn imgsz=320
# -> creates yolov8n_ncnn_model/  (a directory). To fall back to .pt,
#    set MODEL_PATH = "yolov8n.pt" (slower/hotter).
MODEL_PATH   = "/home/ekapop/smartfarm/models/yolov8n_ncnn_model"
IMG_SIZE     = 320
CONF_THRESH  = 0.40
# COCO labels we care about. 'backpack' = knapsack sprayer (rough placeholder).
PERSON_LABELS  = {"person"}
SPRAYER_LABELS = {"backpack"}

# --- Throttle + motion gate (thermal) ---
PROCESS_INTERVAL_SEC = 3        # process one frame every N seconds
MOTION_PIXEL_RATIO   = 0.010    # >=1% pixels changed -> "movement"
MOTION_DIFF_THRESH   = 25

# --- Active hours (spraying is a daytime job) ---
ACTIVE_START = dtime(8, 0)      # 08:00
ACTIVE_END   = dtime(17, 0)     # 17:00

# --- Snapshots (throttled; not every frame) ---
SNAPSHOT_DIR          = "/home/ekapop/smartfarm/snapshots/spray"
SNAPSHOT_MIN_INTERVAL = 120     # save at most one snapshot / N seconds

# --- Database: Pi 5 connects to the PN64 server over the LAN ---
DB_CONFIG = {
    "host":     _env("SMARTFARM_DB_HOST", "DB_HOST", default="192.168.0.254"),  # PN64
    "port":     int(_env("SMARTFARM_DB_PORT", "DB_PORT", default="3306")),
    "user":     _env("SMARTFARM_DB_USER", "DB_USER", default="smartfarm_rw"),
    "password": _env("SMARTFARM_DB_PASSWORD", "DB_PASSWORD", default=""),
    "database": _env("SMARTFARM_DB_NAME", "DB_NAME", default="smartfarm"),
    "charset":  "utf8mb4",
}

# ======================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("detect_spray")

_running = True
def _stop(signum, _f):
    global _running
    log.info("Signal %s -> shutting down.", signum)
    _running = False
signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


# ======================================================================
# Helpers
# ======================================================================
def within_active_hours(now: datetime) -> bool:
    return ACTIVE_START <= now.time() <= ACTIVE_END


def to_gray_small(frame_bgr):
    """Small grayscale copy for the cheap motion check."""
    small = cv2.resize(frame_bgr, (320, 180))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def has_motion(prev_gray, curr_gray) -> bool:
    if prev_gray is None:
        return True
    diff = cv2.absdiff(prev_gray, curr_gray)
    changed = np.count_nonzero(diff > MOTION_DIFF_THRESH)
    return (changed / diff.size) >= MOTION_PIXEL_RATIO


def save_snapshot(frame_bgr, when: datetime) -> str | None:
    try:
        day_dir = os.path.join(SNAPSHOT_DIR, when.strftime("%Y%m%d"))
        os.makedirs(day_dir, exist_ok=True)
        path = os.path.join(day_dir, f"{CAMERA_CODE}_{when.strftime('%H%M%S')}.jpg")
        cv2.imwrite(path, frame_bgr)
        return path
    except Exception as e:
        log.warning("Snapshot save failed: %s", e)
        return None


class DB:
    """MariaDB wrapper with lazy reconnect (Pi 5 -> PN64 over LAN)."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.conn = None

    def _ensure(self):
        if self.conn is not None and self.conn.is_connected():
            return
        self.conn = mysql.connector.connect(**self.cfg, autocommit=True)
        log.info("Connected to MariaDB %s/%s", self.cfg["host"], self.cfg["database"])

    def insert(self, camera_code, plot_id, detected_at, person_count,
               sprayer_detected, confidence, snapshot_path):
        sql = ("INSERT INTO t_person_detection "
               "(camera_code, plot_id, detected_at, person_count, "
               " sprayer_detected, confidence, snapshot_path) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s)")
        params = (camera_code, plot_id, detected_at, int(person_count),
                  int(sprayer_detected), round(float(confidence), 3), snapshot_path)
        for attempt in (1, 2):
            try:
                self._ensure()
                cur = self.conn.cursor()
                cur.execute(sql, params)
                cur.close()
                return
            except mysql.connector.Error as e:
                log.warning("DB insert attempt %d failed: %s", attempt, e)
                self.conn = None
        log.error("Giving up on this row (DB unreachable).")


# ======================================================================
# Main
# ======================================================================
def main():
    if not DB_CONFIG["password"]:
        log.error("No DB password (SMARTFARM_DB_PASSWORD/DB_PASSWORD) in .env.")
        sys.exit(1)

    log.info("Loading YOLO model: %s", MODEL_PATH)
    model = YOLO(MODEL_PATH, task="detect")
    names = model.names

    # CSI camera setup (fixed focus on the tank spot)
    # Pass CAMERA_NUM so we open the RIGHT camera (Pi 5 has 2 CSI cams).
    picam2 = Picamera2(CAMERA_NUM)
    cfg = picam2.create_preview_configuration(
        main={"format": "RGB888", "size": CAPTURE_SIZE})
    picam2.configure(cfg)
    picam2.start()
    picam2.set_controls({"AfMode": 0, "LensPosition": LENS_POSITION})
    time.sleep(1)  # let AF/exposure settle

    db = DB(DB_CONFIG)
    prev_gray = None
    last_snapshot_ts = 0.0

    log.info("Spray detector started | camera=%s plot=%s", CAMERA_CODE, PLOT_ID)

    try:
        while _running:
            loop_start = time.time()
            now = datetime.now()

            # Sleep outside working hours (no capture, no YOLO -> cool).
            if not within_active_hours(now):
                prev_gray = None
                time.sleep(60)
                continue

            # Grab one frame (RGB from picamera2 -> BGR for OpenCV/YOLO).
            frame_rgb = picam2.capture_array()
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

            # Motion gate: skip YOLO if nothing moved.
            curr_gray = to_gray_small(frame_bgr)
            if not has_motion(prev_gray, curr_gray):
                prev_gray = curr_gray
                _sleep_remainder(loop_start)
                continue
            prev_gray = curr_gray

            # Run detection (NCNN on CPU, imgsz small).
            try:
                results = model.predict(frame_bgr, imgsz=IMG_SIZE,
                                        conf=CONF_THRESH, verbose=False)
            except Exception as e:
                log.error("YOLO inference error: %s", e)
                _sleep_remainder(loop_start)
                continue

            # Tally person + sprayer boxes.
            person_count = 0
            sprayer_detected = 0
            top_conf = 0.0
            for box in results[0].boxes:
                label = names[int(box.cls[0])]
                conf = float(box.conf[0])
                if label in PERSON_LABELS:
                    person_count += 1
                    top_conf = max(top_conf, conf)
                elif label in SPRAYER_LABELS:
                    sprayer_detected = 1
                    top_conf = max(top_conf, conf)

            # Log only if someone (or a sprayer) is at the station.
            if person_count > 0 or sprayer_detected:
                detected_at = now.strftime("%Y-%m-%d %H:%M:%S")
                snapshot_path = None
                if (loop_start - last_snapshot_ts) >= SNAPSHOT_MIN_INTERVAL:
                    snapshot_path = save_snapshot(frame_bgr, now)
                    last_snapshot_ts = loop_start

                db.insert(
                    camera_code=CAMERA_CODE, plot_id=PLOT_ID,
                    detected_at=detected_at,
                    person_count=max(person_count, 1),   # >=1 if sprayer seen
                    sprayer_detected=sprayer_detected,
                    confidence=top_conf, snapshot_path=snapshot_path,
                )
                log.info("SPRAY station: person=%d sprayer=%d conf=%.3f snap=%s",
                         person_count, sprayer_detected, top_conf,
                         snapshot_path or "-")

            _sleep_remainder(loop_start)
    finally:
        picam2.stop()
        log.info("Spray detector stopped safely.")


def _sleep_remainder(loop_start: float):
    """Hold a steady ~PROCESS_INTERVAL_SEC cadence (keeps CPU idle between)."""
    remaining = PROCESS_INTERVAL_SEC - (time.time() - loop_start)
    if remaining > 0:
        time.sleep(remaining)


if __name__ == "__main__":
    main()