#!/usr/bin/env python3
# session_manager.py — รันบน PN64 (สมองกลาง SFC2)
# ---------------------------------------------------------------------------
# Part 3+4: state machine ของรอบพ่นยา (conversational workflow)
#
#   subscribe:
#     sfc2/spray/detected     {conf, image_path}          ← Part1 เจอ worker+sprayer
#     sfc2/telegram/incoming  {chat_id, text, has_photo, file_id, ...}  ← M ตอบ
#     sfc2/capture/result     {session_id, image_path, data, ok}        ← Pi5 OCR (STEP4)
#   publish:
#     sfc2/telegram/send      {chat_id, text, image_path?}   → ส่งข้อความหา M
#     sfc2/capture/request    {session_id}                   → ขอ Pi5 ถ่ายขวด (STEP4)
#     sfc2/spray/state        {session_id, status, plot_code}  → บอก node อื่น
#     sfc2/tv/mode, sfc2/speak                                 → STEP6/7
#
#   DB (source of truth):
#     t_spray_session         หัว lifecycle (ไฟล์นี้เขียน)
#     t_chemical_application   รายละเอียดต่อขวด (เขียนตอน close ผ่าน record_spray — STEP5)
#
# ขอบเขตไฟล์นี้ตอนนี้: STEP 3 (yes/no) ทำครบ + วาง scaffold STEP4/5 ไว้ชัดเจน
#   [STEP4] = ต้องมี bottle_capture.py (Pi5) ก่อนถึงจะ loop ถ่ายจริง
#   [STEP5] = ต่อ record_spray (batch_id ร่วม) ตอน close session
# ---------------------------------------------------------------------------

import json
import os
import re
import threading
import time
import uuid
import datetime as dt

import mysql.connector
import paho.mqtt.client as mqtt

# ---------- config ----------
BROKER, PORT = "192.168.0.254", 1883
MQTT_USER, MQTT_PASS = "pop", "pop1"

T_DETECTED = "sfc2/spray/detected"
T_INCOMING = "sfc2/telegram/incoming"
T_RESULT   = "sfc2/capture/result"
T_SEND     = "sfc2/telegram/send"
T_CAPTURE  = "sfc2/capture/request"
T_STATE    = "sfc2/spray/state"
T_TV       = "sfc2/tv/mode"
T_SPEAK    = "sfc2/speak"

# DB — session_manager รันบน PN64 เดียวกับ MariaDB → default localhost
#   ใช้ user ที่ INSERT/UPDATE ได้ (smartfarm_rw); password จาก env เท่านั้น
DB_CONFIG = {
    "host":     os.environ.get("SMARTFARM_DB_HOST", "127.0.0.1"),
    "port":     int(os.environ.get("SMARTFARM_DB_PORT", "3306")),
    "user":     os.environ.get("SMARTFARM_DB_USER", "smartfarm_rw"),
    "password": os.environ.get("SMARTFARM_DB_PASSWORD", ""),
    "database": os.environ.get("SMARTFARM_DB_NAME", "smartfarm"),
    "charset":  "utf8mb4",
    "collation": "utf8mb4_general_ci",
}

# ผู้พ่น default = M (id 2). chat_id ดึงจาก m_worker.telegram_chat_id
SPRAY_WORKER_ID = int(os.environ.get("SPRAY_WORKER_ID", "2"))

# lifecycle timeout — session ที่ค้าง open เกินนี้ → timeout (คืนจอ TV, ปิด)
SESSION_TIMEOUT_MIN = int(os.environ.get("SPRAY_TIMEOUT_MIN", "30"))

# สถานะที่ยังเปิดอยู่ (รับคำสั่งต่อได้) vs ปิดแล้ว
OPEN_STATES = ("pending", "capturing", "awaiting_plot", "awaiting_confirm")
# ----------------------------


# ===========================================================================
# DB layer
# ===========================================================================
def db_conn():
    return mysql.connector.connect(**DB_CONFIG)


def worker_info(worker_id: int):
    """คืน (telegram_chat_id, nickname) ของ worker — (None, None) ถ้าไม่มี."""
    with db_conn() as c, c.cursor() as cur:
        cur.execute("SELECT telegram_chat_id, nickname FROM m_worker WHERE id = %s",
                    (worker_id,))
        row = cur.fetchone()
        return (row[0], row[1]) if row else (None, None)


