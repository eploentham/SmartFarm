#!/bin/bash
# run_kiosk.sh — spray dashboard fullscreen on the 55" TV (HDMI-A-1).
#
# WHY XWayland: labwc can't reliably send a *fullscreen* window to a chosen
# output, so we position the window by pixel coordinates instead. Chromium
# honors --window-position ONLY under XWayland (x11), not Wayland ozone.
#
# Start tv_display.py first, then run this.

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)

OUTPUT="HDMI-A-1"
URL="http://localhost:5000"

# --- Read HDMI-A-1 position + current resolution from wlr-randr ------------
geom=$(wlr-randr | awk -v out="$OUTPUT" '
  $1==out {found=1; next}
  found && /Position:/ {split($2,p,","); px=p[1]; py=p[2]}
  found && /current/   {split($1,m,"x"); print px","py","m[1]","m[2]; exit}
')
IFS=',' read -r X Y W H <<< "$geom"

if [ -z "$X" ]; then
  echo "Could not read $OUTPUT geometry from wlr-randr. Run 'wlr-randr' and check the name."
  exit 1
fi
echo "Placing kiosk on $OUTPUT at ${X},${Y}, size ${W}x${H}"

# --- Launch Chromium under XWayland, positioned on HDMI-A-1 ----------------
chromium-browser \
  --app="$URL" \
  --ozone-platform=x11 \
  --window-position="${X},${Y}" \
  --window-size="${W},${H}" \
  --start-fullscreen \
  --noerrdialogs \
  --disable-infobars \
  --incognito \
  --check-for-update-interval=31536000

# If --start-fullscreen lands on the wrong screen, remove that line: the
# --window-position/--window-size already cover HDMI-A-1 exactly (borderless
# via --app), so the window fills the TV without needing fullscreen.