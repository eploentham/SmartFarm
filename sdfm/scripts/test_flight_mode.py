# ~/smartfarm/scripts/test_flight_mode.py

from __future__ import annotations

import sys
import time

from pymavlink import mavutil

from sdfm.flight.commands import FlightCommands
from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.modes import FlightMode
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


TELEMETRY_STARTUP_TIMEOUT_SEC = 5.0
MODE_SETTLE_SEC = 1.0


def wait_for_heartbeat_state(
    telemetry: TelemetryState,
    timeout_sec: float,
) -> bool:
    """
    Wait until TelemetryState has received at least one HEARTBEAT.
    """

    deadline = time.monotonic() + timeout_sec

    while time.monotonic() < deadline:

        if telemetry.heartbeat_received:
            return True

        time.sleep(0.05)

    return telemetry.heartbeat_received


def print_vehicle_state(
    telemetry: TelemetryState,
) -> None:
    """
    Print current vehicle state.
    """

    snapshot = telemetry.snapshot()

    vehicle = snapshot["vehicle"]
    heartbeat = snapshot["heartbeat"]

    print()
    print("Vehicle state")
    print("-" * 60)

    print(
        f"Armed         : "
        f"{vehicle['armed']}"
    )

    print(
        f"Mode          : "
        f"{vehicle['mode']}"
    )

    print(
        f"Heartbeat age : "
        f"{heartbeat['age_sec']}"
    )

    print("-" * 60)


def print_result(
    title: str,
    result,
) -> None:
    """
    Print OperationResult.
    """

    print()
    print("=" * 60)
    print(title)
    print("=" * 60)

    print(
        f"Success : {result.success}"
    )

    print(
        f"Code    : {result.code.value}"
    )

    print(
        f"Message : {result.message}"
    )

    if result.details:

        print()

        for key, value in result.details.items():

            print(
                f"{key:<20}: {value}"
            )

    print("=" * 60)


def request_test_telemetry(
    pixhawk: PixhawkConnection,
) -> None:
    """
    Request telemetry needed by this test.

    Only telemetry rates are changed.
    No flight movement command is sent here.
    """

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
        mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
        5.0,
    )


def main() -> int:

    print()
    print("=" * 60)
    print(" SDFM FLIGHT MODE TEST")
    print("=" * 60)

    print("Vehicle : DR01")
    print("Test    : DISARMED flight mode change")
    print()

    pixhawk = PixhawkConnection()

    telemetry = TelemetryState()

    router = MavlinkRouter(
        pixhawk=pixhawk,
        telemetry=telemetry,
    )

    try:

        # ----------------------------------------------------------
        # Connect Pixhawk
        # ----------------------------------------------------------

        print("Connecting Pixhawk...")

        pixhawk.connect()

        print(
            f"Device    : {pixhawk.device}"
        )

        print(
            f"System ID : {pixhawk.system_id}"
        )

        print(
            f"Component : {pixhawk.component_id}"
        )

        # ----------------------------------------------------------
        # Start single MAVLink receive path
        # ----------------------------------------------------------

        print()
        print("Starting MAVLink router...")

        router.start()

        # ----------------------------------------------------------
        # Configure telemetry
        # ----------------------------------------------------------

        request_test_telemetry(
            pixhawk
        )

        # ----------------------------------------------------------
        # Wait for telemetry heartbeat
        # ----------------------------------------------------------

        print(
            "Waiting for telemetry heartbeat..."
        )

        if not wait_for_heartbeat_state(
            telemetry,
            TELEMETRY_STARTUP_TIMEOUT_SEC,
        ):

            print()
            print(
                "FAILED: TELEMETRY_HEARTBEAT_TIMEOUT"
            )

            return 1

        print_vehicle_state(
            telemetry
        )

        # ----------------------------------------------------------
        # CRITICAL SAFETY GUARD
        # ----------------------------------------------------------

        if telemetry.is_armed():

            print()
            print(
                "ABORT: VEHICLE_IS_ARMED"
            )

            print(
                "This script must only run "
                "while DR01 is DISARMED."
            )

            return 1

        print(
            "Safety check: vehicle is DISARMED"
        )

        # ----------------------------------------------------------
        # Flight command layer
        # ----------------------------------------------------------

        commands = FlightCommands(
            pixhawk=pixhawk,
            router=router,
            telemetry=telemetry,
        )

        original_mode = (
            telemetry.flight_mode
        )

        print()
        print(
            f"Original mode : {original_mode}"
        )

        # ----------------------------------------------------------
        # TEST 1
        #
        # Change to GUIDED while DISARMED.
        # ----------------------------------------------------------

        print()
        print(
            "TEST 1: Change mode -> GUIDED"
        )

        result = commands.set_mode(
            FlightMode.GUIDED
        )

        print_result(
            "GUIDED RESULT",
            result,
        )

        print_vehicle_state(
            telemetry
        )

        if not result.success:

            print(
                "GUIDED test FAILED."
            )

            return 1

        # Safety verification again.
        if telemetry.is_armed():

            print()
            print(
                "CRITICAL: VEHICLE BECAME ARMED "
                "UNEXPECTEDLY"
            )

            return 1

        time.sleep(
            MODE_SETTLE_SEC
        )

        # ----------------------------------------------------------
        # TEST 2
        #
        # Return to STABILIZE.
        # ----------------------------------------------------------

        print()
        print(
            "TEST 2: Change mode -> STABILIZE"
        )

        result = commands.set_mode(
            FlightMode.STABILIZE
        )

        print_result(
            "STABILIZE RESULT",
            result,
        )

        print_vehicle_state(
            telemetry
        )

        if not result.success:

            print(
                "STABILIZE test FAILED."
            )

            return 1

        # ----------------------------------------------------------
        # Final safety verification
        # ----------------------------------------------------------

        if telemetry.is_armed():

            print()
            print(
                "CRITICAL: VEHICLE IS ARMED"
            )

            return 1

        print()
        print("=" * 60)
        print(" FLIGHT MODE TEST PASSED")
        print("=" * 60)

        print(
            "GUIDED       : SUCCESS"
        )

        print(
            "STABILIZE    : SUCCESS"
        )

        print(
            "Armed        : NO"
        )

        print()
        print(
            "COMMAND -> ACK -> VERIFY STATE "
            "test passed."
        )

        print("=" * 60)

        return 0

    except KeyboardInterrupt:

        print()
        print(
            "Test interrupted by user."
        )

        return 130

    except Exception as exc:

        print()
        print("=" * 60)
        print(" TEST FAILED")
        print("=" * 60)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        print("=" * 60)

        return 1

    finally:

        # ----------------------------------------------------------
        # Shutdown
        # ----------------------------------------------------------

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