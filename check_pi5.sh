#!/bin/bash
echo "=== Raspberry Pi 5 System Check ==="
echo "Model: $(cat /sys/firmware/devicetree/base/model)"
echo "Kernel: $(uname -r)"
echo "Uptime: $(uptime -p)"
echo "IP Address: $(hostname -I | awk '{print $1}')"

echo -e "\n--- CPU & Temperature ---"
echo "CPU Temp: $(vcgencmd measure_temp)"
echo "PMIC Temp: $(vcgencmd measure_temp pmic 2>/dev/null || echo 'N/A')"
echo "CPU Clock: $(( $(vcgencmd measure_clock arm | cut -d= -f2) / 1000000 )) MHz"
echo "GPU Clock: $(( $(vcgencmd measure_clock core | cut -d= -f2) / 1000000 )) MHz"

echo -e "\n--- Memory & Load ---"
free -h
echo "Load Average: $(cat /proc/loadavg | awk '{print $1 " " $2 " " $3}')"

echo -e "\n--- Voltage & Throttling ---"
echo "Core Voltage: $(vcgencmd measure_volts core)"
vcgencmd get_throttled

echo -e "\n--- Disk Usage ---"
df -h / 

echo -e "\n--- GPIO & Camera Status ---"
vcgencmd get_camera
ls /dev/video* 2>/dev/null || echo "No camera detected"