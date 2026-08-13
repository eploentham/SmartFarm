#!/bin/bash

echo "========================================"
echo " SYSTEM SPEC"
echo "========================================"

echo
echo "=== HOST ==="
echo "Hostname : $(hostname)"
echo "Date     : $(date)"
echo "Uptime   : $(uptime -p)"

echo
echo "=== OS ==="
cat /etc/os-release | grep -E '^(PRETTY_NAME|VERSION_ID)='
echo "Kernel   : $(uname -r)"
echo "Arch     : $(uname -m)"

echo
echo "=== CPU ==="
lscpu | grep -E \
'Model name|Socket|Core|Thread|CPU\(s\)|CPU max MHz|CPU min MHz'

echo
echo "=== MEMORY ==="
free -h

echo
echo "=== DISK ==="
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS

echo
echo "=== DISK USAGE ==="
df -h -x tmpfs -x devtmpfs

echo
echo "=== NETWORK ==="
ip -br addr

echo
echo "=== TEMPERATURE ==="
if command -v sensors >/dev/null 2>&1; then
    sensors
else
    echo "sensors command not installed"
fi

echo
echo "=== PCI DEVICES ==="
lspci | grep -Ei \
'vga|3d|display|network|ethernet|wireless|nvme'

echo
echo "=== USB DEVICES ==="
lsusb

echo
echo "=== PYTHON ==="
python3 --version 2>/dev/null || echo "Python3 not installed"

echo
echo "=== UV ==="
uv --version 2>/dev/null || echo "uv not installed"

echo
echo "========================================"
echo " DONE"
echo "========================================"