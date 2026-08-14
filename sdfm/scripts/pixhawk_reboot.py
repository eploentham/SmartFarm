# ~/smartfarm/scripts/pixhawk_reboot.py

from __future__ import annotations

import sys
import time

from pymavlink import mavutil

from sdfm.flight.pixhawk import PixhawkConnection


def main() -> int:

    print()
    print("=" * 64)
    print(" SDFM PIXHAWK REBOOT")
    print("=" * 64)
    print("Vehicle : DR01")
    print("Action  : REBOOT AUTOPILOT")
    print()

    pixhawk = PixhawkConnection()

    try:
        print("Connecting Pixhawk...")

        pixhawk.connect()
        master = pixhawk.master
        print("Reboot command sent.")
        print()
        print("Waiting for Pixhawk to reboot...")

        # รอให้ Pixhawk เริ่ม reboot
        time.sleep(3.0)

        # เคลียร์ message เก่า
        while master.recv_match(blocking=False):
            pass

        print("Waiting for Pixhawk heartbeat...")

        deadline = time.monotonic() + 30.0

        heartbeat = None

        while time.monotonic() < deadline:

            heartbeat = master.recv_match(
                type="HEARTBEAT",
                blocking=True,
                timeout=1.0,
            )

            if heartbeat is not None:
                break

            print(".", end="", flush=True)

        print()

        if heartbeat is None:
            print("FAILED: PIXHAWK_BOOT_TIMEOUT")
            return 1

        armed = bool(
            heartbeat.base_mode
            & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        )

        mode = mavutil.mode_string_v10(
            heartbeat
        )

        print()
        print("=" * 64)
        print(" PIXHAWK BOOT COMPLETE")
        print("=" * 64)
        print(f"Heartbeat : OK")
        print(f"Armed     : {armed}")
        print(f"Mode      : {mode}")
        print("=" * 64)

        return 0

    except Exception as exc:
        print()
        print("=" * 64)
        print(" FAILED")
        print("=" * 64)
        print(f"{type(exc).__name__}: {exc}")
        return 1

    finally:
        try:
            pixhawk.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())