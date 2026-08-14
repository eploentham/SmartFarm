# ~/smartfarm/scripts/test_lidar_front.py

from __future__ import annotations

import sys
import time

from pymavlink import mavutil

from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


TEST_DURATION_SEC = 15.0
LIDAR_TIMEOUT_SEC = 5.0
STALE_TIMEOUT_SEC = 1.0

FRONT_ORIENTATION = (
    mavutil.mavlink.MAV_SENSOR_ROTATION_NONE
)


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM FRONT LiDAR TEST")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Sensor  : TFmini Plus Front")
    print("Action  : READ ONLY")
    print()

    pixhawk = PixhawkConnection()
    telemetry = TelemetryState()

    router = MavlinkRouter(
        pixhawk=pixhawk,
        telemetry=telemetry,
    )

    last_message = None
    last_message_time = None
    message_count = 0

    def on_distance_sensor(message) -> None:

        nonlocal last_message
        nonlocal last_message_time
        nonlocal message_count

        #
        # Only accept forward-facing distance sensor.
        #
        if message.orientation != FRONT_ORIENTATION:
            return

        last_message = message
        last_message_time = time.monotonic()
        message_count += 1

    try:

        print("Connecting Pixhawk...")

        pixhawk.connect()

        print(f"Device    : {pixhawk.device}")
        print(f"System ID : {pixhawk.system_id}")
        print()

        router.subscribe(
            "DISTANCE_SENSOR",
            on_distance_sensor,
        )

        router.start()

        # Request DISTANCE_SENSOR telemetry.
        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_DISTANCE_SENSOR,
            10.0,
        )

        print(
            "Waiting for forward DISTANCE_SENSOR..."
        )

        deadline = (
            time.monotonic()
            + LIDAR_TIMEOUT_SEC
        )

        while (
            last_message is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_message is None:

            print()
            print("=" * 64)
            print(" FRONT LiDAR TEST FAILED")
            print("=" * 64)
            print(
                "No forward-facing DISTANCE_SENSOR received"
            )
            print("=" * 64)

            return 1

        print()
        print(
            f"Receiving front LiDAR for "
            f"{TEST_DURATION_SEC:.0f} seconds..."
        )

        print(
            "Move an object closer/farther "
            "in front of the TFmini Plus."
        )

        print()

        end_time = (
            time.monotonic()
            + TEST_DURATION_SEC
        )

        while time.monotonic() < end_time:

            message = last_message

            if message is not None:

                distance_m = (
                    message.current_distance / 100.0
                )

                print(
                    "\r"
                    f"Distance={distance_m:6.2f} m  "
                    f"Raw={message.current_distance:4d} cm  "
                    f"ID={message.id:2d}  "
                    f"Orientation={message.orientation:3d}",
                    end="",
                    flush=True,
                )

            time.sleep(0.1)

        print()
        print()

        if last_message_time is None:

            print(
                "LiDAR STATUS : FAILED"
            )

            return 1

        age = (
            time.monotonic()
            - last_message_time
        )

        distance_cm = (
            last_message.current_distance
        )

        min_cm = (
            last_message.min_distance
        )

        max_cm = (
            last_message.max_distance
        )

        print("=" * 64)
        print(" FRONT LiDAR SUMMARY")
        print("=" * 64)

        print(
            f"Messages       : {message_count}"
        )

        print(
            f"Last age       : {age:.3f} sec"
        )

        print(
            f"Sensor ID      : {last_message.id}"
        )

        print(
            f"Orientation    : {last_message.orientation}"
        )

        print(
            f"Min distance   : {min_cm} cm"
        )

        print(
            f"Max distance   : {max_cm} cm"
        )

        print(
            f"Current        : {distance_cm} cm"
        )

        # ----------------------------------------------------------
        # Stale check
        # ----------------------------------------------------------

        if age > STALE_TIMEOUT_SEC:

            print(
                "LiDAR STATUS   : STALE"
            )

            return 1

        # ----------------------------------------------------------
        # Basic data sanity
        # ----------------------------------------------------------

        if distance_cm == 0:

            print(
                "LiDAR STATUS   : NO VALID DISTANCE"
            )

            return 1

        #
        # Values outside min/max can be meaningful depending on
        # sensor/autopilot handling, so do not classify them as
        # hardware failure here.
        #

        print(
            "LiDAR STATUS   : OK"
        )

        print("=" * 64)

        return 0

    except KeyboardInterrupt:

        print()
        print(
            "Test interrupted."
        )

        return 130

    except Exception as exc:

        print()
        print("=" * 64)
        print(" TEST FAILED")
        print("=" * 64)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        print("=" * 64)

        return 1

    finally:

        try:
            router.unsubscribe(
                "DISTANCE_SENSOR",
                on_distance_sensor,
            )
        except Exception:
            pass

        try:
            router.stop()
        except Exception:
            pass

        try:
            pixhawk.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(
        main()
    )