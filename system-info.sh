#!/bin/bash

echo "===== HOSTNAME ====="
hostname

echo
echo "===== OS ====="
cat /etc/os-release

echo
echo "===== KERNEL ====="
uname -a

echo
echo "===== CPU ====="
lscpu | grep -E 'Model name|Socket|Core|Thread|CPU\(s\)'

echo
echo "===== MEMORY ====="
free -h

echo
echo "===== DISK ====="
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT

echo
echo "===== DISK USAGE ====="
df -h

echo
echo "===== IP ADDRESS ====="
hostname -I

echo
echo "===== UPTIME ====="
uptime

echo
echo "===== TEMPERATURE ====="
sensors 2>/dev/null || echo "lm-sensors not installed"