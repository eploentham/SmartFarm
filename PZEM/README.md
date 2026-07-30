# SmartFarm PZEM pump-energy

วัดพลังงานไฟฟ้าปั๊มน้ำด้วย PZEM-004T v3.0 → ESP32 (TTGO T-Display, ไม่ใช้จอ) → MQTT → MariaDB.
เริ่มที่ **WS-01** (2 ปั๊ม: WS1-P1, WS1-P2 บน 1 ESP32 + 2 PZEM) แล้วขยายไปสถานีอื่น.

## Files

| File | หน้าที่ |
|------|--------|
| `pzem/pzem.ino` | bench test ตัวเดียว (serial/TFT) — legacy |
| `pzem_mqtt/pzem_mqtt.ino` | **firmware จริง**: WiFiManager + 2×PZEM + NTP + MQTT (2 topic) |
| `config.py` | config กลาง (env-driven) |
| `db_helper.py` | MariaDB: whitelist จาก m_pump + batch insert |
| `mqtt_helper.py` | MQTT subscriber wrapper (paho) |
| `pump_energy_logger.py` | main: MQTT → buffer → batch insert |
| `pzem_sim.py` | simulator (ทดสอบ pipeline ไม่ต้องมี hardware) |
| `pressure_mqtt/pressure_mqtt.ino` | **firmware pressure**: 1 ESP32 + 2 transducer → 2 topic |
| `pressure_logger.py` | main pressure: MQTT → buffer → batch insert `t_water_pressure` |
| `pressure_sim.py` | simulator pressure (ทดสอบไม่ต้องมี hardware) |
| `smartfarm-pump-energy.service` | systemd unit (pump-energy logger) |
| `smartfarm-pressure.service` | systemd unit (pressure logger) |
| `sql/create_writer_user.sql` | สร้าง DB user ที่ INSERT ได้ (รันด้วย admin) |
| `sql/t_water_pressure.sql` | ตาราง pressure (sync กับ live schema แล้ว) |

> **Reuse:** pressure ใช้ `config.py` / `.env` / `db_helper.py` / `mqtt_helper.py`
> ชุดเดียวกับ pump-energy — ต่างแค่ topic (`smartfarm/pressure/#`) กับตาราง.

## MQTT payload contract

1 ESP32 → 2 PZEM → publish **2 topic แยก** `smartfarm/pump/{pump_code}`
(PZEM1→pump_code1, PZEM2→pump_code2). ค่า I/P/E หารด้วย `CT_TURNS` (3) ใน firmware แล้ว.

```json
{"pump_id":"WS1-P1","voltage_v":220.1,"current_a":6.812,"power_w":1499.2,
 "energy_kwh":0.123,"frequency_hz":50.0,"power_factor":0.99,
 "is_running":1,"reading_at":"2026-07-27 14:30:05"}
```

- `reading_at`: firmware ใส่จาก NTP (เวลาไทย). logger ใช้ค่านี้ถ้ามี ไม่งั้น stamp เวลารับเอง.
- `is_running`: `power_w > 200`.
- คอลัมน์ DB ที่เว้นว่างไว้ (NULL): `motor_temp_c`, `active_valves`, `tou_period`.
- pump_code valid (8): WS1-P1, WS1-P2, WS2-P1/P2/P3, WS3-P1/P2, WS4-P1 — logger กรองกับ `m_pump` กัน FK 1452.

---

## Blocker 1 — DB write user (ต้องใช้ admin สร้าง)

`claude_readonly` = SELECT-only. สร้าง `smartfarm_writer` (least-privilege):

```bash
mysql --default-character-set=utf8mb4 -h <host> -u root -p smartfarm < sql/create_writer_user.sql
```
(แก้รหัสผ่านในไฟล์ก่อน) จากนั้นเก็บรหัสไว้ที่ `/etc/smartfarm/pump-energy.env` → `DB_PASS=...`

## Blocker 2 — MQTT broker (bench: local ก่อน)

```bash
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto        # 127.0.0.1:1883
mosquitto_sub -h 127.0.0.1 -t 'smartfarm/pump/#' -v
```
Production: ย้ายไป mini-PC `192.168.0.254` (user pop/pop1) — แค่แก้ env `MQTT_BROKER`.

---

## Bench test (end to end, ไม่ต้องมี hardware)

```bash
pip install paho-mqtt mysql-connector-python

# terminal 1 — logger (ชี้ localhost)
cd ~/smartfarm/PZEM
DB_PASS='...' python3 pump_energy_logger.py

# terminal 2 — จำลอง 2 ปั๊ม WS-01, P1 เป็นกาต้ม 1500W
python3 pzem_sim.py --pump WS1-P1 --pump WS1-P2 --watts 1500

# verify
mysql -u smartfarm_writer -p smartfarm \
  -e "SELECT pump_id,reading_at,power_w,is_running FROM t_pump_energy ORDER BY reading_at DESC LIMIT 5;"
```

---

