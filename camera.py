import cv2
import time
import threading
from flask import Flask, Response, render_template_string

class IPCameraStream:
    def __init__(self, rtsp_url):
        self.rtsp_url = rtsp_url
        self.cap = None
        self.frame = None
        self.stopped = False
        self.lock = threading.Lock()
        
    def start(self):
        """Start the thread to read frames from the video stream"""
        print(f"Connecting to camera at {self.rtsp_url}...")
        self.connect()
        threading.Thread(target=self.update, args=()).start()
        return self
    
    def connect(self):
        """Connect to the RTSP stream"""
        # Set RTSP over TCP (better for unstable networks)
        cv2.setUseOptimized(True)
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
        
        # Try to connect to the camera
        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        
        if not self.cap.isOpened():
            raise Exception(f"Failed to connect to IP camera at {self.rtsp_url}")
        
        print("Successfully connected to camera")
    
    def update(self):
        """Keep reading the camera stream in a loop"""
        retry_count = 0
        max_retries = 5
        
        while not self.stopped:
            if not self.cap.isOpened():
                retry_count += 1
                print(f"Connection lost. Retrying... ({retry_count}/{max_retries})")
                
                if retry_count > max_retries:
                    self.stopped = True
                    print("Max retries reached. Stopping stream.")
                    break
                
                self.connect()
                continue
            
            # Read the next frame from the stream
            ret, frame = self.cap.read()
            
            if not ret:
                print("Failed to read frame. Reconnecting...")
                self.connect()
                continue
            
            # If frame was successfully read, reset retry counter
            retry_count = 0
            
            # Update the frame
            with self.lock:
                self.frame = frame.copy()
            
            # Sleep to reduce CPU usage
            time.sleep(0.01)
            
    def read(self):
        """Return the most recently read frame"""
        with self.lock:
            if self.frame is None:
                return False, None
            return True, self.frame.copy()
    
    def stop(self):
        """Stop the camera stream thread"""
        self.stopped = True
        if self.cap is not None:
            self.cap.release()

# Flask app for web streaming
app = Flask(__name__)

# Configure your camera URL here
RTSP_URL = "rtsp://admin:Ekartc2c51%2A@192.168.1.179:554/stream1"  # Update with your camera details
#RTSP_URL = "rtsp://192.168.1.179:554/stream1"
#RTSP_URL = "rtsp://192.168.1.179:554"
#RTSP_URL = "rtsp://ekapop:Ekartc2c51*@192.168.1.179:554/live"
#RTSP_URL = "rtsp://admin:Ekartc2c51*@192.168.1.179:554/h264/ch1/main/av_stream"
RTSP_URL = "rtsp://admin:Ekartc2c51*@192.168.1.115:554/stream1"
camera_stream = None

def gen_frames():
    """Generate frame-by-frame from the camera stream"""
    while True:
        ret, frame = camera_stream.read()
        if not ret:
            continue
            
        # Add timestamp to the frame
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        cv2.putText(frame, timestamp, (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Encode the frame in JPEG format
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        
        # Yield the frame in the byte format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    """Video streaming home page"""
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>IP Camera Stream</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                text-align: center;
                background-color: #f0f0f0;
            }
            h1 {
                color: #333;
            }
            .video-container {
                margin: 20px auto;
                max-width: 800px;
                border: 1px solid #ccc;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            img {
                width: 100%;
                height: auto;
            }
        </style>
    </head>
    <body>
        <h1>IP Camera Live Stream</h1>
        <div class="video-container">
            <img src="{{ url_for('video_feed') }}" alt="IP Camera Stream">
        </div>
        <p>Stream started at: {{ start_time }}</p>
    </body>
    </html>
    ''', start_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

@app.route('/video_feed')
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag"""
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    import os
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='IP Camera Streaming')
    parser.add_argument('--url', type=str, help='RTSP URL of the camera', default=RTSP_URL)
    parser.add_argument('--port', type=int, help='Port for the web server', default=5000)
    parser.add_argument('--host', type=str, help='Host for the web server', default='0.0.0.0')
    args = parser.parse_args()
    
    # Start camera stream
    camera_stream = IPCameraStream(args.url).start()
    
    # Start Flask app
    try:
        print(f"Starting web server at http://{args.host}:{args.port}")
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
    finally:
        # Clean up resources when the app is shut down
        if camera_stream is not None:
            camera_stream.stop()
            print("Camera stream stopped")