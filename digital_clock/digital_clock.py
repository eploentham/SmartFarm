import argparse
import re
import subprocess
import tkinter as tk
from tkinter import font
import ntplib
import time
from datetime import datetime
import pytz
import mysql.connector
#   systemctl list-units --all | grep -i clock
# หรือหาไฟล์ service
#   ls /etc/systemd/system/ | grep -i clock
#pkill -f digital_clock.py
#pkill -f mpv
#pkill -f cctv_wall
#   sudo wayvncctl --socket=/tmp/wayvnc/wayvncctl.sock output-set HDMI-A-1
# Last edited: 2026-05-19 by Ekapop P. (Added rain duration details)
# Last edited: 2026-06-09 by Ekapop P. (Added Lightning, Wind detection API)
# Last edited: 2026-07-06 by Ekapop P. (Added get_display_geometry)
db_config = {    'host': 'localhost',    'user': 'ekapop',    'password': 'Ekartc2c51*',    'database': 'smartfarm'}

"""
Possible return values:
  - "ฝนตกอยู่"             when currently raining
  - "ฝนหยุดวันนี้"          when rain stopped today
  - "ฝนไม่ตกแล้ว X วัน"     when it's been X days since last rain
  - "ยังไม่มีข้อมูลฝน"      when no rain has ever been recorded
  - "อ่านข้อมูลไม่ได้"      on database error (fail-safe)
"""
def get_display_geometry(display_name):
    """หาตำแหน่งและขนาดของจอที่ระบุจาก wlr-randr

    Returns (x, y, width, height) for the requested display.
    Falls back to (1920, 0, 1920, 1080) — the expected HDMI-A-2 position
    on a typical dual-monitor pi5camera01 setup — if detection fails.
    """
    try:
        result = subprocess.run(
            ["wlr-randr"], capture_output=True, text=True, timeout=5,
        )
        output = result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print(f"⚠ wlr-randr not available — falling back to (1920,0) 1920x1080")
        return (1920, 0, 1920, 1080)

    # wlr-randr blocks start with a name at column 0, followed by indented details
    blocks = re.split(r"\n(?=\S)", output)
    for block in blocks:
        if block.strip().startswith(display_name):
            pos_match = re.search(r"Position:\s*(\d+),(\d+)", block)
            active_mode = re.search(
                r"(\d+)x(\d+)\s+px.*current", block, re.IGNORECASE,
            )
            any_mode = re.search(r"(\d+)x(\d+)\s+px", block)
            mode_match = active_mode or any_mode

            x = int(pos_match.group(1)) if pos_match else 0
            y = int(pos_match.group(2)) if pos_match else 0
            w = int(mode_match.group(1)) if mode_match else 1920
            h = int(mode_match.group(2)) if mode_match else 1080
            print(f"✓ Display {display_name}: {w}x{h} at ({x},{y})")
            return (x, y, w, h)

    print(f"⚠ Display '{display_name}' not found — using fallback (1920,0) 1920x1080")
    return (1920, 0, 1920, 1080)


