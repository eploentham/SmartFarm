/* t_water_pressure.sql  (pressure transducer 0.5-4.5V, 10 bar / 145 psi)
 * Run:
 *   mysql --default-character-set=utf8mb4 -h <host> -u root -p smartfarm < t_water_pressure.sql
 *
 * NOTE: this file is kept in sync with the LIVE table (dumped 2026-07-30).
 *   - Columns: voltage_raw (NOT sensor_v), pressure_psi decimal(6,2),
 *     plus is_running + status_flag (added after the first draft).
 *   - No FOREIGN KEY on the live table: pump_id is validated by the logger
 *     against m_pump instead (avoids FK 1452 while keeping inserts flexible).
 *   - charset/collation utf8mb4_unicode_ci to match m_pump.
 *   - /* *\/ comments only, file saved UTF-8.
 *
 * Conversion (firmware or logger):  bar = (voltage_raw - 0.5) * 10 / 4
 *                                   psi = bar * 14.5038
 */

CREATE TABLE IF NOT EXISTS `t_water_pressure` (
  `id`           bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'รหัสอ้างอิงแถว (auto PK)',
  `pump_id`      varchar(32) NOT NULL COMMENT 'รหัสปั๊ม อ้างอิง m_pump.pump_code เช่น WS1-P1 (pump code, FK to m_pump)',
  `reading_at`   datetime NOT NULL COMMENT 'เวลาที่อ่านค่าจริงจากเซ็นเซอร์ (sensor reading timestamp, logger ต้องใส่เอง)',
  `pressure_bar` decimal(5,2) DEFAULT NULL COMMENT 'ความดันน้ำ หน่วย bar (water pressure in bar, 0.00-10.00)',
  `pressure_psi` decimal(6,2) DEFAULT NULL COMMENT 'ความดันน้ำ หน่วย psi (water pressure in psi, เผื่ออ้างอิง)',
  `voltage_raw`  decimal(4,3) DEFAULT NULL COMMENT 'แรงดัน sensor ก่อนแปลง หน่วย V (raw sensor voltage 0.5-4.5V, ไว้ debug/calibrate)',
  `is_running`   tinyint(1) NOT NULL DEFAULT 0 COMMENT 'สถานะปั๊มขณะอ่าน 1=ทำงาน 0=หยุด (pump running flag, sync กับ t_pump_energy)',
  `status_flag`  enum('NORMAL','LOW','HIGH','NO_FLOW','SENSOR_ERR') DEFAULT NULL COMMENT 'สถานะความดัน: ปกติ/ต่ำ/สูง/ไม่มีน้ำไหล/เซ็นเซอร์ผิดพลาด (pressure status)',
  `created_at`   timestamp NOT NULL DEFAULT current_timestamp() COMMENT 'เวลาที่บันทึกลง DB (row insert time, auto)',
  PRIMARY KEY (`id`),
  KEY `idx_pump_time` (`pump_id`, `reading_at`) COMMENT 'ค้นตามปั๊มและเวลา (query by pump + time range)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='บันทึกความดันน้ำในท่อรายปั๊ม จาก pressure transducer 0-10bar/145psi ผ่าน ESP32 (water pressure log per pump)';
