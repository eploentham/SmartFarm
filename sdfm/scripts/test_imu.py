# ~/smartfarm/scripts/test_imu.py

from __future__ import annotations

import sys
import time

from pymavlink import mavutil

from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


TEST_DURATION_SEC = 15.0
IMU_TIMEOUT_SEC = 5.0


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM IMU TEST")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Sensor  : Pixhawk IMU")
    print("Action  : READ ONLY")
    print()

    pixhawk = PixhawkConnection()
    telemetry = TelemetryState()

    router = MavlinkRouter(
        pixhawk=pixhawk,
        telemetry=telemetry,
    )

    last_imu_message = None
    last_imu_time = None
    imu_message_count = 0

    def on_highres_imu(message) -> None:

        nonlocal last_imu_message
        nonlocal last_imu_time
        nonlocal imu_message_count

        last_imu_message = message
        last_imu_time = time.monotonic()
        imu_message_count += 1

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

        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_HIGHRES_IMU,
            10.0,
        )

        print("Waiting for HIGHRES_IMU...")

        deadline = (
            time.monotonic()
            + IMU_TIMEOUT_SEC
        )

        while (
            last_imu_message is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_imu_message is None:

            print()
            print("HIGHRES_IMU not received.")
            print("Trying RAW_IMU fallback...")

            router.unsubscribe(
                "HIGHRES_IMU",
                on_highres_imu,
            )

            def on_raw_imu(message) -> None:

                nonlocal last_imu_message
                nonlocal last_imu_time
                nonlocal imu_message_count

                last_imu_message = message
                last_imu_time = time.monotonic()
                imu_message_count += 1

            router.subscribe(
                "RAW_IMU",
                on_raw_imu,
            )

            pixhawk.request_message_interval(
                mavutil.mavlink.MAVLINK_MSG_ID_RAW_IMU,
                10.0,
            )

            deadline = (
                time.monotonic()
                + IMU_TIMEOUT_SEC
            )

            while (
                last_imu_message is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)

            if last_imu_message is None:

                print()
                print("=" * 64)
                print(" IMU TEST FAILED")
                print("=" * 64)
                print("No HIGHRES_IMU or RAW_IMU received")
                print("=" * 64)

                return 1

        print()
        print(
            f"Receiving IMU data for "
            f"{TEST_DURATION_SEC:.0f} seconds..."
        )

        print(
            "Gently tilt DR01 by hand "
            "and watch values change."
        )

        print()

        end_time = (
            time.monotonic()
            + TEST_DURATION_SEC
        )

        while time.monotonic() < end_time:

            message = last_imu_message

            if message is not None:

                msg_type = message.get_type()

                if msg_type == "HIGHRES_IMU":

                    print(
                        "\r"
                        f"ACC "
                        f"X={message.xacc:8.3f} "
                        f"Y={message.yacc:8.3f} "
                        f"Z={message.zacc:8.3f}   "
                        f"GYRO "
                        f"X={message.xgyro:8.3f} "
                        f"Y={message.ygyro:8.3f} "
                        f"Z={message.zgyro:8.3f}",
                        end="",
                        flush=True,
                    )

                elif msg_type == "RAW_IMU":

                    print(
                        "\r"
                        f"ACC "
                        f"X={message.xacc:6d} "
                        f"Y={message.yacc:6d} "
                        f"Z={message.zacc:6d}   "
                        f"GYRO "
                        f"X={message.xgyro:6d} "
                        f"Y={message.ygyro:6d} "
                        f"Z={message.zgyro:6d}",
                        end="",
                        flush=True,
                    )

            time.sleep(0.1)

        print()
        print()

        if last_imu_time is None:

            print("IMU STATUS : FAILED")
            return 1

        age = (
            time.monotonic()
            - last_imu_time
        )

        print("=" * 64)
        print(" IMU SUMMARY")
        print("=" * 64)

        print(
            f"Messages     : {imu_message_count}"
        )

        print(
            f"Last age     : {age:.3f} sec"
        )

        print(
            f"Message type : "
            f"{last_imu_message.get_type()}"
        )

        if age > 1.0:

            print(
                "IMU STATUS    : STALE"
            )

            return 1

        print(
            "IMU STATUS    : OK"
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