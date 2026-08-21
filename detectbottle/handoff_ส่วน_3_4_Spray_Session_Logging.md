# 🌿 Smartfarm — Handoff ส่วน 3+4: Spray Session Logging (พร้อมเขียนโค้ดใน Claude Code)

> วางไฟล์นี้ตอนเริ่ม chat ใหม่ใน **Claude Code** (บน PN64/Pi5) → สานต่อเขียนโค้ดได้ทันที
> Part 1 (detect worker+sprayer → Telegram) **เสร็จแล้ว** ✅ ไฟล์นี้คือส่วนต่อไป

---

## 🎯 เป้าหมาย: ระบบบันทึกการพ่นแบบ "ไม่ต้องกรอกฟอร์ม"

หลัง Part 1 ถาม "M กำลังจะพ่นยาใช่ไหม?" แล้ว → สร้างระบบ conversational workflow ที่:
1. จับคำตอบ M ทาง Telegram (**Part 3**)
2. ถ่ายภาพขวด/ซองสารเคมี วน loop → OCR → บันทึกประวัติ (**Part 4**)
3. แสดงผลบน TV 55" + พูดออกลำโพง Pi5 (ให้คนสวนคนอื่นเห็น/ได้ยินด้วย)

**ปรัชญาหลัก: "ระบบปฏิบัติการเกษตร" (Agricultural OS)**
- **Zero manual entry** — คนไม่กรอกฟอร์ม ระบบสังเกตเอง (กล้อง → YOLO → OCR → บันทึก)
- **Confirm ได้ แต่ input ไม่ได้** — Telegram ใช้แค่ยืนยัน/ตอบสั้น ไม่ใช่กรอกข้อมูลยาว
- **MQTT = transport layer** (สื่อสาร real-time), **MariaDB = source of truth** (ความจำถาวร)
- ทุก node (SKY/RVR/SCOUT) คุยผ่าน MQTT → ออกแบบให้ pub/sub ไม่ hardcode

---

## 🗺️ สถาปัตยกรรมภาพรวม

```
PN64 (สมองกลาง SFC2, 192.168.0.254)
├─ mqtt_yolo_receiver.py (Part1 ✅) ──publish──> sfc2/spray/detected
├─ 🆕 telegram_io.py     (Part3) ── poll getUpdates ↔ MQTT (I/O adapter)
│        │ publish sfc2/telegram/incoming (ข้อความดิบจาก M)
│        │ subscribe sfc2/telegram/send   (ส่งข้อความ/รูปออก)
│        └─ ⚠️ เป็น poller ตัวเดียวที่แตะ getUpdates (ห้ามมี 2 ตัว!)
│
└─ 🆕 session_manager.py (Part3+4) ── สมอง state machine
         │ subscribe sfc2/telegram/incoming, sfc2/capture/result
         │ publish  sfc2/telegram/send, sfc2/capture/request, sfc2/tv/mode, sfc2/speak
         └─ เขียน DB: t_spray_session (หัว) + t_chemical_application (รายละเอียด)

Pi5 (pi5camera01, 192.168.0.253) — มีกล้อง CSI + ลำโพง + ต่อ TV 55"
├─ 🆕 bottle_capture.py  (Part4) ── เจ้าของ Camera 1 (หันขวา, ติดตั้งเพื่องานนี้)
│        │ subscribe sfc2/capture/request → ถ่าย → reuse gemini_extract → publish result
│        └─ reuse: gemini_extract.py (OCR), record_spray.py (เขียน DB)
├─ 🆕 tv_controller       (Part4) ── subscribe sfc2/tv/mode → สลับ bottle mode ↔ cctv_wall
└─ 🆕 speaker service     (Part4) ── subscribe sfc2/speak → TTS ออกลำโพง
```

**หลักแยกชั้น (ทำตามลำดับ):**
1. **Logic layer ก่อน** — session + listener + เก็บภาพ + DB (หัวใจ)
2. **Presentation layer ทีหลัง** — TV takeover + ลำโพง (subscribe MQTT มาแสดง)