def worker_chat_id(worker_id: int):
    """คืน telegram_chat_id ของ worker (None ถ้าไม่มี)."""
    return worker_info(worker_id)[0]


def worker_by_chat(chat_id):
    """map chat_id (คนพิมพ์เข้ามา) → worker_id (None ถ้าไม่รู้จัก)."""
    with db_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id FROM m_worker WHERE telegram_chat_id = %s", (chat_id,))
        row = cur.fetchone()
        return row[0] if row else None


def active_plot_codes():
    """คืน list plot_code ที่ is_active=1 (ไม่ hardcode)."""
    with db_conn() as c, c.cursor() as cur:
        cur.execute("SELECT plot_code FROM m_plot WHERE is_active = 1")
        return [r[0] for r in cur.fetchall()]


def create_session(batch_id, worker_id, conf, image_path):
    """INSERT session ใหม่ (status=pending, confirmed_at=now). คืน session_id."""
    with db_conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO t_spray_session "
            "(batch_id, worker_id, status, detection_conf, detection_image) "
            "VALUES (%s, %s, 'pending', %s, %s)",
            (batch_id, worker_id, conf, image_path),
        )
        c.commit()
        return cur.lastrowid


def get_session(session_id):
    """คืนแถว session ตาม id (dict หรือ None)."""
    with db_conn() as c, c.cursor(dictionary=True) as cur:
        cur.execute(
            "SELECT session_id, batch_id, worker_id, plot_code, status, bottle_count "
            "FROM t_spray_session WHERE session_id = %s", (session_id,))
        return cur.fetchone()


def find_active_session(worker_id):
    """หา session ที่ยังเปิดอยู่ล่าสุดของ worker คนนี้ (dict หรือ None)."""
    placeholders = ", ".join(["%s"] * len(OPEN_STATES))
    with db_conn() as c, c.cursor(dictionary=True) as cur:
        cur.execute(
            f"SELECT session_id, batch_id, worker_id, plot_code, status, bottle_count "
            f"FROM t_spray_session "
            f"WHERE worker_id = %s AND status IN ({placeholders}) "
            f"ORDER BY session_id DESC LIMIT 1",
            (worker_id, *OPEN_STATES),
        )
        return cur.fetchone()


def update_session(session_id, status=None, **fields):
    """UPDATE status + คอลัมน์อื่น. ตั้ง closed_at อัตโนมัติเมื่อเข้า state ปิด."""
    sets, vals = [], []
    if status is not None:
        sets.append("status = %s")
        vals.append(status)
        if status in ("closed", "cancelled", "timeout"):
            sets.append("closed_at = %s")
            vals.append(dt.datetime.now())
    for k, v in fields.items():
        sets.append(f"{k} = %s")
        vals.append(v)
    if not sets:
        return
    vals.append(session_id)
    with db_conn() as c, c.cursor() as cur:
        cur.execute(f"UPDATE t_spray_session SET {', '.join(sets)} WHERE session_id = %s", vals)
        c.commit()


def sweep_timeouts():
    """ปิด session ที่ค้าง open เกิน SESSION_TIMEOUT_MIN → timeout. คืน list ที่ปิด."""
    placeholders = ", ".join(["%s"] * len(OPEN_STATES))
    cutoff = dt.datetime.now() - dt.timedelta(minutes=SESSION_TIMEOUT_MIN)
    with db_conn() as c, c.cursor(dictionary=True) as cur:
        cur.execute(
            f"SELECT session_id, worker_id FROM t_spray_session "
            f"WHERE status IN ({placeholders}) AND created_at < %s",
            (*OPEN_STATES, cutoff),
        )
        stale = cur.fetchall()
        for s in stale:
            cur.execute(
                "UPDATE t_spray_session SET status='timeout', closed_at=%s WHERE session_id=%s",
                (dt.datetime.now(), s["session_id"]),
            )
        c.commit()
    return stale


# ===========================================================================
# Thai command parsing — normalize + keyword หลวม (กันพิมพ์ผิดกลางแดด)
# ===========================================================================
# ตัด Thai combining marks ที่คนมัก "หล่น" ตอนพิมพ์เร็ว:
#   ั (0E31), สระบน/ล่าง+พินทุ ิ-ฺ (0E34-0E3A), ไม้ไต่คู้+วรรณยุกต์+การันต์ ็-๎ (0E47-0E4E)
# ทำให้ "เสร็จ"→"เสรจ", "ยืนยัน"→"ยนยน", "ครบถ้วน"→"ครบถวน", "ยกเลิก"→"ยกเลก"
# (สระหน้า เ แ โ ใ ไ และพยัญชนะ เป็น base char ไม่ถูกตัด → ความหมายยังอ่านออก)
_COMB = re.compile(r"[ัิ-ฺ็-๎]")


