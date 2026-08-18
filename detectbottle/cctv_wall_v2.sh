#!/bin/bash
# cctv_wall_v2.sh — CCTV wall on the 55" TV (HDMI-A-1), FIXED 3x2 grid.
#
# Why this version: labwc (Wayland) IGNORES mpv's --geometry, so the old
# "one mpv window per camera + --geometry" approach could not tile them.
# Instead we let ffmpeg COMPOSE all cameras into ONE 3x2 grid image with the
# xstack filter, then pipe that single image to ONE fullscreen mpv window.
# No geometry needed -> Wayland can't mess up the layout.
#
# Grid is fixed 3 columns x 2 rows (6 cells). Empty cells show black.
#
# CHANGE (Aug 2026): now supports MIXED camera brands. VIGI and Hamrol (XMEye)
# use DIFFERENT RTSP URL schemes and DIFFERENT password rules, so every camera
# line now carries its own "type|ip|password". Build the URL per-type.

# ===== EDIT THESE =====
USER="admin"

# --- VIGI settings (TP-Link) ---
VIGI_PASS="Ekartc2c51*"          # VIGI RTSP password (raw, no encoding). May contain symbols.
VIGI_STREAM="stream2"            # sub-stream (640x480) — light on the Pi5.
#VIGI_STREAM="stream1"           # main-stream (2304x1296) — heavy.

# --- Hamrol settings (XMEye, 8MP PoE) ---
# NOTE: Hamrol password MUST be alphanumeric only (no  *  &  @  =).
#       stream=1 -> sub-stream (light). stream=0 -> main 8MP (VERY heavy, avoid on the wall).
HAMROL_STREAM="1"

# Camera list. One line per camera:  "type|ip|password"
#   type = vigi    -> rtsp://USER:PASS@IP:554/<VIGI_STREAM>
#   type = hamrol  -> rtsp://IP:554/user=USER&password=PASS&channel=1&stream=<N>.sdp?real_stream
CAMS=(
  "vigi|192.168.0.251|$VIGI_PASS"
  "vigi|192.168.0.252|$VIGI_PASS"
  "hamrol|192.168.0.241|CHANGEME_alnum"   # <-- Hamrol 8MP: set the ALPHANUMERIC pw here
  "hamrol|192.168.0.240|CHANGEME_alnum" # <-- second Hamrol, uncomment when installed
)

FPS=12                           # output frame rate (lower = lighter on the Pi)
# ======================

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)

GRID_COLS=3
GRID_ROWS=2
CELLS=$(( GRID_COLS * GRID_ROWS ))   # = 6

# --- Build one RTSP URL for a given camera type ---
build_url() {
  local ctype="$1" cip="$2" cpass="$3"
  case "$ctype" in
    vigi)
      echo "rtsp://${USER}:${cpass}@${cip}:554/${VIGI_STREAM}"
      ;;
    hamrol)
      echo "rtsp://${cip}:554/user=${USER}&password=${cpass}&channel=1&stream=${HAMROL_STREAM}.sdp?real_stream"
      ;;
    *)
      echo ""   # unknown type -> empty, caught below
      ;;
  esac
}

# --- Quick liveness check for one camera (fault tolerance) ---
# Returns 0 (alive) if ffprobe can open the RTSP stream within the time budget,
# else non-zero. The shell `timeout` HARD-kills ffprobe after PROBE_SECS no
# matter what, so a dead/offline camera can never hang the wall at startup.
PROBE_SECS=6
probe_cam() {
  local url="$1"
  timeout "${PROBE_SECS}" ffprobe -rtsp_transport tcp -loglevel quiet \
    -i "$url" >/dev/null 2>&1
}

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

echo "Wall: $n camera(s) in a ${GRID_COLS}x${GRID_ROWS} grid, each tile ${CW}x${CH}"

# --- Build ffmpeg inputs (FAULT TOLERANT) ---
# Each camera keeps its OWN fixed cell (stable positions). A camera that is
# offline / broken / unknown-type becomes a BLACK tile instead of killing the
# whole wall. If a live camera dies mid-stream, ffmpeg errors out, the restart
# loop re-probes, and that camera then becomes a black tile automatically.
BLACK_TILE=( -f lavfi -i "color=c=black:s=${CW}x${CH}:r=${FPS}" )
live=0
inputs=()
for entry in "${CAMS[@]}"; do
  IFS='|' read -r ctype cip cpass <<< "$entry"
  url="$(build_url "$ctype" "$cip" "$cpass")"
  if [ -z "$url" ]; then
    echo "WARN: unknown camera type in '$entry' -> black tile" >&2
    inputs+=( "${BLACK_TILE[@]}" )
  elif probe_cam "$url"; then
    echo "OK  : ${cip} live"
    inputs+=( -rtsp_transport tcp -i "$url" )
    live=$(( live + 1 ))
  else
    echo "DOWN: ${cip} not responding -> black tile"
    inputs+=( "${BLACK_TILE[@]}" )
  fi
done
# Pad any remaining empty cells with black.
for (( k=${#CAMS[@]}; k<CELLS; k++ )); do
  inputs+=( "${BLACK_TILE[@]}" )
done

echo "Live cameras: ${live}/${#CAMS[@]}"
if [ "$live" -eq 0 ]; then
  echo "No cameras are reachable right now — retrying in 15s ..."
  sleep 15
  exec "$0"   # restart from scratch; a camera may have come back
fi

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