ถ้า TV/ลำโพงมีปัญหา → logic ยังทำงาน (แยก concern)

---

## 🎬 UX Flow เต็ม (conversational workflow)

```
[Part 1 ✅] เจอ worker+sprayer → Telegram "M กำลังจะพ่นยาใช่ไหม?" + เสียง
      │
      ▼ M ตอบ "yes"  ────────────────► status: pending → capturing
[เปิด session] TV 55" แย่งจอจาก cctv_wall → เข้า bottle mode
      │
      ▼
[ถ่ายขวด - LOOP] TV ครึ่งจอ = live video (เหมือนกล้องสด)
      │           รอภาพชัด → auto-shutter 📸  (GATE 1: blur check เดิม)
      │           ├─ ภาพสวย + อ่านได้ → OCR (Gemini) → เก็บใน session
      │           └─ ภาพไม่สวย/อ่านไม่ได้ → Telegram "ภาพ OK ไหม?" + เสียง
      │                                     → M ตอบ (ถ่ายใหม่ / ใช้ภาพนี้)
      │           ▼ ถ่ายขวดถัดไป... (วน loop)
      │           M พิมพ์ "หมดแล้ว" ──────► status: capturing → awaiting_plot
      ▼
[ถามแปลง] TV + ลำโพง "พ่นแปลงไหน?" → M พิมพ์ "a1"
      │                              → map a1 → DURIAN-A1 (validate กับ m_plot)
      │                              → status: awaiting_plot → awaiting_confirm
      ▼
[ยืนยัน] TV แสดง N ภาพ(ขวดที่ถ่าย) + ลำโพง "ช่วยยืนยันการใช้สารเคมี"
      │        → M พิมพ์ "ครบถ้วน" ──► status: awaiting_confirm → closed
      ▼
[บันทึก] เขียน DB: ทุกขวดผูก batch_id เดียว + plot=DURIAN-A1 + worker=M
      │        TV แสดง "พ่นสารเคมี แปลง A1 xxxxx" + ลำโพงแนะนำ (ความรู้/เตือน)
      ▼
[ปิด session] TV กลับไป cctv_wall_v2.sh
```

**หมายเหตุ lifecycle:**
- M ตอบ "no" ที่ Part 1 → status: cancelled (ไม่เปิด session)
- Timeout ทุกจุด (เช่น 30 นาทีไม่ขยับ) → status: timeout + คืนจอ cctv_wall (default safe)
- ลำโพง **พูดเฉพาะเจาะจง** ไม่พูดทุก event: แนะนำการพ่น / ความรู้ / "คราวก่อนก็พ่นไปแล้วนะ" (เตือนซ้ำ)

---

## 🗄️ Schema Changes (ทำก่อนเป็นอันดับแรก)

> กฎ MariaDB ของโปรเจกต์: InnoDB, utf8mb4_unicode_ci, bilingual comment ทุกคอลัมน์+table,
> `t_` prefix สำหรับ transaction table, FK แยกเป็น ALTER, ห้าม `--` comment ใช้ `/* */`

### 1. สร้าง `t_spray_session` (หัว — คุม lifecycle)

