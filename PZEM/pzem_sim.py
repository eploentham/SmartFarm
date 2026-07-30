#!/usr/bin/env python3
"""
pzem_sim.py — fake PZEM pump node for pipeline testing (no hardware).

Publishes the same JSON contract as the ESP32 firmware to
    smartfarm/pump/{pump_code}
so you can exercise pump_energy_logger.py -> MariaDB end to end.

Payload fields match t_pump_energy:
    pump_id, voltage_v, current_a, power_w, energy_kwh, frequency_hz,
    power_factor, is_running, reading_at ("YYYY-MM-DD HH:MM:SS")

Examples:
    # WS-01 both pumps idle, publish every 2s
    python pzem_sim.py --pump WS1-P1 --pump WS1-P2

    # simulate a 1500W kettle (I~6.8A, PF~0.99) on WS1-P1
    python pzem_sim.py --pump WS1-P1 --watts 1500

    # duty-cycle several pumps on/off
    python pzem_sim.py --pump WS2-P1 --pump WS2-P2 --watts 2200 --duty
"""

import os
import json
import time
import random
import argparse
from datetime import datetime

import paho.mqtt.client as mqtt

MAINS_V   = 220.0
FREQ_HZ   = 50.0
RUN_WATTS = 200.0     # is_running threshold, matches firmware/DB


def make_reading(state, watts, jitter):
    v = MAINS_V + random.uniform(-jitter, jitter)
    if watts <= 0:
        current, power, pf = 0.0, 0.0, 0.0
    else:
        pf = 0.99
        power = watts + random.uniform(-watts * 0.01, watts * 0.01)
        current = power / (v * pf)
        state["energy"] += power * state["dt"] / 3600.0 / 1000.0   # kWh

    return {
        "voltage_v":    round(v, 1),
        "current_a":    round(current, 3),
        "power_w":      round(power, 1),
        "energy_kwh":   round(state["energy"], 3),
        "frequency_hz": round(FREQ_HZ + random.uniform(-0.1, 0.1), 1),
        "power_factor": round(pf, 2),
        "is_running":   1 if power > RUN_WATTS else 0,
        "reading_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    ap = argparse.ArgumentParser(description="Simulated PZEM pump publisher")
    ap.add_argument("--pump", action="append", required=True,
                    help="pump_code (repeat for multiple pumps)")
    ap.add_argument("--broker", default=os.getenv("MQTT_BROKER", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--watts", type=float, default=0.0, help="load in watts (0=idle). Kettle ~1500")
    ap.add_argument("--jitter", type=float, default=0.5, help="+/- volts of noise")
    ap.add_argument("--duty", action="store_true",
                    help="cycle each pump on/off (~30s on, ~15s off)")
    args = ap.parse_args()

    client = mqtt.Client()
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()
    print(f"Publishing to {args.broker}:{args.port} every {args.interval}s for {args.pump}")

    states = {p: {"energy": round(random.uniform(0, 5), 3),
                  "dt": args.interval,
                  "phase": random.uniform(0, 1)} for p in args.pump}

    try:
        while True:
            for pump in args.pump:
                st = states[pump]
                if args.duty:
                    t = (time.time() / 45.0 + st["phase"]) % 1.0
                    watts = args.watts if t < 0.66 else 0.0
                else:
                    watts = args.watts
                payload = make_reading(st, watts, args.jitter)
                payload["pump_id"] = pump
                topic = f"smartfarm/pump/{pump}"
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
