# TFmini Plus Setup — I2C Mode (Up-facing canopy LiDAR)

Status: sensor configured and verified — ready to wire to Pixhawk.

## Why I2C
All 4 Pixhawk UART ports already used (Telem1=SiK radio, Telem2=ELRS RX, GPS1=M10 GPS, GPS2/SERIAL4=MTF-01P optical flow). TFmini Plus factory-defaults to UART, so it needed a one-time mode switch to I2C to avoid needing a 5th UART port.

## Mode switch (done via Benewake LiDAR GUI Viewer + FT232RL FTDI, confirmed working)
- Switch to I2C: `5A 05 0A 01 6A`
- Save settings (persist to flash): `5A 04 11 6F`
- Verified: sensor detected on Raspberry Pi 5's I2C bus after switch.

## Wiring to Pixhawk 6C Mini
GPS2 connector, I2C2 pins (pins 4-5: SCL/SDA) — NOT pins 2-3 (those are UART, already used by MTF-01P). Plus 5V + GND.

## Mission Planner parameters (RNGFND2 slot — RNGFND1 is the MTF-01P)
| Parameter | Value |
|---|---|
| RNGFND2_TYPE | 25 (Benewake TFminiPlus-I2C) |
| RNGFND2_ADDR | 16 (0x10) |
| RNGFND2_MIN_CM | 10 |
| RNGFND2_MAX_CM | 600 (conservative outdoor/sunlight figure) |
| RNGFND2_ORIENT | Up |

5A 05 0A 01 6A     ← switch to I2C mode
5A 04 11 6F        ← save settings

5A 05 0A 01 6A     ← switch to I2C mode
5A 05 0B 11 7B     ← change I2C address to 0x11
5A 04 11 6F        ← save settings

Verify each on the Pi 5 after config — i2cdetect -y 1

Write RNGFND2_TYPE first, reboot, then the rest of RNGFND2_* params appear (dynamic param tree — same behavior seen with RNGFND1).

## Verification
Status tab → `rangefinder2` field, or MAVLink Inspector → second `DISTANCE_SENSOR` message.