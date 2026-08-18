/* ======================================================================
   t_system_health — Watchdog check log / บันทึกผลการตรวจสุขภาพระบบ
   ----------------------------------------------------------------------
   Purpose (EN): One row per individual check performed by the watchdog.
                 The watchdog runs once each morning and writes several
                 rows (one per check). A separate cleanup process trims
                 old rows later — retention is NOT enforced here.
   วัตถุประสงค์ (TH): เก็บผลการเช็คของ watchdog แบบ 1 แถวต่อ 1 การเช็ค
                 watchdog รันเช้าวันละครั้ง เขียนหลายแถว (แถวละ check)
                 การลบข้อมูลเก่าทำโดย process แยกต่างหาก (ไม่ผูกในตารางนี้)
   ====================================================================== */

CREATE TABLE `t_system_health` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT
      COMMENT 'Auto-increment primary key / คีย์หลัก',

  `check_name` VARCHAR(96) NOT NULL
      COMMENT 'Identifier of the thing checked, e.g. detect-worker-zone1, t_pi_health_freshness, pi5_temp, pn64_disk_root / ชื่อสิ่งที่ตรวจ',

  `check_type` VARCHAR(24) NOT NULL
      COMMENT 'Category: service | data_freshness | thermal | disk / ประเภทการตรวจ',

  `target_host` VARCHAR(32) DEFAULT NULL
      COMMENT 'Which machine this check refers to: pn64 | pi5camera01 | gpu01 / เครื่องที่เกี่ยวข้อง',

  `status` VARCHAR(12) NOT NULL
      COMMENT 'Result: OK | WARNING | CRITICAL / ผลการตรวจ',

  `metric_value` DECIMAL(12,2) DEFAULT NULL
      COMMENT 'Numeric measure when relevant: temp C, disk percent, age in hours (else NULL) / ค่าตัวเลข (ถ้ามี)',

  `metric_unit` VARCHAR(16) DEFAULT NULL
      COMMENT 'Unit of metric_value: C | pct | hours | rows (else NULL) / หน่วยของค่า',

  `detail` VARCHAR(255) DEFAULT NULL
      COMMENT 'Human-readable explanation, e.g. "last row 17.2h old" / รายละเอียดอ่านง่าย',

  `checked_at` DATETIME NOT NULL DEFAULT current_timestamp()
      COMMENT 'When this check ran (server local time) / เวลาที่ตรวจ',

  PRIMARY KEY (`id`),
  KEY `idx_checked_at` (`checked_at`),
  KEY `idx_name_time` (`check_name`,`checked_at`),
  KEY `idx_status_time` (`status`,`checked_at`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Watchdog system-health check log — 1 row per check (service/stale/thermal/disk); retention handled by separate cleanup / บันทึกผลตรวจสุขภาพระบบจาก watchdog';