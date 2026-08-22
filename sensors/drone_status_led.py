#!/usr/bin/env python3
"""
drone_status_led.py  —  8-LED WS2812 drone-readiness indicator for pi5-drone1

Runs ON THE PI 5. Reads flight state from the Pixhawk over MAVLink + checks the
D435i locally, and shows each subsystem's health on one LED of an 8-LED WS2812 bar.

LED map (left -> right):
  1 GPS 3D fix        2 EKF healthy       3 TFmini front (rf1)  4 TFmini up (rf2)
  5 MTF-01P range(rf3) 6 MTF-01P flow      7 D435i depth cam     8 Battery

Per-LED color: GREEN=ok  AMBER=pending/marginal  RED=fail/missing
Whole bar:     all 8 GREEN = ready to arm       PURPLE pulse = armed / mission running
               RED pulse (all) = link to Pixhawk lost

Requires (on the Pi):  uv pip install pymavlink pi5neo
Run:  python3 drone_status_led.py
"""

import sys
import math
import time
import subprocess
from pymavlink import mavutil
from pi5neo import Pi5Neo

# ---------------- Config ----------------
MAV_CONN   = '/dev/ttyACM0'     # Pixhawk link (same as rngfnd_config.py)
MAV_BAUD   = 115200
SPI_DEV    = '/dev/spidev0.0'
NUM_LEDS   = 8
SPI_KHZ    = 800
BRIGHTNESS = 0.40               # 0..1 global scale (keeps current + glare down)
STALE_S    = 3.0                # a message older than this = "missing"

# Battery thresholds (4S LiPo). Adjust to your pack.
BATT_GREEN = 14.0               # >= this = green
BATT_AMBER = 13.2               # >= this = amber, below = red

# EKF variance thresholds (lower = healthier)
EKF_GREEN  = 0.5
EKF_AMBER  = 0.8

# Base colors (pre-brightness)
GREEN  = (0, 255, 0)
AMBER  = (255, 120, 0)
RED    = (255, 0, 0)
PURPLE = (160, 0, 255)
OFF    = (0, 0, 0)

# ---------------- State ----------------
state = {}           # msg_type -> (data, timestamp)


def scale(c, b=BRIGHTNESS):
    return (int(c[0] * b), int(c[1] * b), int(c[2] * b))


def fresh(key, now):
    """True if we have a recent value for this message key."""
    if key not in state:
        return False
    return (now - state[key][1]) <= STALE_S


def get(key):
    return state[key][0] if key in state else None


# ---------------- D435i local check (not on MAVLink) ----------------
_d435_last = (0.0, False)
def d435i_ok(now):
    """Check the RealSense D435i via lsusb, cached for 5s (lsusb is slow-ish)."""
    global _d435_last
    if now - _d435_last[0] < 5.0:
        return _d435_last[1]
    ok = False
    try:
        out = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=2).stdout.lower()
        ok = ('realsense' in out) or ('8086:0b3a' in out)  # Intel RealSense D435i VID:PID
    except Exception:
        ok = False
    _d435_last = (now, ok)
    return ok


# ---------------- Subsystem evaluation -> 'green'/'amber'/'red' ----------------
def eval_gps(now):
    if not fresh('GPS_RAW_INT', now):
        return 'red'
    fix = get('GPS_RAW_INT').fix_type
    if fix >= 3:
        return 'green'
    if fix == 2:
        return 'amber'
    return 'red'


def eval_ekf(now):
    if not fresh('EKF_STATUS_REPORT', now):
        return 'red'
    e = get('EKF_STATUS_REPORT')
    worst = max(e.velocity_variance, e.pos_horiz_variance,
                e.pos_vert_variance, e.compass_variance)
    if worst < EKF_GREEN:
        return 'green'
    if worst < EKF_AMBER:
        return 'amber'
    return 'red'


def eval_rangefinder(now, orientation):
    """Green if a DISTANCE_SENSOR for this orientation is fresh and in-range."""
    key = f'DIST_{orientation}'
    if not fresh(key, now):
        return 'red'
    d = get(key)
    if d.min_distance <= d.current_distance <= d.max_distance:
        return 'green'
    return 'amber'   # sensor alive but reading out of range / no target


def eval_flow(now):
    if not fresh('OPTICAL_FLOW', now):
        return 'red'
    q = get('OPTICAL_FLOW').quality
    if q > 50:
        return 'green'
    if q > 0:
        return 'amber'
    return 'red'


def eval_battery(now):
    if not fresh('SYS_STATUS', now):
        return 'red'
    mv = get('SYS_STATUS').voltage_battery      # millivolts
    if mv in (0, 65535):
        return 'red'
    v = mv / 1000.0
    if v >= BATT_GREEN:
        return 'green'
    if v >= BATT_AMBER:
        return 'amber'
    return 'red'


COLOR_OF = {'green': GREEN, 'amber': AMBER, 'red': RED}

