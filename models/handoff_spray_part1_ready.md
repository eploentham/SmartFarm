# 🌿 Smartfarm — Flow ส่วน 1: Telegram "M กำลังจะพ่นยาใช่ไหม?" (พร้อมเริ่ม)

> วางไฟล์นี้ตอนเริ่ม chat ใหม่ → ทำ flow ส่วน 1 ต่อได้ทันที

---

## 🎯 งานวันนี้ (สำคัญสุด — มาก่อน)

แก้ `mqtt_yolo_receiver.py` (PN64) ให้:
```
เมื่อ detect worker + sprayer พร้อมกัน (conf ≥ 0.5) ในภาพเดียว
   → ส่ง Telegram "M กำลังจะพ่นยาใช่ไหม?" + รูป annotated (วาดกรอบ)
   → throttle 5 นาที (กันสแปม)
```

**M = ผู้จัดการสวน = คนเดียวที่พ่นยา → detect "worker" = สันนิษฐานเป็น M** (ไม่ต้อง face recognition)

นี่คือ flow เต็ม (ทำทีละส่วน):
```
ส่วน 1 (วันนี้): detect worker+sprayer → Telegram "M กำลังจะพ่นยาใช่ไหม?" + รูป   ⏳
ส่วน 3: รอ M ตอบ "yes" (state machine จับ reply)
ส่วน 4: เชื่อม detectbottle pipeline เดิม (เริ่มบันทึกสารเคมี)
+ ลำโพง Pi5 พูด "M กำลังจะพ่นยาใช่ไหม?"
```

---

## ✅ พร้อมทุกอย่างแล้ว

```
✅ pipeline MQTT + service 2 ฝั่ง (Pi5 sender + PN64 receiver) รัน 24/7
✅ โมเดล YOLO ทำงาน (Worker conf 0.72-0.97)
✅ iGPU กลับมาแล้ว (หลัง reboot → GPU.0) *ดูหมายเหตุด้านล่าง*
✅ Telegram เทสส่งหา M ผ่านแล้ว (test_telegram.py สำเร็จ)
✅ M + chat_id อยู่ใน m_worker แล้ว
✅ requests ลงใน venv yolo แล้ว (ถ้ายังไม่ลง: pip install requests)
```

**ต้องเตรียม/ยืนยันก่อนเขียนโค้ด:**
- [ ] **TG_TOKEN** — bot token (ใช้ตัวเดิมจาก detectbottle; ถ้า revoke แล้วใช้ตัวใหม่)
- [ ] **TG_CHAT_ID ของ M** — ดึงจาก m_worker (`SELECT telegram_chat_id, nickname FROM m_worker;`)
- [ ] ยืนยัน throttle 5 นาที + เงื่อนไข "worker AND sprayer พร้อมกัน"

---

## 💻 โค้ดส่วน 1 (พร้อมใช้ — แก้ mqtt_yolo_receiver.py)

จุดที่ต้องเพิ่มใน receiver: (1) config Telegram, (2) ฟังก์ชัน send_telegram, (3) เงื่อนไข worker AND sprayer + throttle ใน on_message

