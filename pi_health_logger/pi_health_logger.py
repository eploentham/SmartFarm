"""Smart farm — Pi 5 health + top-process logger.
   Writes both t_pi_health and t_pi_top_processes in a single pass.
   Run as systemd: smartfarm-pi-health.service
"""
import time
import socket
import subprocess
import psutil
import pymysql
from pymysql import Error

# ───── Config ─────
DEVICE_ID              = socket.gethostname()              # e.g. 'pi5_camera_01'
SAMPLE_INTERVAL_SECONDS = 60                               # 1 min between samples
TOP_N_PROCESSES         = 5                                # how many hot procs to log
CPU_MEASURE_WINDOW_S    = 1.0                              # let CPU% stabilize

DB_CONFIG = {
    'host':     '192.168.0.253',
    'user':     'ekapop',
    'password': 'Ekartc2c51*',   # See note below about security
    'database': 'smartfarm',
}

THERMAL_FILE = '/sys/class/thermal/thermal_zone0/temp'

# ───── Sensors ─────
def read_cpu_temp():
    with open(THERMAL_FILE) as f:
        return round(int(f.read().strip()) / 1000.0, 2)

def read_throttle():
    r = subprocess.run(['vcgencmd', 'get_throttled'],
                       capture_output=True, text=True, check=True)
    hex_val = r.stdout.strip().split('=')[1]
    return hex_val, (1 if int(hex_val, 16) != 0 else 0)

def read_load_avg():
    with open('/proc/loadavg') as f:
        load_1m = float(f.read().split()[0])
    return load_1m

def read_top_processes(n: int = 5):
    """Return list of dicts: top N processes by CPU% over CPU_MEASURE_WINDOW_S."""
    # First pass primes cpu_percent (psutil quirk — first call returns 0)
    for p in psutil.process_iter(['pid']):
        try:
            p.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(CPU_MEASURE_WINDOW_S)

    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_percent']):
        try:
            cpu = p.cpu_percent(interval=None)
            info = p.info
            cmdline = ' '.join(info.get('cmdline') or [info['name']])[:255]
            procs.append({
                'pid':     info['pid'],
                'name':    info['name'][:120],
                'cpu':     round(cpu / psutil.cpu_count(), 2),   # normalize to %total
                'mem':     round(info['memory_percent'] or 0, 2),
                'command': cmdline,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs.sort(key=lambda x: x['cpu'], reverse=True)
    return procs[:n]

def read_overall_cpu_pct():
    """Average CPU% across all cores at this moment."""
    return psutil.cpu_percent(interval=CPU_MEASURE_WINDOW_S)

# ───── DB writes (paired) ─────
def insert_health_and_processes(conn, health, processes):
    """Write t_pi_health + t_pi_top_processes in one transaction."""
    sql_health = """
        INSERT INTO t_pi_health
            (device_id, cpu_temp_c, cpu_usage_pct, cpu_load_1min,
             throttled_hex, is_throttled, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
    """
    sql_proc = """
        INSERT INTO t_pi_top_processes
            (device_id, process_name, pid, cpu_pct, mem_pct,
             command, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    cur = conn.cursor()
    try:
        cur.execute(sql_health, (
            DEVICE_ID, health['temp'], health['cpu_pct'], health['load'],
            health['throttle_hex'], health['is_throttled'],
        ))
        # Get the recorded_at we just wrote so processes get the same timestamp
        cur.execute("SELECT recorded_at FROM t_pi_health WHERE id = LAST_INSERT_ID()")
        recorded_at = cur.fetchone()[0]

        proc_rows = [
            (DEVICE_ID, p['name'], p['pid'], p['cpu'], p['mem'],
             p['command'], recorded_at)
            for p in processes
        ]
        cur.executemany(sql_proc, proc_rows)
        conn.commit()
    finally:
        cur.close()

# ───── Main loop ─────
def main():
    print(f"[START] pi_health_logger device={DEVICE_ID}  "
          f"interval={SAMPLE_INTERVAL_SECONDS}s  top_n={TOP_N_PROCESSES}")

    # Prime psutil so the first iteration gives real percentages
    psutil.cpu_percent(interval=None)

    while True:
        try:
            health = {
                'temp':         read_cpu_temp(),
                'cpu_pct':      read_overall_cpu_pct(),     # includes 1s wait
                'load':         read_load_avg(),
                **dict(zip(('throttle_hex', 'is_throttled'), read_throttle())),
            }
            processes = read_top_processes(TOP_N_PROCESSES)

            conn = pymysql.connect(**DB_CONFIG)
            insert_health_and_processes(conn, health, processes)
            conn.close()

            top1 = processes[0] if processes else {'name': '?', 'cpu': 0}
            print(f"[OK] temp={health['temp']}°C  cpu={health['cpu_pct']:.1f}%  "
                  f"load={health['load']}  top={top1['name']}({top1['cpu']}%)  "
                  f"throttled={health['throttle_hex']}")

        except Error as e:
            print(f"[DB ERROR] {e}")
        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(SAMPLE_INTERVAL_SECONDS)

if __name__ == '__main__':
    main()