## Water pressure (`pressure_mqtt.ino` + `pressure_logger.py`)

วัดแรงดันน้ำในท่อด้วย pressure transducer **0.5–4.5V / 10 bar (145 psi)**.
1 ESP32 → 2 transducer → 2 pumps (WS1-P1, WS1-P2), publish **2 topic แยก**
`smartfarm/pressure/{pump_code}`.

- Sensor1 → **GPIO34**, Sensor2 → **GPIO35** (ADC1, ทำงานพร้อม WiFi).
- สัญญาณ 0.5–4.5V > ADC 3.3V → ต้องมี **voltage divider 1:1** (R1 4.7k / R2 4.7k)
  ลงครึ่งนึง + cap 100nF กันสัญญาณรบกวนจากปั๊ม. `DIV_FACTOR = 2.0`.
- firmware อ่าน `analogReadMilliVolts()` (calibrated), เฉลี่ย 20 ครั้ง, คูณ 2 กลับ
  → `voltage_raw`, แปลงเป็น bar/psi, ส่ง MQTT.
- **is_running + status_flag** logger คำนวณเอง (threshold ปรับใน `.env` ไม่ต้อง re-flash).

### Payload contract

```json
{"pump_id":"WS1-P1","voltage_raw":2.100,"pressure_bar":4.00,
 "pressure_psi":58.02,"reading_at":"2026-07-30 14:30:05"}
```

- คอลัมน์ตาราง `t_water_pressure` (live): `pump_id, reading_at, pressure_bar,
  pressure_psi, voltage_raw, is_running, status_flag`.
- `status_flag` = `NORMAL / LOW / HIGH / NO_FLOW / SENSOR_ERR` (logger จำแนกจาก threshold).
- **ไม่มี FK** บนตาราง → logger กรอง `pump_id` กับ `m_pump` เอง.
- calibrate: ตั้ง `v_min/v_max` ต่อ sensor ใน config portal (เทียบกับ SUMO gauge).

### Bench test (pressure, ไม่ต้องมี hardware)

```bash
# terminal 1 — pressure logger
cd ~/smartfarm/PZEM
DB_PASS='...' python3 pressure_logger.py

# terminal 2 — จำลอง 2 sensor WS-01 ~4 bar (ลอง --duty / --fault ดู status_flag)
python3 pressure_sim.py --pump WS1-P1 --pump WS1-P2 --bar 4

# verify
mysql -u smartfarm_writer -p smartfarm \
  -e "SELECT pump_id,reading_at,pressure_bar,is_running,status_flag \
      FROM t_water_pressure ORDER BY reading_at DESC LIMIT 5;"
```

### Deploy pressure logger (systemd)

```bash
sudo cp smartfarm-pressure.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now smartfarm-pressure
journalctl -u smartfarm-pressure -f
```

Threshold ปรับได้ใน `.env`: `PRESSURE_MIN_BAR`, `PRESSURE_MAX_BAR`,
`PRESSURE_NOFLOW_BAR`, `PRESSURE_RUN_BAR`, `PRESSURE_V_MIN/MAX`.

---

## Firmware (`pzem_mqtt.ino`)

- Libraries: **mandulaj/PZEM-004T-v30**, **tzapu/WiFiManager**, **PubSubClient**, **ArduinoJson**.
- First boot → AP `PZEM-Setup` (pass `12345678`) → กรอก WiFi + MQTT IP/port + **MQTT user/pass** (pop/pop1 ถ้า broker เปิด auth) + pump_code1 + pump_code2. เก็บใน LittleFS.
- **ปุ่ม BOOT (GPIO0):** กดสั้น (<2s) = เปิด config portal แก้ค่า **โดยไม่ลบ WiFi** · กดค้าง 5s = factory reset ล้างทั้งหมด.
- **OTA:** หลังแฟลช USB ครั้งแรก อัปเดตครั้งต่อไปผ่าน WiFi ได้: `arduino-cli compile --fqbn esp32:esp32:esp32 --port <device_ip> --upload <sketch>` (hostname `pzem-<pump_code1>.local`). config ไม่หายตอน re-flash (อยู่คนละ partition).
- Pins: PZEM1 RX27/TX26 (Serial2), PZEM2 RX22/TX21 (Serial1). Divider เฉพาะสาย TX.
- แฟลช USB ครั้งแรก: ใช้สาย USB สั้น + ถอด PZEM ก่อน (กัน csum err). อย่าเปิด "Erase All Flash" (ไม่งั้น config หาย).
- Libraries เพิ่ม: **ArduinoOTA** (มากับ ESP32 core, ไม่ต้องลงแยก).

## Deploy logger (systemd)

```bash
sudo cp smartfarm-pump-energy.service /etc/systemd/system/
sudo mkdir -p /etc/smartfarm && echo 'DB_PASS=...' | sudo tee /etc/smartfarm/pump-energy.env
sudo systemctl daemon-reload && sudo systemctl enable --now smartfarm-pump-energy
journalctl -u smartfarm-pump-energy -f
```
