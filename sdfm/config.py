# sdfm/config.py

from pathlib import Path

from dotenv import load_dotenv


SDFM_ROOT = Path(__file__).resolve().parent
ENV_FILE = SDFM_ROOT / ".env"

load_dotenv(ENV_FILE)

# Vehicle
VEHICLE_NAME = "DR01"

# Pixhawk
MAVLINK_BAUD = 115200

# Safety
HEARTBEAT_TIMEOUT_SEC = 5.0

# Battery
MIN_BATTERY_VOLTAGE = 14.0
MIN_BATTERY_REMAINING = 30