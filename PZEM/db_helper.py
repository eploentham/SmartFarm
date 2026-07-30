"""
db_helper.py — MariaDB access for the pump-energy logger.

- Loads the valid pump_code whitelist from m_pump (prevents FK 1452 on insert).
- Batch-inserts readings into t_pump_energy.

Column contract (t_pump_energy), verified against the live schema:
    pump_id (FK m_pump.pump_code), reading_at (DATETIME NOT NULL, we set it),
    voltage_v, current_a, power_w, energy_kwh, frequency_hz, power_factor,
    is_running (NOT NULL default 0). motor_temp_c / active_valves / tou_period
    are left NULL for now (no sensor / computed later).
"""

import logging
import mysql.connector

import config

log = logging.getLogger("db_helper")

# Columns we insert, in order. reading_at first (always required).
INSERT_COLUMNS = [
    "pump_id", "reading_at", "voltage_v", "current_a", "power_w",
    "energy_kwh", "frequency_hz", "power_factor", "is_running",
]
_PLACEHOLDERS = ", ".join(["%s"] * len(INSERT_COLUMNS))
INSERT_SQL = (
    f"INSERT INTO t_pump_energy ({', '.join(INSERT_COLUMNS)}) "
    f"VALUES ({_PLACEHOLDERS})"
)


def connect():
    return mysql.connector.connect(**config.db_kwargs())


def load_valid_pumps():
    """Return the set of pump_code values that exist in m_pump."""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pump_code FROM m_pump WHERE is_active = 1")
        pumps = {row[0] for row in cur.fetchall()}
        cur.close()
        log.info("Loaded %d valid pump_codes: %s", len(pumps), sorted(pumps))
        return pumps
    finally:
        conn.close()


def row_from_payload(payload, reading_at):
    """Build a tuple matching INSERT_COLUMNS from a decoded MQTT payload."""
    return (
        payload.get("pump_id"),
        reading_at,
        payload.get("voltage_v"),
        payload.get("current_a"),
        payload.get("power_w"),
        payload.get("energy_kwh"),
        payload.get("frequency_hz"),
        payload.get("power_factor"),
        int(payload.get("is_running", 0) or 0),
    )


def batch_insert(rows):
    """Insert a list of tuples. Raises on failure so the caller can re-buffer."""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.executemany(INSERT_SQL, rows)
        conn.commit()
        cur.close()
        return len(rows)
    finally:
        conn.close()


# ===========================================================================
# Water-pressure branch (t_water_pressure) — separate node/logger, same DB.
#
# Column contract, verified against the LIVE schema (2026-07-30):
#     pump_id (varchar), reading_at (DATETIME NOT NULL, we set it),
#     pressure_bar (decimal 5,2), pressure_psi (decimal 6,2),
#     voltage_raw (decimal 4,3, the transducer volts 0.5-4.5),
#     is_running (tinyint NOT NULL default 0, we derive it),
#     status_flag enum(NORMAL,LOW,HIGH,NO_FLOW,SENSOR_ERR, we derive it).
# created_at is DB-defaulted. No FK on the live table -> we still validate
# pump_id against m_pump in the logger.
# ===========================================================================
PRESSURE_INSERT_COLUMNS = [
    "pump_id", "reading_at", "pressure_bar", "pressure_psi",
    "voltage_raw", "is_running", "status_flag",
]
_P_PLACEHOLDERS = ", ".join(["%s"] * len(PRESSURE_INSERT_COLUMNS))
PRESSURE_INSERT_SQL = (
    f"INSERT INTO t_water_pressure ({', '.join(PRESSURE_INSERT_COLUMNS)}) "
    f"VALUES ({_P_PLACEHOLDERS})"
)

_PSI_PER_BAR = 14.5037738


def bar_from_voltage(v):
    """Convert transducer volts -> bar using the config calibration. None-safe."""
    if v is None:
        return None
    span = config.PRESSURE_V_MAX - config.PRESSURE_V_MIN
    if span <= 0:
        return None
    bar = (v - config.PRESSURE_V_MIN) * config.PRESSURE_FS_BAR / span
    return round(max(bar, 0.0), 2)      # clamp tiny negatives from noise at 0 bar


def classify_pressure(pressure_bar, voltage_raw):
    """Return (is_running:int, status_flag:str) from thresholds in config."""
    if (voltage_raw is None
            or voltage_raw < config.PRESSURE_V_ERR_LO
            or voltage_raw > config.PRESSURE_V_ERR_HI
            or pressure_bar is None):
        return 0, "SENSOR_ERR"
    if pressure_bar <= config.PRESSURE_NOFLOW_BAR:
        status = "NO_FLOW"
    elif pressure_bar < config.PRESSURE_MIN_BAR:
        status = "LOW"
    elif pressure_bar > config.PRESSURE_MAX_BAR:
        status = "HIGH"
    else:
        status = "NORMAL"
    is_running = 1 if pressure_bar >= config.PRESSURE_RUN_BAR else 0
    return is_running, status


def pressure_row_from_payload(payload, reading_at):
    """Build a tuple matching PRESSURE_INSERT_COLUMNS from a decoded payload.

    The firmware may send pressure_bar/pressure_psi already; if absent we
    compute them from voltage_raw so the DB is always consistent. is_running
    and status_flag are always derived here (single source of truth)."""
    voltage_raw = payload.get("voltage_raw")
    pressure_bar = payload.get("pressure_bar")
    if pressure_bar is None:
        pressure_bar = bar_from_voltage(voltage_raw)
    pressure_psi = payload.get("pressure_psi")
    if pressure_psi is None and pressure_bar is not None:
        pressure_psi = round(pressure_bar * _PSI_PER_BAR, 2)
    is_running, status_flag = classify_pressure(pressure_bar, voltage_raw)
    return (
        payload.get("pump_id"),
        reading_at,
        pressure_bar,
        pressure_psi,
        voltage_raw,
        is_running,
        status_flag,
    )


def batch_insert_pressure(rows):
    """Insert pressure rows. Raises on failure so the caller can re-buffer."""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.executemany(PRESSURE_INSERT_SQL, rows)
        conn.commit()
        cur.close()
        return len(rows)
    finally:
        conn.close()
