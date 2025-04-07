import os
from datetime import datetime

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')
IMAGES_DIR = os.path.join(DATA_DIR, 'images')
RAIN_IMAGES_DIR = os.path.join(DATA_DIR, 'rain_images')  # เพิ่มโฟลเดอร์สำหรับภาพฝนตก
RECORDS_DIR = os.path.join(DATA_DIR, 'records')

# Create directories if they don't exist
for directory in [LOGS_DIR, IMAGES_DIR, RAIN_IMAGES_DIR, RECORDS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Camera settings
RTSP_URL = "rtsp://username:password@camera_ip:554/stream1"  # แก้ไขตามกล้องที่ใช้
CAMERA_ID = 0  # สำหรับ USB camera

# Detection settings
RAIN_THRESHOLD = 30
BRIGHTNESS_THRESHOLD = 20
SAVE_INTERVAL = 60  # บันทึกทุก 60 วินาที
CONTINUOUS_RAIN_COUNT = 3  # จำนวนครั้งที่ต้องตรวจพบฝนต่อเนื่องก่อนบันทึกภาพ

def get_date_folder(base_dir):
    """สร้างและคืนค่า path ของโฟลเดอร์ตามวันที่"""
    date_folder = os.path.join(base_dir, datetime.now().strftime('%Y%m%d'))
    if not os.path.exists(date_folder):
        os.makedirs(date_folder)
    return date_folder

def get_filename(prefix, ext):
    """สร้างชื่อไฟล์พร้อมเวลา"""
    timestamp = datetime.now().strftime("%H%M%S")
    return f"{prefix}_{timestamp}.{ext}"
