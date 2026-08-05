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

# 1. โหลดโมเดล YOLOv8 (จะดึงไฟล์การตรวจจับมาตรฐานมาใช้)
model = YOLO('yolov8n.pt')

# 2. ตั้งค่ากล้อง Picamera2 บน Pi 5
picam2 = Picamera2()
# ใช้ขนาด 640x480 เพื่อให้ AI มองเห็นระยะ 10 เมตรได้ชัดเจน
config = picam2.create_preview_configuration(main={"format": "RGB888", "size": (640, 480)})
picam2.configure(config)
picam2.start()

# บังคับเปิดระบบ Autofocus แบบต่อเนื่อง (Continuous) ภาพจะได้ชัดตลอดเวลาที่คนเดิน
picam2.set_controls({"AfMode": 2}) 

print("YOLOv8 Detection Starting on Pi 5 (imgsz=640)... Press 'q' to stop.")

try:
    while True:
        # ดึงภาพจากกล้องมาเป็น Array
        frame = picam2.capture_array()
        
        # แปลงสีจาก RGB เป็น BGR สำหรับ OpenCV
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # 3. ส่งภาพให้ YOLO ประมวลผลที่ความละเอียด 640x640
        results = model(frame_bgr, stream=True, conf=0.4, imgsz=640)

        for r in results:
            # วาดกรอบสี่เหลี่ยมรอบวัตถุที่เจอ
            annotated_frame = r.plot()
            cv2.imshow("Orchard Monitor Pi 5", annotated_frame)

            # ตรวจสอบ Class วัตถุที่เจอ (Person = คน, Backpack = ถังพ่นยาสะพายหลัง)
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = model.names[cls_id]
                
                if label in ['person', 'backpack']:
                    conf = box.conf[0]
                    print(f" Detected: {label} ({conf:.2f}) ที่ระยะสวน")

        # กด 'q' เพื่อปิดโปรแกรม
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
finally:
    picam2.stop()
    cv2.destroyAllWindows()
    print("System stopped safely.")
