#!/usr/bin/env python3
"""
Rain Detection for Orchard - WITH DATABASE LOGGING
===================================================
- Camera: IP camera at 192.168.0.252
- Checks every 30 seconds
- Logs every check to MariaDB t_rain table
- Saves images only when rain is detected
- Designed for Raspberry Pi (SD card friendly)
- Headless (no display window) - run as a systemd service
"""
#update: 2026-07-01 user database name to smartfarm, and user to ekapop, password to Ekartc2c51*
import cv2
import numpy as np
import time
import logging
import os
from datetime import datetime
import mysql.connector

# =====================================================================
# CONFIG - edit these for your setup
# =====================================================================

# IMPORTANT: replace USERNAME, PASSWORD, and stream path for your camera.
RTSP_URL = "rtsp://USERNAME:PASSWORD@192.168.0.252:554/stream1"

# Sensor identifier - follow naming convention from t_sensor
SENSOR_DEVICE = "nw01_orchard01_camera_01"

# Database - same credentials as mqtt.py
DB_CONFIG = {    'host': '192.168.0.253',    'user': 'ekapop',    'password': 'Ekartc2c51*',    'database': 'smartfarm'}

# Check interval in seconds
CHECK_INTERVAL = 30

# Time between the two compared frames (seconds)
FRAME_GAP = 1.0

# Detection tuning - LOWERED from 800 to 500 based on real rain data analysis
RAIN_PIXEL_THRESHOLD = 500     # min motion pixels to call it rain
DIFF_THRESHOLD = 20            # pixel difference to count as "moved"
BRIGHTNESS_MIN = 25            # too dark = night, skip
BRIGHTNESS_MAX = 230           # too bright = overexposed, skip

# File paths
LOG_DIR = "/home/ekapop/smartfarm/logs"
IMAGE_DIR = "/home/ekapop/smartfarm/rain_images"
LOG_FILE = "rain_detect.log"

# =====================================================================
# Setup
# =====================================================================

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[        logging.FileHandler(os.path.join(LOG_DIR, LOG_FILE)),        logging.StreamHandler()    ]
)

os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'

# =====================================================================
# Database
# =====================================================================

def save_to_database(motion_pixels, brightness, is_raining, image_path=None):
    """
    Save one rain check to MariaDB.
    Never crashes the main loop - DB errors are logged and ignored.
    """
    try:
        conn = mysql.connector.connect(**DB_CONFIG, connection_timeout=5)
        cursor = conn.cursor()
        sql = """INSERT INTO t_detect_rain 
                (motion_pixels, brightness, is_raining, image_path, sensor_device) 
                VALUES (%s, %s, %s, %s, %s)"""
        values = (int(motion_pixels),     float(brightness),   1 if is_raining else 0,     image_path,     SENSOR_DEVICE  )
        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        logging.error(f"DB save failed: {e}")
    except Exception as e:
        logging.error(f"Unexpected DB error: {e}")


# =====================================================================
# Camera functions
# =====================================================================

def capture_frame_pair(rtsp_url, gap=1.0):
    """Open RTSP stream, grab 2 frames with a gap, then close."""
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        raise RuntimeError("Cannot open RTSP stream")

    try:
        for _ in range(3):
            cap.read()
            time.sleep(0.1)

        ret1, frame1 = cap.read()
        if not ret1 or frame1 is None:
            raise RuntimeError("Failed to read frame 1")

        time.sleep(gap)

        ret2, frame2 = cap.read()
        if not ret2 or frame2 is None:
            raise RuntimeError("Failed to read frame 2")

        return frame1, frame2
    finally:
        cap.release()


# =====================================================================
# Detection
# =====================================================================

def analyze_frames(frame1, frame2):
    """Compare two frames. Return (motion_pixel_count, brightness)."""
    scale = 0.5
    f1 = cv2.resize(frame1, None, fx=scale, fy=scale)
    f2 = cv2.resize(frame2, None, fx=scale, fy=scale)

    gray1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)

    gray1 = cv2.GaussianBlur(gray1, (5, 5), 0)
    gray2 = cv2.GaussianBlur(gray2, (5, 5), 0)

    diff = cv2.absdiff(gray1, gray2)
    _, thresh = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

    motion_pixels = int(cv2.countNonZero(thresh))
    brightness = float(np.mean(gray2))

    return motion_pixels, brightness


def is_rain(motion_pixels, brightness):
    """Decide if conditions look like rain."""
    if brightness < BRIGHTNESS_MIN or brightness > BRIGHTNESS_MAX:
        return False
    return motion_pixels > RAIN_PIXEL_THRESHOLD


# =====================================================================
# Save image (only when rain)
# =====================================================================

def save_rain_image(frame, motion_pixels, brightness):
    """Save image to date-based folder. Returns the saved file path."""
    now = datetime.now()
    date_folder = os.path.join(IMAGE_DIR, now.strftime('%Y%m%d'))
    os.makedirs(date_folder, exist_ok=True)

    filename = f"rain_{now.strftime('%H%M%S')}_m{motion_pixels}.jpg"
    filepath = os.path.join(date_folder, filename)

    label = now.strftime('%Y-%m-%d %H:%M:%S')
    cv2.putText(frame, label + " "+ f"motion={motion_pixels} bright={brightness:.0f}",                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    #cv2.putText(frame, f"motion={motion_pixels} bright={brightness:.0f}",                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return filepath


# =====================================================================
# Main loop
# =====================================================================

def main():
    logging.info("Rain detection started (with DB logging)")
    logging.info("Camera: %s", RTSP_URL.split('@')[-1])
    logging.info("Sensor: %s", SENSOR_DEVICE)
    logging.info("Check interval: %ds, rain threshold: %d pixels",                 CHECK_INTERVAL, RAIN_PIXEL_THRESHOLD)

    consecutive_errors = 0

    while True:
        loop_start = time.time()

        try:
            f1, f2 = capture_frame_pair(RTSP_URL, FRAME_GAP)
            motion, brightness = analyze_frames(f1, f2)
            raining = is_rain(motion, brightness)

            # Save image only if rain is detected
            image_path = None
            if raining:
                image_path = save_rain_image(f2, motion, brightness)

            # Save every check to database (rain or not)
            save_to_database(motion, brightness, raining, image_path)

            status = "RAIN" if raining else "dry"
            if image_path:
                logging.info("%s | motion=%d | brightness=%.1f | saved: %s",                             status, motion, brightness, os.path.basename(image_path))
            else:
                logging.info("%s | motion=%d | brightness=%.1f",                             status, motion, brightness)

            consecutive_errors = 0

        except Exception as e:
            consecutive_errors += 1
            logging.error("Check failed (%d in a row): %s",
                          consecutive_errors, e)
            if consecutive_errors > 5:
                logging.warning("Camera seems offline - backing off 60s")
                time.sleep(60)

        elapsed = time.time() - loop_start
        sleep_for = max(0, CHECK_INTERVAL - elapsed)
        time.sleep(sleep_for)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by user")
    except Exception as e:
        logging.exception("Fatal error: %s", e)