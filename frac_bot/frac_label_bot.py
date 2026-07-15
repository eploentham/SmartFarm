#!/usr/bin/env python3
"""
frac_label_bot.py
=================
New Telegram bot for the chemical spray logging system (replaces the
deleted bot). Two jobs only:

  1. KEEP PICTURE  -> every photo a worker sends is saved to disk
                      (original kept) + a metadata record.
  2. FRAC ANALYSIS -> Gemini reads the label, we look up the FRAC code
                      in the smartfarm DB, and warn if the same FRAC
                      group was used last time (resistance risk).

It does NOT write a spray record to t_chemical_application yet.
That insert needs the final data model, which we agreed to do later.
For now: save + read + analyze + report. (See the TODO near the bottom.)

Token, API key, and DB settings come from a .env file so you never
hard-code secrets. If a bot is ever deleted again, change only TELEGRAM_TOKEN
in .env and restart -- no code change.

Run:
    pip install python-telegram-bot google-generativeai pymysql pillow python-dotenv
    python frac_label_bot.py
"""

import os
import io
import json
import logging
from datetime import datetime
from pathlib import Path
import typing
import typing
from urllib import response

import pymysql
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# Config (from .env -- see .env.example)
# ---------------------------------------------------------------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")            # from BotFather
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")  # set to your current Flash model

DB_HOST = os.getenv("DB_HOST", "192.168.0.253")        # RPi 4 (MariaDB)
DB_USER = os.getenv("DB_USER", "logger")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "smartfarm")

# Where pictures are kept. On the home computer this is your dataset base.
IMAGE_DIR = Path(os.getenv("IMAGE_DIR", "./frac_labels"))

# ---------------------------------------------------------------------------
# IMPORTANT: verify these column names against your real tables.
# Run in MariaDB:  DESCRIBE frac_fungicide;  DESCRIBE irac_insecticide;
#                  DESCRIBE t_chemical_application;
# Adjust the constants below if your columns are named differently.
# ---------------------------------------------------------------------------
FRAC_TABLE  = "frac_fungicide"
IRAC_TABLE  = "irac_insecticide"
AI_COL      = "active_ingredient"   # UNIQUE in both master tables -> natural key
FRAC_CODE_COL = "frac_code"         # FRAC group code column in frac_fungicide
IRAC_CODE_COL = "irac_code"         # IRAC group code column in irac_insecticide

APP_TABLE   = "t_chemical_application"
APP_DATE_COL = "spray_date"
APP_FUNGI_FK = "fungicide_id"       # FK -> frac_fungicide.id
CHAT_TABLE  = "t_telegram_chat"          # NEW: chat log table
# ---------------------------------------------------------------------------
logging.basicConfig(    format="%(asctime)s  %(levelname)s  %(message)s",    level=logging.INFO,)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
log = logging.getLogger("frac_bot")

prompt = """
You are an expert plant pathologist and an advanced agricultural AI vision system.
Analyze the provided crop leaf image in detail.

Your tasks:
1. Examine the leaf for any signs of plant diseases (e.g., Algal Leaf Spot, Fungal infections like Mildew/Rust/Anthracnose, Bacterial Leaf Blight, or Viral infections).
2. If a disease is detected:
   - Identify the specific 'disease_name' (e.g., 'Anthracnose', 'Powdery Mildew'). If multiple, name the primary one. If healthy, set it to "None".
   - Assess the 'severity_level' ('low', 'medium', 'high') based on the percentage of leaf area affected.
3. In the 'recommended_chemical' field, provide the most effective treatment based on the disease type and severity:
   - If 'disease_detected' is false, set it to "None".
   - If 'severity_level' is low, prefer organic solutions (e.g., 'Bacillus subtilis (BS)', 'Trichoderma', or 'Neem oil').
   - If 'severity_level' is medium or high, recommend the standard chemical active ingredient for that specific disease class:
     * For Algal Leaf Spot: 'Copper Oxychloride' or 'Copper Hydroxide'
     * For Fungal leaf spots/anthracnose: 'Difenoconazole', 'Azoxystrobin', or 'Mancozeb'
     * For Powdery/Downy Mildew: 'Metalaxyl' or 'Hexaconazole'
     * For Bacterial diseases: 'Copper compounds' or 'Kasugamycin'
     * For Pests/Mites: Suggest appropriate insecticides/acaricides.

Note: Output must strictly conform to the defined JSON schema. Do not include any conversational text or markdown code blocks in your final output.
"""
class CropAnalysisSchema(typing.TypedDict):
    disease_detected: bool
    disease_name: str
    confidence_score: float
    severity_level: str
    recommended_chemical: typing.List[str]  # เพิ่มฟิลด์นี้สำหรับแนะนำสารเคมี/สารชีวภัณฑ์

