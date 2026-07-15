#!/usr/bin/env python3
"""
check_camera.py — Verify Raspberry Pi Camera Module 3 is healthy.

Runs 5 diagnostic checks in order (fail fast):
  1. Hardware detection via libcamera
  2. CSI ribbon cable health (kernel log)
  3. Pi thermal state (throttling risk)
  4. Live capture test with one-shot autofocus
  5. Image sharpness (Laplacian variance)

Usage:
  python3 check_camera.py
  python3 check_camera.py --output-dir /path/to/save

Exit codes:
  0 = all checks passed
  1 = camera not detected (fix CSI cable)
  2 = capture failed (software or driver issue)
  3 = image too blurry (Laplacian variance < 100)

Author: Smartfarm project
Location: /home/pi/smartfarm/check_camera.py
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ANSI color codes for readable terminal output
class C:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# ---------- small print helpers ----------

def header(msg: str) -> None:
    print(f"\n{C.BOLD}{C.BLUE}▶ {msg}{C.RESET}")


def ok(msg: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {C.YELLOW}⚠{C.RESET} {msg}")


def err(msg: str) -> None:
    print(f"  {C.RED}✗{C.RESET} {msg}")


# ---------- diagnostic checks ----------

def check_hardware_detected() -> bool:
    """Ask libcamera which cameras are visible on the CSI bus.

    Returns True if a camera is detected (any model), False if none.
    """
    header("1. Hardware detection")
    try:
        result = subprocess.run(
            ["rpicam-hello", "--list-cameras"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout + result.stderr
    except FileNotFoundError:
        err("rpicam-hello not installed.")
        err("  Install with:  sudo apt install rpicam-apps")
        return False
    except subprocess.TimeoutExpired:
        err("rpicam-hello hung for 10 seconds — CSI cable might be loose.")
        return False

    lower = output.lower()
    if "imx708" in lower:
        ok("Camera Module 3 (Sony IMX708 sensor) detected")
        return True
    elif "available cameras" in lower and "0 :" in output:
        # A camera is present but not Module 3 (e.g. Module 2 IMX219)
        warn("A camera is detected but not Module 3.")
        print(f"    {output.strip()[:300]}")
        return True
    else:
        err("No cameras detected on the CSI bus.")
        err("  Check the ribbon cable orientation — on Pi 5, the blue/silver")
        err("  stiffener should face the Ethernet port on both ends.")
        return False


def check_dmesg_errors() -> None:
    """Search kernel log for camera or CSI errors.

    Non-fatal — prints warnings only; doesn't fail the whole check.
    """
    header("2. CSI cable health (kernel log)")
    try:
        result = subprocess.run(
            ["dmesg", "-T"], capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        warn("Could not read dmesg (try running with sudo for full log)")
        return

    keywords_camera = ("imx708", "unicam", "csi", "camera", "cfe")
    keywords_error = ("error", "fail", "timeout", "reset", "unable")

    camera_lines = [l for l in result.stdout.splitlines()
                    if any(k in l.lower() for k in keywords_camera)]
    error_lines = [l for l in camera_lines
                   if any(k in l.lower() for k in keywords_error)]

    if error_lines:
        warn(f"Found {len(error_lines)} camera-related error(s) in dmesg:")
        for line in error_lines[-3:]:  # show only the 3 most recent
            print(f"    {line}")
    else:
        ok(f"No CSI errors ({len(camera_lines)} normal camera messages found)")


def check_thermal() -> None:
    """Read SoC temperature — high temp causes sensor noise and throttling."""
    header("3. Pi thermal state")
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp_c = int(f.read().strip()) / 1000.0
    except (FileNotFoundError, PermissionError):
        warn("Thermal sensor not readable")
        return

    if temp_c < 70:
        ok(f"SoC temperature: {temp_c:.1f}°C  (healthy)")
    elif temp_c < 80:
        warn(f"SoC temperature: {temp_c:.1f}°C  (warm — image noise may increase)")
    else:
        err(f"SoC temperature: {temp_c:.1f}°C  (THROTTLING RISK — improve cooling)")


def capture_test_image(output_dir: Path):
    """Take one still with autofocus. Returns (path, laplacian_variance).

    Uses the sequence from past testing:
      1. Configure still mode at 2304x1296
      2. Start camera
      3. Trigger one-shot autofocus
      4. Wait 1.5 s for AF to converge
      5. Capture and save JPEG
    """
    header("4. Capture test with autofocus")

    # Import inside the function so the earlier checks can still report
    # missing libraries clearly without crashing the whole script.
    try:
        from picamera2 import Picamera2
        from libcamera import controls
    except ImportError:
        err("picamera2 not installed.")
        err("  Install with:  sudo apt install python3-picamera2")
        return None, 0.0

    try:
        import cv2
    except ImportError:
        err("OpenCV not installed.")
        err("  Install with:  sudo apt install python3-opencv")
        return None, 0.0

    picam2 = Picamera2()
    still_config = picam2.create_still_configuration(
        main={"size": (2304, 1296)},   # good default for Module 3 stills
    )
    picam2.configure(still_config)

    image_path = None
    variance = 0.0
    try:
        picam2.start()

        # Trigger one-shot autofocus and wait 1.5 s (Module 3 has AF motor)
        print("  triggering autofocus, waiting 1.5 s...")
        picam2.set_controls({"AfMode": controls.AfModeEnum.Auto})
        try:
            picam2.autofocus_cycle()
        except Exception:
            # Older picamera2 versions or non-AF sensors — ignore
            pass
        time.sleep(1.5)

        # Save image with timestamp so we don't overwrite past tests
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = output_dir / f"camera_test_{timestamp}.jpg"
        picam2.capture_file(str(image_path))
        ok(f"Image saved: {image_path}")

        # Compute Laplacian variance as a rough sharpness metric.
        # High variance = many edges = sharp image.
        # Low variance = smooth blur = out of focus or motion blur.
        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            err(f"Could not re-read saved image at {image_path}")
            return image_path, 0.0
        variance = cv2.Laplacian(img, cv2.CV_64F).var()

    except Exception as e:
        err(f"Capture failed: {e}")
    finally:
        try:
            picam2.close()
        except Exception:
            pass

    return image_path, variance


def assess_sharpness(variance: float) -> bool:
    """Interpret the Laplacian variance number.

    Thresholds from past field testing on this project:
      < 100  = clearly blurry — bad focus or intermittent CSI cable
      100-500 = acceptable for OCR and general use
      > 500  = sharp, good for training images and detailed labels
    """
    header("5. Image sharpness (Laplacian variance)")

    if variance <= 0:
        err("No sharpness score computed (capture failed earlier)")
        return False

    if variance < 100:
        err(f"Variance: {variance:.1f}  — TOO BLURRY for OCR")
        err("Common fixes for blur on this project:")
        err("  - Re-seat the CSI ribbon at BOTH ends")
        err("  - Add strain relief (Kapton tape or small hot glue dot)")
        err("  - Confirm the AF motor clicked audibly during the test")
        err("  - Increase 1.5 s wait to 2.5 s if the room is dim")
        return False
    elif variance < 500:
        warn(f"Variance: {variance:.1f}  — acceptable, could be sharper")
        return True
    else:
        ok(f"Variance: {variance:.1f}  — sharp")
        return True


# ---------- main entry point ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose Pi Camera Module 3 health (5-stage check)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/home/pi/smartfarm/camera_tests"),
        help="Where to save the test image (default: /home/pi/smartfarm/camera_tests)",
    )
    args = parser.parse_args()

    print(
        f"{C.BOLD}Pi Camera Module 3 diagnostic  —  "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}{C.RESET}"
    )

    # Stage 1: hardware — fail fast, no point continuing if no camera
    if not check_hardware_detected():
        print(f"\n{C.RED}{C.BOLD}✗ FAIL — camera not detected.{C.RESET}")
        sys.exit(1)

    # Stages 2 & 3: passive diagnostics (never fatal)
    check_dmesg_errors()
    check_thermal()

    # Stage 4: real capture
    image_path, variance = capture_test_image(args.output_dir)
    if image_path is None:
        print(f"\n{C.RED}{C.BOLD}✗ FAIL — capture step failed.{C.RESET}")
        sys.exit(2)

    # Stage 5: sharpness
    is_sharp = assess_sharpness(variance)

    print()
    if is_sharp:
        print(f"{C.GREEN}{C.BOLD}✓ ALL CHECKS PASSED{C.RESET}")
        print(f"Camera is ready for the bottle-detection pipeline.")
        print(f"Open the test image to verify visually:")
        print(f"  {image_path}")
        sys.exit(0)
    else:
        print(f"{C.RED}{C.BOLD}✗ CAMERA WORKS BUT IMAGES ARE BLURRY{C.RESET}")
        print(f"Fix focus / cable before running Gemini Vision on real bottles.")
        sys.exit(3)


if __name__ == "__main__":
    main()