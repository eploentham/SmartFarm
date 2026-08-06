#!/bin/bash
# cctv_wall.sh — CCTV wall on the 55" TV (HDMI-A-1), FIXED 3x2 grid.
#
# Why this version: labwc (Wayland) IGNORES mpv's --geometry, so the old
# "one mpv window per camera + --geometry" approach could not tile them.
# Instead we let ffmpeg COMPOSE all cameras into ONE 3x2 grid image with the
# xstack filter, then pipe that single image to ONE fullscreen mpv window.
# No geometry needed -> Wayland can't mess up the layout.
#
# Grid is fixed 3 columns x 2 rows (6 cells). Empty cells show black.
# Add cameras by adding their IP to CAMS (up to 6).

# ===== EDIT THESE =====
USER="admin"
PASS="Ekartc2c51*"                       # the VIGI RTSP password (raw, no encoding)
CAMS=(
  "192.168.0.251"
  "192.168.0.252"
  # "192.168.0.253"              # <- uncomment as you install more (max 6)
  # "192.168.0.254"
  # "192.168.0.255"
  # "192.168.0.256"
)
STREAM="stream2"                 # sub-stream (640x480) — MUCH lighter on Pi5.
#STREAM="stream1"                # main-stream (2304x1296) — heavy: 5-6 of these
                                 # will overload the Pi5 (software H.264 decode).
FPS=12                           # output frame rate (lower = lighter on the Pi)
# ======================

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)

GRID_COLS=3
GRID_ROWS=2
CELLS=$(( GRID_COLS * GRID_ROWS ))   # = 6

# --- Screen size of HDMI-A-1 (auto-read; falls back to 1920x1080) ---
read SW SH < <(wlr-randr | awk '
  /^[^ \t]/ { inblk = ($1=="HDMI-A-1") }
  inblk && /current/ { split($1,m,"x"); print m[1], m[2]; exit }')
: "${SW:=1920}"; : "${SH:=1080}"

# Each tile size (integer division; grid fills the whole screen).
CW=$(( SW / GRID_COLS ))
CH=$(( SH / GRID_ROWS ))

n=${#CAMS[@]}
[ "$n" -eq 0 ] && { echo "No cameras in CAMS."; exit 1; }
[ "$n" -gt "$CELLS" ] && { echo "Max $CELLS cameras for a ${GRID_COLS}x${GRID_ROWS} grid."; exit 1; }

# --- Close any previous wall ---
pkill -f "mpv.*--really-quiet" 2>/dev/null
pkill -f "ffmpeg.*xstack"      2>/dev/null
sleep 1

echo "Wall: $n camera(s) in a ${GRID_COLS}x${GRID_ROWS} grid, each tile ${CW}x${CH} (stream=$STREAM)"

# --- Build ffmpeg inputs ---
# Real cameras first (indices 0..n-1), then black fillers for empty cells.
inputs=()
for ip in "${CAMS[@]}"; do
  inputs+=( -rtsp_transport tcp -i "rtsp://${USER}:${PASS}@${ip}:554/${STREAM}" )
done
for (( k=n; k<CELLS; k++ )); do
  inputs+=( -f lavfi -i "color=c=black:s=${CW}x${CH}:r=${FPS}" )
done

# --- Build the filter graph ---
# 1) scale each of the 6 inputs to one tile size, fix SAR (xstack needs equal SAR)
# 2) xstack them into the 3x2 layout
filter=""
for (( idx=0; idx<CELLS; idx++ )); do
  filter+="[${idx}:v]scale=${CW}:${CH},setsar=1,fps=${FPS}[v${idx}];"
done
# 3x2 layout (tiles are uniform, so w0/h0 = tile size for every reference)
layout="0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0"
filter+="[v0][v1][v2][v3][v4][v5]xstack=inputs=${CELLS}:layout=${layout}[out]"

# --- Run: ffmpeg composes the grid -> pipe raw frames -> one fullscreen mpv ---
# Wrapped in a loop so if a camera drops (ffmpeg exits) the wall auto-restarts.
echo "Starting wall.  Stop it with:  pkill -f 'mpv.*--really-quiet'"
while true; do
  ffmpeg -hide_banner -loglevel error \
    "${inputs[@]}" \
    -filter_complex "$filter" -map "[out]" \
    -c:v rawvideo -pix_fmt yuv420p -f nut - 2>/dev/null \
  | mpv - \
      --no-audio \
      --fullscreen \
      --no-border \
      --no-osc --no-input-default-bindings --really-quiet \
      --profile=low-latency \
      >/dev/null 2>&1

  # If we get here, the pipe died (camera drop / mpv closed).
  # Small pause, then rebuild the wall. Break out if user killed mpv on purpose.
  pgrep -f "mpv.*--really-quiet" >/dev/null && break
  echo "$(date '+%H:%M:%S') wall pipeline ended — restarting in 5s ..."
  sleep 5
done