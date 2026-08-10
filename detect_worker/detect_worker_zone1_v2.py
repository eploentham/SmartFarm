#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_worker_zone1_v2.py  (SNAPSHOT version — ffmpeg grabs one frame / 15s)
Worker (คนสวน) presence detector for ONE orchard CCTV camera.

Versions:
  * detect_worker_zone1_v1.py  (RTSP version)  — OpenCV holds an RTSP stream
    open 24/7. Kept failing on this VIGI camera (bytestream errors -> endless
    "reopen stream"). Kept as a fallback.
  * detect_worker_zone1_v2.py  (SNAPSHOT version, THIS FILE) — ffmpeg grabs a
    SINGLE frame each cycle, then YOLO runs on it. No live stream to stall,
    no reopen loop. ffmpeg connects to this camera reliably (cctv_wall proves
    it), so this is far more stable.

Flow every SAMPLE_INTERVAL_SEC:
  ffmpeg grab 1 frame -> YOLO detect person -> if found: log + snapshot.

One script per camera. Copy -> detect_worker_zone2_v2.py, edit the CONFIG block.
Secrets come from ~/smartfarm/.env (never hard-coded).
"""

import os
import sys
import time
import shutil
import signal
import logging
import subprocess
from pathlib import Path
from datetime import datetime, time as dtime

import mysql.connector
from dotenv import load_dotenv
from ultralytics import YOLO

# ---- load .env (one level up: ~/smartfarm/.env) ----------------------
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)


def _env(*keys, default=None):
    for k in keys:
        v = os.getenv(k)
        if v not in (None, ""):
            return v
    return default


# ======================================================================
# CONFIG
# ======================================================================
CAMERA_CODE = "CAM-ORCHARD-01"      # <= 20 chars
PLOT_ID     = "DURIAN-A1"           # must match m_plot.plot_code (or None)

# --- RTSP source (password RAW, not URL-encoded — VIGI rejects encoded) ---
RTSP_USER = _env("RTSP_USER", default="admin")
RTSP_PASS = _env("RTSP_PASSWORD", "RTSP_PASS", default="CHANGE_ME")
RTSP_HOST = _env("RTSP_HOST", default="192.168.0.251")
RTSP_PATH = _env("RTSP_PATH", default="stream2")     # sub=stream2, main=stream1
RTSP_URL  = f"rtsp://{RTSP_USER}:{RTSP_PASS}@{RTSP_HOST}:554/{RTSP_PATH}"

# --- YOLO model (OpenVINO on Intel iGPU) ---
MODEL_PATH     = "/home/ekapop/smartfarm/models/yolo11n_openvino_model"
YOLO_DEVICE    = "intel:gpu"        # fallback: "cpu"
IMG_SIZE       = 320
PERSON_CLASS   = 0                  # COCO class 0 = person
CONF_THRESHOLD = 0.45

# --- Sampling ---
SAMPLE_INTERVAL_SEC = 15            # grab one frame every N seconds
GRAB_TIMEOUT_SEC    = 20            # give ffmpeg up to N s to fetch a frame
FRAME_TMP           = f"/tmp/worker_{CAMERA_CODE}.jpg"   # ffmpeg writes here

# --- Active hours ---
ACTIVE_START = dtime(8, 0)         # 08:00
ACTIVE_END   = dtime(17, 0)        # 17:00

# --- Snapshots (throttled) ---
SNAPSHOT_DIR          = "/home/ekapop/smartfarm/snapshots/worker"
SNAPSHOT_MIN_INTERVAL = 120        # keep at most one snapshot / N seconds

# --- Database (PN64 localhost) ---
DB_CONFIG = {
    "host":     _env("SMARTFARM_DB_HOST", "DB_HOST", default="127.0.0.1"),
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
log = logging.getLogger("detect_worker")

_running = True
def _stop(signum, _f):
    global _running
    log.info("Signal %s received -> shutting down.", signum)
    _running = False
signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


# ======================================================================
# Helpers
# ======================================================================
def within_active_hours(now: datetime) -> bool:
    return ACTIVE_START <= now.time() <= ACTIVE_END


def grab_frame(dst: str) -> bool:
    """
    Grab ONE fresh frame from the camera with ffmpeg and save it to `dst`.
    Returns True on success. ffmpeg connects, decodes a single frame, exits —
    no long-lived stream to stall. A bad grab just means we skip this cycle.
    """
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-rtsp_transport", "tcp",
        "-i", RTSP_URL,
        "-frames:v", "1",          # one frame only
        "-q:v", "3",               # good JPEG quality
        "-an",                     # no audio
        "-loglevel", "error",
        dst,
    ]
    try:
        r = subprocess.run(cmd, timeout=GRAB_TIMEOUT_SEC,
                           capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        log.warning("ffmpeg grab timed out (%ds).", GRAB_TIMEOUT_SEC)
        return False
    if r.returncode != 0:
        log.warning("ffmpeg grab failed: %s", (r.stderr or "").strip()[:200])
        return False
    return os.path.exists(dst) and os.path.getsize(dst) > 0


def save_snapshot(src: str, when: datetime) -> str | None:
    """Copy the grabbed frame into a dated folder; return its path."""
    try:
        day_dir = os.path.join(SNAPSHOT_DIR, when.strftime("%Y%m%d"))
        os.makedirs(day_dir, exist_ok=True)
        dst = os.path.join(day_dir, f"{CAMERA_CODE}_{when.strftime('%H%M%S')}.jpg")
        shutil.copyfile(src, dst)
        return dst
    except Exception as e:
        log.warning("Snapshot save failed: %s", e)
        return None


class DB:
    """MariaDB wrapper with lazy reconnect."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.conn = None

    def _ensure(self):
        if self.conn is not None and self.conn.is_connected():
            return
        self.conn = mysql.connector.connect(**self.cfg, autocommit=True)
        log.info("Connected to MariaDB %s/%s", self.cfg["host"], self.cfg["database"])

    def insert_detection(self, camera_code, plot_id, detected_at,
                         person_count, sprayer_detected, confidence, snapshot_path):
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
        log.error("Giving up on this detection row (DB unreachable).")


