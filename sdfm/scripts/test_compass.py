# ~/smartfarm/scripts/test_compass.py

from __future__ import annotations

import sys
import time

from pymavlink import mavutil

from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


TEST_DURATION_SEC = 15.0
COMPASS_TIMEOUT_SEC = 5.0


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM COMPASS TEST")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Sensor  : Pixhawk Compass / Magnetometer")
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

    def on_highres_imu(message) -> None:

        nonlocal last_message
        nonlocal last_message_time
        nonlocal message_count

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
            "HIGHRES_IMU",
            on_highres_imu,
        )

        router.start()

        #
        # HIGHRES_IMU contains:
        # xmag, ymag, zmag
        #
        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_HIGHRES_IMU,
            10.0,
        )

        print("Waiting for magnetometer data...")

        deadline = (
            time.monotonic()
            + COMPASS_TIMEOUT_SEC
        )

        while (
            last_message is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_message is None:

            print()
            print("=" * 64)
            print(" COMPASS TEST FAILED")
            print("=" * 64)
            print("HIGHRES_IMU not received")
            print("=" * 64)

            return 1

        print()
        print(
            f"Receiving compass data for "
            f"{TEST_DURATION_SEC:.0f} seconds..."
        )

        print(
            "Slowly rotate DR01 left/right "
            "and watch MAG values change."
        )

        print()

        end_time = (
            time.monotonic()
            + TEST_DURATION_SEC
        )

        while time.monotonic() < end_time:

            message = last_message

            if message is not None:

                print(
                    "\r"
                    f"MAG "
                    f"X={message.xmag:9.4f} "
                    f"Y={message.ymag:9.4f} "
                    f"Z={message.zmag:9.4f}",
                    end="",
                    flush=True,
                )

            time.sleep(0.1)

        print()
        print()

        if last_message_time is None:

            print("COMPASS STATUS : FAILED")
            return 1

        age = (
            time.monotonic()
            - last_message_time
        )

        print("=" * 64)
        print(" COMPASS SUMMARY")
        print("=" * 64)

        print(
            f"Messages       : {message_count}"
        )

        print(
            f"Last age       : {age:.3f} sec"
        )

        print(
            f"MAG X          : {last_message.xmag:.4f}"
        )

        print(
            f"MAG Y          : {last_message.ymag:.4f}"
        )

        print(
            f"MAG Z          : {last_message.zmag:.4f}"
        )

        if age > 1.0:

            print(
                "COMPASS STATUS  : STALE"
            )

            return 1

        #
        # Basic sanity check:
        # all zero would normally indicate no useful mag data.
        #
        magnitude = (
            last_message.xmag ** 2
            + last_message.ymag ** 2
            + last_message.zmag ** 2
        ) ** 0.5

        print(
            f"MAG magnitude  : {magnitude:.4f}"
        )

        if magnitude <= 0.0001:

            print(
                "COMPASS STATUS  : NO VALID DATA"
            )

            return 1

        print(
            "COMPASS STATUS  : OK"
        )

        print("=" * 64)

        return 0

    except KeyboardInterrupt:

        print()
        print("Test interrupted.")

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