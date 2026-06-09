# Open-Meteo Weather Logger — Deployment Guide

**Target:** Raspberry Pi 5 at Thong Pha Phum orchard  
**Coordinates:** 14.755135, 98.646364  
**Source:** Open-Meteo free API (no key required)

---

## Pre-flight check

Verify on the Pi that `pymysql` and `requests` are installed:
```bash
python3 -c "import pymysql, requests; print('OK')"
```

If not installed:
```bash
pip3 install pymysql requests --break-system-packages
```

---

## Step 1 — Test the API in your browser FIRST

Before installing anything, paste this URL in any browser to confirm the API works for your orchard:

```
https://api.open-meteo.com/v1/forecast?latitude=14.755135&longitude=98.646364&daily=shortwave_radiation_sum,et0_fao_evapotranspiration,precipitation_sum&timezone=Asia/Bangkok&forecast_days=7
```

Expected: JSON with 7 days of `shortwave_radiation_sum` (~15-25 MJ/m²) and `et0_fao_evapotranspiration` (~3-6 mm).

If you see reasonable numbers → proceed. If you see an error → stop and check coordinates.

---

## Step 2 — Create database tables

Run `01_schema.sql` in DBeaver against the `smartfarm` database on the Pi.

Verify:
```sql
SHOW CREATE TABLE t_weather_open_meteo_daily;
-- Should show generated columns for irrigation_need_durian, _guava, _wax_apple
```

---

## Step 3 — Copy files to the Pi

From your Windows machine (Tailscale):
```bash
scp fetch_open_meteo.py pi@100.74.144.57:/home/pi/smartfarm/
scp open-meteo-fetch.service pi@100.74.144.57:/tmp/
scp open-meteo-fetch.timer   pi@100.74.144.57:/tmp/
```

---

## Step 4 — Install systemd units on the Pi

SSH into the Pi:
```bash
ssh pi@100.74.144.57
sudo mv /tmp/open-meteo-fetch.service /etc/systemd/system/
sudo mv /tmp/open-meteo-fetch.timer   /etc/systemd/system/
sudo systemctl daemon-reload
```

---

## Step 5 — Run once manually to verify

```bash
sudo systemctl start open-meteo-fetch.service
sudo journalctl -u open-meteo-fetch.service -n 30 --no-pager
```

Expected log lines:
```
Fetched OK. Grid cell at (14.75, 98.625), elevation 215m
Upserted 96 hourly rows
Upserted 4 daily rows
Done
```

---

## Step 6 — Verify data in MariaDB

```sql
SELECT 
    record_date,
    ROUND(et0_fao_sum, 1)             AS et0_mm,
    ROUND(precipitation_sum, 1)        AS rain_mm,
    ROUND(irrigation_need_durian, 1)   AS durian_mm,
    ROUND(irrigation_need_guava, 1)    AS guava_mm,
    ROUND(irrigation_need_wax_apple, 1) AS wax_apple_mm,
    is_forecast
FROM t_weather_open_meteo_daily
ORDER BY record_date;
```

You should see 4 rows: yesterday (actual) + today + tomorrow + day after (forecasts).

---

## Step 7 — Enable hourly auto-run

```bash
sudo systemctl enable --now open-meteo-fetch.timer
sudo systemctl list-timers | grep open-meteo
```

Expected output: timer scheduled to run within 1 hour.

---

## Step 8 — Monitor

```bash
# Live log
tail -f /home/pi/smartfarm/logs/open_meteo.log

# Check timer is still active after reboot
sudo systemctl status open-meteo-fetch.timer

# Last 10 runs
sudo journalctl -u open-meteo-fetch.service -n 100 --no-pager
```

---

## What you have now

| Capability | Source | Update freq |
|---|---|---|
| Hourly solar radiation (W/m²) | API | Every hour |
| Daily solar dose (MJ/m²) | API | Every hour, refreshed |
| Daily ET₀ (mm of water) | API | Every hour, refreshed |
| Per-crop irrigation need (mm) | DB generated column | Real-time on SELECT |
| 3-day forecast | API | Every hour |
| Yesterday's actuals | API past_days=1 | Once it becomes "past" |

**Disk usage estimate:** ~100 rows/day × 365 = 36,500 rows/year hourly. Negligible.

---

## Future enhancements (later)

1. Add a `/weather` route in smartfarm-admin with Chart.js for ET₀ trend
2. Auto-trigger irrigation when `irrigation_need_durian > 4 mm` for the day
3. Compare API forecast vs your camera-based rain detector — log a "forecast accuracy" metric
4. Add historical fetch (`past_days=92`) on first install to backfill 3 months