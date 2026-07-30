#!/usr/bin/env python3
"""
frac_label_bot.py
=================
Telegram Bot สำหรับวิเคราะห์ภาพใบพืชและฉลากสารเคมี/ชีวภัณฑ์
มุ่งเน้นการจัดการศัตรูพืชแบบ Organic 100% และ Biocontrol
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
import typing
from typing_extensions import TypedDict

import pymysql
from PIL import Image
from dotenv import load_dotenv

from google import genai
from google.genai import types

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# Load Environment Variables First!
# ---------------------------------------------------------------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

DB_HOST = os.getenv("DB_HOST", "192.168.0.253")
DB_USER = os.getenv("DB_USER", "ekapop")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "smartfarm")

IMAGE_DIR = Path(os.getenv("IMAGE_DIR", "./frac_labels"))

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing in .env file")

client = genai.Client(api_key=GEMINI_API_KEY,http_options={'api_version': 'v1'})

# ---------------------------------------------------------------------------
# Database Tables Constant
# ---------------------------------------------------------------------------
FRAC_TABLE   = "frac_fungicide"
IRAC_TABLE   = "irac_insecticide"
AI_COL       = "active_ingredient"
FRAC_CODE_COL = "frac_code"
IRAC_CODE_COL = "irac_code"

APP_TABLE    = "t_chemical_application"
APP_DATE_COL = "spray_date"
APP_FUNGI_FK = "fungicide_id"
CHAT_TABLE   = "t_telegram_chat"

logging.basicConfig(
    format="%(asctime)s  %(levelname)s  %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
log = logging.getLogger("frac_bot")

# ---------------------------------------------------------------------------
# Schema and Prompts for Organic Smart Farming
# ---------------------------------------------------------------------------
prompt = """
You are an expert plant pathologist and an advanced digital organic farming AI vision system for Durian and tropical crops.
Analyze the provided image carefully. The image could be either a diseased crop leaf OR a chemical/fertilizer product label.

Your tasks:
1. Determine if the image shows a CROPS LEAF or a PRODUCT LABEL.
2. If it is a CROPS LEAF with symptoms:
   - Identify 'disease_name' (e.g., 'Algal Leaf Spot (Cephaleuros virescens)', 'Rhizoctonia Leaf Blight', 'Anthracnose').
   - Estimate 'severity_level' ('low', 'medium', 'high') based on spot coverage.
   - Set 'disease_detected' to true and 'confidence_score' between 0.70 to 0.99 based on visibility.
   - In 'recommended_biocontrol', list strictly ORGANIC / BIOCONTROL solutions (e.g., 'Copper Hydroxide', 'Bacillus subtilis (BS)', 'Trichoderma harzianum', 'Chaetomium').
   - Provide an 'organic_management_tip' for under-canopy UAV/Rover spot-treatment spraying.
3. If it is a PRODUCT LABEL:
   - Extract the 'active_ingredient' and FRAC/IRAC code if present.