```sql
CREATE TABLE t_spray_session (
    session_id       BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT COMMENT 'รหัส session (PK) / session primary key',
    batch_id         VARCHAR(36)      NOT NULL COMMENT 'รหัสรอบพ่น UUID เชื่อม t_chemical_application / batch UUID linking all bottles in this session',
    worker_id        TINYINT UNSIGNED NULL COMMENT 'ผู้พ่น FK m_worker (M=2) / sprayer worker FK',
    plot_code        VARCHAR(20)      NULL COMMENT 'แปลงที่พ่น เช่น DURIAN-A1 (ใส่ตอน M ตอบแปลง) / plot code, filled after M answers',
    status           ENUM('pending','capturing','awaiting_plot','awaiting_confirm','closed','cancelled','timeout') NOT NULL DEFAULT 'pending' COMMENT 'สถานะ session lifecycle / session state machine',
    detection_conf   DECIMAL(4,3)     NULL COMMENT 'ความมั่นใจตอน Part1 เจอ / YOLO detection confidence',
    detection_image  VARCHAR(255)     NULL COMMENT 'พาธรูป annotated ตอนถาม / annotated detection image path',
    bottle_count     INT              NOT NULL DEFAULT 0 COMMENT 'จำนวนขวดที่ถ่ายใน session นี้ / bottles captured',
    confirmed_at     DATETIME         NULL COMMENT 'เวลา M ตอบ yes / time M confirmed spraying',
    closed_at        DATETIME         NULL COMMENT 'เวลาปิด session / session close time',
    created_at       TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'เวลาสร้างแถว / row creation time',
    PRIMARY KEY (session_id),
    KEY idx_batch (batch_id),
    KEY idx_status (status),
    KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='หัวรอบพ่นยา คุม lifecycle (pending→capturing→...→closed) / spray session header';
```

FK แยก:
```sql
ALTER TABLE t_spray_session
  ADD CONSTRAINT fk_spray_session_worker
  FOREIGN KEY (worker_id) REFERENCES m_worker (id);
```

### 2. เพิ่มคอลัมน์ `application_category` ใน `t_chemical_application`

```sql
ALTER TABLE t_chemical_application
  ADD COLUMN application_category ENUM('chemical','biological','fertilizer')
    NOT NULL DEFAULT 'chemical'
    COMMENT 'ประเภทใหญ่: สารเคมี/ชีวภัณฑ์/ปุ๋ย / major application category'
  AFTER chemical_type;
```

**ความสัมพันธ์:** `t_spray_session.batch_id` = `t_chemical_application.batch_id` (1 session : N ขวด)
เชื่อมผ่าน batch_id (ไม่ต้องเพิ่ม session_id FK — batch_id index อยู่แล้ว, code เดิมใช้ batch_id)

---

## 📡 MQTT Topics (prefix `sfc2/` = central brain)

| Topic | ทิศทาง | payload (JSON) | ใช้ทำอะไร |
|---|---|---|---|
| `sfc2/spray/detected` | receiver → | `{conf, image_path}` | Part1 เจอ worker+sprayer (optional publish) |
| `sfc2/telegram/incoming` | telegram_io → | `{chat_id, text, has_photo, file_id}` | ข้อความดิบจาก M |
| `sfc2/telegram/send` | → telegram_io | `{chat_id, text, image_path?}` | สั่งส่งข้อความ/รูปออก Telegram |
| `sfc2/spray/state` | session_mgr → | `{session_id, status, plot_code}` | สถานะ session เปลี่ยน (ให้ node อื่นรู้) |
| `sfc2/capture/request` | session_mgr → Pi5 | `{session_id}` | ขอถ่ายขวด 1 ใบ |
| `sfc2/capture/result` | Pi5 → session_mgr | `{session_id, image_path, data, ok}` | ผล OCR กลับมา |
| `sfc2/tv/mode` | session_mgr → Pi5 | `{mode: "bottle"\|"cctv", payload}` | สลับจอ TV |
| `sfc2/speak` | session_mgr → Pi5 | `{text, lang: "th"}` | พูดออกลำโพง |

**กฎสำคัญ:** parse คำสั่งภาษาไทย (yes/หมดแล้ว/a1/ครบถ้วน) ทำที่ **session_manager** ไม่ใช่ telegram_io เพราะความหมายขึ้นกับ state (เช่น "a1" = แปลง เฉพาะตอน `awaiting_plot`)

---

## 🔤 การ parse ภาษาไทย (สำคัญมาก — กันพิมพ์ผิดในภาคสนาม)

คนสวนพิมพ์บนมือถือ กลางแดด รีบๆ → **ห้าม match แบบเป๊ะ** ต้อง normalize + keyword หลวม

