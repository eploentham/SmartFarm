#!/usr/bin/env python3
"""
preview_camera.py — Live camera preview on a specific HDMI display.

Shows a live video feed from one of the Pi 5's cameras as a Qt window
positioned on the requested monitor (default: camera 1 on HDMI-A-1).

Usage:
  python3 preview_camera.py                          # cam1 on HDMI-A-1
  python3 preview_camera.py --camera 0               # cam0 on HDMI-A-1
  python3 preview_camera.py --display HDMI-A-2       # cam1 on the 55" TV
  python3 preview_camera.py --fullscreen             # fill the whole display
  python3 preview_camera.py --af-mode auto           # one-shot AF only
  python3 preview_camera.py --width 1280 --height 720

Press Ctrl+C in the terminal to stop the preview cleanly.

Author: Smartfarm project
Location: /home/pi/smartfarm/preview_camera.py
"""

import argparse
import re
import signal
import subprocess
import sys
import time


class C:
    """ANSI color codes for terminal output."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {C.YELLOW}⚠{C.RESET} {msg}")


def err(msg: str) -> None:
    print(f"  {C.RED}✗{C.RESET} {msg}")


def get_display_geometry(display_name: str) -> tuple:
    """Ask wlr-randr where a specific display is positioned.

    Returns (x, y, width, height) for the requested display.
    Falls back to (0, 0, 1920, 1080) if detection fails or the
    display isn't found.
    """
    try:
        result = subprocess.run(
            ["wlr-randr"], capture_output=True, text=True, timeout=5,
        )
        output = result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        warn("wlr-randr not available — using fallback (0,0) 1920x1080")
        return (0, 0, 1920, 1080)

    # wlr-randr blocks start with a name on a line with no leading whitespace,
    # followed by indented details. Split on those name lines.
    blocks = re.split(r"\n(?=\S)", output)
    for block in blocks:
        if block.strip().startswith(display_name):
            pos_match = re.search(r"Position:\s*(\d+),(\d+)", block)
            # Find the ACTIVE mode (marked "current") or fall back to any mode
            active_mode = re.search(
                r"(\d+)x(\d+)\s+px.*current", block, re.IGNORECASE,
            )
            any_mode = re.search(r"(\d+)x(\d+)\s+px", block)
            mode_match = active_mode or any_mode

            x = int(pos_match.group(1)) if pos_match else 0
            y = int(pos_match.group(2)) if pos_match else 0
            w = int(mode_match.group(1)) if mode_match else 1920
            h = int(mode_match.group(2)) if mode_match else 1080
            return (x, y, w, h)

    warn(f"Display '{display_name}' not found — using fallback (0,0) 1920x1080")
    return (0, 0, 1920, 1080)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live camera preview on a specific HDMI display."
    )
    parser.add_argument("--camera", type=int, default=1,
                        help="Camera number (default: 1)")
    parser.add_argument("--display", default="HDMI-A-1",
                        help="Target display name (default: HDMI-A-1)")
    parser.add_argument("--width", type=int, default=None,
                        help="Preview window width (default: display width - 100)")
    parser.add_argument("--height", type=int, default=None,
                        help="Preview window height (default: display height - 100)")
    parser.add_argument("--fullscreen", action="store_true",
                        help="Cover the entire display, no window borders")
    parser.add_argument("--af-mode",
                        choices=["continuous", "auto", "manual"],
                        default="continuous",
                        help="Autofocus mode (default: continuous)")
    args = parser.parse_args()

    print(
        f"{C.BOLD}Camera preview  —  camera {args.camera} on {args.display}{C.RESET}"
    )

    # Figure out where the target display lives in screen coordinates
    disp_x, disp_y, disp_w, disp_h = get_display_geometry(args.display)
    ok(f"Display {args.display}: {disp_w}x{disp_h} at ({disp_x},{disp_y})")

    # Decide window size + position
    if args.fullscreen:
        win_x, win_y = disp_x, disp_y
        win_w, win_h = disp_w, disp_h
    else:
        # Leave a small margin so window controls are visible/draggable
        win_w = args.width or max(disp_w - 100, 640)
        win_h = args.height or max(disp_h - 100, 480)
        win_x = disp_x + 50
        win_y = disp_y + 50
    ok(f"Preview window: {win_w}x{win_h} at ({win_x},{win_y})")

    # Import picamera2 here so we can show a nice error if it's missing
    try:
        from picamera2 import Picamera2, Preview
        from libcamera import controls
    except ImportError:
        err("picamera2 not installed.")
        err("  Install:  sudo apt install python3-picamera2")
        sys.exit(1)

    # Initialize the camera
    try:
        picam2 = Picamera2(camera_num=args.camera)
    except (IndexError, RuntimeError) as e:
        err(f"Camera {args.camera} not found: {e}")
        err("  Check CSI connections and run check_dual_camera.py first.")
        sys.exit(1)

    # Use a preview-optimized configuration (lower resolution = smoother video)
    preview_config = picam2.create_preview_configuration(
        #main={"size": (1280, 720)},
        main={"size": (4608, 2592)},
    )
    picam2.configure(preview_config)

    # Start the Qt preview window at the computed position.
    # QTGL uses OpenGL for hardware-accelerated rendering — smooth even at 60 fps.
    #picam2.start_preview(
    #    Preview.QTGL, x=win_x, y=win_y, width=win_w, height=win_h,
    #)
    picam2.start_preview(        Preview.QT, x=win_x, y=win_y, width=win_w, height=win_h,    )
    picam2.start()

    # Configure autofocus (Module 3 only — errors are harmless on Module 2)
    try:
        if args.af_mode == "continuous":
            picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
            ok("Continuous autofocus active (adjusts as scene changes)")
        elif args.af_mode == "auto":
            picam2.set_controls({"AfMode": controls.AfModeEnum.Auto})
            picam2.autofocus_cycle()
            ok("One-shot autofocus complete (focus locked)")
        else:
            picam2.set_controls({"AfMode": controls.AfModeEnum.Manual})
            warn("Manual focus — AF disabled")
    except Exception as e:
        warn(f"Autofocus setup failed: {e}  (Module 2 has no AF — this is OK)")

    print(
        f"\n{C.BOLD}Preview running. "
        f"Press {C.YELLOW}Ctrl+C{C.RESET}{C.BOLD} in this terminal to stop.{C.RESET}\n"
    )

    # Handle Ctrl+C gracefully
    def stop_preview(sig, frame):
        print(f"\n{C.YELLOW}Stopping preview...{C.RESET}")
        try:
            picam2.stop_preview()
        except Exception:
            pass
        try:
            picam2.stop()
            picam2.close()
        except Exception:
            pass
        ok("Preview stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, stop_preview)
    signal.signal(signal.SIGTERM, stop_preview)

    # Just idle — the preview is running in its own thread
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()