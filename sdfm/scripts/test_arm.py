# ~/smartfarm/scripts/test_arm.py

from __future__ import annotations

import sys
import time

from sdfm.flight.commands import FlightCommands
from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


HEARTBEAT_TIMEOUT_SEC = 5.0

# Keep first bench ARM intentionally short.
ARM_HOLD_SEC = 2.0


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


def print_result(
    title: str,
    result,
) -> None:

    print()
    print("=" * 64)
    print(f" {title}")
    print("=" * 64)

    print(f"Success : {result.success}")
    print(f"Code    : {result.code.value}")
    print(f"Message : {result.message}")

    if result.details:
        print()

        for key, value in result.details.items():
            print(
                f"{key:<22}: {value}"
            )

    print("=" * 64)


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM ARM / DISARM BENCH TEST")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Action  : ARM -> VERIFY -> DISARM -> VERIFY")
    print()
    print("WARNING : PROPELLERS MUST BE REMOVED")
    print()

    pixhawk = PixhawkConnection()
    telemetry = TelemetryState()

    router = MavlinkRouter(
        pixhawk=pixhawk,
        telemetry=telemetry,
    )

    commands = None

    try:

        # ----------------------------------------------------------
        # Pixhawk
        # ----------------------------------------------------------

        print("Connecting Pixhawk...")

        pixhawk.connect()

        print(f"Device    : {pixhawk.device}")
        print(f"System ID : {pixhawk.system_id}")
        print()

        # ----------------------------------------------------------
        # MAVLink single-reader
        # ----------------------------------------------------------

        router.start()

        print("Waiting for HEARTBEAT...")

        if not wait_for_heartbeat(
            telemetry,
            HEARTBEAT_TIMEOUT_SEC,
        ):

            print(
                "FAILED: PIXHAWK_HEARTBEAT_TIMEOUT"
            )

            return 1

        print(
            f"Mode  : {telemetry.flight_mode}"
        )

        print(
            f"Armed : {telemetry.armed}"
        )

        # ----------------------------------------------------------
        # Initial safety guard
        # ----------------------------------------------------------

        if telemetry.is_armed():

            print()
            print(
                "ABORT: DR01 IS ALREADY ARMED"
            )

            return 1

        commands = FlightCommands(
            pixhawk=pixhawk,
            router=router,
            telemetry=telemetry,
        )

        # ----------------------------------------------------------
        # ARM
        # ----------------------------------------------------------

        print()
        print("Sending ARM command...")

        arm_result = commands.arm()

        print_result(
            "ARM RESULT",
            arm_result,
        )

        if not arm_result.success:

            print()
            print(
                "ARM TEST FAILED"
            )

            return 1

        # Independent state check.
        if not telemetry.is_armed():

            print()
            print(
                "CRITICAL: ARM reported success "
                "but telemetry is not armed"
            )

            return 1

        print()
        print(
            f"ARM VERIFIED. Holding for "
            f"{ARM_HOLD_SEC:.0f} seconds..."
        )

        time.sleep(
            ARM_HOLD_SEC
        )

        # ----------------------------------------------------------
        # DISARM
        # ----------------------------------------------------------

        print()
        print("Sending DISARM command...")

        disarm_result = commands.disarm()

        print_result(
            "DISARM RESULT",
            disarm_result,
        )

        if not disarm_result.success:

            print()
            print(
                "DISARM TEST FAILED"
            )

            return 1

        if telemetry.is_armed():

            print()
            print(
                "CRITICAL: VEHICLE STILL ARMED"
            )

            return 1

        # ----------------------------------------------------------
        # Success
        # ----------------------------------------------------------

        print()
        print("=" * 64)
        print(" ARM / DISARM TEST PASSED")
        print("=" * 64)

        print("ARM command       : SUCCESS")
        print("ARM ACK           : SUCCESS")
        print("ARM state verify  : SUCCESS")
        print("DISARM command    : SUCCESS")
        print("DISARM ACK        : SUCCESS")
        print("DISARM verify     : SUCCESS")
        print("Final Armed       : NO")

        print("=" * 64)

        return 0

    except KeyboardInterrupt:

        print()
        print(
            "Test interrupted by user."
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

        return 1

    finally:

        # ----------------------------------------------------------
        # Emergency cleanup
        #
        # If ARM succeeded but something later failed,
        # make a best-effort DISARM before closing MAVLink.
        # ----------------------------------------------------------

        if (
            commands is not None
            and telemetry.is_armed()
        ):

            print()
            print(
                "SAFETY: vehicle still armed; "
                "attempting DISARM..."
            )

            try:
                result = commands.disarm()

                print(
                    f"Safety disarm: "
                    f"{result.code.value}"
                )

            except Exception as exc:
                print(
                    "WARNING: automatic DISARM "
                    f"failed: {exc}"
                )

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