def normalize_th(text: str) -> str:
    t = (text or "").strip().lower()
    t = _COMB.sub("", t)          # ตัดเครื่องหมายประกอบ (ดูคอมเมนต์ด้านบน)
    t = t.replace(" ", "")
    return t


def map_plot(norm_text: str, plots):
    """'a1'/'เอ1'/'durian-a1' → 'DURIAN-A1' (match ท้าย string กับ plot จริง)."""
    for code in plots:
        suffix = code.split("-")[-1].lower()      # 'a1','a2','a3'
        if norm_text.endswith(suffix) or norm_text == code.lower():
            return code
    return None


def parse_command(text: str, state: str, plots):
    """แปลข้อความตาม state ปัจจุบัน (ความหมายขึ้นกับ state)."""
    t = normalize_th(text)
    if state == "pending":
        if any(k in t for k in ["ใช", "yes", "y", "พน", "ครบ", "ok"]):
            return ("YES", None)
        if any(k in t for k in ["ไม", "no", "ยกเลก"]):
            return ("NO", None)
    elif state == "capturing":
        if any(k in t for k in ["หมด", "จบ", "เสรจ", "พอ", "done"]):
            return ("END_BOTTLES", None)
        if any(k in t for k in ["ถาย", "ขวด", "next", "snap", "capture"]):
            return ("CAPTURE", None)
    elif state == "awaiting_plot":
        plot = map_plot(t, plots)
        if plot:
            return ("PLOT", plot)
    elif state == "awaiting_confirm":
        if any(k in t for k in ["ครบ", "ยนยน", "ถวน", "confirm", "ok"]):
            return ("CONFIRM", None)
    return ("UNKNOWN", text)


