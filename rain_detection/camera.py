import cv2
import os

class IPCamera:
    def __init__(self, rtsp_url):
        self.rtsp_url = rtsp_url
        self.cap = None

    def connect(self):
        """เชื่อมต่อกับ IP Camera"""
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not self.cap.isOpened():
            raise Exception("ไม่สามารถเชื่อมต่อกับ IP Camera ได้")

    def read_frame(self):
        """อ่านเฟรมจากกล้อง"""
        if self.cap is None:
            self.connect()
        
        ret, frame = self.cap.read()
        if not ret:
            self.connect()
            return self.read_frame()
        
        return frame

    def release(self):
        """ปิดการเชื่อมต่อกล้อง"""
        if self.cap is not None:
            self.cap.release()
