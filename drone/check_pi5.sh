#!/bin/bash
echo "=================================================="
echo "     Raspberry Pi 5 - Durian Drone Monitor"
echo "=================================================="
echo "Date     : $(date)"
echo "Hostname : $(hostname)"
echo "Uptime   : $(uptime -p)"
echo "IP       : $(hostname -I | awk '{print $1}')"

echo -e "\n--- Temperature ---"
echo "CPU Temp : $(vcgencmd measure_temp)"
echo "PMIC Temp: $(vcgencmd measure_temp pmic 2>/dev/null || echo 'N/A')"

echo -e "\n--- Throttling & Voltage (สำคัญมาก) ---"
vcgencmd get_throttled
echo "Core Voltage : $(vcgencmd measure_volts core)"

echo -e "\n--- CPU & Memory ---"
echo "CPU Usage : $(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}')"
free -h | grep -v total

echo -e "\n--- Camera Status ---"
vcgencmd get_camera
ls /dev/video* 2>/dev/null || echo "No camera detected"

echo -e "\n--- Disk Usage ---"
df -h /

echo -e "\n=================================================="
echo "พร้อมใช้งานโดรนแล้วหรือยัง? 🚁"
