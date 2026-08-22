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
CONFIRMED WORKING 2026-08 (Pi5 read live params over /dev/ttyACM0, heartbeat sys 1).

Tool: `rngfnd_config.py` (runs on Pi 5, uses pymavlink).
  ssh pi@pi5-drone1   (over Tailscale)  — path: ~/smartfarm/scripts/
  python3 rngfnd_config.py --show        # read current RNGFND params
  python3 rngfnd_config.py --distance     # LIVE distances = real sensor test
  python3 rngfnd_config.py --set RNGFND1_MAX_CM 600
  python3 rngfnd_config.py --reboot       # reboot FC (needed after wiring/TYPE/ADDR change)
  python3 rngfnd_config.py --apply        # (only after aligning DESIRED dict to slots!)
Edit CONNECTION at top of script to match Pi5<->Pixhawk link (USB=/dev/ttyACM0,
GPIO serial=/dev/serial0, or mavlink-router UDP endpoint).
NOTE: script's DESIRED dict now matches the slot layout below — --apply is a safe
full-restore.

## Reboot rule (IMPORTANT)
ArduPilot scans the I2C bus ONLY at boot. It never notices a mid-session wiring
change. So:

| Change | Reboot needed? |
|---|---|
| Physical I2C wiring (connect/disconnect sensor, swap SDA/SCL, add device) | YES |
| RNGFNDx_TYPE (enable/change driver) | YES |
| RNGFNDx_ADDR (change I2C address) | YES |
| RNGFNDx_MIN_CM / MAX_CM / ORIENT (tuning) | No — takes effect live |

**Wiring-change procedure:**
1. Power OFF the Pixhawk, then change the wiring (avoid hot-plugging I2C).
2. Power back on (that boot = the reboot). Or `rngfnd_config.py --reboot` if live.
3. Wait ~30s for boot + I2C scan.
4. Verify: `--distance`, or Status tab (rangefinder1/2/3), or watch PreArm messages.

## Current sensor map (FINAL — as configured on the aircraft)
| Slot | Sensor | Interface | Params | Orient |
|---|---|---|---|---|
| RNGFND1 | TFmini Plus #1 (front) | I2C @ 0x10 | TYPE=25, ADDR=16, MIN_CM=10, MAX_CM=600 | Forward (0) |
| RNGFND2 | TFmini Plus #2 (up) | I2C @ 0x11 | TYPE=25, ADDR=17, MIN_CM=10, MAX_CM=600 | Up (24) |
| RNGFND3 | MTF-01P (down range) | UART/MAVLink, GPS2/SERIAL4 | TYPE=10, MIN_CM=5, MAX_CM=1200 | Down (25) |

Also on MTF-01P: FLOW_TYPE=5 (optical flow, same UART/MAVLink stream).
STATUS 2026-08: RNGFND3/MTF-01P working (Down ~9-11cm). RNGFND1/front TFmini working
after SDA/SCL fix. RNGFND2/up TFmini — pending splitter reconnect + reboot.

Note: only the DOWN rangefinder (RNGFND3 / MTF-01P) feeds altitude/terrain following.
Front + up TFminis feed proximity/obstacle avoidance (PRX subsystem) — configured
separately later.

## I2C wiring — the SDA/SCL cross (gotcha that cost debugging time — RESOLVED)
I2C is a bus, NOT crossed like UART on the signal *names*: SDA->SDA, SCL->SCL,
VCC->VCC, GND->GND. BUT the two connectors number these in OPPOSITE pin order, so a
straight pin1-1/2-2/3-3 cable physically CROSSES SDA and SCL and the sensor goes silent.
THIS WAS THE BUG — front TFmini read 0 until the two signal wires were swapped.

- TFmini Plus (I2C mode): pin2 = White = **SDA**, pin3 = Green = **SCL**
  (dual-labeled RXD/SDA and TXD/SCL — easy to misread. White is SDA, not SCL.)
- Pixhawk 6C Mini I2C port: pin1=VCC, pin2=**SCL**, pin3=**SDA**, pin4=GND

Correct by NAME: White(SDA) -> Pixhawk pin3(SDA); Green(SCL) -> Pixhawk pin2(SCL).
= the two middle wires cross between the connectors.
Swapping SDA/SCL causes NO damage — safe to try both ways, then reboot to test.
Keep I2C cables short, especially the up-facing run. Pixhawk I2C port has pull-ups.
Apply the SAME corrected orientation to the splitter for both sensors.

## Why MTF-01P is different from TFmini
- TFmini = rangefinder-only → distance fits over I2C → moved to I2C to save UART ports.
- MTF-01P = optical flow + rangefinder → flow only works over serial/MAVLink in
  ArduPilot → must stay on UART. Its range reading comes bundled in the same stream.

## Open item
- Reconnect up TFmini via splitter (corrected SDA/SCL) + reboot → confirm rangefinder2 > 0.
  Then all three rangefinders live and sensor bring-up is complete.