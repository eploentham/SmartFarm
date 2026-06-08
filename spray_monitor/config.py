"""Central configuration — load once, import everywhere."""
import os
from dotenv import load_dotenv

load_dotenv()

# Database
DB_CONFIG = {
    'host':     os.getenv('DB_HOST', 'localhost'),
    'user':     os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'smartfarm'),
}

# Telegram
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
TG_CHAT_ID   = os.getenv('TG_CHAT_ID')
TG_ALLOWED_WORKERS = os.getenv('TG_ALLOWED_WORKERS', 'M').split(',')

# Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL   = 'gemini-2.0-flash'

# Cameras (Picamera2 indices)
CAM1_INDEX = 0   # detection camera (worker + tank)
CAM2_INDEX = 1   # chemical bottle camera

# TV display window (HDMI2 = second display)
TV_X_OFFSET = int(os.getenv('TV_X_OFFSET', '1920'))
TV_Y_OFFSET = int(os.getenv('TV_Y_OFFSET', '0'))
TV_WIDTH    = int(os.getenv('TV_WIDTH', '960'))
TV_HEIGHT   = int(os.getenv('TV_HEIGHT', '1080'))

# Detection thresholds
YOLO_CONF             = 0.45     # min confidence for person/backpack
TRIGGER_HOLD_SECONDS  = 3.0      # both labels must persist this long
COOLDOWN_SECONDS      = 300      # 5 min between detections to avoid spam
TELEGRAM_TIMEOUT_S    = 120      # wait up to 2 min for YES reply
PHOTO_READY_TIMEOUT_S = 120      # wait up to 2 min for worker to hold up bottle

# Paths
CAPTURE_DIR = '/home/ekapop/smartfarm/spray_monitor/captures'
LOG_DIR     = '/home/ekapop/smartfarm/spray_monitor/logs'