#!/bin/bash
# run_kiosk.sh — open the spray-record dashboard fullscreen on the 55" TV.
#
# The TV is HDMI-A-1 on pi5camera01 (Wayland session).
# Start tv_display.py first (systemd service or `python tv_display.py`),
# then run this to launch the kiosk browser.

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)

URL="http://localhost:5000"

# --ozone-platform=wayland     → native Wayland (sharper, no XWayland blur)
# --kiosk                      → fullscreen, no browser chrome
# --noerrdialogs / --incognito → no popups, no history on the TV
chromium-browser \
  --ozone-platform=wayland \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --incognito \
  --check-for-update-interval=31536000 \
  --app="$URL"

# NOTE: If the kiosk opens on the wrong screen (24" instead of the 55"),
# the compositor decides placement. Two options:
#   1) Make HDMI-A-1 the primary output in the compositor config, or
#   2) Physically ensure only the TV is active when launching, or
#   3) Use a compositor window rule to pin this window to HDMI-A-1.
# On labwc/wayfire this is an output/rule setting, not a Chromium flag.
