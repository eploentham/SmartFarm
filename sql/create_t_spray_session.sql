/* ======================================================================
   t_spray_session — Spray session header / หัวรอบพ่นยา (คุม lifecycle)
   ----------------------------------------------------------------------
   Purpose (EN): One row per conversational spray-logging session driven by
                 session_manager.py. Holds the lifecycle state machine
                 (pending -> capturing -> awaiting_plot -> awaiting_confirm
                  -> closed | cancelled | timeout). Each session owns ONE
                 batch_id that is shared by every bottle row written to
                 t_chemical_application (1 session : N bottles).
   วัตถุประสงค์ (TH): 1 แถวต่อ 1 รอบพ่น (conversational workflow) คุมสถานะ
                 lifecycle และถือ batch_id เดียวที่ทุกขวดใน session ใช้ร่วมกัน
                 เชื่อมกับ t_chemical_application ผ่าน batch_id (1:N)

   Migration order / ลำดับการรัน (STEP 1 ของ handoff Part 3+4):
     1) CREATE TABLE t_spray_session          (ส่วนที่ 1)
     2) ALTER ADD FK fk_spray_session_worker  (ส่วนที่ 2)
     3) ALTER t_chemical_application ADD application_category (ส่วนที่ 3)
   รันครั้งเดียว (ไม่ idempotent) — รันซ้ำจะ error "table/column exists"

   COLLATION NOTE / หมายเหตุ collation (สำคัญ):
     ตารางนี้ใช้ utf8mb4_general_ci ตั้งใจให้ตรงกับ t_chemical_application
     (ซึ่งเป็น general_ci) เพราะต้อง JOIN ด้วย batch_id (VARCHAR) — ถ้า
     collation ต่างกันจะเจอ "Illegal mix of collations" ตอน query.
     (ไฟล์ migration อื่นในโปรเจกต์ใช้ unicode_ci แต่ที่นี่ต้องยึดตารางที่ join)
   ====================================================================== */

/* ---------------------------------------------------------------------
   ส่วนที่ 1 — CREATE TABLE
   --------------------------------------------------------------------- */
CREATE TABLE `t_spray_session` (
  `session_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT
      COMMENT 'รหัส session (PK) / session primary key',

  `batch_id` VARCHAR(36) NOT NULL
      COMMENT 'รหัสรอบพ่น UUID เชื่อม t_chemical_application / batch UUID linking all bottles in this session',

  `worker_id` TINYINT UNSIGNED DEFAULT NULL
      COMMENT 'ผู้พ่น FK m_worker (M=2) / sprayer worker FK',

  `plot_code` VARCHAR(20) DEFAULT NULL
      COMMENT 'แปลงที่พ่น เช่น DURIAN-A1 (ใส่ตอน M ตอบแปลง) / plot code, filled after M answers',

  `status` ENUM('pending','capturing','awaiting_plot','awaiting_confirm','closed','cancelled','timeout')
      NOT NULL DEFAULT 'pending'
      COMMENT 'สถานะ session lifecycle / session state machine',

  `detection_conf` DECIMAL(4,3) DEFAULT NULL
      COMMENT 'ความมั่นใจตอน Part1 เจอ / YOLO detection confidence',

  `detection_image` VARCHAR(255) DEFAULT NULL
      COMMENT 'พาธรูป annotated ตอนถาม / annotated detection image path',

  `bottle_count` INT NOT NULL DEFAULT 0
      COMMENT 'จำนวนขวดที่ถ่ายใน session นี้ / bottles captured',

  `confirmed_at` DATETIME DEFAULT NULL
      COMMENT 'เวลา M ตอบ yes / time M confirmed spraying',

  `closed_at` DATETIME DEFAULT NULL
      COMMENT 'เวลาปิด session / session close time',

  `created_at` TIMESTAMP NOT NULL DEFAULT current_timestamp()
      COMMENT 'เวลาสร้างแถว / row creation time',

  PRIMARY KEY (`session_id`),
  KEY `idx_batch` (`batch_id`),
  KEY `idx_status` (`status`),
  KEY `idx_created` (`created_at`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_general_ci
  COMMENT='หัวรอบพ่นยา คุม lifecycle (pending->capturing->...->closed) / spray session header';

/* ---------------------------------------------------------------------
   ส่วนที่ 2 — FK แยก (worker_id -> m_worker.id)
   --------------------------------------------------------------------- */
ALTER TABLE `t_spray_session`
  ADD CONSTRAINT `fk_spray_session_worker`
  FOREIGN KEY (`worker_id`) REFERENCES `m_worker` (`id`);

/* ---------------------------------------------------------------------
   ส่วนที่ 3 — เพิ่ม application_category ใน t_chemical_application
   ประเภทใหญ่ของสิ่งที่พ่น: สารเคมี / ชีวภัณฑ์ / ปุ๋ย
   (Gemini แยกเอง — zero manual entry; ถ้าไม่มั่นใจ default 'chemical')
   --------------------------------------------------------------------- */
ALTER TABLE `t_chemical_application`
  ADD COLUMN `application_category` ENUM('chemical','biological','fertilizer')
    NOT NULL DEFAULT 'chemical'
    COMMENT 'ประเภทใหญ่: สารเคมี/ชีวภัณฑ์/ปุ๋ย / major application category'
  AFTER `chemical_type`;
