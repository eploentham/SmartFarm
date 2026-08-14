# sdfm/config.py

import os
from pathlib import Path

from dotenv import load_dotenv


SDFM_PACKAGE_DIR = Path(__file__).resolve().parent
SDFM_ROOT = SDFM_PACKAGE_DIR.parent
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

# WALK DEBUG / RealSense.  Modules consume these values and never read .env
# themselves, keeping one configuration boundary for the whole application.
DEBUG_WALK_MODE = os.getenv("DEBUG_WALK_MODE", "true").lower() in {
    "1", "true", "yes", "on",
}
REALSENSE_WIDTH = int(os.getenv("REALSENSE_WIDTH", "640"))
REALSENSE_HEIGHT = int(os.getenv("REALSENSE_HEIGHT", "480"))
REALSENSE_FPS = int(os.getenv("REALSENSE_FPS", "30"))
REALSENSE_ROI_X_MIN = float(os.getenv("REALSENSE_ROI_X_MIN", "0.25"))
REALSENSE_ROI_X_MAX = float(os.getenv("REALSENSE_ROI_X_MAX", "0.75"))
REALSENSE_ROI_Y_MIN = float(os.getenv("REALSENSE_ROI_Y_MIN", "0.25"))
REALSENSE_ROI_Y_MAX = float(os.getenv("REALSENSE_ROI_Y_MAX", "0.75"))
REALSENSE_MIN_DEPTH_M = float(os.getenv("REALSENSE_MIN_DEPTH_M", "0.15"))
REALSENSE_MAX_DEPTH_M = float(os.getenv("REALSENSE_MAX_DEPTH_M", "8.0"))
OBSTACLE_BLOCKED_M = float(os.getenv("OBSTACLE_BLOCKED_M", "0.8"))
OBSTACLE_WARNING_M = float(os.getenv("OBSTACLE_WARNING_M", "1.5"))
DEPTH_MIN_VALID_RATIO = float(os.getenv("DEPTH_MIN_VALID_RATIO", "0.20"))
DEPTH_STALE_AFTER_SEC = float(os.getenv("DEPTH_STALE_AFTER_SEC", "0.50"))

# Three active-high, single-colour status LEDs (BCM numbering). Each LED must
# have its own current-limiting resistor; 330 ohms is the recommended start.
STATUS_LED_ENABLED = os.getenv("STATUS_LED_ENABLED", "true").lower() in {
    "1", "true", "yes", "on",
}
STATUS_LED_BLUE_GPIO = int(os.getenv("STATUS_LED_BLUE_GPIO", "5"))
STATUS_LED_GREEN_GPIO = int(os.getenv("STATUS_LED_GREEN_GPIO", "6"))
STATUS_LED_ORANGE_GPIO = int(os.getenv("STATUS_LED_ORANGE_GPIO", "12"))
