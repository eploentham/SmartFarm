#!/bin/bash
# pi_spec.sh - Show Raspberry Pi specs and health
# Works on Pi 3, Pi 4, Pi 5

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

section() {
    echo -e "\n${CYAN}${BOLD}=== $1 ===${NC}"
}

# ====================== MODEL ======================
section "MODEL"
if [ -r /proc/device-tree/model ]; then
    model=$(tr -d '\0' < /proc/device-tree/model)
    echo "Model:     $model"
else
    echo "Model:     unknown"
fi
# Serial number (unique per board)
serial=$(grep Serial /proc/cpuinfo | awk '{print $3}')
echo "Serial:    $serial"
# Revision code
rev=$(grep Revision /proc/cpuinfo | awk '{print $3}')
echo "Revision:  $rev"

# ====================== CPU ======================
section "CPU"
echo "Cores:     $(nproc)"
cpu_model=$(lscpu | grep "Model name" | head -1 | cut -d: -f2 | xargs)
[ -z "$cpu_model" ] && cpu_model=$(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
echo "CPU:       $cpu_model"
echo "Arch:      $(uname -m)"

# Frequency
if [ -r /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq ]; then
    cur=$(($(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq) / 1000))
    max=$(($(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq) / 1000))
    min=$(($(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq) / 1000))
    echo "Freq:      ${cur} MHz now  (min ${min} / max ${max} MHz)"
fi

# Load average
echo "Load avg:  $(uptime | awk -F'load average:' '{print $2}' | xargs)"

# ====================== TEMPERATURE & POWER ======================
section "TEMPERATURE / POWER"
if command -v vcgencmd &> /dev/null; then
    echo "CPU temp:  $(vcgencmd measure_temp | cut -d= -f2)"
    echo "Core volt: $(vcgencmd measure_volts core | cut -d= -f2)"

    # Throttling status - very important for Pi diagnostics
    throttled_hex=$(vcgencmd get_throttled | cut -d= -f2)
    throttled_dec=$((throttled_hex))
    echo "Throttle:  $throttled_hex"

    if [ "$throttled_dec" -eq 0 ]; then
        echo -e "Status:    ${GREEN}OK${NC} - no power/thermal issues"
    else
        echo -e "Status:    ${RED}WARNING${NC} - issues detected:"
        [ $((throttled_dec & 0x1)) -ne 0 ]    && echo -e "  ${RED}• Under-voltage NOW${NC} (power supply too weak)"
        [ $((throttled_dec & 0x2)) -ne 0 ]    && echo -e "  ${RED}• ARM freq capped NOW${NC}"
        [ $((throttled_dec & 0x4)) -ne 0 ]    && echo -e "  ${RED}• Throttled NOW${NC} (CPU slowed down)"
        [ $((throttled_dec & 0x8)) -ne 0 ]    && echo -e "  ${RED}• Soft temp limit NOW${NC}"
        [ $((throttled_dec & 0x10000)) -ne 0 ] && echo -e "  ${YELLOW}• Under-voltage occurred earlier${NC}"
        [ $((throttled_dec & 0x20000)) -ne 0 ] && echo -e "  ${YELLOW}• ARM freq was capped earlier${NC}"
        [ $((throttled_dec & 0x40000)) -ne 0 ] && echo -e "  ${YELLOW}• Throttling occurred earlier${NC}"
        [ $((throttled_dec & 0x80000)) -ne 0 ] && echo -e "  ${YELLOW}• Soft temp limit reached earlier${NC}"
    fi
fi

# ====================== MEMORY ======================
section "MEMORY"
free -h | awk 'NR==1 {printf "%-10s %s\n", "", $0} NR==2 || NR==3 {printf "%-10s %s\n", $1, substr($0, index($0,$2))}'

# ====================== DISK ======================
section "DISK"
df -h / | awk 'NR==1 {printf "%-12s %-6s %-6s %-6s %-5s %s\n", $1, $2, $3, $4, $5, $6}
               NR==2 {printf "%-12s %-6s %-6s %-6s %-5s %s\n", $1, $2, $3, $4, $5, $6}'

# Storage type
if [ -e /dev/mmcblk0 ]; then
    sd_size=$(lsblk -ndo SIZE /dev/mmcblk0 2>/dev/null)
    echo "Boot:      SD card (/dev/mmcblk0, ${sd_size})"
elif [ -e /dev/nvme0n1 ]; then
    nvme_size=$(lsblk -ndo SIZE /dev/nvme0n1 2>/dev/null)
    echo "Boot:      NVMe SSD (/dev/nvme0n1, ${nvme_size})"
fi

# ====================== OS ======================
section "OS"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "OS:        $PRETTY_NAME"
fi
echo "Kernel:    $(uname -r)"

# ====================== NETWORK ======================
section "NETWORK"
echo "Hostname:  $(hostname)"
echo "IP addrs:"
ip -4 addr show 2>/dev/null \
    | grep -E "inet " \
    | grep -v "127.0.0.1" \
    | awk '{print "           " $NF ":  " $2}'

# ====================== UPTIME ======================
section "UPTIME"
echo "Uptime:    $(uptime -p)"
echo "Booted:    $(uptime -s)"

echo ""