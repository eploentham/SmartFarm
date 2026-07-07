"""
capture_and_read.py — trigger a bottle capture on tv_display, then read it.

SINGLE-CAMERA DESIGN: tv_display.py owns camera 0, so we do NOT open the camera
here. We ask tv_display to take the high-res still (POST /capture), then run
Gemini on the returned photo and push the result to the TV right pane.

Prerequisite: tv_display.py must already be running.

Usage:
    export GEMINI_API_KEY="..."
    python capture_and_read.py
    python capture_and_read.py --worker M
"""

import argparse
import json
import urllib.request
from datetime import date

from config import LOW_CONFIDENCE_THRESHOLD
from gemini_extract import extract_label
import tv_state

TV_URL = "http://localhost:5000"


def _trigger_capture(worker):
    """Ask tv_display to take a high-res still; returns its JSON response."""
    req = urllib.request.Request(f"{TV_URL}/capture?worker={worker}", method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _flag(conf, data):
    """Lightweight review flag WITHOUT the catalog/DB (test mode only).
    The real NO_FK_MATCH check runs in record_spray.py."""
    exp = data.get("expiry_date")
    try:
        if exp and date.fromisoformat(str(exp)[:10]) < date.today():
            return "EXPIRED"
    except (ValueError, TypeError):
        pass
    if (conf or 0) < LOW_CONFIDENCE_THRESHOLD:
        return "LOW_CONFIDENCE"
    return "OK_TO_APPROVE"


def _readable(data):
    """True if Gemini actually found a bottle/label (not an empty frame).
    A sharp photo of the worker's shirt would return brand=None, no ingredient."""
    ings = data.get("active_ingredients") or []
    has_ingredient = bool(ings and ings[0].get("name"))
    has_brand = bool(data.get("brand_name"))
    conf = data.get("confidence") or 0
    return has_ingredient or (has_brand and conf >= 0.4)


def main(worker="M"):
    # 1) Tell the TV we're reading, then ask tv_display to capture ---------
    print("📷 Asking tv_display to capture from camera 0 ...")
    tv_state.set_reading(worker=worker)
    try:
        cap = _trigger_capture(worker)
    except Exception as e:
        print(f"❌ Could not reach tv_display /capture: {e}")
        print("   Is tv_display.py running on port 5000?")
        tv_state.set_error("capture trigger failed")
        return

    if not cap.get("ok"):
        print(f"❌ Capture failed: {cap.get('error')}")
        tv_state.set_error(cap.get("error", "capture failed"))
        return

    path = cap["path"]
    print(f"   saved: {path}")
    print(f"   sharpness={cap['sharpness']:.1f}  blurry={cap['blurry']}  "
          f"attempts={cap.get('attempts')}")

    # GATE 1 — blur (local, free): don't waste a Gemini call on a blurry shot.
    if cap["blurry"]:
        print("🔄 Image blurry after retries — asking worker to try again.")
        tv_state.set_retry("ภาพไม่ชัด — ถือขวดให้นิ่ง",
                           "Image blurry — hold the bottle steady",
                           worker=worker, image_url=path)
        return

    # 2) Send to Gemini ---------------------------------------------------
    print("🤖 Sending to Gemini ...")
    ext = extract_label(path)
    if not ext["ok"]:
        print(f"❌ Gemini failed: {ext['error']}")
        tv_state.set_error(ext["error"], image_url=path)
        return

    data = ext["data"]
    print("✅ Gemini result:")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    # GATE 2 — readability: sharp photo but no bottle/label in frame.
    if not _readable(data):
        print("🔄 No readable bottle/label — asking worker to reposition.")
        tv_state.set_retry("ไม่เห็นขวด / อ่านฉลากไม่ได้",
                           "Bottle/label not visible — reposition",
                           worker=worker, image_url=path)
        return

    # 3) Push to the TV right pane (test flag, no catalog match) -----------
    flag = _flag(data.get("confidence"), data)
    tv_state.set_done(data, {"match_type": "none"}, flag,
                      worker=worker, image_url=path)
    print(f"📺 TV updated (test flag = {flag}; catalog match runs in record_spray.py)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", default="M")
    args = ap.parse_args()
    main(worker=args.worker)
