"""Test what YOLOv8n detects in a given image."""
import sys, cv2
from ultralytics import YOLO

img_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/test_listen5.jpg'
model = YOLO('yolov8s.pt')
img = cv2.imread(img_path)

for conf_threshold in (0.25, 0.40):
    print(f"\n=== conf >= {conf_threshold} ===")
    results = model(img, conf=conf_threshold, imgsz=640, verbose=False)
    for r in results:
        for box in r.boxes:
            label = model.names[int(box.cls[0])]
            c     = float(box.conf[0])
            x1,y1,x2,y2 = [int(v) for v in box.xyxy[0]]
            print(f"  {label:15s} conf={c:.3f}  bbox=({x1},{y1})-({x2},{y2})")

# Save annotated image
annotated = model(img, conf=0.25, imgsz=640, verbose=False)[0].plot()
cv2.imwrite('detection_result.jpg', annotated)
print("\nAnnotated → detection_result.jpg")