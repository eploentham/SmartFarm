#!/bin/bash
# cctv_wall.sh — CCTV wall on the 55" TV (HDMI-A-1) using mpv (no browser, no go2rtc).
#
# Plays VIGI cameras' sub-stream (stream2, low-res) directly over RTSP.
# Auto-arranges by how many cameras you list:
#   1 → fullscreen   2 → side by side   3-4 → 2x2   5-6 → 2x3
#
# Add cameras later by adding their IP to CAMS below — the layout adjusts itself.

# ===== EDIT THESE =====
USER="admin"
PASS="Ekartc2c51*"                 # the VIGI password that worked (Ekartc5...)
CAMS=(
  "192.168.0.251"
  "192.168.0.250"   # <- uncomment / add IPs as you install more cameras
  "192.168.0.249"
  # "192.168.0.254"
  # "192.168.0.255"
  # "192.168.0.256"
)
#STREAM="stream2"                 # sub-stream (low-res) — light on the Pi
STREAM="stream1"                # main-stream (high-res) — heavy on the Pi
# ======================

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)

# Screen size of HDMI-A-1 (auto-read; falls back to 1920x1080).
read SW SH < <(wlr-randr | awk '
  /^[^ \t]/ { inblk = ($1=="HDMI-A-1") }
  inblk && /current/ { split($1,m,"x"); print m[1], m[2]; exit }')
: "${SW:=1920}"; : "${SH:=1080}"

n=${#CAMS[@]}
[ "$n" -eq 0 ] && { echo "No cameras in CAMS."; exit 1; }

# Decide grid: columns x rows.
if   [ "$n" -le 1 ]; then cols=1; rows=1
elif [ "$n" -le 2 ]; then cols=2; rows=1
elif [ "$n" -le 4 ]; then cols=2; rows=2
else                      cols=3; rows=2
fi
cw=$(( SW / cols ))
ch=$(( SH / rows ))

# Close any previous wall.
pkill -f "mpv.*rtsp://" 2>/dev/null
sleep 1

echo "Wall: $n camera(s) → ${cols}x${rows} grid, each tile ${cw}x${ch}"

i=0
for ip in "${CAMS[@]}"; do
  col=$(( i % cols ))
  row=$(( i / cols ))
  x=$(( col * cw ))
  y=$(( row * ch ))
  url="rtsp://${USER}:${PASS}@${ip}:554/${STREAM}"

  mpv "$url" \
    --no-audio \
    --profile=low-latency \
    --rtsp-transport=tcp \
    --no-border \
    --no-osc --no-input-default-bindings --really-quiet \
    --geometry=${cw}x${ch}+${x}+${y} \
    --loop=inf \
    >/dev/null 2>&1 &

  i=$(( i + 1 ))
done

echo "Started $n mpv window(s) on the 55\" TV."
echo "To stop the wall:  pkill -f 'mpv.*rtsp://'"