import cv2
import numpy as np
from datetime import datetime
import os
from config import IMAGES_DIR, RAIN_IMAGES_DIR, get_date_folder, get_filename

class RainDetector:
    def __init__(self, rain_threshold, brightness_threshold):
        self.rain_threshold = rain_threshold
        self.brightness_threshold = brightness_threshold
        self.rain_count = 0  # นับจำนวนครั้งที่ตรวจพบฝนต่อเนื่อง
        self.last_rain_time = None  # เวลาล่าสุดที่ตรวจพบฝน

    def calculate_brightness(self, frame):
        """คำนวณความสว่างเฉลี่ยของเฟรม"""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        return np.mean(hsv[:, :, 2])

    def detect_rain(self, frame1, frame2):
        """ตรวจจับการเคลื่อนไหวของหยดน้ำฝน"""
        scale = 0.5
        frame1_small = cv2.resize(frame1, None, fx=scale, fy=scale)
        frame2_small = cv2.resize(frame2, None, fx=scale, fy=scale)
        
        gray1 = cv2.cvtColor(frame1_small, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2_small, cv2.COLOR_BGR2GRAY)
        
        gray1 = cv2.GaussianBlur(gray1, (21, 21), 0)
        gray2 = cv2.GaussianBlur(gray2, (21, 21), 0)
        
        diff = cv2.absdiff(gray1, gray2)
        _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
        
        movement = np.sum(thresh > 0) > self.rain_threshold
        
        # อัพเดทตัวนับฝนตก
        if movement:
            self.rain_count += 1
            self.last_rain_time = datetime.now()
        else:
            # รีเซ็ตตัวนับถ้าไม่พบฝนเกิน 5 วินาที
            if (self.last_rain_time is None or 
                (datetime.now() - self.last_rain_time).seconds > 5):
                self.rain_count = 0
        
        return movement

    def save_image(self, frame, is_raining):
        """บันทึกภาพแยกตามสถานะฝนตก"""
        if is_raining:
            # บันทึกภาพฝนตกในโฟลเดอร์แยก
            date_folder = get_date_folder(RAIN_IMAGES_DIR)
            filename = get_filename("rain", "jpg")
            filepath = os.path.join(date_folder, filename)
        else:
            # บันทึกภาพปกติ
            date_folder = get_date_folder(IMAGES_DIR)
            filename = get_filename("normal", "jpg")
            filepath = os.path.join(date_folder, filename)

        # เพิ่มข้อความบนภาพ
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        img_with_text = frame.copy()
        cv2.putText(img_with_text, timestamp, (10, frame.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imwrite(filepath, img_with_text)
        return filepath

    def should_save_rain_image(self):
        """ตรวจสอบว่าควรบันทึกภาพฝนตกหรือไม่"""
        return self.rain_count >= 3  # บันทึกเมื่อตรวจพบฝนต่อเนื่อง 3 ครั้ง
