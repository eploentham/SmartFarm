-- ============================================================
-- Open-Meteo Weather Logger Schema
-- For: Thong Pha Phum Orchard (14.755135, 98.646364)
-- Run on: MariaDB on Raspberry Pi 5 (smartfarm database)
-- ============================================================

USE smartfarm;

-- ─── Hourly raw data ───
CREATE TABLE IF NOT EXISTS t_weather_open_meteo_hourly (
    id                    INT AUTO_INCREMENT PRIMARY KEY  COMMENT 'รหัสบันทึก',
    record_time           DATETIME       NOT NULL          COMMENT 'เวลาที่ข้อมูลใช้ได้ (local Bangkok)',
    shortwave_radiation   FLOAT          NULL              COMMENT 'แสงอาทิตย์รวม GHI (W/m²) เฉลี่ยชั่วโมงก่อนหน้า',
    direct_radiation      FLOAT          NULL              COMMENT 'แสงตรง (W/m²)',
    diffuse_radiation     FLOAT          NULL              COMMENT 'แสงกระจาย (W/m²)',
    cloud_cover           FLOAT          NULL              COMMENT 'เปอร์เซ็นต์เมฆปกคลุม (0-100%)',
    temperature_2m        FLOAT          NULL              COMMENT 'อุณหภูมิ 2 เมตรเหนือพื้นดิน (°C)',
    relative_humidity_2m  FLOAT          NULL              COMMENT 'ความชื้นสัมพัทธ์ (%)',
    et0_fao               FLOAT          NULL              COMMENT 'ET₀ ปริมาณน้ำที่พืชต้องการ (mm ต่อชั่วโมง)',
    precipitation         FLOAT          NULL              COMMENT 'ฝนรวม (mm)',
    is_forecast           BOOLEAN        DEFAULT TRUE      COMMENT 'TRUE=พยากรณ์, FALSE=ข้อมูลจริงย้อนหลัง',
    fetched_at            TIMESTAMP      DEFAULT CURRENT_TIMESTAMP COMMENT 'เวลาที่ดึงข้อมูล',
    location_name         VARCHAR(100)   DEFAULT 'Thong Pha Phum Orchard' COMMENT 'ชื่อตำแหน่ง',
    UNIQUE KEY uk_record_time (record_time),
    INDEX idx_record_time (record_time)
) COMMENT='ข้อมูลสภาพอากาศรายชั่วโมงจาก Open-Meteo API สำหรับสวนทองผาภูมิ ใช้คำนวณการให้น้ำและบันทึกประวัติแสง';


-- ─── Daily aggregates with auto-calculated irrigation needs ───
CREATE TABLE IF NOT EXISTS t_weather_open_meteo_daily (
    id                        INT AUTO_INCREMENT PRIMARY KEY COMMENT 'รหัสบันทึก',
    record_date               DATE           NOT NULL         COMMENT 'วันที่ข้อมูล',
    shortwave_radiation_sum   FLOAT          NULL             COMMENT 'แสงรวมรายวัน (MJ/m²) ใช้แทน DLI',
    et0_fao_sum               FLOAT          NULL             COMMENT 'ET₀ รวมรายวัน (mm) = ปริมาณน้ำที่ต้องให้',
    precipitation_sum         FLOAT          NULL             COMMENT 'ฝนรวมรายวัน (mm)',
    uv_index_max              FLOAT          NULL             COMMENT 'ค่า UV สูงสุด เฝ้าระวังชมพู่ไหม้แดด',
    sunrise                   TIME           NULL             COMMENT 'เวลาพระอาทิตย์ขึ้น',
    sunset                    TIME           NULL             COMMENT 'เวลาพระอาทิตย์ตก',
    irrigation_need_durian    FLOAT  GENERATED ALWAYS AS (GREATEST(0, et0_fao_sum * 0.95 - precipitation_sum)) STORED COMMENT 'น้ำที่ต้องให้ทุเรียน (mm) Kc=0.95',
    irrigation_need_guava     FLOAT  GENERATED ALWAYS AS (GREATEST(0, et0_fao_sum * 0.75 - precipitation_sum)) STORED COMMENT 'น้ำที่ต้องให้ฝรั่ง (mm) Kc=0.75',
    irrigation_need_wax_apple FLOAT  GENERATED ALWAYS AS (GREATEST(0, et0_fao_sum * 0.80 - precipitation_sum)) STORED COMMENT 'น้ำที่ต้องให้ชมพู่ (mm) Kc=0.80',
    is_forecast               BOOLEAN        DEFAULT TRUE     COMMENT 'TRUE=พยากรณ์, FALSE=actual',
    fetched_at                TIMESTAMP      DEFAULT CURRENT_TIMESTAMP COMMENT 'เวลาดึงข้อมูล',
    UNIQUE KEY uk_record_date (record_date),
    INDEX idx_record_date (record_date)
) COMMENT='สรุปสภาพอากาศรายวัน + คำนวณปริมาณน้ำที่พืชต้องการ (FAO-56 method) สำหรับวางแผนการให้น้ำ';