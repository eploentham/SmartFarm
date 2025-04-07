import cv2
import time
from rain_detection.camera import IPCamera
from rain_detection.detector import RainDetector
from rain_detection.data_logger import DataLogger
from config import (
    RTSP_URL,
    RAIN_THRESHOLD,
    BRIGHTNESS_THRESHOLD,
    SAVE_INTERVAL,
    CONTINUOUS_RAIN_COUNT
)

def main():
    # สร้าง objects
    camera = IPCamera(RTSP_URL)
    detector = RainDetector(RAIN_THRESHOLD, BRIGHTNESS_THRESHOLD)
    logger = DataLogger()

    try:
        # อ่านเฟรมแรก
        prev_frame = camera.read_frame()
        last_save_time = time.time()
        
        print("เริ่มการตรวจจับฝน...")
        print("กด 'q' เพื่อออกจากโปรแกรม")
        
        while True:
            # อ่านเฟรมปัจจุบัน
            current_frame = camera.read_frame()
            
            # ตรวจจับฝน
            rain_detected = detector.detect_rain(prev_frame, current_frame)
            brightness = detector.calculate_brightness(current_frame)
            is_raining = rain_detected and brightness < BRIGHTNESS_THRESHOLD
            
            # แสดงสถานะบนภาพ
            status_text = "ฝนตก" if is_raining else "ไม่มีฝน"
            cv2.putText(current_frame, status_text, (10, 30),
                      cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(current_frame, f"ความสว่าง: {brightness:.1f}", (10, 60),
                      cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(current_frame, f"Rain Count: {detector.rain_count}", (10, 90),
                      cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # แสดงภาพ
            cv2.imshow('Rain Detection', current_frame)
            
            # บันทึกข้อมูลและภาพ
            current_time = time.time()
            if current_time - last_save_time >= SAVE_INTERVAL:
                # บันทึกภาพปกติตามช่วงเวลา
                image_path = detector.save_image(current_frame, is_raining)
                logger.log_data(status_text, brightness, image_path)
                last_save_time = current_time
            
            # บันทึกภาพเมื่อตรวจพบฝนต่อเนื่อง
            if is_raining and detector.should_save_rain_image():
                rain_image_path = detector.save_image(current_frame, True)
                logger.log_data("ฝนตก (ต่อเนื่อง)", brightness, rain_image_path)
            
            # อัพเดทเฟรมก่อนหน้า
            prev_frame = current_frame.copy()
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
    except Exception as e:
        logger.log_error(f"เกิดข้อผิดพลาด: {str(e)}")
    finally:
        camera.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
