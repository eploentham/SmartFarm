-- ตารางเก็บผลตรวจความพร้อมโดรน (drone_inspector_agent.py)
CREATE TABLE IF NOT EXISTS t_drone_inspection (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id       VARCHAR(64)  NOT NULL,
    overall_status  ENUM('READY','WARNING','NOT_READY') NOT NULL,
    cpu_temp_c      DECIMAL(5,2) NULL,
    cpu_usage_pct   DECIMAL(5,2) NULL,
    mem_usage_pct   DECIMAL(5,2) NULL,
    core_volt       DECIMAL(6,4) NULL,
    throttled_hex   VARCHAR(10)  NULL,
    is_throttled    TINYINT(1)   NOT NULL DEFAULT 0,
    disk_usage_pct  DECIMAL(5,2) NULL,
    disk_free_gb    DECIMAL(8,2) NULL,
    px4_ok          TINYINT(1)   NOT NULL DEFAULT 0,
    px4_branch      VARCHAR(120) NULL,
    deps_missing    VARCHAR(255) NULL,
    camera_ok       TINYINT(1)   NOT NULL DEFAULT 0,
    detail_json     JSON         NULL,
    recorded_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_device_time (device_id, recorded_at),
    KEY idx_status (overall_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
