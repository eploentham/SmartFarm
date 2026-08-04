#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
worker_activity_summary.py
Daily worker-activity DIGEST for the orchard.

Runs ONCE per evening (systemd timer at 20:00). It does NOT watch the camera
— it reads what detect_worker_zone*.py already logged into t_person_detection
during the day, groups the 15-second samples into presence "blocks", and
sends ONE Telegram summary. This is the "daily digest, not real-time alarm"
design: workers are a non-security use case, so one calm summary is enough.

Because it runs once and exits, its systemd unit is Type=oneshot
(the opposite of the detector, which loops forever and is Type=simple).

Reads secrets from ~/smartfarm/.env (same file the detector uses).
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict

import requests
import mysql.connector
from dotenv import load_dotenv

# ---- Load .env (one level up from scripts/) -------------------------
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
# Gap that splits one presence block from the next. If two detections are
# more than this many minutes apart, we treat them as separate visits.
SESSION_GAP_MIN = 10

# Each positive row represents ~this many seconds of presence (detector's
# sampling cadence). Used to give a single-sample block a sensible minimum.
SAMPLE_INTERVAL_SEC = 15

# --- Telegram ---
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN", "BOT_TOKEN", default="")
TELEGRAM_CHAT_ID   = _env("TELEGRAM_CHAT_ID", "CHAT_ID", default="8394445325")  # พี่เอก
# Attach a representative photo (the last snapshot of the day) to the digest.
SEND_PHOTO = True

# --- Database (read-only is enough here) ---
DB_CONFIG = {
    "host":     _env("SMARTFARM_DB_HOST", "DB_HOST", default="127.0.0.1"),
    "port":     int(_env("SMARTFARM_DB_PORT", "DB_PORT", default="3306")),
    "user":     _env("SMARTFARM_DB_USER", "DB_USER", default="smartfarm_rw"),
    "password": _env("SMARTFARM_DB_PASS", "DB_PASSWORD", default=""),
    "database": _env("SMARTFARM_DB_NAME", "DB_NAME", default="smartfarm"),
    "charset":  "utf8mb4",
}

# ======================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("worker_digest")

THAI_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def thai_date(d: date) -> str:
    """4 ส.ค. 2026 — short readable Thai date (Buddhist year)."""
    return f"{d.day} {THAI_MONTHS[d.month]} {d.year + 543}"


def fetch_rows(target: date):
    """Pull all of the target day's detections, oldest first."""
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    sql = (
        "SELECT camera_code, plot_id, detected_at, person_count, snapshot_path "
        "FROM t_person_detection "
        "WHERE detected_at >= %s AND detected_at < %s "
        "ORDER BY camera_code, detected_at"
    )
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, (start, end))
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def build_blocks(detections):
    """
    Turn a time-ordered list of detections into presence blocks.
    A new block starts whenever the gap to the previous detection exceeds
    SESSION_GAP_MIN. Returns a list of dicts: start, end, minutes, max_people,
    last_snapshot.
    """
    blocks = []
    cur = None
    gap = timedelta(minutes=SESSION_GAP_MIN)

    for d in detections:
        t = d["detected_at"]
        if cur is None or (t - cur["end"]) > gap:
            # start a new block
            if cur is not None:
                blocks.append(cur)
            cur = {
                "start": t, "end": t,
                "max_people": d["person_count"] or 1,
                "last_snapshot": d["snapshot_path"],
            }
        else:
            # extend the current block
            cur["end"] = t
            cur["max_people"] = max(cur["max_people"], d["person_count"] or 1)
            if d["snapshot_path"]:
                cur["last_snapshot"] = d["snapshot_path"]

    if cur is not None:
        blocks.append(cur)

    # compute duration per block (minimum = one sample interval)
    for b in blocks:
        secs = (b["end"] - b["start"]).total_seconds() + SAMPLE_INTERVAL_SEC
        b["minutes"] = max(1, round(secs / 60))
    return blocks


def build_message(target: date, rows) -> tuple[str, str | None]:
    """Return (text, photo_path_or_None) for the digest."""
    header = f"📋 สรุปกิจกรรมคนสวน — {thai_date(target)}"

    if not rows:
        return f"{header}\n\n🌙 วันนี้ไม่พบกิจกรรมคนสวน", None

    # group rows by (camera, plot)
    by_cam = defaultdict(list)
    for r in rows:
        by_cam[(r["camera_code"], r["plot_id"])].append(r)

    parts = [header, ""]
    last_photo = None

    for (cam, plot), dets in by_cam.items():
        blocks = build_blocks(dets)
        total_min = sum(b["minutes"] for b in blocks)
        first_seen = min(b["start"] for b in blocks).strftime("%H:%M")
        last_seen = max(b["end"] for b in blocks).strftime("%H:%M")
        max_people = max(b["max_people"] for b in blocks)

        parts.append(f"📷 {cam} ({plot or '-'})")
        parts.append(f"   พบ {len(blocks)} ช่วง · รวม ~{total_min} นาที")
        parts.append(f"   🕐 {first_seen} – {last_seen}")
        parts.append(f"   👥 สูงสุด {max_people} คนพร้อมกัน")
        for b in blocks:
            s = b["start"].strftime("%H:%M")
            e = b["end"].strftime("%H:%M")
            parts.append(f"   • {s}–{e} ({b['minutes']} นาที)")
        parts.append("")

        if blocks and blocks[-1]["last_snapshot"]:
            last_photo = blocks[-1]["last_snapshot"]

    return "\n".join(parts).rstrip(), (last_photo if SEND_PHOTO else None)


def send_telegram(text: str, photo_path: str | None = None) -> bool:
    """Send the digest. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN:
        log.error("No TELEGRAM_BOT_TOKEN in .env — cannot send digest.")
        return False
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as img:
                r = requests.post(
                    f"{base}/sendPhoto",
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": text},
                    files={"photo": img},
                    timeout=15,
                )
        else:
            r = requests.post(
                f"{base}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                timeout=15,
            )
        if r.status_code == 200:
            return True
        log.error("Telegram send failed: HTTP %s %s", r.status_code, r.text[:200])
        return False
    except Exception as e:
        log.error("Telegram send error: %s", e)
        return False


def main():
    # Optional CLI arg: a date (YYYY-MM-DD) to re-run a past day. Default today.
    if len(sys.argv) > 1:
        target = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        target = date.today()

    log.info("Building worker digest for %s", target)
    rows = fetch_rows(target)
    log.info("Rows found: %d", len(rows))

    text, photo = build_message(target, rows)
    ok = send_telegram(text, photo)
    if ok:
        log.info("Digest sent.")
    else:
        log.error("Digest NOT sent.")
        sys.exit(1)


if __name__ == "__main__":
    main()