```python
import re

_TONE = re.compile(r'[\u0e48-\u0e4b]')  /* ตัดวรรณยุกต์ ่ ้ ๊ ๋ */

def normalize_th(text: str) -> str:
    t = text.strip().lower()
    t = _TONE.sub('', t)          /* "แล้ว"→"แลว", "ถ้วน"→"ถวน" */
    t = t.replace(' ', '')
    return t

def parse_command(text: str, state: str):
    """แปลข้อความตาม state ปัจจุบัน (context-dependent)"""
    t = normalize_th(text)

    /* yes/no ตอน pending */
    if state == 'pending':
        if any(k in t for k in ['ใช','yes','y','พน','ครบ','ok']): return ('YES', None)
        if any(k in t for k in ['ไม','no','ยกเลก']):               return ('NO', None)

    /* จบ loop ถ่ายขวด */
    if state == 'capturing':
        if any(k in t for k in ['หมด','จบ','เสรจ','พอ','done']):   return ('END_BOTTLES', None)

    /* ตอบแปลง — map เป็น plot_code จริง */
    if state == 'awaiting_plot':
        plot = map_plot(t)   /* "a1"/"เอ1"/"durian-a1" → "DURIAN-A1" */
        if plot: return ('PLOT', plot)

    /* ยืนยันครบถ้วน */
    if state == 'awaiting_confirm':
        if any(k in t for k in ['ครบ','ยนยน','ถวน','confirm','ok']): return ('CONFIRM', None)

    return ('UNKNOWN', text)
```

### plot mapping — query จาก DB (ไม่ hardcode)

```python
/* ข้อมูลจริงใน m_plot: plot_code = DURIAN-A1, DURIAN-A2 (ทั้งคู่ทุเรียน 10 ไร่) */
/* map: คนพิมพ์ท้าย string ("a1") → หา plot_code ที่ลงท้าย "-A1" */
def map_plot(norm_text: str) -> str | None:
    /* SELECT plot_code FROM m_plot WHERE is_active=1 */
    for code in active_plot_codes:              /* ['DURIAN-A1','DURIAN-A2'] */
        suffix = code.split('-')[-1].lower()    /* 'a1','a2' */
        if norm_text.endswith(suffix) or norm_text == code.lower():
            return code
    return None
```

⚠️ **`t_chemical_application.plot_id` เก็บ plot_code เต็ม** (`DURIAN-A1`) — ยืนยันจากข้อมูลเดิมแล้ว
(handoff เก่าเขียน `--plot A1` = ตัวอย่างผิด ของจริงต้อง `DURIAN-A1`)

---

## 📷 Camera 1 Focus (imx708 / Camera Module 3) — สำคัญต่อคุณภาพ OCR

**ปัญหา:** imx708 เป็น autofocus มีมอเตอร์ → ชอบไพล่ไปโฟกัสวัตถุเด่น/เคลื่อนไหว (เช่น ถังบนหลังคน)
ทำให้ **ขวดสารเคมีที่ต้องอ่านฉลากเบลอ** → Gemini OCR อ่านไม่ออก

### เฟสแรก (ทำก่อน — ง่าย เสถียร): FIX FOCUS

จุดถ่ายขวดตายตัว → fix focus ค่าเดียวพอ ปิด autofocus ไม่ให้ hunt

```python
from picamera2 import Picamera2
from libcamera import controls

/* หาค่าที่ดีที่สุด: วางขวดตรงจุดจริง → รัน autofocus 1 ครั้ง → จด LensPosition */
/* picam2.set_controls({"AfMode": controls.AfModeEnum.Auto}); picam2.autofocus_cycle() */
/* locked = picam2.capture_metadata()["LensPosition"]   ← จดค่านี้ */

LENS_POSITION = 3.33   /* ค่าจาก autofocus_cycle จริง (3.33 ≈ 30 ซม.) */

picam2.set_controls({
    "AfMode": controls.AfModeEnum.Manual,   /* ปิด autofocus */
    "LensPosition": LENS_POSITION,          /* dioptre = 1/ระยะเมตร */
})
```

