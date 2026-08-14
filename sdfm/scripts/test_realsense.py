# ~/smartfarm/scripts/test_realsense.py

from __future__ import annotations

import sys
import time

try:
    import pyrealsense2 as rs
except ImportError:
    print("FAILED: pyrealsense2 is not installed")
    sys.exit(1)


TEST_DURATION_SEC = 10.0
FRAME_TIMEOUT_MS = 3000


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM REALSENSE D435i TEST")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Sensor  : Intel RealSense D435i")
    print("Action  : READ ONLY")
    print()

    pipeline = rs.pipeline()
    config = rs.config()

    try:
        context = rs.context()
        devices = context.query_devices()

        if len(devices) == 0:
            print("RealSense device : NOT FOUND")
            return 1

        device = devices[0]

        name = device.get_info(
            rs.camera_info.name
        )

        serial = device.get_info(
            rs.camera_info.serial_number
        )

        firmware = device.get_info(
            rs.camera_info.firmware_version
        )

        print(f"Device   : {name}")
        print(f"Serial   : {serial}")
        print(f"Firmware : {firmware}")
        print()

        # Depth
        config.enable_stream(
            rs.stream.depth,
            640,
            480,
            rs.format.z16,
            30,
        )

        # RGB
        config.enable_stream(
            rs.stream.color,
            640,
            480,
            rs.format.bgr8,
            30,
        )

        print("Starting streams...")

        pipeline.start(config)

        print("Depth stream : STARTED")
        print("Color stream : STARTED")
        print()

        frame_count = 0
        last_frame_time = None

        first_depth = None

        start_time = time.monotonic()
        end_time = start_time + TEST_DURATION_SEC

        while time.monotonic() < end_time:

            frames = pipeline.wait_for_frames(
                timeout_ms=FRAME_TIMEOUT_MS
            )

            depth_frame = frames.get_depth_frame()
            color_frame = frames.get_color_frame()

            if not depth_frame or not color_frame:
                continue

            frame_count += 1
            last_frame_time = time.monotonic()

            width = depth_frame.get_width()
            height = depth_frame.get_height()

            center_x = width // 2
            center_y = height // 2

            distance_m = depth_frame.get_distance(
                center_x,
                center_y,
            )

            if first_depth is None:
                first_depth = distance_m

            print(
                "\r"
                f"Frames={frame_count:4d}  "
                f"Center depth={distance_m:6.3f} m",
                end="",
                flush=True,
            )

        print()
        print()

        if frame_count == 0:
            print("REALSENSE STATUS : NO FRAMES")
            return 1

        if last_frame_time is None:
            print("REALSENSE STATUS : FAILED")
            return 1

        age = (
            time.monotonic()
            - last_frame_time
        )

        elapsed = (
            time.monotonic()
            - start_time
        )

        fps = (
            frame_count / elapsed
            if elapsed > 0
            else 0.0
        )

        print("=" * 64)
        print(" REALSENSE SUMMARY")
        print("=" * 64)

        print(
            f"Frames          : {frame_count}"
        )

        print(
            f"Measured FPS    : {fps:.1f}"
        )

        print(
            f"Last frame age  : {age:.3f} sec"
        )

        print(
            f"First depth     : {first_depth:.3f} m"
        )

        if age > 1.0:
            print(
                "REALSENSE STATUS : STALE"
            )
            return 1

        print(
            "REALSENSE STATUS : OK"
        )

        print("=" * 64)

        return 0

    except Exception as exc:

        print()
        print("=" * 64)
        print(" REALSENSE TEST FAILED")
        print("=" * 64)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1

    finally:

        try:
            pipeline.stop()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(
        main()
    )