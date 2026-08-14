#!/usr/bin/env python3
"""Manual GPIO diagnostic for the three DR01 status LEDs."""

from __future__ import annotations

import argparse
import time

def main() -> int:
    parser = argparse.ArgumentParser(description="Cycle DR01 Blue/Green/Orange LEDs")
    parser.add_argument("--seconds", type=float, default=2.0, help="duration of each pattern")
    args = parser.parse_args()

    from sdfm import config
    from sdfm.indicators.led import LedStatus, StatusLedController

    leds = StatusLedController.from_gpiozero(
        config.STATUS_LED_BLUE_GPIO,
        config.STATUS_LED_GREEN_GPIO,
        config.STATUS_LED_ORANGE_GPIO,
    )
    try:
        for status in (
            LedStatus.READY,
            LedStatus.CLEAR,
            LedStatus.WARNING,
            LedStatus.BLOCKED,
            LedStatus.UNKNOWN,
            LedStatus.TELEMETRY_LOST,
        ):
            print(status.value, flush=True)
            leds.set_status(status, safety_override=True)
            time.sleep(max(0.1, args.seconds))
    except KeyboardInterrupt:
        return 0
    finally:
        leds.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