Output must strictly conform to the defined JSON schema. No extra markdown.
"""

class CropAnalysisSchema(TypedDict):
    disease_detected: bool
    disease_name: str
    confidence_score: float
    severity_level: str
    active_ingredient: str
    recommended_biocontrol: typing.List[str]
    organic_management_tip: str

# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------
def get_conn():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )

def log_chat(chat_id, worker, direction, msg_type, text=None, image_path=None, meta=None):
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
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT worker_name_th FROM m_worker WHERE telegram_chat_id = %s LIMIT 1",
                (str(chat_id),),
            )
            row = cur.fetchone()
            return row["worker_name_th"] if row else None
    except Exception as e:
        log.warning("worker lookup failed: %s", e)
        return None

def lookup_chemical(active_ingredient: str):
    if not active_ingredient:
        return None
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT id, {AI_COL} AS ai, {FRAC_CODE_COL} AS code "
                f"FROM {FRAC_TABLE} WHERE {AI_COL} = %s LIMIT 1",
                (active_ingredient,),
            )
            row = cur.fetchone()
            if row:
                return {"kind": "fungicide", "id": row["id"], "active_ingredient": row["ai"], "code": row["code"]}

            cur.execute(
                f"SELECT id, {AI_COL} AS ai, {IRAC_CODE_COL} AS code "
                f"FROM {IRAC_TABLE} WHERE {AI_COL} = %s LIMIT 1",
                (active_ingredient,),
            )
            row = cur.fetchone()
            if row:
                return {"kind": "insecticide", "id": row["id"], "active_ingredient": row["ai"], "code": row["code"]}
    except Exception as e:
        log.warning("chemical lookup failed: %s", e)
    return None

def last_fungicide_frac():
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
# Gemini Vision Analysis
# ---------------------------------------------------------------------------
def analyze_label(image_path: Path) -> dict:
    """วิเคราะห์ภาพโดยใช้ google-genai SDK ตัวใหม่"""
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/jpeg",
                ),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CropAnalysisSchema,
            ),
        )

        text = (response.text or "").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)

    except Exception as e:
        log.error("Gemini analysis error: %s", e)
        return {
            "disease_detected": False,
            "disease_name": "Uncertain / System Error",
            "confidence_score": 0.0,
            "severity_level": "low",
            "active_ingredient": "",
            "recommended_biocontrol": [],
            "organic_management_tip": f"Error: {e}"
        }

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def save_image(raw: bytes, chat_id: int) -> Path:
    day = datetime.now().strftime("%Y-%m-%d")
    folder = IMAGE_DIR / day
    folder.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S_%f")
    path = folder / f"{chat_id}_{ts}.jpg"
    path.write_bytes(raw)
    return path

def save_metadata(image_path: Path, meta: dict):
    image_path.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with open(IMAGE_DIR / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------------------
# Telegram Handlers
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = lookup_worker_name(chat_id) or update.effective_user.first_name
    log_chat(chat_id, name, "in", "command", text="/start")
    reply = (
        f"สวัสดีครับคุณ {name} 👋\n"
        f"ระบบผู้ช่วย Smart Farm พร้อมสแกนวิเคราะห์โรคพืชและฉลากสารชีวภัณฑ์แล้วครับ\n\n"
        "ถ่ายรูปใบพืชหรือฉลากสารเคมีส่งมาได้เลยครับ"
    )
    await update.message.reply_text(reply)
    log_chat(chat_id, name, "out", "bot_reply", text=reply)

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    worker = lookup_worker_name(chat_id) or update.effective_user.first_name
    caption = (update.message.caption or "").strip()

    if update.message.document:
        tg_file = await update.message.document.get_file()
        in_type = "document"
    else:
        tg_file = await update.message.photo[-1].get_file()
        in_type = "photo"

    raw = bytes(await tg_file.download_as_bytearray())

    image_path = save_image(raw, chat_id)
    log.info("Saved image %s (%d bytes)", image_path, len(raw))
    log_chat(chat_id, worker, "in", in_type, text=caption or None, image_path=image_path)
    await update.message.reply_text("📥 รับภาพเรียบร้อย กำลังวิเคราะห์ด้วย Gemini AI Vision...")

    parsed = analyze_label(image_path)
    
    disease = parsed.get("disease_name", "")
    ai = parsed.get("active_ingredient", "")
    conf = parsed.get("confidence_score", 0.0)
    severity_level = parsed.get("severity_level", "low")
    disease_detected = parsed.get("disease_detected", False)
    recommended_bio = parsed.get("recommended_biocontrol", [])
    organic_tip = parsed.get("organic_management_tip", "")

    match = lookup_chemical(ai)

    lines = [f"gemini version: {GEMINI_MODEL}", ""]
    lines.append("✅ **วิเคราะห์ภาพถ่ายสำเร็จ**")
    lines.append(f"🔍 สถานะโรค: {'พบการระบาด' if disease_detected else 'ไม่พบโรคชัดเจน / ภาพฉลาก'}")
    if disease_detected:
        lines.append(f"🦠 ชื่อโรคพืช: {disease}")
        lines.append(f"⚠️ ระดับความรุนแรง: {severity_level.upper()}")

    if ai:
        lines.append(f"🧪 สารออกฤทธิ์ที่ระบุ: {ai}")

    lines.append(f"🤖 ความมั่นใจของ AI: {conf:.0%}")

    if recommended_bio:
        lines.append("\n🌿 **การรักษาจำเพาะจุด (Spot-Treatment):**")
        for item in recommended_bio:
            lines.append(f"  • {item}")

    if organic_tip:
        lines.append(f"\n💡 **คำแนะนำการจัดการ:**\n{organic_tip}")

    rotation_warn = False
    if match:
        lines.append(f"\n🔖 ฐานข้อมูลระบบ: {match['kind']} (กลุ่มรหัส {match['code']})")
        if match["kind"] == "fungicide":
            last_code, last_date = last_fungicide_frac()
            if last_code and str(last_code) == str(match["code"]):
                rotation_warn = True
                lines.append(
                    f"\n⚠️ **เตือนความเสี่ยงดื้อยา:** การพ่นครั้งล่าสุด ({last_date}) ใช้ FRAC กลุ่ม {last_code} "
                    "การใช้สารกลุ่มเดิมซ้ำเสี่ยงต่อการดื้อยา ควรเปลี่ยนไปใช้สารชีวภัณฑ์ทดแทน"
                )

    meta = {
        "image": str(image_path),
        "received_at": datetime.now().isoformat(timespec="seconds"),
        "chat_id": chat_id,
        "worker": worker,
        "gemini": parsed,
        "db_match": match,
        "rotation_warning": rotation_warn,
        "confirmed_by_owner": False,
    }
    save_metadata(image_path, meta)

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    worker = lookup_worker_name(chat_id) or update.effective_user.first_name
    log_chat(chat_id, worker, "in", "text", text=update.message.text)
    reply = "กรุณาส่ง 'ภาพถ่ายใบพืช' หรือ 'ฉลากขวดยา' เพื่อทำการวิเคราะห์ครับ"
    await update.message.reply_text(reply)
    log_chat(chat_id, worker, "out", "bot_reply", text=reply)

def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN missing in .env")
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