"""Thin MariaDB wrapper."""
import mysql.connector
import logging
from config import DB_CONFIG

log = logging.getLogger(__name__)

def _conn():
    return mysql.connector.connect(**DB_CONFIG)

def insert_detection(worker_code: str, camera: str, confidence: float) -> int:
    """Insert a new row when YOLO detects person+backpack. Returns application_id."""
    sql = """
        INSERT INTO t_chemical_application
            (worker_code, detection_camera, detection_confidence, status)
        VALUES (%s, %s, %s, 'detected')
    """
    with _conn() as c, c.cursor() as cur:
        cur.execute(sql, (worker_code, camera, confidence))
        c.commit()
        return cur.lastrowid

def update_status(app_id: int, status: str, **fields):
    """Update status + any extra columns (chemical_name, photo_path, etc.)."""
    cols = ['status = %s']
    vals = [status]
    for k, v in fields.items():
        cols.append(f"{k} = %s")
        vals.append(v)
    vals.append(app_id)
    sql = f"UPDATE t_chemical_application SET {', '.join(cols)} WHERE application_id = %s"
    with _conn() as c, c.cursor() as cur:
        cur.execute(sql, vals)
        c.commit()
        log.info(f"app#{app_id} → {status} ({fields})")
def test_insert(worker_code: str, worker_name: str) -> int:
    sql = """
        insert into m_worker (worker_code, worker_name_th) values (%s, %s)
        """
    with _conn() as c, c.cursor() as cur:
        cur.execute(sql, (worker_code, worker_name))
        c.commit()
        return cur.lastrowid