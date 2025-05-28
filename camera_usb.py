import cv2
import time

def view_camera(camera_index=0, window_name="Camera View"):
    # เปิดกล้อง
    cap = cv2.VideoCapture(camera_index)
    
    # ตรวจสอบว่าเปิดกล้องสำเร็จหรือไม่
    if not cap.isOpened():
        print("ไม่สามารถเปิดกล้องได้! โปรดตรวจสอบการเชื่อมต่อหรือ index ของกล้อง")
        return
    
    # ตั้งค่าความละเอียด (ปรับตามความเหมาะสม)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print(f"กำลังเปิดดูภาพจากกล้อง index {camera_index}")
    print("กด 'q' เพื่อออกจากโปรแกรม")
    
    try:
        while True:
            # อ่านเฟรม
            ret, frame = cap.read()
            
            # ตรวจสอบว่าอ่านเฟรมสำเร็จหรือไม่
            if not ret:
                print("ไม่สามารถรับเฟรมได้ (อุปกรณ์อาจถูกถอดออกหรือเกิดปัญหา)")
                break
            
            # แสดงภาพ
            cv2.imshow(window_name, frame)
            
            # รอรับคีย์บอร์ด กด 'q' เพื่อออกจากโปรแกรม
            if cv2.waitKey(1) == ord('q'):
                break
                
    finally:
        # ปล่อยทรัพยากร
        cap.release()
        cv2.destroyAllWindows()
        print("ปิดกล้องเรียบร้อยแล้ว")

if __name__ == "__main__":
    # เริ่มดูภาพจากกล้อง (index 0 คือค่าเริ่มต้น ถ้ามีกล้องหลายตัวอาจต้องเปลี่ยนเป็น 1, 2, ...)
    view_camera()