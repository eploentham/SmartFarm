import cv2
import time
from ultralytics import YOLO
from picamera2 import Picamera2

# 1. Load Model
model = YOLO('yolov8n.pt')

# 2. Setup Camera
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"format": "RGB888", "size": (640, 480)})
picam2.configure(config)
picam2.start()

# ล็อคโฟกัสไปที่จุดวางถังพ่นยา (ระยะประมาณ 0.1 - 0.15)
picam2.set_controls({"AfMode": 0, "LensPosition": 0.12}) 

print("System Running in Headless Mode... Monitoring Sprayer Zone")

try:
    while True:
        # ดึงภาพ
        frame = picam2.capture_array()
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # 3. Detection (imgsz=640)
        results = model(frame_bgr, stream=True, conf=0.4, imgsz=640, verbose=False)

        for r in results:
            for box in r.boxes:
                label = model.names[int(box.cls[0])]
                
                # ถ้าเจอ 'คน' หรือ 'กระเป๋า/ถัง'
                if label in ['person', 'backpack']:
                    timestamp = time.strftime("%H:%M:%S")
                    print(f"[{timestamp}] ตรวจพบ: {label} บริเวณถังพ่นยา!")
                    
                    # บันทึกรูปเป็นหลักฐาน (เฉพาะตอนเจอคน)
                    if label == 'person':
                        cv2.imwrite(f"detect_{time.strftime('%Y%m%d_%H%M%S')}.jpg", frame_bgr)
        
        time.sleep(0.1) # พัก CPU เล็กน้อย

except KeyboardInterrupt:
    print("Stopped by user")
finally:
    picam2.stop()