# ---------------------------------------------------------------------------
# Database helpers (all read-only for now; fail soft so the picture is
# always kept even if the DB is unreachable)
# ---------------------------------------------------------------------------
def get_conn():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )
def log_chat(chat_id, worker, direction, msg_type,
             text=None, image_path=None, meta=None):
    """NEW: store one chat event into t_telegram_chat. Never crashes the bot."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {CHAT_TABLE} "
                "(chat_id, worker, direction, msg_type, text_content, image_path, meta) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    str(chat_id), worker, direction, msg_type, text,
                    str(image_path) if image_path else None,
                    json.dumps(meta, ensure_ascii=False) if meta else None,
                ),
            )
            conn.commit()
    except Exception as e:
        log.warning("chat log failed: %s", e)
def lookup_worker_name(chat_id: int):
    """Return the worker name from m_worker, or None if not registered."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM m_worker WHERE telegram_chat_id = %s LIMIT 1",
                (str(chat_id),),
            )
            row = cur.fetchone()
            return row["name"] if row else None
    except Exception as e:
        log.warning("worker lookup failed: %s", e)
        return None

def lookup_chemical(active_ingredient: str):
    """
    Look up an active ingredient in the FRAC (fungicide) and IRAC (insecticide)
    master tables. Returns dict or None.
    """
    if not active_ingredient:
        return None
    try:
        with get_conn() as conn, conn.cursor() as cur:
            # try fungicide first
            cur.execute(
                f"SELECT id, {AI_COL} AS ai, {FRAC_CODE_COL} AS code "
                f"FROM {FRAC_TABLE} WHERE {AI_COL} = %s LIMIT 1",
                (active_ingredient,),
            )
            row = cur.fetchone()
            if row:
                return {"kind": "fungicide", "id": row["id"],
                        "active_ingredient": row["ai"], "code": row["code"]}

            # then insecticide
            cur.execute(
                f"SELECT id, {AI_COL} AS ai, {IRAC_CODE_COL} AS code "
                f"FROM {IRAC_TABLE} WHERE {AI_COL} = %s LIMIT 1",
                (active_ingredient,),
            )
            row = cur.fetchone()
            if row:
                return {"kind": "insecticide", "id": row["id"],
                        "active_ingredient": row["ai"], "code": row["code"]}
    except Exception as e:
        log.warning("chemical lookup failed: %s", e)
    return None


