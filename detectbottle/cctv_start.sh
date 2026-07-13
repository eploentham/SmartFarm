#!/bin/bash
# cctv_start.sh — start the CCTV wall (called by cron at 08:00).
#
# cron runs with a bare environment, so we set the Wayland session vars here
# before calling the wall script (mpv needs them to reach the display).

export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)

DIR=/home/ekapop/smartfarm/detectbottle
echo "$(date '+%F %T') CCTV wall starting" >> "$DIR/cctv_cron.log"
bash "$DIR/cctv_wall.sh" >> "$DIR/cctv_cron.log" 2>&1