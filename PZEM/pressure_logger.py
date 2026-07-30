#!/usr/bin/env python3
"""
pressure_logger.py — MQTT -> MariaDB logger for the water-pressure nodes.

Twin of pump_energy_logger.py, reusing the SAME config.py / .env / db_helper /
mqtt_helper. Only the topic and target table differ.

Flow:
    subscribe smartfarm/pressure/#  ->  validate pump_id against m_pump
    ->  derive is_running + status_flag  ->  buffer  ->  batch insert into
    t_water_pressure

Details:
    - reading_at: uses the payload's value if present ("YYYY-MM-DD HH:MM:SS"),
      otherwise stamps the receive time (schema: NOT NULL, no default).
    - pump_id is checked against the m_pump whitelist; refreshed periodically.
    - a failed batch is re-buffered (front, order preserved) so no data is lost.

Config comes from config.py (all env-driven). Run:
    DB_PASS=... python3 pressure_logger.py
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime

# Make sibling folders importable regardless of layout (flat here, or
# scripts/config/helpers on the pn64 server) — same shim as the pump logger.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("config", "helpers"):
    _p = os.path.join(_BASE, _d)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import mysql.connector

import config
import db_helper
from mqtt_helper import MqttSubscriber

# ---- logging --------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/pressure_logger.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("pressure_logger")

# ---- shared state ---------------------------------------------------------
_buffer = []
_lock = threading.Lock()
_last_flush = time.monotonic()

_valid_pumps = set()
_valid_lock = threading.Lock()
_last_pump_refresh = 0.0


def _reading_at(payload, received_at):
    """Prefer the firmware's timestamp; fall back to receive time."""
    ts = payload.get("reading_at")
    if ts:
        try:
            datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")   # validate format
            return ts
        except (ValueError, TypeError):
            log.warning("Bad reading_at %r, using receive time", ts)
    return received_at.strftime("%Y-%m-%d %H:%M:%S")


def refresh_pumps(force=False):
    global _last_pump_refresh
    if not force and time.monotonic() - _last_pump_refresh < config.PUMP_REFRESH_SECS:
        return
    try:
        pumps = db_helper.load_valid_pumps()
        with _valid_lock:
            _valid_pumps.clear()
            _valid_pumps.update(pumps)
        _last_pump_refresh = time.monotonic()
    except mysql.connector.Error as e:
        log.error("Could not refresh pump whitelist: %s", e)


def on_reading(topic, payload):
    received_at = datetime.now()
    pump_id = payload.get("pump_id")
    if not pump_id:
        log.warning("No pump_id on %s: %s", topic, payload)
        return

    with _valid_lock:
        known = pump_id in _valid_pumps
    if not known:
        refresh_pumps(force=True)          # maybe a newly-added pump
        with _valid_lock:
            known = pump_id in _valid_pumps
    if not known:
        log.warning("Unknown pump_id '%s' (not in m_pump), dropping", pump_id)
        return

    row = db_helper.pressure_row_from_payload(payload, _reading_at(payload, received_at))
    with _lock:
        _buffer.append(row)
    maybe_flush()


def flush():
    global _last_flush
    with _lock:
        if not _buffer:
            _last_flush = time.monotonic()
            return
        rows = _buffer[:]
        _buffer.clear()
    try:
        n = db_helper.batch_insert_pressure(rows)
        log.info("Inserted %d pressure rows", n)
    except mysql.connector.Error as e:
        log.error("Insert failed (%d rows re-buffered): %s", len(rows), e)
        with _lock:
            _buffer[:0] = rows             # put back at the front, keep order
    finally:
        _last_flush = time.monotonic()


def maybe_flush():
    with _lock:
        due = len(_buffer) >= config.BATCH_SIZE or (
            _buffer and time.monotonic() - _last_flush >= config.FLUSH_SECS
        )
    if due:
        flush()


def main():
    # Wait for the DB (systemd Restart=always will also cover a late DB).
    while True:
        try:
            refresh_pumps(force=True)
            if _valid_pumps:
                break
        except Exception as e:
            log.error("DB not ready (retry 10s): %s", e)
        time.sleep(10)

    sub = MqttSubscriber(on_reading, topic=config.MQTT_PRESSURE_TOPIC)
    while True:
        try:
            sub.connect()
            break
        except Exception as e:
            log.error("MQTT connect error (retry 10s): %s", e)
            time.sleep(10)

    sub.loop_start()
    log.info("Pressure logger running (topic %s).", config.MQTT_PRESSURE_TOPIC)
    try:
        while True:
            time.sleep(1)
            maybe_flush()
            refresh_pumps()                # periodic whitelist refresh
    except KeyboardInterrupt:
        log.info("Shutting down, final flush...")
    finally:
        flush()
        sub.loop_stop()


if __name__ == "__main__":
    main()
