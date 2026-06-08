"""Send chemical photo to Gemini Vision, get structured JSON back."""
import json
import logging
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

log = logging.getLogger(__name__)
genai.configure(api_key=GEMINI_API_KEY)

PROMPT = """You are an agricultural-chemical label reader.
Examine the bottle, sachet, or container in the image. Return ONLY a JSON
object (no markdown, no commentary) with these keys:

{
  "chemical_name":     "trade name as printed (e.g. 'Score 250 EC')",
  "active_ingredient": "active ingredient + concentration (e.g. 'Difenoconazole 250 g/L')",
  "chemical_type":     "one of: fungicide, insecticide, herbicide, fertilizer, biocontrol, adjuvant, other",
  "frac_code":         "FRAC group code if fungicide, else null (e.g. '3')",
  "irac_code":         "IRAC group code if insecticide, else null",
  "manufacturer":      "company name if visible",
  "confidence":        "your confidence 0.0–1.0",
  "notes":             "anything unusual or unreadable"
}

If you cannot read the label, return the JSON with null values and confidence 0.0."""

def analyze_chemical(image_path: str) -> dict:
    model = genai.GenerativeModel(GEMINI_MODEL)
    with open(image_path, 'rb') as f:
        img_bytes = f.read()
    resp = model.generate_content([
        PROMPT,
        {'mime_type': 'image/jpeg', 'data': img_bytes}
    ])
    raw = resp.text.strip()
    # strip ```json fences if present
    if raw.startswith('```'):
        raw = raw.split('```')[1].lstrip('json').strip()
    try:
        return {'parsed': json.loads(raw), 'raw': resp.text}
    except json.JSONDecodeError as e:
        log.error(f"Gemini JSON parse failed: {e}")
        return {'parsed': {}, 'raw': resp.text}