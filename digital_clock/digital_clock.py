import tkinter as tk
from tkinter import font
import ntplib
from datetime import datetime
import time
import pytz

class DigitalClock:
    def __init__(self, root):
        self.root = root
        self.root.title("Digital Clock")
        self.root.geometry("400x200")
        self.root.configure(bg='black')
        
        # Create a custom font
        self.clock_font = font.Font(family='Helvetica', size=60, weight='bold')
        
        # Create label for time
        self.time_label = tk.Label(root, font=self.clock_font, bg='black', fg='white')
        self.time_label.pack(expand=True, pady=(20, 0))
        
        # Create label for date
        self.date_font = font.Font(family='Helvetica', size=16)
        self.date_label = tk.Label(root, font=self.date_font, bg='black', fg='white')
        self.date_label.pack(expand=True, pady=(20, 0))
        
        # Update time immediately and then every second
        self.update_time()
        
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
        date_string = current_time.strftime('%Y-%m-%d')
        self.date_label.config(text=date_string)
        
        # Schedule next update
        self.root.after(1000, self.update_time)

if __name__ == "__main__":
    root = tk.Tk()
    clock = DigitalClock(root)
    root.mainloop() 