# ======================================================================
# Main
# ======================================================================
def main():
    if not DB_CONFIG["password"]:
        log.error("No DB password (SMARTFARM_DB_PASSWORD) in .env.")
        sys.exit(1)

    log.info("Loading YOLO model: %s (device=%s)", MODEL_PATH, YOLO_DEVICE)
    model = YOLO(MODEL_PATH, task="detect")

    db = DB(DB_CONFIG)
    last_snapshot_ts = 0.0

    log.info("Loaded .env from %s", ENV_PATH)
    log.info("Worker detector (snapshot mode) started | camera=%s plot=%s",
             CAMERA_CODE, PLOT_ID)

    while _running:
        loop_start = time.time()
        now = datetime.now()

        # 1) Sleep outside working hours.
        if not within_active_hours(now):
            time.sleep(60)
            continue

        # 2) Grab ONE frame with ffmpeg (no long-lived stream).
        if not grab_frame(FRAME_TMP):
            _sleep_remainder(loop_start)   # skip this cycle, try again next
            continue

        # 3) Run person detection on the grabbed frame.
        try:
            results = model.predict(
                FRAME_TMP, imgsz=IMG_SIZE, device=YOLO_DEVICE,
                classes=[PERSON_CLASS], conf=CONF_THRESHOLD, verbose=False,
            )
        except Exception as e:
            log.error("YOLO inference error: %s", e)
            _sleep_remainder(loop_start)
            continue

        boxes = results[0].boxes
        person_count = 0 if boxes is None else len(boxes)

        # 4) If a worker is present -> record it.
        if person_count > 0:
            top_conf = float(boxes.conf.max())
            detected_at = now.strftime("%Y-%m-%d %H:%M:%S")

            snapshot_path = None
            if (loop_start - last_snapshot_ts) >= SNAPSHOT_MIN_INTERVAL:
                snapshot_path = save_snapshot(FRAME_TMP, now)
                last_snapshot_ts = loop_start

            db.insert_detection(
                camera_code=CAMERA_CODE, plot_id=PLOT_ID,
                detected_at=detected_at, person_count=person_count,
                sprayer_detected=0, confidence=top_conf,
                snapshot_path=snapshot_path,
            )
            log.info("WORKER detected: count=%d conf=%.3f snap=%s",
                     person_count, top_conf, snapshot_path or "-")

        _sleep_remainder(loop_start)

    log.info("Detector stopped.")


def _sleep_remainder(loop_start: float):
    """Hold a steady SAMPLE_INTERVAL_SEC cadence."""
    remaining = SAMPLE_INTERVAL_SEC - (time.time() - loop_start)
    if remaining > 0:
        time.sleep(remaining)


if __name__ == "__main__":
    main()