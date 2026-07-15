"""
tv_state.py — shared state between the record pipeline and the TV display.

The record pipeline WRITES the latest Gemini reading here; the TV display
(tv_display.py) READS it to update the right-hand pane. Decoupling through one
JSON file keeps the two processes independent — if either restarts, the other
is unaffected (important for orchard reliability).

Writes are ATOMIC (temp file + os.replace) so the display never sees a
half-written file.
"""

import json
import os
import tempfile
from datetime import datetime

STATE_PATH = os.environ.get(
    "TV_STATE_PATH", "/home/pi/smartfarm/detectbottle/tv_state.json")

# The four render states the right pane understands.
IDLE = "idle"        # waiting, nothing happening
READING = "reading"  # bottle captured, Gemini is processing
DONE = "done"        # extraction finished, show the data
ERROR = "error"      # extraction failed, show raw photo + message


def write_state(state: dict) -> None:
    """Atomically write the display state to disk."""
    state = {**state, "updated_at": datetime.now().isoformat(timespec="seconds")}
    folder = os.path.dirname(STATE_PATH)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)          # atomic on POSIX
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def read_state() -> dict:
    """Return the current state, or an idle placeholder if none exists."""
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"status": IDLE}


# --- Convenience helpers the record pipeline calls -------------------------

def set_idle():
    write_state({"status": IDLE})


def set_reading(worker=None):
    write_state({"status": READING, "worker": worker})


def set_done(data: dict, match: dict, review_flag: str,
             worker=None, image_url=None):
    """Push a finished Gemini reading to the TV right pane."""
    ings = data.get("active_ingredients") or [{}]
    write_state({
        "status": DONE,
        "worker": worker,
        "image_url": image_url,
        "brand_name": data.get("brand_name"),
        "active_ingredient": ings[0].get("name"),
        "concentration_percent": ings[0].get("concentration_percent"),
        "chemical_type": data.get("chemical_category"),
        "catalog_group": _group_str(match),
        "expiry_date": data.get("expiry_date"),
        "confidence": data.get("confidence"),
        "review_flag": review_flag,
    })


def set_error(message, image_url=None):
    write_state({"status": ERROR, "message": message, "image_url": image_url})


def _group_str(match):
    if not match or match.get("match_type") == "none":
        return None
    cat = "IRAC" if match.get("catalog") == "irac_insecticide" else "FRAC"
    return f"{cat} — {match.get('matched_name')}"
