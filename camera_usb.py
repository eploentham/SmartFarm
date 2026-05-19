import cv2
import time
import os
from datetime import datetime

def capture_high_quality_images(camera_index=0, output_dir="camera_captures", 
                                 interval=2, max_images=None):
    """
    Capture high-quality images from USB camera without GUI
    
    Args:
        camera_index: Camera device index (default 0)
        output_dir: Directory to save images
        interval: Seconds between captures (default 2)
        max_images: Maximum number of images to capture (None = unlimited)
    """
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
    
    # Open camera
    cap = cv2.VideoCapture(camera_index)
    
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera at index {camera_index}")
        print("Check connection or try different index (0, 1, 2...)")
        return
    
    # Set high quality resolution (adjust based on your camera's capabilities)
    # Common resolutions: 640x480, 1280x720 (HD), 1920x1080 (Full HD)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    
    # Get actual resolution (camera may not support requested resolution)
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"Camera opened successfully!")
    print(f"Resolution: {actual_width}x{actual_height}")
    print(f"Saving images to: {output_dir}")
    print(f"Interval: {interval} seconds")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    image_count = 0
    
    try:
        while True:
            # Check if we've reached max_images limit
            if max_images and image_count >= max_images:
                print(f"\nReached maximum images limit: {max_images}")
                break
            
            # Read frame
            ret, frame = cap.read()
            
            if not ret:
                print("ERROR: Cannot read frame from camera")
                break
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{output_dir}/capture_{timestamp}_{image_count:04d}.jpg"
            
            # Save image with high quality
            # Quality: 0-100 (higher = better quality, larger file size)
            # 95 is recommended for high quality without huge file sizes
            cv2.imwrite(filename, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            # Get file size
            file_size = os.path.getsize(filename) / 1024  # KB
            
            print(f"[{image_count + 1}] Saved: {filename} ({file_size:.1f} KB)")
            
            image_count += 1
            time.sleep(interval)
                
    except KeyboardInterrupt:
        print("\n" + "=" * 50)
        print("Stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        cap.release()
        print("=" * 50)
        print(f"Total images captured: {image_count}")
        print("Camera closed successfully")

def capture_single_image(camera_index=0, output_file="capture.jpg"):
    """
    Capture a single high-quality image
    """
    cap = cv2.VideoCapture(camera_index)
    
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera at index {camera_index}")
        return False
    
    # Set high resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    
    # Wait a moment for camera to adjust
    time.sleep(1)
    
    # Capture frame
    ret, frame = cap.read()
    
    if ret:
        cv2.imwrite(output_file, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        file_size = os.path.getsize(output_file) / 1024
        print(f"Image saved: {output_file} ({file_size:.1f} KB)")
        result = True
    else:
        print("ERROR: Failed to capture image")
        result = False
    
    cap.release()
    return result

if __name__ == "__main__":
    # Example 1: Continuous capture every 2 seconds
    capture_high_quality_images(
        camera_index=0,
        output_dir="camera_captures",
        interval=2,
        max_images=None  # Set to a number like 10 to limit captures
    )
    
    # Example 2: Capture single image (uncomment to use)
    # capture_single_image(camera_index=0, output_file="test_capture.jpg")