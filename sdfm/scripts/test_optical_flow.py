# ~/smartfarm/scripts/test_optical_flow.py

from __future__ import annotations

import sys
import time

from pymavlink import mavutil

from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


TEST_DURATION_SEC = 15.0
FLOW_TIMEOUT_SEC = 5.0
STALE_TIMEOUT_SEC = 1.0


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM OPTICAL FLOW TEST")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Sensor  : MicoAir MTF-01P")
    print("Input   : UART / GPS2 -> Pixhawk")
    print("Action  : READ ONLY")
    print()

    pixhawk = PixhawkConnection()
    telemetry = TelemetryState()

    router = MavlinkRouter(
        pixhawk=pixhawk,
        telemetry=telemetry,
    )

    last_flow = None
    last_flow_time = None
    flow_count = 0

    def on_optical_flow(message) -> None:

        nonlocal last_flow
        nonlocal last_flow_time
        nonlocal flow_count

        last_flow = message
        last_flow_time = time.monotonic()
        flow_count += 1

    try:

        print("Connecting Pixhawk...")

        pixhawk.connect()

        print(f"Device    : {pixhawk.device}")
        print(f"System ID : {pixhawk.system_id}")
        print()

        router.subscribe(
            "OPTICAL_FLOW_RAD",
            on_optical_flow,
        )

        router.start()

        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_OPTICAL_FLOW_RAD,
            10.0,
        )

        print("Waiting for OPTICAL_FLOW_RAD...")

        deadline = (
            time.monotonic()
            + FLOW_TIMEOUT_SEC
        )

        while (
            last_flow is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_flow is None:

            print()
            print("=" * 64)
            print(" OPTICAL FLOW TEST FAILED")
            print("=" * 64)
            print("OPTICAL_FLOW_RAD not received")
            print("=" * 64)

            return 1

        print()
        print(
            f"Receiving optical flow for "
            f"{TEST_DURATION_SEC:.0f} seconds..."
        )

        print(
            "Move textured paper or your hand slowly "
            "under the downward-facing sensor."
        )

        print()

        end_time = (
            time.monotonic()
            + TEST_DURATION_SEC
        )

        while time.monotonic() < end_time:

            message = last_flow

            if message is not None:

                print(
                    "\r"
                    f"Flow X={message.integrated_x:9.5f}  "
                    f"Y={message.integrated_y:9.5f}  "
                    f"Quality={message.quality:3d}  "
                    f"Distance={message.distance:6.3f} m",
                    end="",
                    flush=True,
                )

            time.sleep(0.1)

        print()
        print()

        if last_flow_time is None:

            print("FLOW STATUS : FAILED")
            return 1

        age = (
            time.monotonic()
            - last_flow_time
        )

        print("=" * 64)
        print(" OPTICAL FLOW SUMMARY")
        print("=" * 64)

        print(
            f"Messages       : {flow_count}"
        )

        print(
            f"Last age       : {age:.3f} sec"
        )

        print(
            f"Quality        : {last_flow.quality}"
        )

        print(
            f"Integrated X   : {last_flow.integrated_x:.5f}"
        )

        print(
            f"Integrated Y   : {last_flow.integrated_y:.5f}"
        )

        print(
            f"Distance       : {last_flow.distance:.3f} m"
        )

        if age > STALE_TIMEOUT_SEC:

            print(
                "FLOW STATUS    : STALE"
            )

            return 1

        #
        # We do not fail simply because flow is close to zero.
        # If the drone/surface is stationary, near-zero flow is normal.
        #
        print(
            "FLOW STATUS    : OK"
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
            router.unsubscribe(
                "OPTICAL_FLOW_RAD",
                on_optical_flow,
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
    sys.exit(main())