# ===========================================================================
# Session manager — state machine
# ===========================================================================
class SessionManager:
    def __init__(self, client):
        self.client = client
        # เก็บผล OCR ต่อ session ระหว่าง capturing (in-memory)
        #   session_id -> [{"image_path":..., "data":{...}}, ...]
        #   [STEP5] ใช้ list นี้เขียน t_chemical_application ตอน close (ผูก batch_id เดียว)
        self.bottles = {}

    # ---- helpers -------------------------------------------------------
    def send(self, chat_id, text, image_path=None):
        payload = {"chat_id": chat_id, "text": text}
        if image_path:
            payload["image_path"] = image_path
        self.client.publish(T_SEND, json.dumps(payload, ensure_ascii=False))

    def announce_state(self, session_id, status, plot_code=None):
        self.client.publish(T_STATE, json.dumps(
            {"session_id": session_id, "status": status, "plot_code": plot_code}))
        print(f"[state] session {session_id} → {status}")

    # ---- sfc2/spray/detected → เปิด session ----------------------------
    def on_detected(self, conf, image_path):
        chat_id, nickname = worker_info(SPRAY_WORKER_ID)
        if chat_id is None:
            print(f"[detected] worker {SPRAY_WORKER_ID} ไม่มี chat_id — ข้าม")
            return
        name = nickname or "คุณ"
        existing = find_active_session(SPRAY_WORKER_ID)
        if existing:
            # มี session เปิดอยู่แล้ว → ไม่เปิดซ้ำ (กัน Part1 ยิงถี่)
            print(f"[detected] session {existing['session_id']} ยังเปิด "
                  f"({existing['status']}) — ไม่เปิดใหม่")
            return
        batch_id = str(uuid.uuid4())
        session_id = create_session(batch_id, SPRAY_WORKER_ID, conf, image_path)
        self.announce_state(session_id, "pending")
        self.send(chat_id, f"🌿 {name} กำลังจะพ่นยาใช่ไหม? ตอบ 'ใช่' หรือ 'ไม่'")
        print(f"[detected] เปิด session {session_id} batch={batch_id} conf={conf}")

    # ---- sfc2/telegram/incoming → เดิน state machine -------------------
    def on_incoming(self, chat_id, text, has_photo, file_id):
        worker_id = worker_by_chat(chat_id)
        if worker_id is None:
            print(f"[in] chat {chat_id} ไม่รู้จัก — ข้าม")
            return
        sess = find_active_session(worker_id)
        if not sess:
            print(f"[in] worker {worker_id} ไม่มี session เปิด — ข้าม '{text[:30]}'")
            return

        state = sess["status"]
        plots = active_plot_codes()
        cmd, arg = parse_command(text, state, plots)
        print(f"[in] session {sess['session_id']} state={state} cmd={cmd} arg={arg}")

        handler = {
            "pending":          self._h_pending,
            "capturing":        self._h_capturing,
            "awaiting_plot":    self._h_awaiting_plot,
            "awaiting_confirm": self._h_awaiting_confirm,
        }.get(state)
        if handler:
            handler(sess, chat_id, cmd, arg, has_photo, file_id)

    def _h_pending(self, sess, chat_id, cmd, arg, has_photo, file_id):
        sid = sess["session_id"]
        if cmd == "YES":
            update_session(sid, status="capturing", confirmed_at=dt.datetime.now())
            self.bottles[sid] = []
            self.announce_state(sid, "capturing")
            self.send(chat_id, "📸 เริ่มบันทึกขวด — พิมพ์ 'ถ่าย' (หรือส่งรูป) "
                               "เพื่อบันทึกทีละใบ, ครบแล้วพิมพ์ 'หมดแล้ว'")
        elif cmd == "NO":
            update_session(sid, status="cancelled")
            self.announce_state(sid, "cancelled")
            self.send(chat_id, "ยกเลิกแล้ว ไม่บันทึกรอบพ่นนี้ ✅")
        else:
            self.send(chat_id, "ตอบ 'ใช่' ถ้ากำลังจะพ่น หรือ 'ไม่' ถ้าไม่พ่น")

    def _h_capturing(self, sess, chat_id, cmd, arg, has_photo, file_id):
        sid = sess["session_id"]
        if cmd == "END_BOTTLES":
            if sess["bottle_count"] == 0:
                self.send(chat_id, "ยังไม่มีขวดที่บันทึกเลย ถ่ายอย่างน้อย 1 ใบก่อนนะ")
                return
            update_session(sid, status="awaiting_plot")
            self.announce_state(sid, "awaiting_plot")
            plots = ", ".join(c.split("-")[-1] for c in active_plot_codes())
            self.send(chat_id, f"พ่นแปลงไหน? ({plots})")
        elif cmd == "CAPTURE" or has_photo:
            # trigger ถ่าย 1 ใบ — Pi5 (bottle_capture.py) subscribe topic นี้
            #   (has_photo = ช่องทางสำรอง M ส่งรูปเอง; mock จะไม่ใช้รูปนั้น แค่ trigger)
            self.client.publish(T_CAPTURE, json.dumps({"session_id": sid}))
            self.send(chat_id, "📸 กำลังบันทึกขวด…")
        else:
            self.send(chat_id, "พิมพ์ 'ถ่าย' เพื่อบันทึกขวด (หรือส่งรูป), เสร็จแล้วพิมพ์ 'หมดแล้ว'")

    def _h_awaiting_plot(self, sess, chat_id, cmd, arg, has_photo, file_id):
        sid = sess["session_id"]
        if cmd == "PLOT":
            update_session(sid, status="awaiting_confirm", plot_code=arg)
            self.announce_state(sid, "awaiting_confirm", plot_code=arg)
            self.send(chat_id, f"แปลง {arg} ✅ ช่วยยืนยันการใช้สารเคมี พิมพ์ 'ครบถ้วน'")
        else:
            plots = ", ".join(c.split("-")[-1] for c in active_plot_codes())
            self.send(chat_id, f"ไม่รู้จักแปลงนี้ ลองพิมพ์: {plots}")

    def _h_awaiting_confirm(self, sess, chat_id, cmd, arg, has_photo, file_id):
        sid = sess["session_id"]
        if cmd == "CONFIRM":
            # [STEP5] เขียน t_chemical_application ทุกขวด ผูก batch_id เดียว
            #   record_spray.run(..., batch_id=sess['batch_id'], plot=sess['plot_code'])
            # ตอนนี้ (STEP3) แค่ปิด session + แจ้ง — ยังไม่เขียนรายละเอียดขวด
            update_session(sid, status="closed")
            self.announce_state(sid, "closed", plot_code=sess["plot_code"])
            self.send(chat_id,
                      f"บันทึกแล้ว ✅ แปลง {sess['plot_code']} "
                      f"({sess['bottle_count']} ขวด) [STEP5: เขียน DB รายขวด]")
        else:
            self.send(chat_id, "พิมพ์ 'ครบถ้วน' เพื่อยืนยัน หรือ 'ไม่' เพื่อยกเลิก")

    # ---- sfc2/capture/result → นับขวด (STEP4/5) ------------------------
    def on_capture_result(self, session_id, image_path, data, ok):
        sess = get_session(session_id)
        if not sess:
            print(f"[result] ไม่พบ session {session_id} — ข้าม")
            return
        chat_id = worker_chat_id(sess["worker_id"])
        if sess["status"] != "capturing":
            print(f"[result] session {session_id} ไม่ได้อยู่ capturing ({sess['status']}) — ข้าม")
            return

        if not ok:
            # ภาพเบลอ/อ่านไม่ได้ → ให้ถ่ายใหม่ (GATE 1/2)
            if chat_id:
                self.send(chat_id, "⚠️ ภาพไม่ชัด/อ่านฉลากไม่ได้ — พิมพ์ 'ถ่าย' ลองใหม่นะ")
            return

        self.bottles.setdefault(session_id, []).append(
            {"image_path": image_path, "data": data})
        n = len(self.bottles[session_id])
        update_session(session_id, bottle_count=n)

        d = data or {}
        brand = d.get("brand_name") or "ไม่ทราบยี่ห้อ"
        cat = d.get("application_category") or "chemical"
        ings = d.get("active_ingredients") or []
        ing = ings[0].get("name") if ings and ings[0].get("name") else "-"
        if chat_id:
            self.send(chat_id, f"✅ ขวดที่ {n}: {brand} ({ing}, {cat}) — "
                               f"ถ่ายต่อพิมพ์ 'ถ่าย' หรือ 'หมดแล้ว' เมื่อครบ")
        print(f"[result] session {session_id} ขวด {n}: {brand}")