def subsystem_colors(now):
    """Return the 8 per-LED (r,g,b) colors in order."""
    verdicts = [
        eval_gps(now),                    # 1 GPS
        eval_ekf(now),                    # 2 EKF
        eval_rangefinder(now, 0),         # 3 TFmini front (forward)
        eval_rangefinder(now, 24),        # 4 TFmini up
        eval_rangefinder(now, 25),        # 5 MTF-01P range (down)
        eval_flow(now),                   # 6 MTF-01P optical flow
        'green' if d435i_ok(now) else 'red',  # 7 D435i depth camera
        eval_battery(now),                # 8 Battery
    ]
    return [COLOR_OF[v] for v in verdicts]


def is_armed(now):
    if not fresh('HEARTBEAT', now):
        return None            # link down
    hb = get('HEARTBEAT')
    return bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)


# ---------------- MAVLink ----------------
def connect():
    print(f"Connecting to {MAV_CONN} ...")
    m = mavutil.mavlink_connection(MAV_CONN, baud=MAV_BAUD)
    m.wait_heartbeat(timeout=15)
    print(f"Heartbeat from system {m.target_system}")
    # Ask for the messages we need, at 5 Hz.
    for msg_id in (24, 1, 193, 100, 132):     # GPS_RAW_INT, SYS_STATUS, EKF, FLOW, DIST
        try:
            m.mav.command_long_send(
                m.target_system, m.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                msg_id, 200000, 0, 0, 0, 0, 0)
        except Exception:
            pass
    return m


def drain(m, now):
    """Read all pending MAVLink messages and update state."""
    while True:
        msg = m.recv_match(blocking=False)
        if msg is None:
            break
        t = msg.get_type()
        if t == 'DISTANCE_SENSOR':
            state[f'DIST_{msg.orientation}'] = (msg, now)
        else:
            state[t] = (msg, now)


# ---------------- Render ----------------
def render(neo, colors, mode, now):
    """mode: 'normal' | 'armed' | 'linkdown'."""
    if mode == 'armed':
        # purple pulse across the whole bar
        b = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(now * 4.0))
        c = scale(PURPLE, BRIGHTNESS * b)
        neo.fill_strip(*c)
    elif mode == 'linkdown':
        # slow red pulse = no telemetry from Pixhawk
        b = 0.2 + 0.5 * (0.5 + 0.5 * math.sin(now * 2.0))
        c = scale(RED, BRIGHTNESS * b)
        neo.fill_strip(*c)
    else:
        for i, col in enumerate(colors):
            r, g, bch = scale(col)
            neo.set_led_color(i, r, g, bch)
    neo.update_strip()


# ---------------- Main loop ----------------
def main():
    neo = Pi5Neo(SPI_DEV, num_leds=NUM_LEDS, spi_speed_khz=SPI_KHZ)
    m = connect()
    print("Running status display. Ctrl+C to stop.")
    try:
        while True:
            now = time.time()
            drain(m, now)
            armed = is_armed(now)
            if armed is None:
                render(neo, None, 'linkdown', now)
            elif armed:
                render(neo, None, 'armed', now)
            else:
                render(neo, subsystem_colors(now), 'normal', now)
            time.sleep(0.05)   # ~20 Hz for smooth pulsing
    except KeyboardInterrupt:
        neo.fill_strip(*OFF)
        neo.update_strip()
        print("\nStopped, LEDs off.")


def led_test():
    """Standalone LED test — no Pixhawk needed. Checks wiring, count, colors."""
    neo = Pi5Neo(SPI_DEV, num_leds=NUM_LEDS, spi_speed_khz=SPI_KHZ)
    print("LED test: walking each LED, then full colors, then status palette.")

    # 1) Walk one green LED across the bar — confirms count + order.
    for i in range(NUM_LEDS):
        neo.fill_strip(*OFF)
        neo.set_led_color(i, *scale(GREEN))
        neo.update_strip()
        print(f"  LED {i+1}")
        time.sleep(0.3)

    # 2) Full-bar primaries — confirms color order (RGB vs GRB).
    for name, c in [('RED', RED), ('GREEN', GREEN), ('BLUE', (0, 0, 255)), ('WHITE', (255, 255, 255))]:
        print(f"  all {name}")
        neo.fill_strip(*scale(c))
        neo.update_strip()
        time.sleep(0.8)

    # 3) The actual status palette — so you see exactly how they'll look.
    for name, c in [('green=ok', GREEN), ('amber=pending', AMBER), ('red=fail', RED), ('purple=armed', PURPLE)]:
        print(f"  {name}")
        neo.fill_strip(*scale(c))
        neo.update_strip()
        time.sleep(0.8)

    neo.fill_strip(*OFF)
    neo.update_strip()
    print("Done. If RED showed as GREEN (or swapped), your board is RGB not GRB — tell me and I'll flip it.")


if __name__ == '__main__':
    if '--test' in sys.argv:
        led_test()
    else:
        main()