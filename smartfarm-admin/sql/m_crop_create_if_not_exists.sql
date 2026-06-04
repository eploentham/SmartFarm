-- ================================================================
-- m_crop : ตารางหลัก ชนิดของพืชที่ปลูกในสวน (Durian / Guava / Wax Apple)
-- ใช้คู่กับ m_plot (FK: m_plot.crop_id -> m_crop.id)
-- รันเฉพาะกรณีที่ m_crop ยังไม่มีในฐานข้อมูล
-- ================================================================

CREATE TABLE IF NOT EXISTS m_crop (
  id              INT(11) NOT NULL AUTO_INCREMENT             COMMENT 'รหัสภายในของระบบ',
  crop_code       VARCHAR(20) NOT NULL                         COMMENT 'รหัสพืชแบบสั้น เช่น DURIAN, GUAVA, WAXAPPLE',
  name_th         VARCHAR(100) NOT NULL                        COMMENT 'ชื่อพืชภาษาไทย เช่น ทุเรียน',
  name_en         VARCHAR(100) NOT NULL                        COMMENT 'ชื่อพืชภาษาอังกฤษ เช่น Durian',
  scientific_name VARCHAR(150) DEFAULT NULL                    COMMENT 'ชื่อวิทยาศาสตร์ เช่น Durio zibethinus',
  variety_th      VARCHAR(100) DEFAULT NULL                    COMMENT 'สายพันธุ์/พันธุ์ปลูก เช่น หมอนทอง',
  notes_th        TEXT DEFAULT NULL                            COMMENT 'หมายเหตุเพิ่มเติม ภาษาไทย',
  is_active       TINYINT(1) DEFAULT 1                         COMMENT 'สถานะใช้งาน (1=active, 0=ปิดใช้/soft delete)',
  created_at      TIMESTAMP NULL DEFAULT current_timestamp()   COMMENT 'วันเวลาที่สร้างเรคคอร์ด',
  updated_at      TIMESTAMP NULL DEFAULT current_timestamp()
                    ON UPDATE current_timestamp()              COMMENT 'วันเวลาที่แก้ไขล่าสุด',
  PRIMARY KEY (id),
  UNIQUE KEY uk_crop_code (crop_code),
  KEY idx_m_crop_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='ตารางหลักของชนิดพืชที่ปลูกในสวน — ใช้อ้างอิงจาก m_plot และ t_disease_diagnosis';

-- ================================================================
-- Seed data (optional) — รัน 1 ครั้งหลังสร้างตาราง
-- ================================================================

INSERT IGNORE INTO m_crop (crop_code, name_th, name_en, scientific_name, variety_th, notes_th) VALUES
  ('DURIAN',   'ทุเรียน', 'Durian',    'Durio zibethinus',      'หมอนทอง',     'พืชหลักของสวน'),
  ('GUAVA',    'ฝรั่ง',   'Guava',     'Psidium guajava',       'กิมจู',        NULL),
  ('WAXAPPLE', 'ชมพู่',   'Wax Apple', 'Syzygium samarangense', 'ทับทิมจันท์',  NULL);

-- ตรวจสอบผล:
-- SELECT * FROM m_crop;
