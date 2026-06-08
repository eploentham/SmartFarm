"""Telegram send + long-poll for YES/NO reply."""
import requests
import time
import logging
from config import TG_BOT_TOKEN, TG_CHAT_ID, TELEGRAM_TIMEOUT_S

log  = logging.getLogger(__name__)
BASE = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"

def send_message(text: str) -> int | None:
    """Send a message; returns message_id or None."""
    try:
        r = requests.post(f"{BASE}/sendMessage",
                          json={'chat_id': TG_CHAT_ID, 'text': text},
                          timeout=10)
        return r.json().get('result', {}).get('message_id')
    except Exception as e:
        log.error(f"telegram send failed: {e}")
        return None

def send_photo(photo_path: str, caption: str = "") -> bool:
    try:
        with open(photo_path, 'rb') as f:
            r = requests.post(f"{BASE}/sendPhoto",
                              data={'chat_id': TG_CHAT_ID, 'caption': caption},
                              files={'photo': f},
                              timeout=30)
        return r.ok
    except Exception as e:
        log.error(f"telegram photo failed: {e}")
        return False

def wait_for_yes_no(prompt_time: float, timeout: int = TELEGRAM_TIMEOUT_S) -> str | None:
    """Long-poll getUpdates until we see a yes/no reply newer than prompt_time.
       Returns 'yes', 'no', or None on timeout."""
    deadline = time.time() + timeout
    offset = None
    while time.time() < deadline:
        params = {'timeout': 25}
        if offset is not None:
            params['offset'] = offset
        try:
            r = requests.get(f"{BASE}/getUpdates", params=params, timeout=30).json()
        except Exception as e:
            log.warning(f"poll error: {e}")
            time.sleep(2)
            continue

        for upd in r.get('result', []):
            offset = upd['update_id'] + 1
            msg = upd.get('message') or {}
            if msg.get('date', 0) < prompt_time:
                continue                                  # ignore old messages
            text = (msg.get('text') or '').strip().lower()
            if text in ('yes', 'y', 'ใช่', '/yes'):
                return 'yes'
            if text in ('no', 'n', 'ไม่', '/no', 'cancel'):
                return 'no'
    return None