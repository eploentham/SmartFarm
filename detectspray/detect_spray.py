import cv2
import numpy as np
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
