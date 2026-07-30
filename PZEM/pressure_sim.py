#!/usr/bin/env python3
"""
pressure_sim.py — fake water-pressure node for pipeline testing (no hardware).

Publishes the same JSON contract as the ESP32 pressure firmware to
    smartfarm/pressure/{pump_code}
so you can exercise pressure_logger.py -> MariaDB end to end.

Payload fields (logger derives is_running + status_flag itself):
    pump_id, voltage_raw, pressure_bar, pressure_psi,
    reading_at ("YYYY-MM-DD HH:MM:SS")

Examples:
    # WS-01 both pumps, steady ~4 bar, publish every 2s
    python pressure_sim.py --pump WS1-P1 --pump WS1-P2 --bar 4

    # simulate a pump losing prime: pressure drifts toward 0 (NO_FLOW)
    python pressure_sim.py --pump WS1-P1 --bar 4 --duty

    # simulate a broken sensor wire (voltage out of 0.5-4.5 band => SENSOR_ERR)
    python pressure_sim.py --pump WS1-P2 --fault
"""

import os
import json
import time
import random
import argparse
from datetime import datetime

import paho.mqtt.client as mqtt

FS_BAR      = 10.0      # full scale, matches config.PRESSURE_FS_BAR
V_MIN       = 0.5       # sensor V at 0 bar
V_MAX       = 4.5       # sensor V at full scale
PSI_PER_BAR = 14.5037738


def volts_for_bar(bar):
    """Inverse of the transducer transfer function: bar -> sensor volts."""
    return V_MIN + bar * (V_MAX - V_MIN) / FS_BAR


def make_reading(bar, fault):
    if fault:                                   # broken wire -> ~0V, out of band
        v = round(random.uniform(0.0, 0.2), 3)
        return {"voltage_raw": v, "pressure_bar": None, "pressure_psi": None,
                "reading_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    bar = max(bar, 0.0)
    v = volts_for_bar(bar) + random.uniform(-0.01, 0.01)   # a little ADC noise
    return {
        "voltage_raw":  round(v, 3),
        "pressure_bar": round(bar, 2),
        "pressure_psi": round(bar * PSI_PER_BAR, 2),
        "reading_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    ap = argparse.ArgumentParser(description="Simulated water-pressure publisher")
    ap.add_argument("--pump", action="append", required=True,
                    help="pump_code (repeat for multiple pumps)")
    ap.add_argument("--broker", default=os.getenv("MQTT_BROKER", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--bar", type=float, default=4.0, help="target pressure (bar)")
    ap.add_argument("--fault", action="store_true", help="simulate SENSOR_ERR (bad wire)")
    ap.add_argument("--duty", action="store_true",
                    help="cycle each pump: pressurized ~30s, then bleed to 0 ~15s")
    args = ap.parse_args()

    client = mqtt.Client()
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()
    print(f"Publishing to {args.broker}:{args.port} every {args.interval}s for {args.pump}")

    phases = {p: random.uniform(0, 1) for p in args.pump}

    try:
        while True:
            for pump in args.pump:
                if args.duty:
                    t = (time.time() / 45.0 + phases[pump]) % 1.0
                    bar = args.bar if t < 0.66 else 0.0
                else:
                    bar = args.bar
                payload = make_reading(bar, args.fault)
                payload["pump_id"] = pump
                topic = f"smartfarm/pressure/{pump}"
                client.publish(topic, json.dumps(payload))
                print(f"{topic}  {json.dumps(payload)}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
