#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_worker_zone1.py
Worker (คนสวน) presence detector for ONE orchard CCTV camera.

Same pattern as detect_yellowing_durian.py:
  * Runs on PN64 (Intel iGPU + OpenVINO YOLO).
  * Reads ONE RTSP CCTV stream (VIGI C330I).
  * Motion-gated inference -> YOLO only runs when the frame changes
    (biggest thermal win, same lesson as detect_spray.py). imgsz=320.
  * Logs each positive detection into smartfarm.t_person_detection.
  * Non-real-time ACTIVITY LOG (feeds the daily Telegram digest,
    NOT a live security alarm).

One script per camera/zone. To add a second camera:
  cp detect_worker_zone1.py detect_worker_zone2.py
  and edit only the CONFIG block (CAMERA_CODE / PLOT_ID / RTSP_URL).

DB password comes from the environment, never hard-coded:
  export WORKER_DB_PASSWORD='...'
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, time as dtime

import cv2
import numpy as np
import mysql.connector
from dotenv import load_dotenv
from ultralytics import YOLO

# ======================================================================
# Load secrets from the .env file
# ======================================================================
# Layout on PN64:
#   ~/smartfarm/.env                              <- secrets live HERE
#   ~/smartfarm/scripts/detect_worker_zone1.py    <- this file
#
# __file__            = .../smartfarm/scripts/detect_worker_zone1.py
#   .parent           = .../smartfarm/scripts
#   .parent.parent    = .../smartfarm          (the folder that has .env)
#
# Using an ABSOLUTE path means .env loads correctly even under systemd,
# no matter what WorkingDirectory / current folder the service uses.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

#print(f"Loaded .env from {ENV_PATH} (SMARTFARM_DB_PASSWORD is {'set' if os.getenv('SMARTFARM_DB_PASSWORD') else 'NOT set'})")
#print(f"Loaded .env from {ENV_PATH}")

def _env(*keys, default=None):
    """Return the first non-empty env var among `keys` (lets us fall back
    to the generic DB_* names your .env may already use)."""
    for k in keys:
        v = os.getenv(k)
        if v not in (None, ""):
            return v
    return default

# ======================================================================
# CONFIG  — edit this block per camera. Everything else stays the same.
# ======================================================================

# --- Camera / zone identity (goes into t_person_detection) ---
CAMERA_CODE = "CAM-ORCHARD-01"      # e.g. CAM-ORCHARD-01 ; must be <= 20 chars
PLOT_ID     = "DURIAN-A1"           # must match m_plot.plot_code (or None)

# --- RTSP source (VIGI C330I sub-stream = light + thermal-safe) ---
# TP-Link VIGI: /stream1 = main (2304x1296), /stream2 = sub (640x480).
# Use the SUB stream for detection — plenty for a "person in frame" check.
RTSP_USER = _env("RTSP_USER", default="admin")
RTSP_PASS = _env("RTSP_PASSWORD", "RTSP_PASS", default="CHANGE_ME")   # from .env
#RTSP_PASS = "Ekartc2c51*"
RTSP_HOST = _env("RTSP_HOST", default="192.168.0.251")               # VIGI camera IP
RTSP_PATH = _env("RTSP_PATH", default="stream2")                     # sub=stream2, main=stream1
# URL-encode user & pass so special chars (@ : / # & ?) don't break the URL.
#RTSP_URL  = (
#    f"rtsp://{quote(RTSP_USER, safe='')}:{quote(RTSP_PASS, safe='')}"
#    f"@{RTSP_HOST}:554/{RTSP_PATH}"
#)
RTSP_URL  = (
    f"rtsp://{RTSP_USER}:{RTSP_PASS}"
    f"@{RTSP_HOST}:554/{RTSP_PATH}"
)
# --- YOLO model (OpenVINO-exported, runs on Intel iGPU) ---
# Export once on PN64:
#   yolo export model=yolo11n.pt format=openvino imgsz=320
# -> creates ./yolo11n_openvino_model/  (a directory, not a .pt file)
MODEL_PATH   = "/home/ekapop/smartfarm/models/yolo11n_openvino_model"
YOLO_DEVICE  = "intel:gpu"   # Intel iGPU via OpenVINO. Fallback: "cpu"
IMG_SIZE     = 320           # small = cool. Enough for whole-person boxes.
PERSON_CLASS = 0             # COCO class 0 = "person"
CONF_THRESHOLD = 0.45        # min confidence to count as a real person

# --- Sampling & motion gating (keeps the iGPU cool) ---
SAMPLE_INTERVAL_SEC = 15     # take one sample every N seconds (not real-time)
MOTION_PIXEL_RATIO  = 0.010  # >=1.0% of pixels changed -> "there is movement"
MOTION_DIFF_THRESH  = 25     # per-pixel diff level counted as "changed"