```python
# ===== เพิ่มบนสุด (import) =====
import time, requests   # requests ต้อง pip install

# ===== เพิ่มใน config =====
TG_TOKEN    = "ใส่_BOT_TOKEN"          # ⚠️ ใส่ token จริง
TG_CHAT_ID  = "ใส่_CHAT_ID_ของM"       # จาก m_worker
TG_COOLDOWN = 300                      # 5 นาที (กันสแปม)
TG_MIN_CONF = 0.50                     # ส่งเฉพาะ conf >= 0.5
last_tg = 0                            # เวลา Telegram ครั้งล่าสุด (global)

# ===== ฟังก์ชันส่ง Telegram =====
def send_telegram(text, img_bgr):
    try:
        ok, jpg = cv2.imencode(".jpg", img_bgr)
        if not ok: return
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        files = {"photo": ("detect.jpg", jpg.tobytes(), "image/jpeg")}
        data  = {"chat_id": TG_CHAT_ID, "caption": text}
        r = requests.post(url, data=data, files=files, timeout=10)
        print(f"  -> Telegram {'ส่งแล้ว' if r.status_code==200 else 'error '+str(r.status_code)}")
    except Exception as e:
        print(f"  -> Telegram ส่งไม่ได้: {e}")

# ===== ใน on_message (หลังได้ results/found) =====
# ... โค้ดเดิม: predict, found, print("เจอ:", ...) ...

annotated = results[0].plot()   # รูปวาดกรอบ

# --- เงื่อนไขส่วน 1: worker AND sprayer พร้อมกัน + conf สูง ---
labels_conf = [(model.names[int(b.cls)], float(b.conf)) for b in boxes]
has_worker  = any(n == "Worker"  and c >= TG_MIN_CONF for n, c in labels_conf)
has_sprayer = any(n == "sprayer" and c >= TG_MIN_CONF for n, c in labels_conf)

global last_tg
now = time.time()
if has_worker and has_sprayer and (now - last_tg) > TG_COOLDOWN:
    send_telegram("M กำลังจะพ่นยาใช่ไหม? 🌿\n(ตรวจพบคน + ถังพ่นยา)", annotated)
    last_tg = now
    print("  -> เข้าเงื่อนไข worker+sprayer → ส่ง Telegram")
```

**หมายเหตุโค้ด:**
- เงื่อนไข = **worker AND sprayer พร้อมกัน** (มีคน + มีถัง = กำลังจะพ่น) ไม่ใช่อย่างใดอย่างหนึ่ง
- `last_tg` เป็น global (ประกาศนอกฟังก์ชัน + `global last_tg` ใน on_message)
- ส่งรูป annotated (วาดกรอบ + conf) ให้ M เห็นว่าเจออะไร

---

## ⚠️ หมายเหตุจากเมื่อคืน (สำคัญ)

### 1. iGPU vs CPU (แก้แล้วด้วย reboot)
- เจอปัญหา: service รันบน **CPU** แทน iGPU (user เทสได้ GPU.0 แต่ service ได้ CPU)
- ลองแก้: device="intel:gpu" ✓, SupplementaryGroups=render video ✓, HOME=/home/ekapop ✓, PrivateDevices=no ✓, DeviceAllow renderD128+card1 ✓ — **ยัง CPU**
- **reboot แก้ได้!** หลัง reboot log ตอน start ยังโชว์ CPU แต่ **inference จริงเป็น GPU.0** (23:20 log: "on GPU.0" + "เจอ: Worker(0.72)")
- **สรุป: ตอนนี้ใช้ iGPU แล้ว** — ถ้า service แสดง CPU ตอน start อย่าเพิ่งตกใจ ให้ส่งภาพเทสดู log ว่า inference เป็น GPU.0 ไหม
- **ถ้า CPU ก็ยอมรับได้** — motion-gated ไม่ต้องเร็วมาก (อย่าเสียเวลากับ iGPU เกินจำเป็น)

### 2. Insight เรื่องมุมกล้อง (ต้องเก็บภาพเพิ่มทีหลัง)
- **คนหันหลังให้กล้อง → ไม่พบ / คนหันหน้า → พบ**
- โมเดลเรียนจากภาพที่เห็นด้านหน้าเยอะ → หลังคนยังไม่แม่น
- **ทำทีหลัง (รองจากส่วน 1):** เก็บภาพคนหันหลังเพิ่ม → เทรน → จับได้ทุกมุม

### 3. systemd + PYTHONUNBUFFERED
- print ใน Python ถูก buffer → log ไม่ขึ้นทันที
- แก้แล้ว: `Environment=PYTHONUNBUFFERED=1` ใน service → log real-time
- **ถ้าแก้ service แล้วต้อง `daemon-reload` + `restart` เสมอ** (มักลืม)

---

## 📊 สถานะโมเดล (สรุป 4 รอบ)

| รอบ | รูป | mAP50 | Worker | sprayer | brush-cutter | หมายเหตุ |
|---|---|---|---|---|---|---|
| v7 | 215 | 0.668 | 0.785 | 0.711 | 0.587 | label ไม่ครบ |
| **327** | 327 | **0.792** | 0.878 | 0.817 | 0.681 | **ดีสุด** ✅ |
| 402/561 | 561 | 0.693 | 0.78 | 0.802 | 0.499 | เพิ่มรูปไม่มี brush → เจือจาง |

