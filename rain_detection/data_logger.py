import csv
import os
from datetime import datetime
import logging
from config import RECORDS_DIR, LOGS_DIR

class DataLogger:
    def __init__(self):
        self.setup_logging()
        self.csv_file = self._create_csv_file()

    def setup_logging(self):
        """ตั้งค่า logging"""
        log_file = os.path.join(LOGS_DIR, f"rain_detection_{datetime.now().strftime('%Y%m%d')}.log")
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _create_csv_file(self):
        """สร้างไฟล์ CSV สำหรับบันทึกข้อมูล"""
        filename = os.path.join(RECORDS_DIR, f"rain_data_{datetime.now().strftime('%Y%m%d')}.csv")
        
        # สร้างไฟล์ใหม่ถ้ายังไม่มี
        if not os.path.exists(filename):
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Timestamp', 'Rain Status', 'Brightness', 'Image Path'])
        
        return filename

    def log_data(self, rain_status, brightness, image_path=None):
        """บันทึกข้อมูลลงไฟล์ CSV"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, rain_status, brightness, image_path or ''])
        
        self.logger.info(f"Data logged - Status: {rain_status}, Brightness: {brightness:.1f}")

    def log_error(self, error_message):
        """บันทึก error"""
        self.logger.error(error_message)
