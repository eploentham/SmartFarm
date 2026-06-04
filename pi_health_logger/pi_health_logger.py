#!/usr/bin/env python3
"""
pi_health_logger.py
Logs Raspberry Pi 5 CPU temperature and throttle state into MariaDB.
Runs continuously, sampling once per minute.
"""

import time
import subprocess
import pymysql
from pymysql import Error
import os
import psutil

# --- Configuration ---
DEVICE_ID = "rpi5_camera_01"
SAMPLE_INTERVAL_SECONDS = 60

DB_CONFIG = {
    "host": "192.168.0.253",
    "user": "ekapop",
    "password": "Ekartc2c51*",   # See note below about security
    "database": "smartfarm",
}

THERMAL_FILE = "/sys/class/thermal/thermal_zone0/temp"

def read_cpu_temp_celsius():
    """Read SoC temperature from the kernel thermal zone (no sudo needed)."""
    with open(THERMAL_FILE, "r") as f:
        millideg = int(f.read().strip())
    return round(millideg / 1000.0, 2)


def read_throttle_state():
    """Call vcgencmd to detect undervoltage or thermal throttling."""
    result = subprocess.run(
        ["vcgencmd", "get_throttled"],
        capture_output=True, text=True, check=True
    )
    # Output looks like: "throttled=0x0"
    hex_value = result.stdout.strip().split("=")[1]
    is_throttled = 1 if int(hex_value, 16) != 0 else 0
    return hex_value, is_throttled

def insert_record(conn, temp_c, throttled_hex, is_throttled):
    sql = """
        INSERT INTO t_pi_health
            (device_id, cpu_temp_c, throttled_hex, is_throttled)
        VALUES (%s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (DEVICE_ID, temp_c, throttled_hex, is_throttled))
    conn.commit()

def read_cpu_usage_pct():
    """
    Instantaneous CPU usage percent, averaged across all cores.
    NOTE: blocks for 1 second to compute the delta — this shifts the
    effective sample interval from 60s to ~61s, which is fine.
    """
    return round(psutil.cpu_percent(interval=1), 2)

def read_load_1min():
    """1-minute load average from /proc/loadavg."""
    load_1, _, _ = os.getloadavg()
    return round(load_1, 2)

def insert_record(conn, temp_c, cpu_pct, load_1, throttled_hex, is_throttled):
    sql = """
        INSERT INTO t_pi_health
            (device_id, cpu_temp_c, cpu_usage_pct, cpu_load_1min,
             throttled_hex, is_throttled)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (DEVICE_ID, temp_c, cpu_pct, load_1,
                          throttled_hex, is_throttled))
    conn.commit()

def main():
    print(f"[START] pi_health_logger device={DEVICE_ID} interval={SAMPLE_INTERVAL_SECONDS}s")
    while True:
        try:
            temp_c = read_cpu_temp_celsius()
            cpu_pct = read_cpu_usage_pct()      # blocks ~1s
            load_1 = read_load_1min()
            throttled_hex, is_throttled = read_throttle_state()

            conn = pymysql.connect(**DB_CONFIG)
            insert_record(conn, temp_c, cpu_pct, load_1, throttled_hex, is_throttled)
            conn.close()

            print(f"[OK] {DEVICE_ID} "
                  f"temp={temp_c}°C cpu={cpu_pct}% load1={load_1} "
                  f"throttled={throttled_hex}")
        except Error as e:
            print(f"[DB ERROR] {e}")
        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(SAMPLE_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()