# --- Stream resilience ---
# A corrupt H.264 frame makes read() fail, but that does NOT mean the stream
# is dead. Only reopen after this many failures IN A ROW (skip the rest).
MAX_READ_FAILS = 10

# --- Active hours (only watch while workers are around) ---
# Daytime only: 08:00–17:00. Outside this window the detector releases the
# camera and sleeps ("กลางคืนพัก" = rests at night, no inference, iGPU cool).
ACTIVE_START = dtime(8, 0)    # 08:00
ACTIVE_END   = dtime(17, 0)   # 17:00

# --- Snapshots (saved for later review; throttled to save disk) ---
SNAPSHOT_DIR          = "/home/ekapop/smartfarm/snapshots/worker"
SNAPSHOT_MIN_INTERVAL = 120  # save at most one snapshot every N seconds

# --- Database (script runs ON PN64 -> localhost) ---
DB_CONFIG = {
    # WORKER_DB_* keys win; if they are missing we fall back to the generic
    # DB_* keys that may already be in your .env.
    # NOTE: this script INSERTs, so the user MUST have write privilege.
    # If your generic DB_USER is read-only (e.g. claude_readonly), add
    # WORKER_DB_USER=smartfarm_rw + WORKER_DB_PASSWORD=... to .env.
    "host":     _env("SMARTFARM_DB_HOST", "DB_HOST", default="127.0.0.1"),
    "port":     int(_env("SMARTFARM_DB_PORT", "DB_PORT", default="3306")),
    "user":     _env("SMARTFARM_DB_USER", "DB_USER", default="smartfarm_rw"),
    "password": _env("SMARTFARM_DB_PASSWORD", "DB_PASSWORD", default=""),
    "database": _env("SMARTFARM_DB_NAME", "DB_NAME", default="smartfarm"),
    "charset":  "utf8mb4",
}

# NOTE: Real-time alerts are intentionally NOT here. Worker activity is a
# non-security use case -> a once-a-day DIGEST (worker_activity_summary.py,
# runs 20:00) reads this data and sends one Telegram summary. This script's
# only job is: detect -> log to t_person_detection -> save snapshots.

# ======================================================================
# Logging (systemd/journalctl captures stdout)
# ======================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("detect_worker")
log.info("Loaded .env from %s", ENV_PATH)
# Graceful shutdown flag, set by SIGTERM (systemd stop) / SIGINT (Ctrl-C)
_running = True
def _stop(signum, _frame):
    global _running
    log.info("Signal %s received -> shutting down.", signum)
    _running = False
signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


# ======================================================================
# Helpers
# ======================================================================
def within_active_hours(now: datetime) -> bool:
    """True only between ACTIVE_START and ACTIVE_END (local time)."""
    return ACTIVE_START <= now.time() <= ACTIVE_END

def open_stream() -> cv2.VideoCapture:
    """
    Open the RTSP stream over TCP with a SOCKET TIMEOUT so a stalled stream
    makes read() fail in ~5s instead of blocking for minutes.
      stimeout          = socket timeout in microseconds (5_000_000 = 5s)
      max_delay         = tolerate reordering/jitter
      reorder_queue_size= 0 -> don't wait to reorder packets (lower latency)
    This is what lets us recover fast (like mpv does) instead of freezing.
    """
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "rtsp_transport;tcp"
        "|stimeout;5000000"
        "|max_delay;500000"
        "|reorder_queue_size;0"
    )
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    # Keep the internal buffer tiny so we always read a FRESH frame.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap

def has_motion(prev_gray, curr_gray) -> bool:
    """
    Cheap frame-difference gate. Returns True if enough pixels changed.
    Running this before YOLO is what keeps the iGPU from overheating.
    """
    if prev_gray is None:
        return True  # first sample: always inspect once
    diff = cv2.absdiff(prev_gray, curr_gray)
    changed = np.count_nonzero(diff > MOTION_DIFF_THRESH)
    ratio = changed / diff.size
    return ratio >= MOTION_PIXEL_RATIO


def to_gray_small(frame):
    """Grayscale + downscale copy used ONLY for the motion check (fast)."""
    small = cv2.resize(frame, (320, 180))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def save_snapshot(frame, when: datetime) -> str | None:
    """Write a dated JPEG and return its path (or None if it fails)."""
    try:
        day_dir = os.path.join(SNAPSHOT_DIR, when.strftime("%Y%m%d"))
        os.makedirs(day_dir, exist_ok=True)
        fname = f"{CAMERA_CODE}_{when.strftime('%H%M%S')}.jpg"
        path = os.path.join(day_dir, fname)
        cv2.imwrite(path, frame)
        return path
    except Exception as e:
        log.warning("Snapshot save failed: %s", e)
        return None


