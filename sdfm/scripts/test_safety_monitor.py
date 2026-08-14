# ~/smartfarm/scripts/test_safety_monitor.py

from __future__ import annotations

import sys
import time

from pymavlink import mavutil

from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState
from sdfm.safety.monitor import SafetyMonitor


STARTUP_TIMEOUT_SEC = 5.0
TEST_DURATION_SEC = 15.0


def request_telemetry(
    pixhawk: PixhawkConnection,
) -> None:
    pixhawk.request_message_interval(
        mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT,
        2.0,
    )

    pixhawk.request_message_interval(
        mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
        2.0,
    )

    pixhawk.request_message_interval(
        mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
        2.0,
    )

    pixhawk.request_message_interval(
        mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
        5.0,
    )

    pixhawk.request_message_interval(
        mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
        5.0,
    )


def wait_for_heartbeat(
    telemetry: TelemetryState,
    timeout_sec: float,
) -> bool:
    deadline = time.monotonic() + timeout_sec

    while time.monotonic() < deadline:
        if telemetry.heartbeat_received:
            return True

        time.sleep(0.05)

    return telemetry.heartbeat_received


def print_status(
    monitor: SafetyMonitor,
) -> None:
    status = monitor.evaluate()

    print()
    print("=" * 64)
    print(" SAFETY STATUS")
    print("=" * 64)

    print(f"Safe     : {status.safe}")
    print(f"Severity : {status.severity.value}")

    if not status.issues:
        print("Issues   : none")

    else:
        print("Issues:")

        for issue in status.issues:
            print(
                f"  [{issue.severity.value:<8}] "
                f"{issue.code} - {issue.message}"
            )

            for key, value in issue.details.items():
                print(
                    f"      {key:<20}: {value}"
                )

    print("=" * 64)


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM SAFETY MONITOR TEST")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Action  : READ ONLY")
    print("ARM     : NO")
    print()

    pixhawk = PixhawkConnection()
    telemetry = TelemetryState()

    router = MavlinkRouter(
        pixhawk=pixhawk,
        telemetry=telemetry,
    )

    try:
        print("Connecting Pixhawk...")

        pixhawk.connect()

        print(f"Device    : {pixhawk.device}")
        print(f"System ID : {pixhawk.system_id}")

        router.start()

        request_telemetry(
            pixhawk
        )

        print()
        print("Waiting for telemetry...")

        if not wait_for_heartbeat(
            telemetry,
            STARTUP_TIMEOUT_SEC,
        ):
            print(
                "FAILED: PIXHAWK_HEARTBEAT_TIMEOUT"
            )
            return 1

        monitor = SafetyMonitor(
            telemetry=telemetry,
        )

        print()
        print(
            f"Monitoring for "
            f"{TEST_DURATION_SEC:.0f} seconds..."
        )

        end_time = (
            time.monotonic()
            + TEST_DURATION_SEC
        )

        while time.monotonic() < end_time:

            status = monitor.evaluate()

            snapshot = telemetry.snapshot()

            heartbeat = snapshot["heartbeat"]
            vehicle = snapshot["vehicle"]
            battery = snapshot["battery"]
            gps = snapshot["gps"]

            print(
                "\r"
                f"Safety={status.severity.value:<8} "
                f"Armed={str(vehicle['armed']):<5} "
                f"Mode={str(vehicle['mode']):<10} "
                f"HB={heartbeat['age_sec']!s:<8} "
                f"Bat={battery['remaining_percent']!s:<4}% "
                f"GPS={gps['fix_type']!s:<3}",
                end="",
                flush=True,
            )

            time.sleep(0.5)

        print()
        print_status(
            monitor
        )

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