"""
config.py — central config for the PZEM pump-energy pipeline.

All values come from environment variables so the same code runs on the bench
(localhost) and in production (mini-PC .254) without edits. Defaults target the
bench setup.
"""

import os


def _load_dotenv():
    """Minimal .env loader (no external deps). Loads KEY=VALUE lines into the
    environment without overriding vars already set in the real environment.
    Looks for .env at the project root (parent of this file's dir), then next
    to this file, then in the current dir. Must run before the getenv() calls."""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, ".env"),                    # next to config.py (config/.env)
                 os.path.join(os.path.dirname(here), ".env"),   # project root
                 os.path.join(os.getcwd(), ".env")):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        print(f"config: loaded env from {path}")
        return
    print("config: no .env found (using defaults / real env)")


_load_dotenv()

# ---- MQTT -----------------------------------------------------------------
MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")   # prod: 192.168.0.254
MQTT_PORT   = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC  = os.getenv("MQTT_TOPIC", "smartfarm/pump/#")
# Pressure transducer nodes publish on their own topic tree (separate logger):
MQTT_PRESSURE_TOPIC = os.getenv("MQTT_PRESSURE_TOPIC", "smartfarm/pressure/#")
MQTT_USER   = os.getenv("MQTT_USER", "")              # prod: pop / pop1
MQTT_PASS   = os.getenv("MQTT_PASS", "")

# ---- MariaDB --------------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")           # prod: 192.168.0.254
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "smartfarm")
DB_USER = os.getenv("DB_USER", "smartfarm_writer")    # INSERT-capable user
DB_PASS = os.getenv("DB_PASS", "")

# ---- Pressure sensor ------------------------------------------------------
# Transducer: ratiometric 0.5-4.5V = 0..full-scale. Conversion lives here so
# the logger can (re)compute bar/psi if the firmware sends only voltage_raw.
PRESSURE_FS_BAR  = float(os.getenv("PRESSURE_FS_BAR", "10.0"))   # full scale (bar) = 145 psi
PRESSURE_V_MIN   = float(os.getenv("PRESSURE_V_MIN", "0.5"))     # sensor V at 0 bar
PRESSURE_V_MAX   = float(os.getenv("PRESSURE_V_MAX", "4.5"))     # sensor V at full scale
# status_flag thresholds (bar) — tune per farm without re-flashing the ESP32:
PRESSURE_NOFLOW_BAR = float(os.getenv("PRESSURE_NOFLOW_BAR", "0.2"))  # <= this => NO_FLOW
PRESSURE_MIN_BAR    = float(os.getenv("PRESSURE_MIN_BAR", "1.0"))     # < this  => LOW
PRESSURE_MAX_BAR    = float(os.getenv("PRESSURE_MAX_BAR", "8.0"))     # > this  => HIGH
PRESSURE_RUN_BAR    = float(os.getenv("PRESSURE_RUN_BAR", "0.5"))     # >= this => is_running=1
# voltage_raw outside this band => broken wire / short => SENSOR_ERR:
PRESSURE_V_ERR_LO = float(os.getenv("PRESSURE_V_ERR_LO", "0.35"))
PRESSURE_V_ERR_HI = float(os.getenv("PRESSURE_V_ERR_HI", "4.70"))

# ---- Logger behaviour -----------------------------------------------------
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))       # flush after N rows...
FLUSH_SECS = int(os.getenv("FLUSH_SECS", "10"))       # ...or after N seconds
# Reload the valid pump_code whitelist from m_pump this often (seconds):
PUMP_REFRESH_SECS = int(os.getenv("PUMP_REFRESH_SECS", "300"))


def db_kwargs():
    return {
        "host": DB_HOST, "port": DB_PORT, "database": DB_NAME,
        "user": DB_USER, "password": DB_PASS,
    }