สูตร: `LensPosition = 1 / ระยะโฟกัส(เมตร)` → 20ซม.=5.0, 30ซม.=3.33, 50ซม.=2.0, 1ม.=1.0, ∞=0.0

ประโยชน์: ขวดคมทุกครั้ง + ถ่ายเร็ว (ไม่รอ autofocus) + GATE 1 blur ผ่านบ่อยขึ้น + Pi5 ร้อนน้อยลง

### เฟสหลัง (future enhancement — ต่อยอดเมื่อ loop นิ่งแล้ว): DETECT-DRIVEN FOCUS (ROI)

**ไอเดียจริง (ROI-based):** YOLO detect เจอวัตถุ**ตรงไหนในเฟรม** → สั่งกล้อง focus **บริเวณนั้น**
ไม่ใช่แค่เลือกค่าระยะตามชนิด — แต่ใช้ **ตำแหน่ง (bounding box)** จริงมาชี้จุดโฟกัส

```
cam1 (หันขวา):  detect อะไรอยู่ → focus บริเวณ box นั้น
cam0 (เดิม):    คนสวนยกขวดมาโชว์ (ระยะไม่แน่นอน!) → detect ขวด → focus ตามขวดที่ยกมา
                *** fix focus เอาไม่อยู่เพราะยกใกล้/ไกลไม่เท่ากัน → ROI focus ชนะขาด ***
```

imx708 รองรับ **focus เจาะพื้นที่** ในตัว (`AfWindows` + `AfMetering=Windows`):
```python
from libcamera import controls

/* YOLO ให้ box ของวัตถุ (x,y,w,h) → บอกกล้อง focus แค่กรอบนั้น */
box = yolo_detect(frame)
picam2.set_controls({
    "AfMode": controls.AfModeEnum.Auto,
    "AfMetering": controls.AfMeteringEnum.Windows,
    "AfWindows": [(box.x, box.y, box.w, box.h)],   /* focus เฉพาะ ROI */
})
picam2.autofocus_cycle()   /* โฟกัสไปที่วัตถุ ไม่สนฉากหลัง */
/* → ถ่ายภาพคม → Gemini OCR */
```

**ความท้าทาย (ไก่-ไข่):** ต้อง detect เห็นวัตถุก่อนถึงรู้ ROI — แต่ YOLO ทน blur ได้พอควร
**ทางแก้ (2 จังหวะ):** เฟรมแรก focus กว้าง → detect เจอ box → focus ROI → เฟรมสองคม → OCR

**หลักการกลาง "detect-driven focus" reuse ได้ทั้งระบบ:** SKY เห็นใบเป็นโรค→focus ใบนั้น /
RVR เห็นวัชพืช→focus พื้นตรงนั้น / SCOUT เห็นแมลง→focus จุดนั้น (AI เป็นตา สั่ง hardware โฟกัส)

⚠️ ทำ **หลัง** fix focus เฟสแรกเสถียรแล้วเท่านั้น (กัน debug ปนกันระหว่าง focus กับ loop)

---

## ♻️ โค้ดเดิมที่ reuse ได้ (อยู่บน Pi5 `~/smartfarm/detectbottle/`)

| ไฟล์ | ใช้ต่อยังไง | ต้องแก้ไหม |
|---|---|---|
| `gemini_extract.py` | `extract_label(path)` → OCR ฉลาก คืน dict | ⚠️ เพิ่ม `application_category` ใน prompt (ดูล่าง) |
| `record_spray.py` | orchestrator เขียน DB | ⚠️ ต้องแก้ 2 จุด (ดูล่าง) |
| `catalog_match.py` | match FRAC/IRAC | ใช้ได้ |
| `db.py` | `get_connection()` | ใช้ได้ |
| `config.py` | `COL`, `COL_MAXLEN`, `GEMINI_*` | ใช้ได้ |
| `capture_and_read.py` | pattern ขอภาพจาก tv_display via HTTP | อ้างอิงเป็น pattern (single-cam owner) |

