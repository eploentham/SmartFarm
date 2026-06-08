# /home/pi/smartfarm/detect_sprinkler_zone1.py
# Sprinkler detection for Zone 1
"""
/home/pi/smartfarm/
├── rain_detect_orchard.py        ☔ Rain detection
├── detect_spray.py               💨 Chemical spray
├── detect_sprinkler_zone1.py     💧 CCTV #1 (Zone 1)
├── detect_sprinkler_zone2.py     💧 CCTV #2 (Zone 2)
├── detect_sprinkler_zone3.py     💧 CCTV #3 (Zone 3)

Copy template
cp detect_sprinkler_zone1.py detect_sprinkler_zone2.py

Edit only these 3 lines:
LOCATION = "ORCHARD_ZONE_2"
CAMERA_RTSP = "rtsp://admin:Pass@192.168.1.101:554/stream1"
CAMERA_NAME = "Zone 2 - Durian Area"

command ubuntu 
sudo systemctl enable detect-sprinkler-zone1.service
sudo systemctl start detect-sprinkler-zone1.service

# Check status
sudo systemctl status detect-sprinkler-zone1.service

# View logs
journalctl -u detect-sprinkler-zone1.service -f

Repeat for each zone:
sudo systemctl enable detect-sprinkler-zone2.service
sudo systemctl enable detect-sprinkler-zone3.service

"""

import cv2
import numpy as np
import mysql.connector
import time
from datetime import datetime

# ===== CONFIG (change per file) =====
LOCATION = "ORCHARD_ZONE_1"
CAMERA_RTSP = "rtsp://admin:Pass123@192.168.1.251:554/stream1"
CAMERA_NAME = "Zone 1 - Durian Area1"

DB_CONFIG = {
    'host': '192.168.1.253',
    'user': 'ekapop',
    'password': 'Ekartc2c51*',   # See note below about security
    'database': 'smartfarm',
}

# ===== Detection =====
def detect_sprinkler_spray(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_water = np.array([0, 0, 200])
    upper_water = np.array([180, 50, 255])
    water_mask = cv2.inRange(hsv, lower_water, upper_water)
    
    water_pixels = cv2.countNonZero(water_mask)
    total_pixels = frame.shape[0] * frame.shape[1]
    water_ratio = water_pixels / total_pixels
    
    return water_ratio > 0.05, water_ratio

# ===== Logging =====
def log_event(status, water_level):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """
        INSERT INTO t_detect_sprinkler_log 
        (status, water_level, location, detected_at)
        VALUES (%s, %s, %s, NOW())
        """
        cursor.execute(query, (status, float(water_level), LOCATION))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"✅ [{LOCATION}] {status} ({water_level:.2%})")
    except Exception as e:
        print(f"❌ DB Error: {e}")

# ===== Main =====
def main():
    print(f"💧 {CAMERA_NAME} - {LOCATION}")
    print(f"📹 {CAMERA_RTSP}\n")
    
    cap = cv2.VideoCapture(CAMERA_RTSP)
    if not cap.isOpened():
        print("❌ Cannot connect to camera!")
        return
    
    print("✅ Connected\n")
    last_status = None
    consecutive_frames = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Reconnecting...")
            time.sleep(5)
            cap = cv2.VideoCapture(CAMERA_RTSP)
            continue
        
        frame = cv2.resize(frame, (640, 480))
        is_spraying, water_ratio = detect_sprinkler_spray(frame)
        status = "SPRAYING" if is_spraying else "OFF"
        
        if status != last_status:
            consecutive_frames += 1
            if consecutive_frames >= 5:
                log_event(status, water_ratio)
                last_status = status
                consecutive_frames = 0
        else:
            consecutive_frames = 0
        
        time.sleep(0.1)
    
    cap.release()

if __name__ == "__main__":
    main()