class DB:
    """Thin MariaDB wrapper with lazy reconnect (remote farm = flaky link)."""
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
        """One row per positive sample into t_person_detection."""
        sql = (
            "INSERT INTO t_person_detection "
            "(camera_code, plot_id, detected_at, person_count, "
            " sprayer_detected, confidence, snapshot_path) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        params = (camera_code, plot_id, detected_at, int(person_count),
                  int(sprayer_detected), round(float(confidence), 3), snapshot_path)
        for attempt in (1, 2):                 # try, reconnect once, try again
            try:
                self._ensure()
                cur = self.conn.cursor()
                cur.execute(sql, params)
                cur.close()
                return
            except mysql.connector.Error as e:
                log.warning("DB insert attempt %d failed: %s", attempt, e)
                self.conn = None               # force reconnect next loop
        log.error("Giving up on this detection row (DB unreachable).")


# ======================================================================
# Main loop
# ======================================================================
def main():
    if not DB_CONFIG["password"]:
        log.error("SMARTFARM_DB_PASSWORD is not set. Export it and restart.")
        sys.exit(1)

    log.info("Loading YOLO model: %s (device=%s)", MODEL_PATH, YOLO_DEVICE)
    model = YOLO(MODEL_PATH, task="detect")

    db = DB(DB_CONFIG)
    cap = None
    prev_gray = None
    last_snapshot_ts = 0.0
    read_fails = 0

    log.info("Worker detector started | camera=%s plot=%s", CAMERA_CODE, PLOT_ID)

    while _running:
        loop_start = time.time()
        now = datetime.now()

        # 1) Sleep through the night — no workers, no need to watch.
        if not within_active_hours(now):
            if cap is not None:
                cap.release()
                cap = None
                prev_gray = None
            time.sleep(60)
            continue

        # 2) (Re)open the stream if needed.
        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            log.info("Opening RTSP stream ...")
            cap = open_stream()
            if not cap.isOpened():
                log.warning("Cannot open RTSP. Retry in 10s.")
                time.sleep(10)
                continue
        # ทิ้ง 2-3 เฟรมแรก
        for _ in range(3):
            cap.read()
        # 3) Grab one frame. Tolerate transient decode hiccups: a corrupt
        #    H.264 frame makes read() fail, but the stream is usually still
        #    alive. Skip the bad frame and try again; only reopen the whole
        #    stream after MAX_READ_FAILS failures IN A ROW (a real stall).
        ok, frame = cap.read()
        if not ok or frame is None:
            read_fails += 1
            if read_fails >= MAX_READ_FAILS:
                log.warning("%d read fails in a row -> reopening stream.",
                            read_fails)
                cap.release()
                cap = None
                read_fails = 0
                time.sleep(2)
            # otherwise: just skip this frame, keep the stream open
            _sleep_remainder(loop_start)
            continue
        read_fails = 0   # a good frame resets the counter

        # 4) Motion gate — skip YOLO if nothing moved.
        curr_gray = to_gray_small(frame)
        if not has_motion(prev_gray, curr_gray):
            prev_gray = curr_gray
            _sleep_remainder(loop_start)
            continue
        prev_gray = curr_gray

        # 5) Run person detection (OpenVINO on the iGPU).
        try:
            results = model.predict(
                frame, imgsz=IMG_SIZE, device=YOLO_DEVICE,
                classes=[PERSON_CLASS], conf=CONF_THRESHOLD, verbose=False,
            )
        except Exception as e:
            log.error("YOLO inference error: %s", e)
            _sleep_remainder(loop_start)
            continue

        boxes = results[0].boxes
        person_count = 0 if boxes is None else len(boxes)

        # 6) If a worker is present -> record it.
        if person_count > 0:
            top_conf = float(boxes.conf.max())
            detected_at = now.strftime("%Y-%m-%d %H:%M:%S")

            # Snapshot is throttled so we don't fill the disk.
            snapshot_path = None
            if (loop_start - last_snapshot_ts) >= SNAPSHOT_MIN_INTERVAL:
                snapshot_path = save_snapshot(frame, now)
                last_snapshot_ts = loop_start

            db.insert_detection(
                camera_code=CAMERA_CODE,
                plot_id=PLOT_ID,
                detected_at=detected_at,
                person_count=person_count,
                sprayer_detected=0,   # TODO: wire the custom sprayer model later
                confidence=top_conf,
                snapshot_path=snapshot_path,
            )
            log.info("WORKER detected: count=%d conf=%.3f snap=%s",
                     person_count, top_conf, snapshot_path or "-")
        #   เพิ่ม ให้ clear rtsp stream ทุกครั้งหลังจาก detect worker เสร็จ
        cap.release()
        cap = None
        _sleep_remainder(loop_start)

    # Clean shutdown
    if cap is not None:
        cap.release()
    log.info("Detector stopped.")

def _sleep_remainder(loop_start: float):
    """Keep a steady SAMPLE_INTERVAL_SEC cadence regardless of work done."""
    elapsed = time.time() - loop_start
    remaining = SAMPLE_INTERVAL_SEC - elapsed
    if remaining > 0:
        time.sleep(remaining)

if __name__ == "__main__":
    main()