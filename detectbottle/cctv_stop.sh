#!/bin/bash
# cctv_stop.sh — stop the CCTV wall (called by cron at 18:00).
pkill -f "mpv.*rtsp://" 2>/dev/null
echo "$(date '+%F %T') CCTV wall stopped" >> /home/ekapop/smartfarm/detectbottle/cctv_cron.log