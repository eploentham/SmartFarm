#!/usr/bin/env python3
"""
roi_picker_v2.py
Pull ONE frame from VIGI stream1, let you draw a box around each durian tree,
and report the pixel coverage + a verdict for each. Paste the printed ROIS
dict into detect_yellowing_durian.py when done.

Run on the Pi (needs a display or X-forwarding). Draw a box, press ENTER to
confirm, ESC/empty-box to stop.
"""

import cv2

RTSP_URL = "rtsp://admin:Ekartc2c51*@192.168.0.251:554/stream1"   # <-- your stream1

# Pixel-coverage thresholds for reliable colour averaging
GOOD, ADEQUATE = 60 * 60, 40 * 40   # >=60x60 good, >=40x40 adequate, else too small


def grab_frame():
    """Open RTSP, discard first frames so exposure settles, return one frame."""
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise RuntimeError("Cannot open stream1")
    frame = None
    for _ in range(10):
        ok, frame = cap.read()
    cap.release()
    if frame is None:
        raise RuntimeError("No frame received")
    return frame


def verdict(w, h):
    """Turn box size into a Thai+English verdict (worker-friendly labels)."""
    area = w * h
    if area >= GOOD:
        return "ดีมาก (GOOD)"
    if area >= ADEQUATE:
        return "พอใช้ (ADEQUATE)"
    return "น้อยเกินไป (TOO SMALL)"


def main():
    frame = grab_frame()
    fh, fw = frame.shape[:2]
    print(f"\nFrame size: {fw} x {fh}\n")   # should print 2304 x 1296

    rois = {}
    i = 1
    while True:
        title = f"Draw box around durian tree #{i}  (ENTER=confirm, ESC=finish)"
        x, y, w, h = cv2.selectROI(title, frame, showCrosshair=True)
        cv2.destroyWindow(title)
        if w == 0 or h == 0:          # empty selection -> stop
            break
        tree_id = f"DURIAN-A1-T{i:02d}"
        rois[tree_id] = (int(x), int(y), int(w), int(h))
        print(f"{tree_id}: (x={x}, y={y}, w={w}, h={h})  "
              f"= {w*h} px  ->  {verdict(w, h)}")
        i += 1

    print("\n--- paste this into detect_yellowing_durian.py ---")
    print("ROIS = {")
    for tid, box in rois.items():
        print(f'    "{tid}": {box},')
    print("}")


if __name__ == "__main__":
    main()