"""Smart farm — Durian Drone inspector agent (Raspberry Pi 5).
   รวมการตรวจจาก check_pi5.sh / check_px4.sh / check_storage.sh ไว้ในตัวเดียว
   ตรวจความพร้อมก่อนบิน (pre-flight) แล้วบันทึกผลลง t_drone_inspection

   Run once:        python3 drone_inspector_agent.py
   Run as service:  python3 drone_inspector_agent.py --loop   (smartfarm-drone-inspector.service)
"""
import argparse
import importlib
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import psutil
import pymysql
from pymysql import Error

# ───── Config ─────
DEVICE_ID               = socket.gethostname()          # e.g. 'pi5_drone_01'
SAMPLE_INTERVAL_SECONDS = 300                           # 5 min between samples (loop mode)

DB_CONFIG = {
    'host':     '192.168.0.253',
    'user':     'ekapop',
    'password': 'Ekartc2c51*',
    'database': 'smartfarm',
}

PX4_DIR       = Path.home() / 'PX4-Autopilot'
ROS_LOG_DIR   = Path.home() / '.ros' / 'log'
THERMAL_FILE  = '/sys/class/thermal/thermal_zone0/temp'

# Thresholds
TEMP_WARN_C     = 70.0
TEMP_CRIT_C     = 85.0
DISK_WARN_PCT   = 80.0
DISK_CRIT_PCT   = 95.0

# Dependencies ที่ PX4 build ต้องใช้ (module name ที่ import ได้จริง)
PYTHON_DEPS = ['kconfiglib', 'genmsg', 'em', 'jinja2']   # pyros-genmsg → genmsg, empy → em
COMMANDS    = ['ros2', 'colcon', 'gz']

# ───── Checks ─────
def run_cmd(args):
    """รันคำสั่งแล้วคืน stdout (หรือ None ถ้ารันไม่ได้)"""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

def check_pi_health():
    with open(THERMAL_FILE) as f:
        cpu_temp = round(int(f.read().strip()) / 1000.0, 2)

    throttled = run_cmd(['vcgencmd', 'get_throttled'])
    throttle_hex = throttled.split('=')[1] if throttled else None
    is_throttled = 1 if throttle_hex and int(throttle_hex, 16) != 0 else 0

    volts = run_cmd(['vcgencmd', 'measure_volts', 'core'])
    core_volt = float(volts.split('=')[1].rstrip('V')) if volts else None

    return {
        'cpu_temp_c':    cpu_temp,
        'throttle_hex':  throttle_hex,
        'is_throttled':  is_throttled,
        'core_volt':     core_volt,
        'cpu_usage_pct': psutil.cpu_percent(interval=1.0),
        'mem_usage_pct': psutil.virtual_memory().percent,
    }

def check_storage():
    disk = psutil.disk_usage('/')
    ros_log_mb = 0.0
    if ROS_LOG_DIR.exists():
        ros_log_mb = round(
            sum(f.stat().st_size for f in ROS_LOG_DIR.rglob('*') if f.is_file()) / 1024 / 1024, 1)
    return {
        'disk_usage_pct': disk.percent,
        'disk_free_gb':   round(disk.free / 1024**3, 2),
        'ros_log_mb':     ros_log_mb,
    }

def check_px4():
    px4_ok = PX4_DIR.is_dir()
    branch = None
    if px4_ok:
        branch = run_cmd(['git', '-C', str(PX4_DIR), 'branch', '--show-current'])
    return {'px4_dir_ok': px4_ok, 'px4_branch': branch}

def check_dependencies():
    missing = []
    for mod in PYTHON_DEPS:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    for cmd in COMMANDS:
        if shutil.which(cmd) is None:
            missing.append(cmd)
    return {'deps_missing': missing}

def check_camera():
    videos = sorted(str(p) for p in Path('/dev').glob('video*'))
    return {'camera_ok': len(videos) > 0, 'camera_devices': videos}

