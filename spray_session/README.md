# SFC2 Spray Session (Part 3+4)

ระบบบันทึกการพ่นแบบ conversational (zero manual entry) — สมองกลางอยู่ PN64.
สเปกเต็มดู `detectbottle/handoff_spray_part3_4_ready.md`

```
Part1 (YOLO เจอ worker+sprayer)
   └─ publish sfc2/spray/detected ─┐
                                   ▼
telegram_io.py ◄──sfc2/telegram/send──  session_manager.py ──sfc2/capture/request──► bottle_capture.py (Pi5, STEP4)
   │  getUpdates                          │ state machine + DB
   └──sfc2/telegram/incoming────────────► │ t_spray_session (หัว) + t_chemical_application (ขวด)
```

## ไฟล์
| ไฟล์ | เครื่อง | หน้าที่ | STEP |
|---|---|---|---|
| `../sql/create_t_spray_session.sql` | PN64 (DB) | schema | 1 ✅ |
| `telegram_io.py` | PN64 | poller เดียว ↔ MQTT | 2 ✅ |
| `session_manager.py` | PN64 | state machine + DB | 3 ✅ (yes/no) · 4/5 scaffold |
| `bottle_capture.py` | Pi5 | ถ่าย+OCR | 4 ⏳ |
| tv_controller / speaker | Pi5 | จอ/เสียง | 6/7 ⏳ |

## Deploy (PN64)
convention: repo เก็บ source ใน `spray_session/` แต่ **script รันจริงอยู่ `~/smartfarm/scripts/`**
(เหมือน detect_worker / PZEM) — .service ชี้ ExecStart ไป `scripts/`

```bash
# 1) schema (ครั้งเดียว)
mysql -u smartfarm_rw -p smartfarm < ~/smartfarm/sql/create_t_spray_session.sql

# 2) copy code เข้า scripts/ + ลบ CRLF (ไฟล์มาจาก Windows)
cp ~/smartfarm/spray_session/telegram_io.py ~/smartfarm/spray_session/session_manager.py ~/smartfarm/scripts/
sed -i 's/\r$//' ~/smartfarm/scripts/telegram_io.py ~/smartfarm/scripts/session_manager.py

# 3) secrets (ไม่เข้า git)
sudo mkdir -p /etc/sfc2
echo 'TELEGRAM_BOT_TOKEN=<token>' | sudo tee /etc/sfc2/telegram.env
printf 'SMARTFARM_DB_PASSWORD=<pw>\n' | sudo tee /etc/sfc2/db.env
# แก้ sfc2-telegram-io.service: เปลี่ยนบรรทัด Environment=TELEGRAM_BOT_TOKEN=... เป็น
#   EnvironmentFile=/etc/sfc2/telegram.env

# 4) services
sudo cp ~/smartfarm/spray_session/sfc2-telegram-io.service \
        ~/smartfarm/spray_session/sfc2-session-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sfc2-telegram-io sfc2-session-manager
```

⚠️ **ก่อนสตาร์ท telegram_io ต้องไม่มี poller อื่นแตะ getUpdates** (เช่น service ของ `spray_monitor/telegram_helper.py::wait_for_yes_no`) — เช็ค:
```bash
systemctl list-units --state=running | grep -iE 'spray|telegram|frac'
```

## Test ทีละ STEP
```bash
# ── watch bus ────────────────────────────────────────────────
mosquitto_sub -h 192.168.0.254 -u pop -P pop1 -t 'sfc2/#' -v

# ── STEP2: telegram_io ───────────────────────────────────────
# M พิมพ์ใน Telegram → เห็น sfc2/telegram/incoming เด้ง
# ทดสอบส่งออก:
mosquitto_pub -h 192.168.0.254 -u pop -P pop1 -t sfc2/telegram/send \
  -m '{"chat_id":8979584153,"text":"ทดสอบจาก MQTT"}'

# ── STEP3: session_manager (จำลอง Part1 detected) ────────────
mosquitto_pub -h 192.168.0.254 -u pop -P pop1 -t sfc2/spray/detected \
  -m '{"conf":0.91,"image_path":"/tmp/x.jpg"}'
# → M ได้ "M กำลังจะพ่นยาใช่ไหม?"  → ตอบ "ใช่" → status=capturing
#   ตอบ "ไม่" → status=cancelled
```
ตรวจ DB:
```sql
SELECT session_id,batch_id,worker_id,plot_code,status,bottle_count,confirmed_at,closed_at
FROM t_spray_session ORDER BY session_id DESC LIMIT 5;
```

## ยังค้าง (ต่อ Part1)
`mqtt_yolo_receiver.py` ปัจจุบัน **ส่ง Telegram ถามเอง** ยังไม่ publish `sfc2/spray/detected`.
ต้องแก้ให้ Part1 publish topic นั้น (พร้อม conf+image) และ **เลิกถาม M เอง** ให้ session_manager เป็นเจ้าของบทสนทนา — ทำตอนต่อ end-to-end (STEP5)
