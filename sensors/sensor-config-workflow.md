# Sensor Config Workflow — Two Layers

The repeatable pattern for every I2C sensor added to the drone (TFmini, etc).

## Layer 1 — Bench setup (once, at purchase) — NOT remote
Done on the computer with an FT232RL FTDI adapter + Benewake GUI (or MicoAssistant).
Converts the sensor from factory UART mode to I2C, and sets its I2C address.
This is stored in the SENSOR's own flash. Cannot be changed via Pixhawk/MAVLink.

TFmini Plus commands (checksum = sum of prior bytes, low 8 bits):
- Switch to I2C:        `5A 05 0A 01 6A`
- Switch back to UART:  `5A 05 0A 00 69`
- Set I2C addr 0x10:    `5A 05 0B 10 7A`
- Set I2C addr 0x11:    `5A 05 0B 11 7B`
- Save settings:        `5A 04 11 6F`

For a unit whose address must change: send address-change + save FIRST (while still
on UART), THEN switch to I2C + save. Once in I2C, the UART GUI can no longer reach it.

**Discipline: write down each sensor's burned-in I2C address.** As long as this is
known, Layer 2 can always point the Pixhawk at the right address remotely.

## Layer 2 — Remote param config (anytime, from Bangkok) — via Pi5
Pi5 --MAVLink--> Pixhawk. Fixes ArduPilot RNGFND* parameters (which live in the
Pixhawk), NOT the sensor's internal address. Covers the majority of config mistakes.

Tool: `rngfnd_config.py` (runs on Pi 5, uses pymavlink). Delivered to user 2026-08.
  ssh pi@farm-pi5   (over Tailscale)
  python3 rngfnd_config.py --show
  python3 rngfnd_config.py --set RNGFND2_ADDR 17
  python3 rngfnd_config.py --apply
Edit CONNECTION at top of script to match Pi5<->Pixhawk link (USB=/dev/ttyACM0,
GPIO serial=/dev/serial0, or mavlink-router UDP endpoint).

## Current sensor map
| Sensor | Interface | ArduPilot | Orient | Notes |
|---|---|---|---|---|
| MTF-01P (flow + down range) | UART/MAVLink, GPS2/SERIAL4 | FLOW_TYPE=5, RNGFND1_TYPE=10 | Down (25) | Stays UART — optical flow needs serial, no I2C path |
| TFmini Plus #1 (front) | I2C @ 0x10 | RNGFND2_TYPE=25, ADDR=16 | Forward (0) | |
| TFmini Plus #2 (up) | I2C @ 0x11 | RNGFND3_TYPE=25, ADDR=17 | Up (24) | Address changed from default to avoid I2C clash |

Note: only the DOWN rangefinder feeds altitude/terrain following. Front + up feed
proximity/obstacle avoidance (PRX subsystem) — configured separately later.

## Why MTF-01P is different from TFmini
- TFmini = rangefinder-only → distance fits over I2C → moved to I2C to save UART ports.
- MTF-01P = optical flow + rangefinder → flow only works over serial/MAVLink in
  ArduPilot → must stay on UART. Its range reading comes bundled in the same stream.