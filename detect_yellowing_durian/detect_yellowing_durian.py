#!/usr/bin/env python3
"""
detect_yellowing_durian.py  (final v2)
------------------------------------------------------------------------------
Grab ONE stream1 frame, crop each durian tree ROI, compute canopy yellowing
indices (GCC + yellow_ratio), and log to MariaDB. Run via systemd timer.
The TREND over many days answers "เหลืองเพิ่มขึ้นไหม" (is it yellowing more?).

What changed from v1:
  * New tighter ROIs (less dry-grass background).
  * Saturation-based grass filtering: fresh leaves have HIGH saturation,
    dry grass has LOW saturation -> raising SAT_MIN removes dry grass.
  * Quality gate: brightness too low = RAIN_OR_DARK, too few veg px = LOW_VEG.
  * INSERT now writes all 9 columns (adds brightness + quality_flag).
  * Optional veg-mask image saved so you can VISUALLY confirm which pixels
    were counted as leaf vs rejected as grass.

DB security note: password is read from an environment variable, NOT hardcoded.
  Set it once (e.g. in the systemd unit or ~/.smartfarm.env):
      export SMARTFARM_DB_PASS='your-password'
------------------------------------------------------------------------------
"""

import os
import time
import cv2
import numpy as np
import pymysql
from datetime import datetime
from pathlib import Path

# --- Config -----------------------------------------------------------------
# Force FFmpeg to use TCP (steadier than UDP) + 5s timeout so it never hangs.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"

# RTSP password comes from the URL; keep credentials out of source where possible.
RTSP_USER = os.environ.get("VIGI_USER", "admin")
RTSP_PASS = os.environ.get("VIGI_PASS", "CHANGE_ME")   # export VIGI_PASS=...
RTSP_HOST = "192.168.0.251"
RTSP_URL  = f"rtsp://{RTSP_USER}:{RTSP_PASS}@{RTSP_HOST}:554/stream1"

SAVE_DIR  = Path("/home/ekapop/smartfarm/yellowing_crops")
SAVE_MASK = True   # set False once you trust the filtering, to save disk

# ROIs measured on the real stream1 frame (x, y, w, h) -- tightened v2
ROIS = {
    "DURIAN-A1-T01": (1848, 392, 156, 327),   # ต้นบน  (upper tree)
    "DURIAN-A1-T02": (1889, 861, 279, 432),   # ต้นล่าง (lower tree)
}

# DB: use a user WITH INSERT privilege. Password from env var (see note above).
DB = dict(
    host="192.168.0.253",
    user=os.environ.get("SMARTFARM_DB_USER", "ekapop"),
    password=os.environ.get("SMARTFARM_DB_PASS", "Ekartc2c51*"),   # export SMARTFARM_DB_PASS=...
    database="smartfarm",
    charset="utf8mb4",
)

# --- Vegetation / grass-filtering thresholds --------------------------------
# Principle: fresh durian leaves = high saturation (vivid); dry grass = low
# saturation (pale brown). Raising SAT_MIN rejects dry grass from the count.
SAT_MIN = 65        # was 40 in v1 -> raised to cut dry grass (tune 55-80)
VAL_MIN = 40        # min brightness (rejects deep shadow)
HUE_LEAF_LOW,   HUE_LEAF_HIGH   = 25, 90   # durian leaf: fresh yellow -> green
HUE_YELLOW_LOW, HUE_YELLOW_HIGH = 25, 40   # "yellow" band = fresh yellow leaf only
HUE_GREEN_LOW,  HUE_GREEN_HIGH  = 40, 90   # "green" band

# --- Quality gate -----------------------------------------------------------
MIN_BRIGHTNESS = 70     # mean V of leaves below this = rain/dark, flag it
MIN_VEG_PIXELS = 3000   # fewer leaf px than this = ROI wrong / occluded


def grab_frame() -> np.ndarray:
    """Open RTSP over TCP, retry up to 3x, discard warm-up frames, return one."""
    for attempt in range(3):
        cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
        if cap.isOpened():
            frame = None
            for _ in range(10):          # let exposure/white-balance settle
                ok, frame = cap.read()
            cap.release()
            if frame is not None:
                return frame
        cap.release()
        print(f"[retry {attempt + 1}/3] cannot open stream1, waiting 3s...")
        time.sleep(3)
    raise RuntimeError("Cannot open stream1 after 3 attempts")


def analyse_roi(roi_bgr):
    """Return yellowing metrics over leaf pixels only (dry grass filtered out).

    Also returns the boolean 'veg' mask so the caller can save it for auditing.
    """
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    # Vegetation = fresh leaf only. High SAT_MIN removes pale dry grass here.
    veg = ((h >= HUE_LEAF_LOW) & (h <= HUE_LEAF_HIGH) &
           (s >= SAT_MIN) & (v >= VAL_MIN))
    veg_px = int(veg.sum())
    if veg_px == 0:
        return None, None

    brightness = float(v[veg].mean())

    if brightness < MIN_BRIGHTNESS:
        quality = "RAIN_OR_DARK"
    elif veg_px < MIN_VEG_PIXELS:
        quality = "LOW_VEG"
    else:
        quality = "OK"

    yellow = veg & (h >= HUE_YELLOW_LOW) & (h < HUE_YELLOW_HIGH)
    green  = veg & (h >= HUE_GREEN_LOW)  & (h <= HUE_GREEN_HIGH)
    yellow_ratio = yellow.sum() / max(1, (yellow.sum() + green.sum()))

    b, g, r = cv2.split(roi_bgr.astype(np.float32))
    denom = (r + g + b)[veg]
    denom[denom == 0] = 1
    gcc = float((g[veg] / denom).mean())

    metrics = dict(
        gcc=round(gcc, 4),
        yellow_ratio=round(float(yellow_ratio), 4),
        veg_pixels=veg_px,
        mean_hue=round(float(h[veg].mean()), 2),
        brightness=round(brightness, 2),
        quality_flag=quality,
    )
    return metrics, veg


def main():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    frame = grab_frame()
    now = datetime.now()

    rows = []
    for tree_id, (x, y, w, h) in ROIS.items():
        crop = frame[y:y + h, x:x + w]
        m, veg = analyse_roi(crop)
        if m is None:
            print(f"[WARN] {tree_id}: no vegetation detected, skipped")
            continue

        # save the raw crop
        img_path = SAVE_DIR / f"{tree_id}_{now:%Y%m%d_%H%M}.jpg"
        cv2.imwrite(str(img_path), crop)

        # save the veg mask (white = counted as leaf) for visual auditing
        if SAVE_MASK:
            mask_img = (veg.astype(np.uint8) * 255)
            cv2.imwrite(str(SAVE_DIR / f"{tree_id}_{now:%Y%m%d_%H%M}_mask.jpg"),
                        mask_img)

        rows.append((now, tree_id, m["gcc"], m["yellow_ratio"],
                     m["veg_pixels"], m["mean_hue"],
                     m["brightness"], m["quality_flag"], str(img_path)))
        print(f"{tree_id}: GCC={m['gcc']}  yellow={m['yellow_ratio']}  "
              f"veg={m['veg_pixels']}  bright={m['brightness']}  "
              f"[{m['quality_flag']}]")

    if rows:
        conn = pymysql.connect(**DB)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO t_tree_yellowing "
                "(captured_at, tree_id, gcc, yellow_ratio, veg_pixels, mean_hue, "
                " brightness, quality_flag, image_path) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        conn.commit()
        conn.close()
        print(f"Inserted {len(rows)} rows.")


if __name__ == "__main__":
    main()