**บทเรียน:**
- **327 = โมเดลดีสุด** (ใช้ตัวนี้)
- เพิ่ม 159 รูป (worker/sprayer, ไม่มี brush-cutter) → **brush-cutter mAP ตก** (เจือจาง)
- **ช่วงนี้ฤดูพ่นยา ไม่ตัดหญ้า** → brush-cutter อ่อนช่วงนี้รับได้ (flow ส่วน 1 ใช้แค่ worker+sprayer)
- test set เปลี่ยนทุกรอบ → **เทียบ mAP ข้ามรอบไม่ได้** (ต้องเทสภาพเดียวกัน)
- label ครบทุก class ในทุกรูป = ปัจจัยสำคัญ (327 ทำ sprayer recall พุ่ง 0.5→0.92)

**โมเดลบน PN64 ตอนนี้:** `/home/ekapop/smartfarm/best_openvino_model/` (ควรเป็น 327 — เช็คก่อนถ้าไม่แน่ใจ)

---

## 🖥️ Infrastructure (ย่อ)

- **PN64** (192.168.0.254, Tailscale 100.97.182.35): i3-1220P iGPU, 32GB. MariaDB (smartfarm), Mosquitto MQTT (1883, user pop/pop1), venv `/home/ekapop/venv/yolo`
- **pi5camera01** (192.168.0.253): Pi5, dual CSI cam, **ลำโพง** (สำหรับส่วนเสียง). Pi5 ส่ง PN64 infer (Pi5 ร้อน+ไม่มี HW encoder)
- **Service:** `smartfarm-mqtt-receiver.service` (PN64, YOLO) + `smartfarm-mqtt-sender.service` (Pi5). แก้ service → daemon-reload + restart เสมอ
- **MQTT topic:** `smartfarm/cam1/frame`
- **เทสส่งภาพ:** (Pi5) `python3 ~/smartfarm/models/test_send.py <ภาพ>` → ดู log PN64

---

## 🗄️ ระบบสารเคมีเดิม (สำหรับส่วน 4 — ยังไม่ทำวันนี้)

- **detectbottle** (`~/smartfarm/detectbottle/`): worker ส่งรูปขวด → bot ถาม "มีขวดอีกไหม?" → batch_id เดียว → t_chemical_application (pending review)
- Scripts: gemini_extract.py, catalog_match.py (irac/frac), record_spray.py
- **t_chemical_application:** batch_id, chemical_type ENUM, spray_date, tree_id, confidence_score, detected_label_raw, notes(JSON), diagnosis_id FK, +brand/concentration/formulation/expiry ฯลฯ
- **m_worker:** telegram_chat_id → id → nickname (M, T). พี่เอก chat_id 8394445325
- **Gemini API:** free tier, billing DISABLED (ห้ามเปิด)

---

## 👤 User (Ekapop) — วิธีทำงาน

- Thai HIS dev, ฝึกภาษาอังกฤษ → **ตอบอังกฤษ + 📝 English notes (2-3 ข้อ) ท้ายทุกคำตอบ**; เขียนไทย = ไม่รู้ศัพท์ → แปล+อธิบายก่อน
- **step-by-step**, ทวนก่อนทำ, one script per task, verify ก่อนเขียน, honest assessment
- **daily digest > real-time alarm** → ระวังส่ง Telegram สแปม (throttle/digest)
- ชอบทำทีละส่วน ไม่รวบ

---

## ▶️ ประโยคเริ่ม chat ใหม่

> "ทำ flow ส่วน 1 — แก้ mqtt_yolo_receiver.py ให้ detect worker+sprayer พร้อมกัน แล้วส่ง Telegram 'M กำลังจะพ่นยาใช่ไหม?' + รูป annotated, throttle 5 นาที (context + โค้ดอยู่ในไฟล์ handoff ที่แนบ)"

**ก่อนรันโค้ด:** ดึง TG_TOKEN + M's chat_id, ยืนยัน model บน PN64 เป็น 327, เช็ค requests ลงแล้ว