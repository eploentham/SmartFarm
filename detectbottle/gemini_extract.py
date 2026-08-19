"""
gemini_extract.py — read a pesticide bottle label with Gemini Vision.

Design notes:
  * We force STRICT JSON output (no markdown, no prose) and still defensively
    strip ``` fences before parsing, because models occasionally add them.
  * Retry only on TRANSIENT errors (rate limit / server / timeout). A bad API
    key or a hard 400 is not retried — retrying those just wastes quota.
  * The active ingredient is what matters most for the FK match, so the prompt
    puts it first and asks for it even if the brand name is unreadable.
"""

import json
import time

import google.generativeai as genai

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MAX_RETRIES,
    GEMINI_BACKOFF_BASE,
)

# Errors worth retrying (transient). We match on the exception text because the
# SDK surfaces several distinct types for these conditions.
_TRANSIENT_MARKERS = ("429", "rate", "quota", "500", "503", "deadline", "timeout", "unavailable")

# The extraction prompt. Bilingual: labels in TH are common, values may be EN.
_PROMPT = """You are reading the label of an agricultural pesticide bottle.
The label may be in Thai, English, or both.

Extract the following fields and respond with ONLY a JSON object — no
markdown, no code fences, no explanation.

{
  "brand_name": string | null,            // trade name / ชื่อการค้า
  "active_ingredients": [                  // สารออกฤทธิ์ (may be more than one)
     { "name": string, "concentration_percent": number | null }
  ],
  "formulation_code": string | null,       // e.g. EC, SC, WP, SL, WG, GR
  "registration_number": string | null,    // เลขทะเบียนวัตถุอันตราย (วอส.)
  "batch_number": string | null,           // รุ่นการผลิต / batch / lot
  "expiry_date": string | null,            // ISO "YYYY-MM-DD" if readable
  "chemical_category": string,             // "insecticide" | "fungicide" | "herbicide" | "other" | "unknown"
  "application_category": string,          // "chemical" | "biological" | "fertilizer"
  "confidence": number                     // 0.0-1.0, your confidence in this extraction
}

Rules:
- If a field is unreadable, use null (do not guess).
- Prefer the ACTIVE INGREDIENT even if the brand name is unclear.
- expiry_date: convert Thai Buddhist year (พ.ศ.) to Gregorian (ค.ศ.) by
  subtracting 543 before formatting.
- application_category: choose "biological" for microbial/antibiotic agents
  (e.g. kasugamycin, Bacillus, Trichoderma, สารชีวภัณฑ์), "fertilizer" for
  ปุ๋ย/plant nutrients, otherwise "chemical". Default to "chemical" if unsure.
"""


def _configure():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")
    genai.configure(api_key=GEMINI_API_KEY)


def _strip_json_fence(text: str) -> str:
    """Remove ```json ... ``` fences if the model added them."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]          # drop the ```json line
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    return t.strip()


def _is_transient(err: Exception) -> bool:
    msg = str(err).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def extract_label(image_path: str) -> dict:
    """
    Send the image to Gemini and return the parsed label dict.

    Returns:
        {"ok": bool, "data": dict|None, "raw": str, "error": str|None}
        `raw` is the raw model text (stored later in detected_label_raw).
    """
    _configure()
    model = genai.GenerativeModel(GEMINI_MODEL)

    # Load image bytes once.
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_part = {"mime_type": "image/jpeg", "data": image_bytes}

    last_error = None
    for attempt in range(GEMINI_MAX_RETRIES):
        try:
            response = model.generate_content(
                [_PROMPT, image_part],
                generation_config={"temperature": 0.0},  # deterministic extraction
            )
            raw = response.text or ""
            cleaned = _strip_json_fence(raw)
            data = json.loads(cleaned)
            return {"ok": True, "data": data, "raw": raw, "error": None}

        except json.JSONDecodeError as e:
            # Model returned non-JSON. Not transient — but try once more since
            # temperature=0 usually self-corrects; keep raw for debugging.
            last_error = f"JSON parse failed: {e}"
            if attempt < GEMINI_MAX_RETRIES - 1:
                time.sleep(GEMINI_BACKOFF_BASE)
                continue
            return {"ok": False, "data": None, "raw": raw, "error": last_error}

        except Exception as e:
            last_error = str(e)
            if _is_transient(e) and attempt < GEMINI_MAX_RETRIES - 1:
                wait = GEMINI_BACKOFF_BASE ** (attempt + 1)
                print(f"[gemini] transient error, backing off {wait:.1f}s: {e}")
                time.sleep(wait)
                continue
            # Non-transient (bad key, hard 400) → stop immediately.
            return {"ok": False, "data": None, "raw": "", "error": last_error}

    return {"ok": False, "data": None, "raw": "", "error": last_error}


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "captures/test_bottle.jpg"
    result = extract_label(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))