# ===========================================================================
# MQTT wiring
# ===========================================================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("เชื่อม MQTT สำเร็จ")
        for t in (T_DETECTED, T_INCOMING, T_RESULT):
            client.subscribe(t)
    else:
        print(f"เชื่อม MQTT ไม่สำเร็จ rc={rc}")


def on_message(client, userdata, msg):
    mgr = userdata
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        print(f"[mqtt] payload ไม่ใช่ JSON บน {msg.topic}: {e}")
        return
    try:
        if msg.topic == T_DETECTED:
            mgr.on_detected(data.get("conf"), data.get("image_path"))
        elif msg.topic == T_INCOMING:
            mgr.on_incoming(data.get("chat_id"), data.get("text", ""),
                            data.get("has_photo", False), data.get("file_id"))
        elif msg.topic == T_RESULT:
            mgr.on_capture_result(data.get("session_id"), data.get("image_path"),
                                  data.get("data"), data.get("ok"))
    except Exception as e:
        # อย่าให้ error รายเหตุการณ์ทำ service ตาย
        print(f"[mqtt] handler error บน {msg.topic}: {e}")


def timeout_worker(mgr):
    """background: กวาด session ค้างเป็น timeout + แจ้ง/คืนจอ."""
    while True:
        time.sleep(60)
        try:
            for s in sweep_timeouts():
                mgr.announce_state(s["session_id"], "timeout")
                chat = worker_chat_id(s["worker_id"])
                if chat:
                    mgr.send(chat, "⏱️ หมดเวลา ปิดรอบพ่นอัตโนมัติ (คืนจอ TV)")
                # [STEP6] คืนจอ cctv_wall
                mgr.client.publish(T_TV, json.dumps({"mode": "cctv"}))
                print(f"[timeout] ปิด session {s['session_id']}")
        except Exception as e:
            print(f"[timeout] sweep error: {e}")


def main():
    if not DB_CONFIG["password"]:
        raise SystemExit("❌ ไม่มี SMARTFARM_DB_PASSWORD ใน env — ตั้งค่าก่อนรัน")

    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    mgr = SessionManager(client)
    client.user_data_set(mgr)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)

    threading.Thread(target=timeout_worker, args=(mgr,), daemon=True).start()
    print(f"session_manager พร้อม (worker={SPRAY_WORKER_ID}, timeout={SESSION_TIMEOUT_MIN}m)")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nปิด session_manager")
        client.disconnect()


if __name__ == "__main__":
    main()