### `gemini_extract.py` — คืน fields (จาก prompt):
```
brand_name, active_ingredients[{name, concentration_percent}],
formulation_code, registration_number, batch_number,
expiry_date (ISO, แปลง พ.ศ.→ค.ศ. แล้ว), chemical_category, confidence
```
**ต้องเพิ่มใน prompt:** field `application_category` = "chemical"|"biological"|"fertilizer"
(เพราะ zero-entry — ให้ Gemini แยกเอง ไม่ให้คนกรอก) ถ้า Gemini ไม่มั่นใจ → default 'chemical' + ให้ review

### `record_spray.py` — ต้องแก้ 2 จุด:
1. **batch_id ต้องใช้ร่วมกันทั้ง session** — โค้ดเดิม `build_row()` gen `uuid.uuid4()` **ต่อขวด** →
   ต้องแก้ให้รับ `batch_id` เป็น parameter (session_manager สร้าง 1 ตัว ส่งให้ทุกขวด)
2. **เพิ่ม `application_category`** ใน row dict + config.COL mapping

`_predict_flag()` precedence (verified 2026-07-06): `EXPIRED → LOW_CONFIDENCE(<0.80) → NO_FK_MATCH → OK_TO_APPROVE` — คงไว้

---

## 🆕 ไฟล์ใหม่ที่ต้องเขียน

### PN64
- **`telegram_io.py`** — poll `getUpdates` (long-polling), publish incoming → MQTT, subscribe send → ส่งออก
  - ⚠️ **poller ตัวเดียวในระบบ** (1 bot token = 1 getUpdates) — ยืนยันแล้วว่าไม่มีตัวอื่น poll อยู่
  - รับรูปได้ด้วย (M ส่งรูปเข้ามา = ช่องทางที่ 2 เก็บภาพ เผื่อไม่อยู่หน้ากล้อง)
- **`session_manager.py`** — state machine, สมองกลาง, เขียน DB, สั่งทุก node ผ่าน MQTT

### Pi5
- **`bottle_capture.py`** — เจ้าของ Camera 1, subscribe capture/request → ถ่าย → gemini_extract → publish result
  - ⚠️ **1 process = 1 เจ้าของกล้อง** (CSI เปิดซ้อนไม่ได้ = device busy) Camera 1 ติดตั้งเพื่องานนี้เฉพาะ
  - ⚠️ **fix focus imx708** ตอน start (AfMode=Manual + LensPosition) — ดูหัวข้อ Camera 1 Focus
  - future: context-aware focus (detect ชนิด → ปรับระยะ) ทำเฟสหลัง
- **`tv_controller`** — subscribe tv/mode, สลับ bottle mode ↔ cctv_wall_v2.sh
- **`speaker`** — subscribe speak, TTS ไทยออกลำโพง

---

## ⚙️ Systemd services (สร้างใหม่ทั้งหมด)

ตั้งชื่อ prefix `sfc2-` ตาม convention. ทุก service **ต้องมี:**
```ini
[Service]
Environment=PYTHONUNBUFFERED=1        # log real-time (ไม่งั้น print ไม่ขึ้น)
ExecStart=/home/ekapop/venv/yolo/bin/python /path/to/script.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target            # ⚠️ ขาดไม่ได้ ไม่งั้น static เปิดเองไม่ได้
```
แก้ service แล้ว → `sudo systemctl daemon-reload && sudo systemctl restart <svc>` เสมอ

services ที่ต้องสร้าง:
- PN64: `sfc2-telegram-io`, `sfc2-session-manager`
- Pi5: `sfc2-bottle-capture`, `sfc2-tv-controller`, `sfc2-speaker`

---

## 🔑 ข้อมูลสำคัญ (verified จาก DB วันนี้)

**m_worker:**
| id | nickname | telegram_chat_id | role |
|---|---|---|---|
| 1 | พี่เอก | 8394445325 | owner |
| 2 | **M** | **8979584153** | (ผู้พ่น) |
| 3 | ทัด | (NULL) | worker |

