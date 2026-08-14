# ~/smartfarm/scripts/test_prearm.py

from __future__ import annotations

import sys
import time

from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


LISTEN_SEC = 35.0


def severity_name(value: int) -> str:
    names = {
        0: "EMERGENCY",
        1: "ALERT",
        2: "CRITICAL",
        3: "ERROR",
        4: "WARNING",
        5: "NOTICE",
        6: "INFO",
        7: "DEBUG",
    }

    return names.get(value, f"UNKNOWN_{value}")


def decode_text(message) -> str:
    text = message.text

    if isinstance(text, bytes):
        return text.decode(
            "utf-8",
            errors="replace",
        ).rstrip("\x00")

    return str(text).rstrip("\x00")


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM PRE-ARM DIAGNOSTIC")
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

    prearm_messages: list[tuple[int, str]] = []
    all_status_messages: list[tuple[int, str]] = []

    def on_statustext(message) -> None:

        text = decode_text(message)
        severity = int(message.severity)

        all_status_messages.append(
            (severity, text)
        )

        if text.lower().startswith("prearm:"):
            prearm_messages.append(
                (severity, text)
            )

            print(
                f"[{severity_name(severity):<8}] "
                f"{text}"
            )

    try:

        # ----------------------------------------------------------
        # Connect
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
        # Router
        # ----------------------------------------------------------

        router.subscribe(
            "STATUSTEXT",
            on_statustext,
        )

        router.start()

        # ----------------------------------------------------------
        # Wait until heartbeat telemetry is available
        # ----------------------------------------------------------

        print()
        print("Waiting for HEARTBEAT...")

        deadline = time.monotonic() + 5.0

        while (
            not telemetry.heartbeat_received
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if not telemetry.heartbeat_received:

            print(
                "FAILED: PIXHAWK_HEARTBEAT_TIMEOUT"
            )

            return 1

        print(
            f"Armed : {telemetry.armed}"
        )

        print(
            f"Mode  : {telemetry.flight_mode}"
        )

        # ----------------------------------------------------------
        # Safety guard
        # ----------------------------------------------------------

        if telemetry.is_armed():

            print()
            print(
                "ABORT: VEHICLE_IS_ARMED"
            )

            print(
                "PreArm diagnostic must run while DISARMED."
            )

            return 1

        # ----------------------------------------------------------
        # Listen
        # ----------------------------------------------------------

        print()
        print(
            f"Listening for ArduPilot STATUSTEXT "
            f"for {LISTEN_SEC:.0f} seconds..."
        )

        print(
            "Waiting for PreArm messages:"
        )

        print("-" * 64)

        end_time = (
            time.monotonic()
            + LISTEN_SEC
        )

        while time.monotonic() < end_time:

            if telemetry.is_armed():

                print()
                print(
                    "ABORT: VEHICLE_BECAME_ARMED"
                )

                return 1

            time.sleep(0.1)

        # ----------------------------------------------------------
        # Summary
        # ----------------------------------------------------------

        print("-" * 64)
        print()

        # Remove duplicates while preserving order.
        unique_prearm: list[
            tuple[int, str]
        ] = []

        seen: set[str] = set()

        for severity, text in prearm_messages:

            if text in seen:
                continue

            seen.add(text)

            unique_prearm.append(
                (severity, text)
            )

        print("=" * 64)
        print(" PRE-ARM SUMMARY")
        print("=" * 64)

        print(
            f"Armed        : {telemetry.armed}"
        )

        print(
            f"Mode         : {telemetry.flight_mode}"
        )

        print(
            f"STATUSTEXT   : "
            f"{len(all_status_messages)} received"
        )

        print(
            f"PreArm msgs  : "
            f"{len(unique_prearm)} unique"
        )

        if unique_prearm:

            print()
            print(
                "ArduPilot reports:"
            )

            for severity, text in unique_prearm:

                print(
                    f"  [{severity_name(severity):<8}] "
                    f"{text}"
                )

            print()
            print(
                "PRE-ARM STATUS : NOT READY"
            )

        else:

            print()
            print(
                "No PreArm failure message was "
                "observed during the listening window."
            )

            print(
                "PRE-ARM STATUS : NO FAILURE OBSERVED"
            )

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

        try:
            router.unsubscribe(
                "STATUSTEXT",
                on_statustext,
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