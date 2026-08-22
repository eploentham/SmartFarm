#!/usr/bin/env python3
"""
rngfnd_config.py  —  Pi 5 -> MAVLink -> Pixhawk rangefinder parameter tool

Runs ON THE PI 5. Connects to the Pixhawk over MAVLink and reads/writes the
ArduPilot RNGFND* parameters remotely. This is what lets you fix a wrong
rangefinder parameter from Bangkok (SSH into the Pi 5 over Tailscale, run this).

NOTE: This changes ArduPilot PARAMETERS inside the Pixhawk. It does NOT change
the TFmini sensor's own internal I2C address/mode (those need the FTDI, or the
Pi 5's I2C bus directly).

Requires: pip install pymavlink

Usage examples:
    python3 rngfnd_config.py --show                 # list current RNGFND params
    python3 rngfnd_config.py --apply                # write the desired config below
    python3 rngfnd_config.py --get RNGFND2_ADDR     # read one param
    python3 rngfnd_config.py --set RNGFND2_ADDR 17  # set one param
"""

import argparse
import sys
import time
from pymavlink import mavutil

# --- Connection string -------------------------------------------------------
# Pi 5 <-> Pixhawk link. Pick the one that matches your wiring:
#   USB cable:                '/dev/ttyACM0'   baud ignored (USB), or 115200
#   Pi GPIO UART -> TELEM:    '/dev/serial0'   baud 921600 (or your SERIALx_BAUD)
# If you run mavlink-router / MAVProxy already, use its UDP endpoint instead:
#   'udp:127.0.0.1:14550'
CONNECTION = '/dev/ttyACM0'
BAUD = 115200

# --- Desired rangefinder configuration --------------------------------------
# Edit these to match your setup, then run with --apply.
# RNGFND1 = MTF-01P (down, MAVLink) is set over its own serial link, not here.
DESIRED = {
    # RNGFND1 — Front-facing TFmini Plus (I2C @ 0x10)
    'RNGFND1_TYPE':   25,    # Benewake TFminiPlus-I2C
    'RNGFND1_ADDR':   16,    # 0x10
    'RNGFND1_ORIENT': 0,     # 0 = Forward
    'RNGFND1_MIN_CM': 10,
    'RNGFND1_MAX_CM': 600,

    # RNGFND2 — Up-facing TFmini Plus (I2C @ 0x11)
    'RNGFND2_TYPE':   25,    # Benewake TFminiPlus-I2C
    'RNGFND2_ADDR':   17,    # 0x11
    'RNGFND2_ORIENT': 24,    # 24 = Up
    'RNGFND2_MIN_CM': 10,
    'RNGFND2_MAX_CM': 600,

    # RNGFND3 — MTF-01P down rangefinder (MAVLink on GPS2/SERIAL4, not I2C)
    'RNGFND3_TYPE':   10,    # 10 = MAVLink
    'RNGFND3_ORIENT': 25,    # 25 = Down
    'RNGFND3_MIN_CM': 5,
    'RNGFND3_MAX_CM': 1200,
}


def connect():
    print(f"Connecting to {CONNECTION} ...")
    m = mavutil.mavlink_connection(CONNECTION, baud=BAUD)
    m.wait_heartbeat(timeout=15)
    print(f"Heartbeat from system {m.target_system}, component {m.target_component}")
    return m


def get_param(m, name, timeout=5):
    m.mav.param_request_read_send(
        m.target_system, m.target_component, name.encode('ascii'), -1)
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=timeout)
        if msg and msg.param_id == name:
            return msg.param_value
    return None


def set_param(m, name, value, timeout=5):
    # ArduPilot params are typed; REAL32 works for these integer values.
    m.mav.param_set_send(
        m.target_system, m.target_component,
        name.encode('ascii'), float(value),
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    # Verify by reading the value the FC echoes back.
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=timeout)
        if msg and msg.param_id == name:
            return msg.param_value
    return None


def show(m):
    print("\nCurrent rangefinder parameters:")
    for slot in (1, 2, 3):
        for suffix in ('TYPE', 'ADDR', 'ORIENT', 'MIN_CM', 'MAX_CM'):
            name = f'RNGFND{slot}_{suffix}'
            val = get_param(m, name)
            if val is not None:
                print(f"  {name:16s} = {val:g}")
    print()


def apply(m):
    print("\nApplying desired configuration...")
    # TYPE must be written first; a reboot is needed before the other
    # RNGFNDx_* fields become writable if the slot was previously unused.
    order = sorted(DESIRED.keys(), key=lambda k: (0 if k.endswith('TYPE') else 1))
    for name in order:
        want = DESIRED[name]
        got = set_param(m, name, want)
        ok = (got is not None and abs(got - want) < 0.5)
        print(f"  {name:16s} -> {want:<4} {'OK' if ok else f'FAILED (got {got})'}")
    print("\nIf any TYPE was newly set, reboot the flight controller, then run "
          "--apply again to write the remaining fields.")


ORIENT_LABEL = {0: 'Forward', 24: 'Up', 25: 'Down'}


def distance(m, seconds=6):
    """Read live DISTANCE_SENSOR messages and show the latest per orientation.
    This proves the sensors actually respond, not just that params are set."""
    # Ask the FC to stream DISTANCE_SENSOR (in case it isn't already).
    try:
        m.mav.command_long_send(
            m.target_system, m.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
            mavutil.mavlink.MAVLINK_MSG_ID_DISTANCE_SENSOR,
            100000, 0, 0, 0, 0, 0)   # 100000 us = 10 Hz
    except Exception:
        pass

    print(f"\nListening {seconds}s for DISTANCE_SENSOR messages...")
    latest = {}   # orientation -> (distance_cm, min, max)
    t0 = time.time()
    while time.time() - t0 < seconds:
        msg = m.recv_match(type='DISTANCE_SENSOR', blocking=True, timeout=seconds)
        if msg:
            latest[msg.orientation] = (msg.current_distance,
                                       msg.min_distance, msg.max_distance)

    if not latest:
        print("  No DISTANCE_SENSOR messages received.")
        print("  -> A sensor that is configured but not physically responding "
              "sends nothing. Check wiring / addresses.")
        return

    print("  Live readings:")
    for orient in sorted(latest):
        d, lo, hi = latest[orient]
        label = ORIENT_LABEL.get(orient, f'orient {orient}')
        flag = '' if lo <= d <= hi else '  <-- out of range / no target'
        print(f"    {label:8s}: {d:4d} cm   (valid {lo}-{hi}){flag}")
    print()


def reboot(m):
    print("Rebooting flight controller...")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
        0, 1, 0, 0, 0, 0, 0, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--show', action='store_true', help='list current RNGFND params')
    ap.add_argument('--apply', action='store_true', help='write DESIRED config')
    ap.add_argument('--distance', action='store_true', help='show live distances (real sensor test)')
    ap.add_argument('--reboot', action='store_true', help='reboot the Pixhawk')
    ap.add_argument('--get', metavar='PARAM', help='read one parameter')
    ap.add_argument('--set', nargs=2, metavar=('PARAM', 'VALUE'), help='set one parameter')
    args = ap.parse_args()

    m = connect()

    if args.get:
        v = get_param(m, args.get)
        print(f"{args.get} = {v}")
    elif args.set:
        name, value = args.set
        v = set_param(m, name, float(value))
        print(f"{name} -> {value}  (readback {v})")
    elif args.apply:
        apply(m)
    elif args.distance:
        distance(m)
    elif args.reboot:
        reboot(m)
    else:
        show(m)


if __name__ == '__main__':
    main()