def last_fungicide_frac():
    """Return the FRAC code of the most recent fungicide spray, or None."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT f.{FRAC_CODE_COL} AS code, t.{APP_DATE_COL} AS d "
                f"FROM {APP_TABLE} t "
                f"JOIN {FRAC_TABLE} f ON t.{APP_FUNGI_FK} = f.id "
                f"WHERE t.{APP_FUNGI_FK} IS NOT NULL "
                f"ORDER BY t.{APP_DATE_COL} DESC LIMIT 1"
            )
            row = cur.fetchone()
            return (row["code"], row["d"]) if row else (None, None)
    except Exception as e:
        log.warning("last frac lookup failed: %s", e)
        return (None, None)


# ---------------------------------------------------------------------------
# Gemini label reader
# ---------------------------------------------------------------------------
def analyze_label(image_path: Path) -> dict:
    """Send the saved image to Gemini and parse the JSON result."""
    genai.configure(api_key=GEMINI_API_KEY)
    #model = genai.GenerativeModel(GEMINI_MODEL)
    # 3. ล็อกโครงสร้างลงในโมเดลผ่าน generation_config
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": CropAnalysisSchema, # บังคับใช้โครงสร้างที่เราตั้งไว้ด้านบน
        }
    )
    img = Image.open(image_path)
    resp = model.generate_content([prompt, img])
    print("AI Analysis Result:", resp)
    text = (resp.text or "").strip()
    # strip ```json fences if present
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Gemini did not return valid JSON: %s", text[:200])
        return {"disease_detected": False, "disease_name": "", "confidence_score": 0.0, "severity_level": "low", "recommended_chemical": []}



# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def save_image(raw: bytes, chat_id: int) -> Path:
    """Keep the picture: save original bytes into a dated folder."""
    day = datetime.now().strftime("%Y-%m-%d")
    folder = IMAGE_DIR / day
    folder.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S_%f")
    path = folder / f"{chat_id}_{ts}.jpg"
    path.write_bytes(raw)
    return path


def save_metadata(image_path: Path, meta: dict):
    """Write one .json sidecar + append to a master log.jsonl."""
    image_path.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with open(IMAGE_DIR / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = lookup_worker_name(chat_id) or update.effective_user.first_name
    log_chat(chat_id, name, "in", "command", text="/start")
    reply = (
        f"สวัสดีครับ {name} 👋\n"
        f"chat_id ของคุณคือ: {chat_id}\n\n"
        "ถ่ายรูปใบพืชแล้วส่งมาได้เลยครับ "
        "(ส่งเป็น 'ไฟล์' จะชัดที่สุด) ผมจะวิเคราะห์ให้"
    )
    await update.message.reply_text(reply)
    log_chat(chat_id, name, "out", "bot_reply", text=reply) 

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    worker = lookup_worker_name(chat_id) or update.effective_user.first_name
    caption = (update.message.caption or "").strip()
    # Get the file: prefer document (full-res) over compressed photo
    if update.message.document:
        tg_file = await update.message.document.get_file()
        in_type = "document"
    else:
        tg_file = await update.message.photo[-1].get_file()  # largest size
        in_type = "photo"

    raw = bytes(await tg_file.download_as_bytearray())

    # 1) KEEP PICTURE
    image_path = save_image(raw, chat_id)
    log.info("saved %s (%d bytes)", image_path, len(raw))
    log_chat(chat_id, worker, "in", in_type, text=caption or None, image_path=image_path)
    await update.message.reply_text("📥 รับรูปแล้ว กำลังวิเคราะห์ภาพ...")

    # 2) FRAC ANALYSIS
    try:
        parsed = analyze_label(image_path)
        print("AI Analysis Result:", parsed)
    except Exception as e:
        log.error("Gemini failed: %s", e)
        await update.message.reply_text(
            "⚠️ อ่านฉลากไม่สำเร็จ แต่เก็บรูปไว้แล้วครับ ลองถ่ายให้ชัดขึ้นแล้วส่งใหม่"
        )
        return

    disease = parsed.get("disease_name", "")
    ai = parsed.get("active_ingredient", "")
    conf = parsed.get("confidence_score", 0.0)
    severity_level = parsed.get("severity_level", "low")
    disease_detected = parsed.get("disease_detected", False)
    recommended_chemical = parsed.get("recommended_chemical", [])

    match = lookup_chemical(ai)

    # Build the reply
    lines = ["✅ เก็บรูปเรียบร้อย", ""]
    lines.append(f"📦 ภาพที่ส่ง: {disease or '(อ่านไม่ออก)'}")
    lines.append(f"🧪 ตรวจพบโรค: {disease_detected or '(อ่านไม่ออก)'}")
    lines.append(f"🧪 สารออกฤทธิ์: {ai or '(อ่านไม่ออก)'}")
    lines.append(f"🤖 Gemini (มั่นใจ {conf:.0%})")
    lines.append(f"⚠️ ระดับความรุนแรง: {severity_level}")
    if recommended_chemical:
        lines.append(f"💊 แนะนำสารเคมี/ชีวภัณฑ์: {', '.join(recommended_chemical)}")
    rotation_warn = False
    if match:
        lines.append(f"🔖 พบในฐานข้อมูล: {match['kind']} | รหัส {match['code']}")
        if match["kind"] == "fungicide":
            last_code, last_date = last_fungicide_frac()
            if last_code and str(last_code) == str(match["code"]):
                rotation_warn = True
                lines.append("")
                lines.append(
                    f"⚠️ เตือน: ครั้งที่แล้ว ({last_date}) ก็ใช้ FRAC {last_code} เหมือนกัน\n"
                    "ใช้กลุ่มเดิมซ้ำ = เสี่ยงเชื้อดื้อยา ควรสลับไปกลุ่ม FRAC อื่น"
                )
            elif last_code:
                lines.append(f"🔄 ครั้งที่แล้วใช้ FRAC {last_code} -> ครั้งนี้ต่างกลุ่ม OK")
    else:
        lines.append("❓ ยังไม่พบสารนี้ในฐานข้อมูล (สินค้าใหม่?) เก็บไว้รอเจ้าของตรวจ")

    lines.append("")
    lines.append("📝 ผลนี้ยังต้องให้เจ้าของยืนยันก่อนบันทึกจริง")

    # metadata record (the dataset value lives here)
    meta = {
        "image": str(image_path),
        "received_at": datetime.now().isoformat(timespec="seconds"),
        "chat_id": chat_id,
        "worker": worker,
        "gemini": parsed,
        "db_match": match,
        "rotation_warning": rotation_warn,
        "confirmed_by_owner": False,   # set True later from the review step
    }
    save_metadata(image_path, meta)

    await update.message.reply_text("\n".join(lines))

    # ----------------------------------------------------------------------
    # TODO (later, when the data model is finalized):
    #   On owner confirmation, INSERT into t_chemical_application using
    #   match['id'] as fungicide_id / insecticide_id + spray_date + plot_id.
    #   Left out on purpose for now -- this MVP only saves + analyzes.
    # ----------------------------------------------------------------------


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    worker = lookup_worker_name(chat_id) or update.effective_user.first_name
    log_chat(chat_id, worker, "in", "text", text=update.message.text)
    reply = "ส่ง 'รูปฉลากขวดยา' มาได้เลยครับ (พิมพ์ /start เพื่อดูวิธีใช้)"
    await update.message.reply_text(reply)
    log_chat(chat_id, worker, "out", "bot_reply", text=reply)



def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN missing. Put it in .env")
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))

    log.info("FRAC label bot started. Waiting for pictures...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