**m_plot (แปลงที่มี):**
| plot_code | name_th | area_rai |
|---|---|---|
| DURIAN-A1 | แปลงทุเรียนหมอนทอง-หลังบ้านชัย | 10.00 |
| DURIAN-A2 | แปลงทุเรียนหมอนทอง-บ่อหน้า | 10.00 |

**t_chemical_application (32 คอลัมน์ที่มีอยู่ — สำคัญ):**
- `batch_id` varchar(36) — session UUID
- `plot_id` varchar(20) — เก็บ **DURIAN-A1** เต็ม
- `worker_id` tinyint unsigned — FK m_worker.id
- `chemical_type` ENUM('Insecticide','Fungicide','Other') — เดิม (คงไว้)
- `detection_source` ENUM('Manual','AutoCamera','DroneVision') — CSI cam = 'AutoCamera'
- `evidence_image_path`, `confidence_score`, `detected_label_raw`, `notes`(full JSON)
- `reviewed_by_human`(default 0), `reviewed_by`, `reviewed_at` — pending review flow
- `brand_name`, `concentration_percent`, `formulation_code`, `batch_number`, `expiry_date`, `registration_number`

**View:** `v_pending_spray_review` — แถวที่ยังไม่ review + review_flag

---

## 🌐 Infrastructure

- **PN64** 192.168.0.254 (Tailscale 100.97.182.35): i3-1220P iGPU, 32GB. MariaDB `smartfarm`, Mosquitto MQTT (1883, user `pop`/`pop1`), venv `/home/ekapop/venv/yolo`
- **Pi5** `pi5camera01` 192.168.0.253: dual CSI cam + **ลำโพง** + ต่อ TV 55" (HDMI-A-1) + จอ 24" (HDMI-A-2)
  - สลับ output: `wayvncctl output-set` (ไม่ใช่ config file)
  - TV 55" ตอนนี้แสดง `cctv_wall_v2.sh`
- **MariaDB users:** `claude_readonly@'%'` (SELECT), `smartfarm_rw@'%'` (SELECT/INSERT/UPDATE/DELETE)
- **MYSQL_DSN** ใน config สำหรับ connection
- **Gemini API:** free tier, billing **DISABLED** (ห้ามเปิด)

---

## 🧭 ลำดับการสร้าง (step-by-step — logic ก่อน, TV/เสียงทีหลัง)

```
STEP 1  Schema: CREATE t_spray_session + ALTER application_category → verify ใน DB
STEP 2  telegram_io.py: poll getUpdates ↔ MQTT
          เทส: M พิมพ์ → เห็น MQTT incoming | publish send → M ได้ข้อความ
          *** นี่คือ Part 3 หัวใจ = "จับ M ตอบ yes" ***
STEP 3  session_manager.py (เริ่มแค่ yes/no):
          Part1 detected → INSERT session pending
          M "yes" → capturing | M "no" → cancelled
          เทส state เปลี่ยนถูก + เขียน DB ถูก
STEP 4  bottle_capture.py (Pi5): Camera 1 owner, capture/request → gemini_extract → result
          - fix focus ก่อน: วางขวดจริง → autofocus_cycle() → จด LensPosition → set Manual
          เทสถ่าย 1 ขวด → OCR → เห็น result กลับมา (ขวดต้องคม)
STEP 5  ต่อ loop เต็ม: ถ่ายวน → "หมดแล้ว" → ถามแปลง → "ครบถ้วน"
          → record_spray (batch_id ร่วม) → close session
          เทส flow ครบ end-to-end (ยังไม่มี TV/เสียง — ดู log แทน)
STEP 6  tv_controller: bottle mode ↔ cctv_wall takeover/คืนจอ
STEP 7  speaker: TTS ไทย (พูดเฉพาะเจาะจง)
```

**หลักการทำงาน:** ทดสอบทีละ step ก่อนต่อ | one script per task | verify ก่อนเขียน | honest assessment

