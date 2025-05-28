import subprocess
import sys
import cv2
import numpy as np
import time
import urllib.parse

password = urllib.parse.quote("Ekartc2c51*")
#rtsp_url = "rtsp://admin:{password}@192.168.1.179:554/stream1"
rtsp_url = f"rtsp://admin:{password}@192.168.1.189:554/stream1"
# ใช้ ffmpeg โดยตรงผ่าน subprocess
command = ['ffmpeg',            '-rtsp_transport', 'tcp',           '-i', rtsp_url,           '-f', 'image2pipe',           '-pix_fmt', 'bgr24',           '-vcodec', 'rawvideo', '-']

pipe = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=10**8)

gst_str = f'rtspsrc location={rtsp_url} latency=0 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! appsink'
cap = cv2.VideoCapture(gst_str, cv2.CAP_GSTREAMER)

while True:
    try:
        # อ่านข้อมูลขนาดของเฟรม
        raw_image = pipe.stdout.read(1280*720*3)  # ปรับขนาดตามความละเอียดของกล้อง (กว้าง*สูง*3)
        
        # แปลงเป็น numpy array
        image = np.frombuffer(raw_image, dtype='uint8')
        image = image.reshape((720, 1280, 3))  # ปรับขนาดตามความละเอียดของกล้อง
        
        # แสดงภาพ
        cv2.imshow('IP Camera', image)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")
        break

pipe.stdout.close()
pipe.terminate()
cv2.destroyAllWindows()