# ───── Verdict ─────
def evaluate(report):
    """สรุปความพร้อมบิน: READY / WARNING / NOT_READY พร้อมเหตุผล"""
    problems, warnings = [], []

    if report['cpu_temp_c'] >= TEMP_CRIT_C:
        problems.append(f"CPU temp {report['cpu_temp_c']}°C สูงเกิน {TEMP_CRIT_C}°C")
    elif report['cpu_temp_c'] >= TEMP_WARN_C:
        warnings.append(f"CPU temp {report['cpu_temp_c']}°C เริ่มสูง")

    if report['is_throttled']:
        problems.append(f"ตรวจพบ throttling ({report['throttle_hex']}) → เช็คไฟเลี้ยง/พัดลม")

    if report['disk_usage_pct'] >= DISK_CRIT_PCT:
        problems.append(f"Disk เต็ม {report['disk_usage_pct']}% → ล้าง ROS log/ภาพเก่า")
    elif report['disk_usage_pct'] >= DISK_WARN_PCT:
        warnings.append(f"Disk ใช้ไป {report['disk_usage_pct']}%")

    if not report['px4_dir_ok']:
        problems.append("ไม่พบโฟลเดอร์ PX4-Autopilot")
    if report['deps_missing']:
        problems.append(f"ขาด dependency: {', '.join(report['deps_missing'])}")
    if not report['camera_ok']:
        warnings.append("ไม่พบกล้อง (/dev/video*)")

    if problems:
        status = 'NOT_READY'
    elif warnings:
        status = 'WARNING'
    else:
        status = 'READY'
    return status, problems, warnings

# ───── DB ─────
def insert_inspection(report, status, problems, warnings):
    sql = """
        INSERT INTO t_drone_inspection
            (device_id, overall_status, cpu_temp_c, cpu_usage_pct, mem_usage_pct,
             core_volt, throttled_hex, is_throttled, disk_usage_pct, disk_free_gb,
             px4_ok, px4_branch, deps_missing, camera_ok, detail_json, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    """
    detail = json.dumps({'problems': problems, 'warnings': warnings,
                         'ros_log_mb': report['ros_log_mb'],
                         'camera_devices': report['camera_devices']},
                        ensure_ascii=False)
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (
                DEVICE_ID, status, report['cpu_temp_c'], report['cpu_usage_pct'],
                report['mem_usage_pct'], report['core_volt'], report['throttle_hex'],
                report['is_throttled'], report['disk_usage_pct'], report['disk_free_gb'],
                1 if report['px4_dir_ok'] else 0, report['px4_branch'],
                ','.join(report['deps_missing']) or None,
                1 if report['camera_ok'] else 0, detail,
            ))
        conn.commit()
    finally:
        conn.close()

# ───── Inspection pass ─────
def inspect_once():
    report = {}
    report.update(check_pi_health())
    report.update(check_storage())
    report.update(check_px4())
    report.update(check_dependencies())
    report.update(check_camera())

    status, problems, warnings = evaluate(report)

    icon = {'READY': '✅', 'WARNING': '⚠️', 'NOT_READY': '❌'}[status]
    print(f"[{status}] {icon} device={DEVICE_ID}  temp={report['cpu_temp_c']}°C  "
          f"cpu={report['cpu_usage_pct']:.1f}%  disk={report['disk_usage_pct']}%  "
          f"throttled={report['throttle_hex']}")
    for msg in problems:
        print(f"  ❌ {msg}")
    for msg in warnings:
        print(f"  ⚠️  {msg}")

    try:
        insert_inspection(report, status, problems, warnings)
    except Error as e:
        print(f"[DB ERROR] {e}")

    return status

# ───── Main ─────
def main():
    parser = argparse.ArgumentParser(description='Durian Drone pre-flight inspector')
    parser.add_argument('--loop', action='store_true',
                        help=f'ตรวจซ้ำทุก {SAMPLE_INTERVAL_SECONDS}s (สำหรับ systemd)')
    args = parser.parse_args()

    print(f"[START] drone_inspector_agent device={DEVICE_ID}  "
          f"mode={'loop' if args.loop else 'once'}")

    if not args.loop:
        status = inspect_once()
        raise SystemExit(0 if status == 'READY' else 1)

    while True:
        try:
            inspect_once()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(SAMPLE_INTERVAL_SECONDS)

if __name__ == '__main__':
    main()
