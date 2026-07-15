"""
record_spray.py — end-to-end orchestrator for one spray-recording event.

Flow:
    capture photo  ->  Gemini extract  ->  catalog FK match  ->  INSERT row
The inserted row is left UNREVIEWED (reviewed_by / reviewed_at = NULL) so it
appears in v_pending_spray_review with the correct review_flag:
    EXPIRED / LOW_CONFIDENCE / NO_FK_MATCH / OK_TO_APPROVE.

Usage:
    python record_spray.py --plot A1 --worker 3
    python record_spray.py --plot A1 --image captures/existing.jpg   # skip camera

The INSERT is built DYNAMICALLY from config.COL: any logical field whose column
is set to None is skipped, so this works even before the full 34-column schema
is confirmed. Edit config.COL — not this file — to fix column names.
"""

import argparse
import datetime as dt
import json
import os
import uuid

from config import COL, COL_MAXLEN, CAPTURE_DIR, LOW_CONFIDENCE_THRESHOLD
from gemini_extract import extract_label
from catalog_match import match_ingredient
from db import get_connection


def _primary_ingredient(data: dict) -> tuple[str | None, float | None]:
    """Return (name, concentration_percent) of the first active ingredient."""
    ings = data.get("active_ingredients") or []
    if not ings:
        return None, None
    first = ings[0]
    return first.get("name"), first.get("concentration_percent")