---

## ⚠️ Gotchas / บทเรียน (อย่าพลาดซ้ำ)

- **1 bot token = 1 getUpdates poller** — 2 ตัว poll พร้อมกัน = แย่ง update ข้อความหายแบบสุ่ม debug ยากมาก → telegram_io เป็นตัวเดียวที่ poll
- **1 process = 1 เจ้าของกล้อง CSI** — เปิดซ้อน = device busy → Camera 1 มี owner เดียว คนอื่นขอผ่าน MQTT/HTTP
- **batch_id ต้องร่วมกันทั้ง session** — record_spray เดิม gen uuid ต่อขวด ต้องแก้ให้รับ param
- **plot_id เก็บ DURIAN-A1 เต็ม** ไม่ใช่ "A1" — map ก่อน INSERT
- **parse ไทยต้อง normalize** (ตัดวรรณยุกต์ + keyword หลวม) — กันคนพิมพ์ "หมดแลว"/"ครบถวน"
- **ลำโพงพูดเฉพาะเจาะจง** ไม่พูดทุก event (กัน spam เสียง) — เหมือน throttle Telegram
- **TV takeover ต้องคืนจอ** — จบ session กลับ cctv_wall_v2.sh เสมอ (timeout ก็คืน)
- **systemd [Install] + PYTHONUNBUFFERED=1** — ขาดไม่ได้
- **CRLF line endings** — ถ้าแก้ไฟล์บน Windows: `sed -i 's/\r$//' script.py`
- **Data retention** — session + รูป captures/ ต้องมี retention policy (ทุก logging feature)
- **daemon-reload + restart** ทุกครั้งที่แก้ .service

---

## ❓ Open decisions (เคลียร์ตอนเขียนใน Claude Code)

1. **application_category detection** — แก้ Gemini prompt ให้แยก chemical/biological/fertilizer เอง (แนะนำ) vs default 'chemical' + ให้ M แก้
2. **TV takeover mechanism** — `cctv_wall_v2.sh` กับ `tv_display.py` (Flask :5000) อยู่ร่วมกันยังไงบน TV 55"? ต้องเช็คก่อนออกแบบ bottle mode (tv_display.py เดิมมี right-pane result อยู่แล้ว อาจต่อยอดได้)
3. **TTS engine** — gTTS (ไทยดี แต่ต้องเน็ต) vs pre-recorded WAV (นิ่งกว่า แต่ไม่ dynamic) vs ผสม (WAV สำหรับประโยคคงที่ + gTTS สำหรับชื่อสาร/แปลง)
4. **Timeout values** — pending รอ M กี่นาที? capturing idle กี่นาทีถึงปิด?
5. **ช่องทางที่ 2 (M ส่งรูปเข้า Telegram เอง)** — เพิ่มทีหลังหลัง CSI เสร็จ (telegram_io รับรูปได้อยู่แล้ว แค่ต่อเข้า pipeline)
6. **detect-driven focus (ROI)** (future) — YOLO ให้ box → กล้อง focus บริเวณนั้น (AfWindows) ทำหลัง fix focus นิ่ง; หลักการ reuse ได้กับ SKY/RVR/SCOUT

---

## ▶️ ประโยคเริ่ม chat ใหม่ใน Claude Code

> "ทำ Smartfarm Part 3+4 (spray session logging) ตาม handoff ที่แนบ เริ่มจาก STEP 1: สร้าง schema t_spray_session + ALTER application_category บน MariaDB smartfarm แล้ว verify ก่อนไป STEP 2 (telegram_io.py poll getUpdates ↔ MQTT). Context/สถาปัตยกรรม/flow/gotchas อยู่ในไฟล์ handoff ครบแล้ว"

**ก่อนเขียนโค้ด:** ยืนยัน schema ผ่าน (STEP 1), เช็ค detectbottle บน Pi5 ครบ, ยืนยัน TG bot token (พี่เอกเก็บเอง — ไม่วางในไฟล์ ใช้ env var)