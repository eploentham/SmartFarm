# ~/smartfarm/scripts/test_elrs.py

from __future__ import annotations

import sys
import time

from pymavlink import mavutil

from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


TEST_DURATION_SEC = 20.0
RC_TIMEOUT_SEC = 5.0


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM ELRS / RC INPUT TEST")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Receiver: Holybro RP3-V2")
    print("Input   : CRSF / TELEM2")
    print("Action  : READ ONLY")
    print()

    pixhawk = PixhawkConnection()
    telemetry = TelemetryState()

    router = MavlinkRouter(
        pixhawk=pixhawk,
        telemetry=telemetry,
    )

    last_rc_message = None
    rc_message_count = 0
    last_rc_time = None

    def on_rc_channels(message) -> None:

        nonlocal last_rc_message
        nonlocal rc_message_count
        nonlocal last_rc_time

        last_rc_message = message
        rc_message_count += 1
        last_rc_time = time.monotonic()

    try:

        print("Connecting Pixhawk...")

        pixhawk.connect()

        print(f"Device    : {pixhawk.device}")
        print(f"System ID : {pixhawk.system_id}")
        print()

        router.subscribe(
            "RC_CHANNELS",
            on_rc_channels,
        )

        router.start()

        # Ask ArduPilot for RC_CHANNELS telemetry.
        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_RC_CHANNELS,
            5.0,
        )

        print(
            "Waiting for RC_CHANNELS..."
        )

        deadline = (
            time.monotonic()
            + RC_TIMEOUT_SEC
        )

        while (
            last_rc_message is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_rc_message is None:

            print()
            print("=" * 64)
            print(" ELRS / RC TEST FAILED")
            print("=" * 64)
            print("RC_CHANNELS : NOT RECEIVED")
            print()
            print("ArduPilot does not currently report RC input.")
            print("=" * 64)

            return 1

        print()
        print("RC_CHANNELS received.")
        print()
        print(
            "Move sticks and switches on the Boxer "
            "for about 20 seconds."
        )
        print()

        end_time = (
            time.monotonic()
            + TEST_DURATION_SEC
        )

        while time.monotonic() < end_time:

            message = last_rc_message

            if message is not None:

                print(
                    "\r"
                    f"CH1={message.chan1_raw:4d}  "
                    f"CH2={message.chan2_raw:4d}  "
                    f"CH3={message.chan3_raw:4d}  "
                    f"CH4={message.chan4_raw:4d}  "
                    f"CH5={message.chan5_raw:4d}  "
                    f"CH6={message.chan6_raw:4d}  "
                    f"RSSI={message.rssi:3d}",
                    end="",
                    flush=True,
                )

            time.sleep(0.1)

        print()
        print()

        if last_rc_time is None:

            print("RC STATUS : FAILED")
            return 1

        # ----------------------------------------------------------
        # Validate actual RC channel values
        # ----------------------------------------------------------

        channels = [
            last_rc_message.chan1_raw,
            last_rc_message.chan2_raw,
            last_rc_message.chan3_raw,
            last_rc_message.chan4_raw,
        ]

        valid_channels = all(
            800 <= value <= 2200
            for value in channels
        )

        if not valid_channels:
            print("=" * 64)
            print(" ELRS / RC SUMMARY")
            print("=" * 64)

            print(
                f"RC messages : {rc_message_count}"
            )

            print(
                "RC STATUS    : NO VALID RC INPUT"
            )

            print(
                f"CH1-CH4     : {channels}"
            )

            print("=" * 64)

            return 1


        age = (
            time.monotonic()
            - last_rc_time
        )

        print("=" * 64)
        print(" ELRS / RC SUMMARY")
        print("=" * 64)

        print(
            f"RC messages : {rc_message_count}"
        )

        print(
            f"Last age    : {age:.3f} sec"
        )

        if age > 1.0:

            print(
                "RC STATUS    : STALE"
            )

            return 1

        print(
            "RC STATUS    : OK"
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

        return 1

    finally:

        try:
            router.unsubscribe(
                "RC_CHANNELS",
                on_rc_channels,
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