def _parse_expiry(value):
    """Return a date object or None. Accepts 'YYYY-MM-DD' strings."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# Gemini chemical_category -> the NOT NULL enum('Insecticide','Fungicide','Other')
_CATEGORY_TO_ENUM = {"insecticide": "Insecticide", "fungicide": "Fungicide"}


def _truncate(value, field):
    """Trim a string to its column's max length so long OCR can't break INSERT."""
    if value is None:
        return None
    maxlen = COL_MAXLEN.get(field)
    s = str(value)
    return s[:maxlen] if maxlen else s


def build_row(data: dict, raw_json: str, match: dict, plot_id: str,
              worker_id, image_path=None, tree_id=None):
    """Assemble a {logical_field: value} dict for the INSERT."""
    ingredient_name, concentration = _primary_ingredient(data)
    confidence = round(float(data.get("confidence") or 0.0), 2)

    # chemical_type is NOT NULL — always resolve to a valid enum value.
    category = (data.get("chemical_category") or "unknown").lower()
    chemical_type = _CATEGORY_TO_ENUM.get(category, "Other")

    # detected_label_raw is VARCHAR(200): store a concise human-readable summary
    # ("brand | ingredient conc%"), NOT the full JSON. Full JSON goes to `notes`.
    raw_bits = [b for b in (data.get("brand_name"), ingredient_name) if b]
    if concentration is not None:
        raw_bits.append(f"{concentration}%")
    detected_label = _truncate(" | ".join(raw_bits) if raw_bits else None,
                               "detected_label_raw")

    row = {
        "batch_id":              str(uuid.uuid4()),
        "plot_id":               plot_id,
        "tree_id":               tree_id,
        "worker_id":             worker_id,
        "spray_date":            dt.datetime.now(),
        "chemical_type":         chemical_type,
        "detection_source":      "AutoCamera",
        "confidence_score":      confidence,
        "detected_label_raw":    detected_label,
        "evidence_image_path":   image_path,
        "brand_name":            _truncate(data.get("brand_name"), "brand_name"),
        "concentration_percent": concentration,
        "formulation_code":      _truncate(data.get("formulation_code"), "formulation_code"),
        "batch_number":          _truncate(data.get("batch_number"), "batch_number"),
        "expiry_date":           _parse_expiry(data.get("expiry_date")),
        "registration_number":   _truncate(data.get("registration_number"), "registration_number"),
        "notes":                 raw_json,   # full Gemini JSON — audit trail
        "reviewed_by":           None,       # stays NULL — pending human review
        "reviewed_at":           None,
        "insecticide_id":        None,
        "fungicide_id":          None,
    }

    # Attach the catalog FK to whichever catalog we matched.
    if match["match_type"] != "none":
        if match["catalog"] == "irac_insecticide":
            row["insecticide_id"] = match["id"]
        elif match["catalog"] == "frac_fungicide":
            row["fungicide_id"] = match["id"]

    return row, confidence


def insert_row(conn, row: dict) -> None:
    """
    Build and execute the INSERT, skipping any logical field whose real column
    name is None in config.COL (i.e. the column doesn't exist in this schema).
    """
    columns, placeholders, values = [], [], []
    for logical_field, value in row.items():
        real_col = COL.get(logical_field)
        if not real_col:
            continue  # column not present in this schema → skip
        columns.append(f"`{real_col}`")
        placeholders.append("%s")
        values.append(value)

    sql = (
        f"INSERT INTO t_chemical_application "
        f"({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
    )
    with conn.cursor() as cur:
        cur.execute(sql, values)
    conn.commit()


def _tv(fn, *args, **kwargs):
    """Push a TV-display update, but never let a display error break recording."""
    try:
        import tv_state
        getattr(tv_state, fn)(*args, **kwargs)
    except Exception as e:
        print(f"[tv] display update skipped: {e}")


def run(plot_id: str, worker_id, tree_id=None, image_path: str | None = None,
        worker_name=None):
    """Execute the full pipeline once and print a human-readable summary."""

    # 1) Get an image ------------------------------------------------------
    if image_path is None:
        from capture_bottle import capture   # imported lazily (needs picamera2)
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        image_path = os.path.join(
            CAPTURE_DIR, f"spray_{dt.datetime.now():%Y%m%d_%H%M%S}.jpg")
        cap = capture(image_path)
        if not cap["ok"]:
            print(f"⚠️  Capture warning: {cap['error']} "
                  f"(sharpness={cap['sharpness']:.1f}) — continuing anyway.")

    # Tell the TV we are now reading the label.
    _tv("set_reading", worker=worker_name)

    # 2) Gemini extract ----------------------------------------------------
    ext = extract_label(image_path)
    if not ext["ok"]:
        print(f"❌ Gemini extraction failed: {ext['error']}")
        _tv("set_error", ext["error"], image_url=image_path)
        return
    data = ext["data"]
    raw_json = json.dumps(data, ensure_ascii=False)

    # 3) Catalog FK match --------------------------------------------------
    ingredient, _ = _primary_ingredient(data)
    match = {"match_type": "none", "catalog": None, "id": None,
             "matched_name": None, "score": 0.0}

    conn = get_connection()
    try:
        if ingredient:
            match = match_ingredient(conn, ingredient,
                                     data.get("chemical_category", "unknown"))

        # 4) Build + insert ------------------------------------------------
        row, confidence = build_row(data, raw_json, match, plot_id,
                                    worker_id, image_path=image_path,
                                    tree_id=tree_id)
        insert_row(conn, row)
    finally:
        conn.close()

    # 5) Summary + push to TV ---------------------------------------------
    flag = _predict_flag(row, confidence, match)
    _tv("set_done", data, match, flag, worker=worker_name, image_url=image_path)
    print("✅ Recorded spray application")
    print(f"   batch_id        : {row['batch_id']}")
    print(f"   brand / active  : {data.get('brand_name')} / {ingredient}")
    print(f"   catalog match   : {match['match_type']} "
          f"({match.get('matched_name')}, score={match['score']:.2f})")
    print(f"   confidence      : {confidence:.2f}")
    print(f"   predicted flag  : {flag}")


def _predict_flag(row, confidence, match) -> str:
    """Mirror v_pending_spray_review precedence EXACTLY (verified 2026-07-06):
       EXPIRED -> LOW_CONFIDENCE (<0.80) -> NO_FK_MATCH -> OK_TO_APPROVE."""
    today = dt.date.today()
    if row.get("expiry_date") and row["expiry_date"] < today:
        return "EXPIRED"
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return "LOW_CONFIDENCE"
    if match["match_type"] == "none":
        return "NO_FK_MATCH"
    return "OK_TO_APPROVE"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Record one spray application.")
    ap.add_argument("--plot", required=True, help="plot_id, e.g. A1")
    ap.add_argument("--worker", required=True, help="worker_id (FK to m_worker)")
    ap.add_argument("--tree", default=None, help="tree_id (optional)")
    ap.add_argument("--image", default=None,
                    help="use an existing image instead of capturing")
    args = ap.parse_args()

    run(args.plot, args.worker, tree_id=args.tree, image_path=args.image)
