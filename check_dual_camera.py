#!/usr/bin/env python3
"""
check_dual_camera.py — Verify both cameras on a Pi 5 dual-camera setup.

Runs the same 5-stage check as check_camera.py but iterates through
every detected camera (typically 0 and 1 on a dual-cam Pi 5).

Usage:
  python3 check_dual_camera.py
  python3 check_dual_camera.py --output-dir /path/to/save
  python3 check_dual_camera.py --resolution 4608x2592   # full Module 3 sensor

Exit codes:
  0 = all cameras passed
  1 = no cameras detected
  2 = at least one camera capture failed
  3 = at least one camera produced blurry images

Author: Smartfarm project
Location: /home/ekapop/smartfarm/check_dual_camera.py
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


class C:
    """ANSI color codes for readable terminal output."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# ---------- print helpers ----------

def header(msg: str) -> None:
    print(f"\n{C.BOLD}{C.BLUE}▶ {msg}{C.RESET}")


def sub(msg: str) -> None:
    print(f"\n{C.BOLD}{C.CYAN}▷ {msg}{C.RESET}")


def ok(msg: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {C.YELLOW}⚠{C.RESET} {msg}")


def err(msg: str) -> None:
    print(f"  {C.RED}✗{C.RESET} {msg}")


# ---------- diagnostic checks ----------

def list_cameras() -> list:
    """Enumerate every camera libcamera can see on the CSI bus.

    Returns a list of dicts from Picamera2.global_camera_info().
    Each dict typically has: Model, Location, Rotation, Id, Num.
    """
    header("1. Hardware detection (all cameras)")
    try:
        from picamera2 import Picamera2
    except ImportError:
        err("picamera2 not installed.")
        err("  Install:  sudo apt install python3-picamera2")
        return []

    try:
        info = Picamera2.global_camera_info()
    except Exception as e:
        err(f"Camera enumeration failed: {e}")
        return []

    if not info:
        err("No cameras detected on the CSI bus.")
        err("  Pi 5 has two camera ports:")
        err("    CAM/DISP 0 (near the USB ports)")
        err("    CAM/DISP 1 (near the HDMI ports)")
        err("  Check the ribbon cable orientation on BOTH ports.")
        return []

    ok(f"Found {len(info)} camera(s):")
    for cam in info:
        num = cam.get("Num", "?")
        model = cam.get("Model", "unknown")
        loc = cam.get("Location", "?")
        print(f"    camera {num}: {model}   (CSI slot {loc})")

    if len(info) == 1:
        warn("Only ONE camera detected — expected 2. Check the other CSI cable.")

    return info


def check_dmesg_errors() -> None:
    """Search kernel log for camera errors. Non-fatal."""
    header("2. CSI cable health (kernel log)")
    try:
        result = subprocess.run(
            ["dmesg", "-T"], capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        warn("Could not read dmesg (try running with sudo)")
        return

    keywords_camera = (
        "imx708", "imx219", "imx477", "unicam", "csi", "camera", "cfe",
    )
    keywords_error = ("error", "fail", "timeout", "reset", "unable")

    camera_lines = [l for l in result.stdout.splitlines()
                    if any(k in l.lower() for k in keywords_camera)]
    error_lines = [l for l in camera_lines
                   if any(k in l.lower() for k in keywords_error)]

    if error_lines:
        warn(f"Found {len(error_lines)} camera-related error(s):")
        for line in error_lines[-3:]:
            print(f"    {line}")
    else:
        ok(f"No CSI errors ({len(camera_lines)} normal camera messages)")


def check_thermal() -> None:
    """Read SoC temperature."""
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
        warn(f"SoC temperature: {temp_c:.1f}°C  (warm)")
    else:
        err(f"SoC temperature: {temp_c:.1f}°C  (THROTTLING RISK)")


def capture_from_camera(camera_num: int, output_dir: Path, resolution: tuple):
    """Capture one still from a specific camera.

    Returns:
      (image_path, laplacian_variance)
      image_path is None if capture failed.
    """
    from picamera2 import Picamera2
    from libcamera import controls
    import cv2

    picam2 = Picamera2(camera_num=camera_num)
    still_config = picam2.create_still_configuration(main={"size": resolution})
    picam2.configure(still_config)

    image_path = None
    variance = 0.0

    try:
        picam2.start()

        # Trigger one-shot AF. Only Module 3 has an AF motor; on Module 2
        # (fixed focus) this silently does nothing — we swallow the error.
        print(f"  triggering autofocus, waiting 1.5 s...")
        try:
            picam2.set_controls({"AfMode": controls.AfModeEnum.Auto})
            picam2.autofocus_cycle()
        except Exception:
            pass
        time.sleep(1.5)

        # Save with camera number in filename so files don't overwrite
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = output_dir / f"cam{camera_num}_test_{timestamp}.jpg"
        picam2.capture_file(str(image_path))
        ok(f"Saved: {image_path.name}")

        # Sharpness score
        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            err(f"Could not re-read saved image")
            return image_path, 0.0
        variance = cv2.Laplacian(img, cv2.CV_64F).var()

    except Exception as e:
        err(f"Capture failed on camera {camera_num}: {e}")
    finally:
        try:
            picam2.close()
        except Exception:
            pass

    return image_path, variance


def sharpness_label(variance: float):
    """Turn a variance number into (label, color) for the summary table."""
    if variance <= 0:
        return "FAILED", C.RED
    elif variance < 100:
        return "BLURRY", C.RED
    elif variance < 500:
        return "acceptable", C.YELLOW
    else:
        return "sharp", C.GREEN


def print_summary(results: list) -> None:
    """Print a side-by-side comparison of every tested camera."""
    header("5. Summary")
    print(f"  {'Cam':<5}{'Model':<10}{'Variance':<12}{'Status':<14}{'File'}")
    print(f"  {'-'*5}{'-'*10}{'-'*12}{'-'*14}{'-'*40}")
    for r in results:
        label, color = sharpness_label(r["variance"])
        var_str = f"{r['variance']:.1f}" if r["variance"] > 0 else "n/a"
        fname = r["path"].name if r["path"] else "(capture failed)"
        print(
            f"  {r['num']:<5}{r['model']:<10}{var_str:<12}"
            f"{color}{label:<14}{C.RESET}{fname}"
        )


# ---------- main entry point ----------

def parse_resolution(s: str) -> tuple:
    """Parse '2304x1296' into (2304, 1296)."""
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except Exception:
        raise argparse.ArgumentTypeError(
            "Resolution must be like '2304x1296' or '4608x2592'"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test every camera on a Pi 5 dual-camera setup."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/home/ekapop/smartfarm/camera_tests"),
        help="Where to save the test images",
    )
    parser.add_argument(
        "--resolution",
        type=parse_resolution,
        default=(2304, 1296),
        help="Capture resolution (default 2304x1296, good for Module 3)",
    )
    args = parser.parse_args()

    print(
        f"{C.BOLD}Pi 5 dual-camera diagnostic  —  "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}{C.RESET}"
    )

    # 1. enumerate
    cameras = list_cameras()
    if not cameras:
        print(f"\n{C.RED}{C.BOLD}✗ FAIL — no cameras detected.{C.RESET}")
        sys.exit(1)

    # 2 & 3. passive
    check_dmesg_errors()
    check_thermal()

    # 4. capture from each
    header(f"4. Capture test — {len(cameras)} camera(s)")
    results = []
    for cam in cameras:
        num = cam.get("Num", 0)
        model = cam.get("Model", "unknown")
        sub(f"Testing camera {num}  ({model})")
        path, variance = capture_from_camera(num, args.output_dir, args.resolution)
        results.append({
            "num": num,
            "model": model,
            "path": path,
            "variance": variance,
        })

    # 5. summary
    print_summary(results)

    capture_failed = any(r["path"] is None for r in results)
    blurry = any(r["variance"] > 0 and r["variance"] < 100 for r in results)

    print()
    if capture_failed:
        print(f"{C.RED}{C.BOLD}✗ FAIL — at least one camera capture failed.{C.RESET}")
        sys.exit(2)
    elif blurry:
        print(f"{C.RED}{C.BOLD}✗ FAIL — at least one camera is blurry.{C.RESET}")
        print(f"Fix focus or CSI cable on the low-variance camera(s) above.")
        sys.exit(3)
    else:
        print(f"{C.GREEN}{C.BOLD}✓ ALL CAMERAS PASSED{C.RESET}")
        print(f"Open the test images in {args.output_dir} to verify visually.")
        sys.exit(0)


if __name__ == "__main__":
    main()