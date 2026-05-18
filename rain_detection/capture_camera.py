#!/usr/bin/env python3
"""
Capture a single frame from the IP camera and save as JPG.
Usage:
    python capture_camera.py            # capture 1 frame
    python capture_camera.py 5          # capture 5 frames (2 sec apart)
"""

import cv2
import os
import sys
import time
from datetime import datetime

# =====================================================================
# CONFIG
# =====================================================================

# Use the same URL as your rain detection script
RTSP_URL = "rtsp://admin:Ekartc2c51*@192.168.0.252:554/stream1"

OUTPUT_DIR = "/home/ekapop/smartfarm/captures"
INTERVAL_SECONDS = 2  # gap between frames if capturing multiple

# =====================================================================


def open_camera():
    """Open RTSP stream and return cv2.VideoCapture."""
    os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
    print(f"Connecting to {RTSP_URL.split('@')[-1]} ...")

    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("❌ ERROR: Cannot open RTSP stream.")
        print("   Check: RTSP_URL, camera IP, username/password, network.")
        sys.exit(1)

    # Warm up - drain buffer so we get a fresh frame
    for _ in range(5):
        cap.read()
        time.sleep(0.1)

    return cap


def capture_one(cap, index=None):
    """Read one frame from open camera and save it."""
    ret, frame = cap.read()
    if not ret or frame is None:
        print("⚠️  Failed to read frame")
        return None

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    suffix = f"_{index:03d}" if index is not None else ""
    filepath = os.path.join(OUTPUT_DIR, f"cap_{timestamp}{suffix}.jpg")

    # Add timestamp on the image (top-left corner)
    label = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cv2.putText(frame, label, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

    h, w = frame.shape[:2]
    size_kb = os.path.getsize(filepath) / 1024
    print(f"✅ Saved {filepath} ({w}x{h}, {size_kb:.1f} KB)")
    return filepath


def main():
    # Read number of frames from command line, default = 1
    count = 1
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            print("Argument must be a number (frame count)")
            sys.exit(1)

    cap = open_camera()
    try:
        for i in range(count):
            capture_one(cap, index=i if count > 1 else None)
            if i < count - 1:
                time.sleep(INTERVAL_SECONDS)
    finally:
        cap.release()
        print("Done.")


if __name__ == "__main__":
    main()