"""
config.py — central configuration for the spray-recorder pipeline.

⚠️ SCHEMA-DEPENDENT SECTION is grouped at the bottom. That is the ONLY place
you must edit once you confirm the live schema with:
    SHOW CREATE TABLE t_chemical_application;
    SHOW CREATE TABLE irac_insecticide;
    SHOW CREATE TABLE frac_fungicide;
Everything above the schema section is safe / verified.
"""

import os

# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
# API key comes from environment — never hard-code it in the file.
#   export GEMINI_API_KEY="..."
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Model string is configurable because Google renames Flash models often.
# Confirm the current one in Google AI Studio before deploy.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# Retry policy for transient Gemini errors (429 rate limit / 5xx / timeout).
GEMINI_MAX_RETRIES = 3
GEMINI_BACKOFF_BASE = 2.0  # seconds; wait = base ** attempt

# ---------------------------------------------------------------------------
# Telegram (worker sends the bottle photo here; bot replies with the reading)
# ---------------------------------------------------------------------------
#   export TELEGRAM_BOT_TOKEN="123456:ABC-..."
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Which plot the spray belongs to. For now a default; later this comes from the
# detection camera's location (each camera watches a known plot).
# Valid plot_codes in m_plot: DURIAN-A1, DURIAN-A2.
DEFAULT_PLOT_ID = os.environ.get("SMARTFARM_DEFAULT_PLOT", "DURIAN-A1")

# ---------------------------------------------------------------------------
# CCTV wall (default TV view) — VIGI cameras via a go2rtc gateway
# ---------------------------------------------------------------------------
# go2rtc converts RTSP → browser-playable video. Runs on the Pi (port 1984).
GO2RTC_URL = os.environ.get("GO2RTC_URL", "http://localhost:1984")
# go2rtc stream names (defined in go2rtc.yaml). 6 cameras → 2x3 grid.
CCTV_STREAMS = ["cam1", "cam2", "cam3", "cam4", "cam5", "cam6"]
# When True, the TV pops the spray board over the wall during a spray, then
# returns to the CCTV wall. Set False for a pure CCTV wall.
SPRAY_OVERLAY = True

# ---------------------------------------------------------------------------
# Camera (pi5camera01 — dual Camera Module 3, 12MP AF)
#   Camera 0 = worker view  (owned by tv_display.py for the live stream)
#   Camera 1 = bottle label reading (owned here, on demand)
# ---------------------------------------------------------------------------
BOTTLE_CAMERA_NUM = 1            # read the bottle with camera 1
CAPTURE_DIR = "/home/ekapop/smartfarm/detectbottle/captures"
CAPTURE_SIZE = (2304, 1296)      # good balance of detail vs Gemini upload size
AF_SETTLE_SECONDS = 1.5          # wait after one-shot AF before capture
BLUR_THRESHOLD = 100.0           # Laplacian variance; below = reject as blurry
CAPTURE_RETRIES = 2              # re-focus & re-shoot up to N times if blurry

# ---------------------------------------------------------------------------
# Database (MariaDB on orchard Pi)
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("SMARTFARM_DB_HOST", "192.168.0.253")
DB_PORT = int(os.environ.get("SMARTFARM_DB_PORT", "3306"))
DB_USER = os.environ.get("SMARTFARM_DB_USER", "ekapop")
DB_PASSWORD = os.environ.get("SMARTFARM_DB_PASSWORD", "Ekartc2c51*")
DB_NAME = os.environ.get("SMARTFARM_DB_NAME", "smartfarm")

# Confidence below this → row is flagged LOW_CONFIDENCE for human review.
# MUST match v_pending_spray_review (verified: view uses < 0.80).
LOW_CONFIDENCE_THRESHOLD = 0.80

# ===========================================================================
# SCHEMA SECTION — VERIFIED against live smartfarm DB on 2026-07-06.
# ===========================================================================

# --- t_chemical_application: map logical field -> real column name ---------
# Set a value to None to make the INSERT builder skip that field.
# Verified column facts (from SHOW CREATE TABLE):
#   * id                  BIGINT AUTO_INCREMENT  (never inserted)
#   * chemical_type       ENUM('Insecticide','Fungicide','Other') NOT NULL  ← required!
#   * spray_date          DATETIME NOT NULL
#   * confidence_score    DECIMAL(3,2)
#   * detected_label_raw  VARCHAR(200)  ← raw text only, NOT full JSON
#   * evidence_image_path VARCHAR(255)
#   * reviewed_by_human   TINYINT(1) NOT NULL DEFAULT 0  ← left to DB default
COL = {
    "batch_id":             "batch_id",              # VARCHAR(36) UUID
    "plot_id":              "plot_id",               # VARCHAR(20) NOT NULL
    "tree_id":              "tree_id",               # VARCHAR(30) nullable
    "worker_id":            "worker_id",             # TINYINT unsigned -> m_worker.id
    "diagnosis_id":         "diagnosis_id",          # BIGINT FK, nullable
    "spray_date":           "spray_date",            # DATETIME NOT NULL
    "chemical_type":        "chemical_type",         # ENUM NOT NULL (required)
    "detection_source":     "detection_source",      # ENUM, we set 'AutoCamera'
    "confidence_score":     "confidence_score",      # DECIMAL(3,2)
    "detected_label_raw":   "detected_label_raw",    # VARCHAR(200) raw text
    "evidence_image_path":  "evidence_image_path",   # VARCHAR(255) photo path
    "brand_name":           "brand_name",            # VARCHAR(120)
    "concentration_percent":"concentration_percent", # DECIMAL(5,2)
    "formulation_code":     "formulation_code",      # VARCHAR(10)
    "batch_number":         "batch_number",          # VARCHAR(60)
    "expiry_date":          "expiry_date",           # DATE
    "registration_number":  "registration_number",   # VARCHAR(40)
    "notes":                "notes",                 # TEXT — full Gemini JSON audit
    "reviewed_by":          "reviewed_by",           # NULL until human approves
    "reviewed_at":          "reviewed_at",           # NULL until human approves
    # FK to catalog — exactly one is set depending on the match.
    "insecticide_id":       "insecticide_id",        # INT FK -> irac_insecticide.id
    "fungicide_id":         "fungicide_id",          # INT FK -> frac_fungicide.id
}

# Max lengths for VARCHAR columns, so long OCR output can't break the INSERT.
COL_MAXLEN = {
    "detected_label_raw": 200,
    "brand_name":         120,
    "formulation_code":    10,
    "batch_number":        60,
    "registration_number": 40,
}

# --- Catalog tables (VERIFIED): PK=id, ingredient col=active_ingredient -----
# Both tables have UNIQUE KEY uk_ai on active_ingredient.
IRAC = {
    "table":    "irac_insecticide",
    "pk":       "id",
    "name_col": "active_ingredient",
}
FRAC = {
    "table":    "frac_fungicide",
    "pk":       "id",
    "name_col": "active_ingredient",
}

# Fuzzy-match acceptance threshold (0-1). Below this we record NO FK match,
# so the row lands in v_pending_spray_review as NO_FK_MATCH.
FUZZY_MATCH_THRESHOLD = 0.82