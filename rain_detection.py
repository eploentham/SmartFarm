#!/usr/bin/env python3
# Rain Detection using Raspberry Pi 5 and Camera
# โค้ดตรวจจับฝนตกโดยใช้ Raspberry Pi 5 และกล้อง

import cv2
import numpy as np
import time
import datetime
import os
from picamera2 import Picamera2
import logging

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("rain_detection.log"),
        logging.StreamHandler()
    ]
)

class RainDetector:
    def __init__(self):
        self.setup_camera()
        
        # พารามิเตอร์สำหรับการตรวจจับ
        self.video_writer = None
        self.motion_threshold = 1000  # ค่าความแตกต่างขั้นต่ำที่ถือว่ามีการเคลื่อนไหว
        self.rain_threshold = 10      # จำนวนการเคลื่อนไหวขั้นต่ำที่ถือว่าฝนตก
        self.droplet_min_size = 10    # ขนาดหยดน้ำขั้นต่ำ (พิกเซล)
        self.droplet_max_size = 200   # ขนาดหยดน้ำสูงสุด (พิกเซล)
        
        # พื้นที่สนใจ (ROI) เป็นพื้นที่ขอบระเบียง (สามารถปรับให้เหมาะกับมุมกล้อง)
        # ค่าเริ่มต้นคือครึ่งล่างของภาพ
        self.roi_y = None  # จะถูกตั้งค่าหลังจากรับภาพแรก
        
        # สถานะการตรวจจับ
        self.is_raining = False
        self.rain_start_time = None
        
        # ที่เก็บภาพ
        self.save_images = True
        self.image_dir = "rain_images"
        os.makedirs(self.image_dir, exist_ok=True)
        
        logging.info("ระบบตรวจจับฝนเริ่มทำงาน")

    def setup_camera(self):
        """ตั้งค่ากล้อง Picamera2"""
        try:
            self.camera = Picamera2()
            config = self.camera.create_still_configuration(main={"size": (640, 480)})
            self.camera.configure(config)
            self.camera.start()
            time.sleep(2)  # รอให้กล้องเริ่มต้น
            logging.info("เชื่อมต่อกล้องสำเร็จ")
        except Exception as e:
            logging.error(f"เกิดข้อผิดพลาดในการตั้งค่ากล้อง: {e}")
            raise

    def capture_frame(self):
        """จับภาพจากกล้อง"""
        frame = self.camera.capture_array()
        if len(frame.shape) > 2 and frame.shape[2] == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        
        # ตั้งค่า ROI ครั้งแรก
        if self.roi_y is None:
            self.roi_y = gray.shape[0] // 2  # ครึ่งล่างของภาพ
        
        return frame, gray

    def detect_motion(self, prev_frame, current_frame):
        """ตรวจจับการเคลื่อนไหวระหว่างเฟรม"""
        # คำนวณความแตกต่างระหว่างเฟรม
        frame_diff = cv2.absdiff(prev_frame, current_frame)
        
        # กรองสัญญาณรบกวน
        blur = cv2.GaussianBlur(frame_diff, (5, 5), 0)
        
        # แปลงเป็นภาพขาวดำโดยใช้ threshold
        _, thresh = cv2.threshold(blur, 20, 255, cv2.THRESH_BINARY)
        
        # ขยายจุดขาวเพื่อเชื่อมจุดที่ใกล้กัน
        dilated = cv2.dilate(thresh, None, iterations=3)
        
        # หาคอนทัวร์ (รูปร่าง) ในภาพ
        contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        # กรองเฉพาะคอนทัวร์ในพื้นที่สนใจ (ROI) และมีขนาดที่เหมาะสม
        valid_drops = []
        for contour in contours:
            (x, y, w, h) = cv2.boundingRect(contour)
            
            # ตรวจสอบว่าอยู่ในพื้นที่สนใจหรือไม่
            if y > self.roi_y:
                # ตรวจสอบขนาด
                if self.droplet_min_size < w * h < self.droplet_max_size:
                    valid_drops.append(contour)
        
        return valid_drops, dilated

    def analyze_drops(self, drops, frame):
        """วิเคราะห์หยดน้ำที่ตรวจพบ"""
        if len(drops) > self.rain_threshold:
            if not self.is_raining:
                self.is_raining = True
                self.rain_start_time = datetime.datetime.now()
                logging.info("เริ่มตรวจพบฝนตก")
                
                # บันทึกภาพเมื่อเริ่มตรวจพบฝน
                if self.save_images:
                    timestamp = self.rain_start_time.strftime("%Y%m%d_%H%M%S")
                    filename = os.path.join(self.image_dir, f"rain_start_{timestamp}.jpg")
                    
                    # วาดกรอบรอบหยดน้ำในภาพ
                    marked_frame = frame.copy()
                    cv2.putText(marked_frame, "RAIN DETECTED", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    for drop in drops:
                        (x, y, w, h) = cv2.boundingRect(drop)
                        cv2.rectangle(marked_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    
                    cv2.imwrite(filename, marked_frame)
                    logging.info(f"บันทึกภาพที่: {filename}")
            
            # อัปเดตระยะเวลาฝนตก
            duration = datetime.datetime.now() - self.rain_start_time
            return True, duration
        elif self.is_raining:
            # ฝนหยุดตก
            self.is_raining = False
            duration = datetime.datetime.now() - self.rain_start_time
            logging.info(f"ฝนหยุดตก (ตรวจพบเป็นเวลา {duration})")
            return False, duration
        
        return False, None
    # เพิ่มฟังก์ชันใหม่ในคลาส
    def send_notification(self, message):
        # โค้ดสำหรับส่งข้อความหรืออีเมล
        logging.info(f"ส่งการแจ้งเตือน: {message}")
        
        # ในเมธอด run เพิ่มส่วนนี้หลังจาก analyze_drops
        if self.is_raining and not self.is_raining:  # เริ่มตรวจพบฝน
            self.send_notification("ตรวจพบฝนตกที่ระเบียง")
        elif not self.is_raining and self.is_raining:  # ฝนหยุดตก
            duration_mins = self.duration.total_seconds() / 60
            self.send_notification(f"ฝนหยุดตกแล้ว (ตกนาน {duration_mins:.1f} นาที)")
    def run(self):
        """ฟังก์ชันหลักของโปรแกรม"""
        prev_frame = None
        
        try:
            while True:
                frame, gray = self.capture_frame()
                
                if prev_frame is not None:
                    # ตรวจจับการเคลื่อนไหว
                    drops, motion_mask = self.detect_motion(prev_frame, gray)
                    
                    # วิเคราะห์หยดน้ำ
                    is_raining, duration = self.analyze_drops(drops, frame)
                    if is_raining and not self.is_recording:
                        # เริ่มบันทึกวิดีโอเมื่อตรวจพบฝน
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        video_file = os.path.join(self.image_dir, f"rain_{timestamp}.mp4")
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        self.video_writer = cv2.VideoWriter(video_file, fourcc, 10.0, (frame.shape[1], frame.shape[0]))
                        self.is_recording = True
                        logging.info(f"เริ่มบันทึกวิดีโอที่: {video_file}")
                    elif self.is_recording:
                        if is_raining:
                            # บันทึกเฟรมปัจจุบัน
                            self.video_writer.write(frame)
                        else:
                            # หยุดบันทึกเมื่อฝนหยุด
                            self.video_writer.release()
                            self.video_writer = None
                            self.is_recording = False
                            logging.info("หยุดบันทึกวิดีโอ")

                    # แสดงสถานะ
                    if is_raining:
                        logging.debug(f"กำลังตรวจพบฝน: {len(drops)} หยด, เวลาที่ฝนตก: {duration}")
                        
                    # สร้างภาพแสดงผล (สำหรับการทดสอบ)
                    debug_frame = frame.copy()
                    
                    # วาดเส้นแสดงพื้นที่สนใจ (ROI)
                    cv2.line(debug_frame, (0, self.roi_y), (frame.shape[1], self.roi_y), (255, 0, 0), 1)
                    
                    # แสดงสถานะบนภาพ
                    status_text = f"{'ฝนกำลังตก' if is_raining else 'ไม่มีฝน'}"
                    count_text = f"พบ {len(drops)} หยด"
                    cv2.putText(debug_frame, status_text, (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255) if is_raining else (0, 255, 0), 2)
                    cv2.putText(debug_frame, count_text, (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    # วาดกรอบรอบหยดน้ำที่ตรวจพบ
                    for drop in drops:
                        (x, y, w, h) = cv2.boundingRect(drop)
                        cv2.rectangle(debug_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    
                    # แสดงภาพ (เปิดใช้เมื่อทดสอบบน Pi ที่มีจอแสดงผล)
                    # cv2.imshow("Rain Detection", debug_frame)
                    # cv2.imshow("Motion Mask", motion_mask)
                    
                prev_frame = gray
                
                # ตรวจสอบการกดปุ่ม (เปิดใช้เมื่อทดสอบบน Pi ที่มีจอแสดงผล)
                # key = cv2.waitKey(1) & 0xFF
                # if key == ord('q'):
                #     break
                
                # รอเล็กน้อยเพื่อลดการใช้ CPU
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            logging.info("โปรแกรมถูกหยุดโดยผู้ใช้")
        except Exception as e:
            logging.error(f"เกิดข้อผิดพลาด: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """ทำความสะอาดทรัพยากร"""
        self.camera.stop()
        cv2.destroyAllWindows()
        logging.info("ปิดระบบเรียบร้อย")

if __name__ == "__main__":
    detector = RainDetector()
    detector.run()