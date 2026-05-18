import tkinter as tk
from tkinter import font
import ntplib
from datetime import datetime
import time
import pytz
import board
import adafruit_dht

# Set sensor type and GPIO pin
SENSORDHT22 = adafruit_dht.DHT22
DHTPIN = board.D4  # GPIO4

class DigitalClock:
    def __init__(self, root):
        self.root = root
        self.root.title("Digital Clock")
        #self.root.geometry("400x200")
        self.root.configure(bg='black')
        # ตรวจสอบขนาดหน้าจอและทำให้เป็น full screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_width}x{screen_height}")
        self.root.attributes('-fullscreen', True)
        #self.root.bind("<Escape>", self.exit_fullscreen) #ใน raspi5 มี error
        # ลองใช้วิธีอื่นในการกำหนด Escape key
        try:
            # Initialize DHT sensor
            DHT_PIN = board.D4  # Example: DHT sensor connected to GPIO 4
            self.dht_device = adafruit_dht.DHT22(DHT_PIN) # Or adafruit_dht.DHT11, etc.

            self.root.bind("<Escape>", self.exit_fullscreen)
        except Exception as e:
            print(f"ไม่สามารถกำหนด Escape key ได้: {e}")
            # ทางเลือกอื่น: สร้างปุ่มสำหรับออกจาก full screen แทน
            #exit_button = tk.Button(root, text="Exit Fullscreen", command=self.exit_fullscreen)
            #exit_button.place(x=10, y=10)
        # สร้าง main frame
        self.main_frame = tk.Frame(root, bg='black', height=100)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.top_frame = tk.Frame(self.main_frame, bg='black')
        self.top_frame.pack(fill=tk.X, side=tk.TOP, padx=10, pady=10)
        self.bottom_frame = tk.Frame(self.main_frame, bg='black')
        self.bottom_frame.pack(fill=tk.BOTH, expand=True)
        # แบ่ง bottom frame เป็น content_frame และ status_bar
        self.content_frame = tk.Frame(self.bottom_frame, bg='black')
        self.content_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        self.status_bar = tk.Frame(self.bottom_frame, bg='#333333', height=30)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_bar.pack_propagate(False)  # ทำให้มีความสูงคงที่
        
        self.top_frame_date = tk.Frame(self.top_frame, bg='black', width=600)
        self.top_frame_date.pack(fill=tk.X, side=tk.LEFT, padx=10, pady=10)
        #self.top_frame_time = tk.Frame(self.top_frame, bg='black')
        #self.top_frame_time.pack(fill=tk.X, side=tk.CENTER, pady=20)
        #self.top_frame_time.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.top_frame_temp = tk.Frame(self.top_frame, bg='black')
        self.top_frame_temp.pack(fill=tk.X, side=tk.RIGHT, pady=10)
        # Create label for date
        self.date_font = font.Font(family='Helvetica', size=50)
        self.clock_font = font.Font(family='Helvetica', size=120, weight='bold')
        self.temp_font = font.Font(family='Helvetica', size=70, weight='bold')
        self.date_label = tk.Label(self.top_frame_date, font=self.date_font, bg='black', fg='orange')
        self.date_label.pack(side=tk.LEFT,padx=(0, 5),expand=True, pady=(10, 0))

        # Create label for time
        self.time_label = tk.Label(self.top_frame_date, font=self.clock_font, bg='black', fg='white')
        self.time_label.pack(expand=True, pady=(10, 0))
        # Create label for temp humidary
        self.temp_label = tk.Label(self.top_frame_temp, font=self.temp_font, bg='black', fg='white')
        self.temp_label.pack(side=tk.LEFT,expand=True, pady=(10, 0))
        self.humi_label = tk.Label(self.top_frame_temp, font=self.temp_font, bg='black', fg='white')
        self.humi_label.pack(side=tk.RIGHT,expand=True, pady=(10, 0))
        
        # Initialize the DHT device (DHT22 or DHT11)
        dht_device = adafruit_dht.DHT22(DHTPIN)

        # Update time immediately and then every second
        self.update_time()
        self.update_temp_dht22()
    def exit_fullscreen(self, event=None):
        try:
            self.root.attributes("-fullscreen", False)
            self.root.geometry("400x200")
        except Exception as e:
            print(f"Error exiting fullscreen: {e}")
        return "break"
    def get_ntp_time(self):
        try:
            ntp_client = ntplib.NTPClient()
            response = ntp_client.request('pool.ntp.org')
            utc_time = datetime.fromtimestamp(response.tx_time, pytz.UTC)
            # Convert UTC to Thailand time (UTC+7)
            thailand_tz = pytz.timezone('Asia/Bangkok')
            thailand_time = utc_time.astimezone(thailand_tz)
            return thailand_time
        except:
            # Fallback to system time if NTP fails
            thailand_tz = pytz.timezone('Asia/Bangkok')
            return datetime.now(thailand_tz)

    def update_time(self):
        # Get current time from NTP server
        current_time = self.get_ntp_time()
        
        # Update time label
        time_string = current_time.strftime('%H:%M:%S')
        self.time_label.config(text=time_string)
        
        # Update date label
        date_string = current_time.strftime('%d-%m-%Y')
        self.date_label.config(text=date_string)
        
        # Schedule next update
        self.root.after(1000, self.update_time)
    def updat_temp_humi(self):
        try:
            temp = "T : "
            self.temp_label.config(text=temp)
            humi = "H : "
            self.humi_label.config(text=humi)
        except Exception as e:
            print(f"Error exiting fullscreen: {e}")
    def update_temp_dht22(self):
        try:
            temperature_c = self.dht_device.temperature
            humidity = self.dht_device.humidity
            if temperature_c is not None and humidity is not None:
                temperature_f = temperature_c * (9 / 5) + 32
                self.temp_label.config(text=f"T: {temperature_c:.1f}°c ")
                self.humi_label.config(text=f"H: {humidity:.1f}%")
            else:
                self.temp_label.config(text="T: N/A")
                self.humi_label.config(text="H: N/A")
        except RuntimeError as e:
            # Reading doesn't always work! Just print error and we'll try again next time.
            print(f"DHT Reading Error: {e}")
            self.temp_label.config(text="T: Error ")
            self.humi_label.config(text="H: Error")
        self.root.after(2000, self.update_temp_dht22)
if __name__ == "__main__":
    root = tk.Tk()
    clock = DigitalClock(root)
    root.mainloop() 