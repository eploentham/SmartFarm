import cv2
import time
import os
from datetime import datetime

def test_all_video_devices():
    """Test which video device works with Pi Camera Module 3"""
    print("Testing video devices for Pi Camera Module 3...")
    print("=" * 60)
    
    working_devices = []
    
    # Test video0 through video7 (rp1-cfe devices)
    for i in range(8):
        print(f"\nTesting /dev/video{i}...")
        
        cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
        
        if not cap.isOpened():
            print(f"  ✗ Cannot open")
            continue
        
        # Try to set resolution and format
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
        
        # Try to capture
        time.sleep(0.5)  # Give camera time to initialize
        ret, frame = cap.read()
        
        if ret and frame is not None:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"  ✓ SUCCESS! Resolution: {width}x{height}")
            
            # Save test image
            test_file = f"test_video{i}.jpg"
            cv2.imwrite(test_file, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            file_size = os.path.getsize(test_file) / 1024
            print(f"  ✓ Test image saved: {test_file} ({file_size:.1f} KB)")
            
            working_devices.append(i)
        else:
            print(f"  ✗ Opened but cannot capture frames")
        
        cap.release()
    
    print("\n" + "=" * 60)
    if working_devices:
        print(f"✓ Working devices: {working_devices}")
        print(f"\nUse camera_index={working_devices[0]} in your script")
    else:
        print("✗ No working video devices found")
        print("\nTroubleshooting:")
        print("1. Check camera cable connection")
        print("2. Make sure camera is enabled in boot config")
        print("3. Try: sudo reboot")

def capture_images(camera_index, output_dir="camera_captures", 
                   interval=2, max_images=None):
    """Capture images from Pi Camera Module 3"""
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
    
    if not cap.isOpened():
        print(f"ERROR: Cannot open /dev/video{camera_index}")
        return
    
    # Set high resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 2304)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1296)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
    
    # Wait for camera to initialize
    time.sleep(1)
    
    # Test capture
    ret, test_frame = cap.read()
    if not ret:
        print("ERROR: Cannot capture frames")
        cap.release()
        return
    
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"Camera ready!")
    print(f"Resolution: {actual_w}x{actual_h}")
    print(f"Saving to: {output_dir}")
    print(f"Interval: {interval} seconds")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    image_count = 0
    
    try:
        while True:
            if max_images and image_count >= max_images:
                break
            
            ret, frame = cap.read()
            if not ret:
                print("WARNING: Frame capture failed")
                time.sleep(0.5)
                continue
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{output_dir}/capture_{timestamp}_{image_count:04d}.jpg"
            
            cv2.imwrite(filename, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            file_size = os.path.getsize(filename) / 1024
            print(f"[{image_count + 1}] {filename} ({file_size:.1f} KB)")
            
            image_count += 1
            time.sleep(interval)
    
    except KeyboardInterrupt:
        print("\n" + "=" * 50)
        print("Stopped by user")
    finally:
        cap.release()
        print(f"Total images captured: {image_count}")

if __name__ == "__main__":
    # First, test which device works
    test_all_video_devices()
    
    # If you found a working device, uncomment and set the correct index:
    # capture_images(camera_index=0, interval=2)