class DigitalClock:
    def __init__(self, root, target_display=None):
        """
        target_display: tuple (x, y, width, height) — position and size
                        for the clock window. If None, uses the old
                        full-screen-on-primary-display behavior.
        """
        self.root = root
        self.root.title("Digital Clock")
        self.root.configure(bg='black')

        if target_display is not None:
            # Pinned to a specific display: use borderless positioned window
            x, y, screen_width, screen_height = target_display
            self.root.geometry(f"{screen_width}x{screen_height}+{x}+{y}")
            self.root.overrideredirect(True)   # no title bar, no borders
            self.root.attributes('-topmost', True)  # stay above other windows
            self.root.focus_force()            # take keyboard focus so ESC works
        else:
            # Legacy behavior: fullscreen on the primary display
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.attributes('-fullscreen', True)

        # ผูกปุ่ม ESC เพื่อออก, F11 เพื่อสลับโหมด
        self.root.bind('<Escape>', self.exit_fullscreen)
        self.root.bind('<F11>', self.toggle_fullscreen)

        # คำนวณขนาดฟอนต์
        time_font_size = int(screen_height / 5)
        date_font_size = int(screen_height / 20)
        temp_font_size = int(screen_height / 40)

        self.clock_font = font.Font(family='Loma', size=time_font_size, weight='bold')
        self.date_font = font.Font(family='Loma', size=date_font_size)
        self.info_font = font.Font(family='Loma', size=int(date_font_size / 2))
        self.temp_font = font.Font(family='Loma', size=temp_font_size)

        # คำนวณตำแหน่งเป็น pixel จริง
        center_x = screen_width // 2
        time_y = int(time_font_size * 0.6)                        # เวลาอยู่บนสุด
        date_y = time_y + int(time_font_size * 0.85)              # วันที่ห่างจากเวลา
        temp_y = date_y

        # Label เวลา
        self.time_label = tk.Label(root, font=self.clock_font, bg='black', fg='#00FF00')
        self.time_label.place(x=center_x, y=time_y, anchor='center')

        # Label วันที่ - ชิดซ้าย
        self.date_label = tk.Label(root, font=self.date_font, bg='black', fg='white')
        self.date_label.place(x=20, y=date_y, anchor='w')

        # Label อุณหภูมิ/ความชื้น - มุมขวาบน ระดับวันที่
        self.temp_label = tk.Label(root, font=self.temp_font, bg='black', fg='#FFA500')
        self.temp_label.place(relx=0.98, y=temp_y, anchor='e')
        self.temp_label.config(text="T: --°C  H: --%")
        # Label rain status - มุมขวาบน ระดับวันที่ ต่ำกว่าอุณหภูมิ
        self.rain_label = tk.Label(root, font=self.temp_font, bg='black', fg='#00BFFF')
        self.rain_label.place(relx=0.98, y=temp_y + int(temp_font_size * 1.8)+90, anchor='e')
        self.rain_label.config(text="ฝน: --")
        # Label สถานะแสง - มุมขวา ใต้ rain (รอเอียดข้อความหลายบรรทัด)
        light_y = temp_y + int(temp_font_size * 1.8) + 90 + int(temp_font_size * 8.5)
        self.light_label = tk.Label(            root, font=self.temp_font, bg='black', fg='#FFD700',            justify='right'        )
        self.light_label.place(relx=0.98, y=light_y, anchor='e')
        self.light_label.config(text="แสง: --")

        # Label สถานะลม - ใต้ light
        wind_y = light_y + int(temp_font_size * 5)+130
        self.wind_label = tk.Label(            root, font=self.temp_font, bg='black', fg='#87CEEB',            justify='right'        )
        self.wind_label.place(relx=0.98, y=wind_y, anchor='e')
        self.wind_label.config(text="ลม: --")

        # Label งานที่ต้องทำ
        task_font_size = int(screen_height / 24)
        self.task_font = font.Font(family='Loma', size=task_font_size)

        # ตำแหน่ง y ของแต่ละ task
        task_y_start = date_y + int(date_font_size * 1.5) + int(task_font_size * 0.5)
        task_spacing = int(task_font_size * 2.0)

        self.task_label1 = tk.Label(root, text="1.  ขี้ไก่ เอาลงสวน ทรงพุ่ม", font=self.task_font,bg='black', fg='#FFFFFF', anchor='w', justify='left'        )
        self.task_label1.place(x=20, y=task_y_start, anchor='w')

        self.task_label2 = tk.Label(
            root, text="2.  เอาเกลือ3กระสอบที่ซื้อมา ปูที่บ่อบน", font=self.task_font,
            bg='black', fg='#FFFFFF', anchor='w', justify='left'
        )
        self.task_label2.place(x=20, y=task_y_start + task_spacing, anchor='w')

        self.task_label3 = tk.Label(
            root, text="3.  เก็บเม็ด ต้นคูน เพาะแล้วปลูก", font=self.task_font,
            bg='black', fg='#FFFFFF', anchor='w', justify='left'
        )
        self.task_label3.place(x=20, y=task_y_start + task_spacing * 2, anchor='w')

        self.task_label4 = tk.Label(
            root, text="4.  เม็ดทุเรียนขึ้นต้นแล้วหรือยัง", font=self.task_font,
            bg='black', fg='#FFFFFF', anchor='w', justify='left'
        )
        self.task_label4.place(x=20, y=task_y_start + task_spacing * 3, anchor='w')

        self.task_label5 = tk.Label(
            root, text="5.  จะทำยังไง ไม่ให้ ต้นคูน ถูกตัด ต้นยางนา ถูกตัด", font=self.task_font,
            bg='black', fg='#FFFFFF', anchor='w', justify='left'
        )
        self.task_label5.place(x=20, y=task_y_start + task_spacing * 4, anchor='w')

        # ตัวแปรสถานะ NTP
        self.ntp_synced = False
        self.last_ntp_sync = 0
        self.ntp_offset = 0

        # ซิงค์ NTP ครั้งแรก
        self.sync_ntp()

        # เริ่มอัปเดตเวลาและข้อมูล
        self.update_time()
        self.update_temp_from_db()
        self.update_rain_status()
        self.update_weather_status()
    def update_rain_status(self):
        """อัปเดตสถานะฝน"""
        rain_status = self.get_rain_status_text()
        self.rain_label.config(text=f"ฝน: {rain_status}")
        # อัปเดตทุก 30 วินาที
        self.root.after(5000, self.update_rain_status)
    def get_rain_status_text(self):
        """
        Query the database and return a Thai status string.
        Never raises - returns a fallback message on error.
        """
        try:
            conn = mysql.connector.connect(**db_config, connection_timeout=5)
            cursor = conn.cursor()
    
            # 1. Check if currently raining (most recent decision)
            cursor.execute("""            SELECT truly_raining             FROM t_rain_decision             ORDER BY id DESC             LIMIT 1        """)
            latest = cursor.fetchone()
    
            if latest and latest[0] == 1:
                cursor.close()
                conn.close()
                return "ฝนตกอยู่"  # raining right now
    
            # 2. Find the last time it was truly raining
            cursor.execute("""            SELECT MAX(timestamp)              FROM t_rain_decision             WHERE truly_raining = 1        """)
            result = cursor.fetchone()
            #cursor.close()

            cursor.execute(""" SELECT SUM(truly_raining) * 0.5 AS minutes_raining_yesterday, MIN(timestamp) AS first_rain, MAX(timestamp) AS last_rain FROM t_rain_decision WHERE DATE(timestamp) = CURDATE()   AND truly_raining = 1;        """)
            resulttoday = cursor.fetchone()
            #cursor.close()
            cursor.execute(""" SELECT SUM(truly_raining) * 0.5 AS minutes_raining_yesterday, MIN(timestamp) AS first_rain, MAX(timestamp) AS last_rain FROM t_rain_decision WHERE DATE(timestamp) = CURDATE() - INTERVAL 1 DAY   AND truly_raining = 1;        """)
            resultyesterday = cursor.fetchone()
            cursor.execute(""" SELECT SUM(truly_raining) * 0.5 AS minutes_raining_two_days_ago, MIN(timestamp) AS first_rain, MAX(timestamp) AS last_rain FROM t_rain_decision WHERE DATE(timestamp) = CURDATE() - INTERVAL 2 DAY   AND truly_raining = 1;        """)
            resulttwo_days_ago = cursor.fetchone()
            cursor.close()

            conn.close()

            if result is None or result[0] is None:
                return "ยังไม่มีข้อมูลฝน"  # no rain data yet
    
            last_rain = result[0]
            now = datetime.now()
            delta = now - last_rain
            days = delta.days
    
            if days == 0:#meaning it rained at least once today, so we can report the last rain time in a more user-friendly way
                date1 = result[0]
                if now.date() > date1.date():
                    txtrain = "ฝนหยุดตกไปเมื่อ " + date1.strftime('%d %H:%M')
                    if(resulttoday[0] is not None and resulttoday[0] > 0):
                        txtrain += f"\n(วันนี้ ฝนตกไปแล้ว {resulttoday[0]:.1f} นาที)"
                    else:
                        txtrain += "\n(วันนี้ ฝนยังไม่ตกเลย)"
                    if(resultyesterday[0] is not None and resultyesterday[0] > 0):
                        txtrain += f"\n(เมื่อวาน ฝนตกไปแล้ว {resultyesterday[0]:.1f} นาที)"
                    else:
                        txtrain += "\n(เมื่อวาน ฝนยังไม่ตกเลย)"
                    if(resulttwo_days_ago[0] is not None and resulttwo_days_ago[0] > 0):
                        txtrain += f"\n(สองวันก่อน ฝนตกไปแล้ว {resulttwo_days_ago[0]:.1f} นาที)"
                    else:
                        txtrain += "\n(สองวันก่อน ฝนยังไม่ตกเลย)"
                    return txtrain  # rain stopped today
                else:
                    txtrain = "ฝนหยุดวันนี้ " + date1.strftime('%d %H:%M') + " "
                    if(resulttoday[0] is not None and resulttoday[0] > 0):
                        txtrain += f"\n(วันนี้ ฝนตกไปแล้ว {resulttoday[0]:.1f} นาที)."
                    else:
                        txtrain += "\n(วันนี้ ฝนยังไม่ตกเลย)"
                    if(resultyesterday[0] is not None and resultyesterday[0] > 0):
                        txtrain += f"\n(เมื่อวาน ฝนตกไปแล้ว {resultyesterday[0]:.1f} นาที)"
                    else:
                        txtrain += "\n(เมื่อวาน ฝนยังไม่ตกเลย)"
                    if(resulttwo_days_ago[0] is not None and resulttwo_days_ago[0] > 0):
                        txtrain += f"\n(สองวันก่อน ฝนตกไปแล้ว {resulttwo_days_ago[0]:.1f} นาที)"
                    else:
                        txtrain += "\n(สองวันก่อน ฝนยังไม่ตกเลย)"
                    return txtrain  # rain stopped today
            else:
                return f"ฝนไม่ตกแล้ว {days} วัน"
    
        except Exception as e:
            # Print so we see it in the console if running interactively
            print(f"rain_status error: {e}")
            return "อ่านข้อมูลไม่ได้"  # fail-safe on DB error
    def update_weather_status(self):
        """ดึงสถานะแสง/ลม จาก views"""
        try:
            conn = mysql.connector.connect(**db_config, connection_timeout=5)
            cursor = conn.cursor()

            # แสงรายชั่วโมง (ล่าสุดที่เป็น actual)
            cursor.execute("""
                SELECT solar_wm2, light_level, plant_status, cloud_cover
                FROM v_light_status_hourly
                WHERE record_time <= NOW() AND is_forecast = 0
                ORDER BY record_time DESC LIMIT 1
            """)
            light_row = cursor.fetchone()

            # ลมรายชั่วโมง
            cursor.execute("""
                SELECT wind_kmh, gust_kmh, dir_compass, spray_decision, gust_assessment
                FROM v_wind_status_hourly
                WHERE record_time <= NOW() AND is_forecast = 0
                ORDER BY record_time DESC LIMIT 1
            """)
            wind_row = cursor.fetchone()

            # แสงรวมวันนี้
            cursor.execute("""
                SELECT solar_mj_day, overall, durian_status
                FROM v_light_status_daily
                WHERE record_date = CURDATE()
                LIMIT 1
            """)
            daily_row = cursor.fetchone()

            cursor.close()
            conn.close()

            # อัปเดต label แสง
            if light_row:
                solar, level, status, cloud = light_row
                txt = f"แสง: {solar:.0f} W/m² ({level})"
                txt += f"\n{status}  เมฆ: {cloud:.0f}%"
                if daily_row:
                    mj, overall, durian = daily_row
                    txt += f"\nรวมวันนี้: {mj:.1f} MJ ({overall})"
                    txt += f"\nทุเรียน: {durian}"
                self.light_label.config(text=txt)
            else:
                self.light_label.config(text="แสง: ไม่มีข้อมูล")

            # อัปเดต label ลม
            if wind_row:
                wind, gust, dir_c, spray, gust_a = wind_row
                self.wind_label.config(
                    text=f"ลม: {wind:.1f} km/h ({dir_c})  กระโชก: {gust:.1f}"
                         f"\n{spray}"
                         f"\nกระโชก: {gust_a}"
                )
            else:
                self.wind_label.config(text="ลม: ไม่มีข้อมูล")

        except Exception as e:
            print(f"Weather status error: {e}")
            self.light_label.config(text="แสง: Error")
            self.wind_label.config(text="ลม: Error")

        # อัปเดตทุก 5 นาที (ข้อมูลรายชั่วโมง)
        self.root.after(300000, self.update_weather_status)
    def update_temp_from_db(self):
        """ดึงข้อมูลอุณหภูมิ/ความชื้นล่าสุดจากฐานข้อมูล"""
        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute("SELECT temperature, humidity, timestamp, sensor_device FROM t_sensor ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row:
                temperature_c, humidity, timestamp, sensor_device = row
                sensor1 = "" # แปลงชื่ออุปกรณ์เป็น sensor1, sensor2, etc.
                if sensor_device == 'nw01_home01_DHT22_01':
                    sensor1 = 'ครัว'
                self.temp_label.config(text=f"T: {temperature_c:.1f}°C  H: {humidity:.1f}%  ({timestamp.strftime('%H:%M')})  [{sensor1}]")
            else:
                self.temp_label.config(text="T: N/A  H: N/A")
        except Exception as e:
            print(f"DB Error: {e}")
            self.temp_label.config(text="T: Error  H: Error")

        # อัปเดตทุก 5 วินาที
        self.root.after(5000, self.update_temp_from_db)

    def sync_ntp(self):
        """ซิงค์เวลากับ NTP server"""
        try:
            ntp_client = ntplib.NTPClient()
            response = ntp_client.request('pool.ntp.org', timeout=3)
            self.ntp_offset = response.tx_time - time.time()
            self.ntp_synced = True
            self.last_ntp_sync = time.time()
            print("NTP sync สำเร็จ")
        except Exception as e:
            self.ntp_synced = False
            self.last_ntp_sync = time.time()
            print(f"NTP sync ไม่สำเร็จ: {e}")

    def get_current_time(self):
        """ดึงเวลาปัจจุบัน"""
        thailand_tz = pytz.timezone('Asia/Bangkok')
        if self.ntp_synced:
            current_timestamp = time.time() + self.ntp_offset
            return datetime.fromtimestamp(current_timestamp, thailand_tz)
        else:
            return datetime.now(thailand_tz)

    def update_time(self):
        # ซิงค์ NTP ใหม่ทุก 30 นาที
        if time.time() - self.last_ntp_sync > 1800:
            self.sync_ntp()

        current_time = self.get_current_time()

        # อัปเดตเวลา
        time_string = current_time.strftime('%H:%M:%S')
        self.time_label.config(text=time_string)

        # ตารางสีประจำวัน (เริ่มจากวันจันทร์ = 0)
        day_colors = {
            0: '#FFD700',  # จันทร์ - เหลืองทอง
            1: '#FF69B4',  # อังคาร - ชมพู
            2: '#00CC00',  # พุธ - เขียว
            3: '#FF8C00',  # พฤหัสบดี - ส้ม
            4: '#00BFFF',  # ศุกร์ - ฟ้า
            5: '#9370DB',  # เสาร์ - ม่วง
            6: '#FF0000',  # อาทิตย์ - แดง
        }
        # เปลี่ยนสีเวลาตามวัน
        self.time_label.config(fg=day_colors[current_time.weekday()])

        # อัปเดตวันที่ (ภาษาไทย พ.ศ.)
        thai_days = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
        thai_months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']

        day_name = thai_days[current_time.weekday()]
        month_name = thai_months[current_time.month - 1]
        thai_year = current_time.year + 543
        date_string = f"วัน{day_name} {current_time.day} {month_name} {thai_year}"
        self.date_label.config(text=date_string)

        # อัปเดตทุก 1 วินาที
        self.root.after(1000, self.update_time)

    def toggle_fullscreen(self, event=None):
        is_fullscreen = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not is_fullscreen)

    def exit_fullscreen(self, event=None):
        self.root.attributes('-fullscreen', False)
        self.root.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Digital clock with weather / rain / task display, "
                    "pinnable to a specific HDMI display on the Pi 5."
    )
    parser.add_argument(
        "--display",
        default="HDMI-A-2",
        help="Target display name (default: HDMI-A-2 = 24\" monitor on pi5camera01). "
             "Pass 'auto' to use the old primary-display fullscreen behavior.",
    )
    args = parser.parse_args()

    if args.display.lower() == "auto":
        target = None
        print("Using primary-display fullscreen (auto mode)")
    else:
        target = get_display_geometry(args.display)

    root = tk.Tk()
    clock = DigitalClock(root, target_display=target)
    root.mainloop()