#!/bin/bash
# run_kiosk.sh — CCTV wall (tv_display.py) on the 55" TV (HDMI-A-1), via chromium.
#
# ONE-TIME prerequisite (removes the stale flag the wrapper injects):
#   sudo sed -i 's/ --js-flags=--no-decommit-pooled-pages//' /usr/bin/chromium
#
# Runs Chromium in the BACKGROUND and logs to /tmp/kiosk.log, so the terminal
# stays free and you can look at the TV.

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)

URL="http://localhost:5000"
BROWSER=$(command -v chromium || command -v chromium-browser)

# Arrange outputs: 55" TV at top-left (0,0), 24" to its right.
wlr-randr --output HDMI-A-1 --pos 0,0    >/dev/null 2>&1
wlr-randr --output HDMI-A-2 --pos 1920,0 >/dev/null 2>&1

pkill -f "chromium.*localhost:5000" 2>/dev/null
sleep 1

"$BROWSER" \
  --ozone-platform=wayland \
  --kiosk "$URL" \
  --autoplay-policy=no-user-gesture-required \
  --user-data-dir=/tmp/kiosk \
  --noerrdialogs \
  --disable-infobars \
  --incognito \
  --check-for-update-interval=31536000 \
  > /tmp/kiosk.log 2>&1 &

echo "Kiosk launched (PID $!). 👉 LOOK AT THE 55\" TV now (give it ~5 seconds)."
echo "If nothing appears:   cat /tmp/kiosk.log   (paste it to me)"
echo "To stop the kiosk:    pkill -f 'chromium.*localhost:5000'"