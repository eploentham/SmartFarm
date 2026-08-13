# ~/smartfarm/sdfm/health/system_check.py

from __future__ import annotations

import glob
import os
import platform
import shutil
import socket
import time
from dataclasses import dataclass
from enum import Enum

from pymavlink import mavutil


class HealthStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    STALE = "STALE"
    NOT_READY = "NOT_READY"


@dataclass
class HealthResult:
    name: str
    status: HealthStatus
    message: str = ""
    details: dict | None = None


@dataclass
class SystemCheckReport:
    vehicle: str
    host: str
    checks: list[HealthResult]

    @property
    def ready(self) -> bool:
        """
        Initial policy.

        For now only the components we actually know how to check
        are considered mandatory.

        This policy will later move to safety/health policy code.
        """
        critical = {
            "Pi5",
            "Pixhawk",
            "Heartbeat",
            "Battery",
            "GPS",
        }

        for check in self.checks:
            if check.name not in critical:
                continue

            if check.status != HealthStatus.OK:
                return False

        return True


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

VEHICLE_NAME = "DR01"

MAVLINK_BAUD = 115200

HEARTBEAT_TIMEOUT_SEC = 5.0
MESSAGE_WAIT_SEC = 3.0

MIN_BATTERY_VOLTAGE = 14.0
MIN_BATTERY_REMAINING = 30

MIN_GPS_FIX_TYPE = 3
MIN_GPS_SATELLITES = 8


# ----------------------------------------------------------------------
# Utility
# ----------------------------------------------------------------------

def find_pixhawk_device() -> str | None:
    """
    Prefer persistent /dev/serial/by-id path.

    Falls back to ttyACM only if persistent path cannot be found.
    """

    patterns = [
        "/dev/serial/by-id/*Holybro*Pixhawk6C*-if00*",
        "/dev/serial/by-id/*Pixhawk6C*-if00*",
        "/dev/serial/by-id/*Pixhawk*-if00*",
    ]

    for pattern in patterns:
        devices = sorted(glob.glob(pattern))
        if devices:
            return devices[0]

    # Development fallback only.
    for device in ("/dev/ttyACM0", "/dev/ttyACM1"):
        if os.path.exists(device):
            return device

    return None


def request_message_interval(
    master,
    message_id: int,
    frequency_hz: float,
) -> None:
    """
    Read-only telemetry request.

    MAV_CMD_SET_MESSAGE_INTERVAL does not arm or move the aircraft.
    """

    if frequency_hz <= 0:
        interval_us = -1
    else:
        interval_us = int(1_000_000 / frequency_hz)

    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        message_id,
        interval_us,
        0,
        0,
        0,
        0,
        0,
    )


def wait_message(master, message_type: str, timeout: float):
    return master.recv_match(
        type=message_type,
        blocking=True,
        timeout=timeout,
    )


# ----------------------------------------------------------------------
# Individual checks
# ----------------------------------------------------------------------

def check_pi5() -> HealthResult:
    try:
        hostname = socket.gethostname()

        disk = shutil.disk_usage("/")

        details = {
            "hostname": hostname,
            "machine": platform.machine(),
            "python": platform.python_version(),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
        }

        # DR01 production computer is Pi5/aarch64.
        machine = platform.machine().lower()

        if machine not in ("aarch64", "arm64"):
            return HealthResult(
                name="Pi5",
                status=HealthStatus.DEGRADED,
                message=f"Unexpected architecture: {machine}",
                details=details,
            )

        return HealthResult(
            name="Pi5",
            status=HealthStatus.OK,
            message="Companion computer operational",
            details=details,
        )

    except Exception as exc:
        return HealthResult(
            name="Pi5",
            status=HealthStatus.FAILED,
            message=str(exc),
        )


def connect_pixhawk():
    device = find_pixhawk_device()

    if device is None:
        return (
            None,
            HealthResult(
                name="Pixhawk",
                status=HealthStatus.FAILED,
                message="PIXHAWK_DEVICE_NOT_FOUND",
            ),
        )

    try:
        master = mavutil.mavlink_connection(
            device,
            baud=MAVLINK_BAUD,
            autoreconnect=True,
        )

        heartbeat = master.wait_heartbeat(
            timeout=HEARTBEAT_TIMEOUT_SEC,
        )

        if heartbeat is None:
            try:
                master.close()
            except Exception:
                pass

            return (
                None,
                HealthResult(
                    name="Pixhawk",
                    status=HealthStatus.FAILED,
                    message="PIXHAWK_HEARTBEAT_TIMEOUT",
                    details={"device": device},
                ),
            )

        return (
            master,
            HealthResult(
                name="Pixhawk",
                status=HealthStatus.OK,
                message="MAVLink connection established",
                details={
                    "device": device,
                    "system_id": master.target_system,
                    "component_id": master.target_component,
                },
            ),
        )

    except Exception as exc:
        return (
            None,
            HealthResult(
                name="Pixhawk",
                status=HealthStatus.FAILED,
                message=f"PIXHAWK_CONNECTION_FAILED: {exc}",
                details={"device": device},
            ),
        )


def check_heartbeat(master) -> HealthResult:
    try:
        message = wait_message(
            master,
            "HEARTBEAT",
            HEARTBEAT_TIMEOUT_SEC,
        )

        if message is None:
            return HealthResult(
                name="Heartbeat",
                status=HealthStatus.FAILED,
                message="PIXHAWK_LOST",
            )

        armed = bool(
            message.base_mode
            & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        )

        try:
            mode = mavutil.mode_string_v10(message)
        except Exception:
            mode = "UNKNOWN"

        return HealthResult(
            name="Heartbeat",
            status=HealthStatus.OK,
            message="Heartbeat received",
            details={
                "armed": armed,
                "mode": mode,
                "system_status": message.system_status,
            },
        )

    except Exception as exc:
        return HealthResult(
            name="Heartbeat",
            status=HealthStatus.FAILED,
            message=f"HEARTBEAT_CHECK_FAILED: {exc}",
        )


def check_battery(master) -> HealthResult:
    try:
        request_message_interval(
            master,
            mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
            2.0,
        )

        message = wait_message(
            master,
            "SYS_STATUS",
            MESSAGE_WAIT_SEC,
        )

        if message is None:
            return HealthResult(
                name="Battery",
                status=HealthStatus.STALE,
                message="BATTERY_TELEMETRY_TIMEOUT",
            )

        voltage = (
            message.voltage_battery / 1000.0
            if message.voltage_battery != 65535
            else None
        )

        current = (
            message.current_battery / 100.0
            if message.current_battery != -1
            else None
        )

        remaining = (
            message.battery_remaining
            if message.battery_remaining >= 0
            else None
        )

        details = {
            "voltage_v": voltage,
            "current_a": current,
            "remaining_percent": remaining,
        }

        if voltage is None:
            return HealthResult(
                name="Battery",
                status=HealthStatus.FAILED,
                message="BATTERY_VOLTAGE_UNAVAILABLE",
                details=details,
            )

        if voltage < MIN_BATTERY_VOLTAGE:
            return HealthResult(
                name="Battery",
                status=HealthStatus.FAILED,
                message="BATTERY_VOLTAGE_LOW",
                details=details,
            )

        if (
            remaining is not None
            and remaining < MIN_BATTERY_REMAINING
        ):
            return HealthResult(
                name="Battery",
                status=HealthStatus.FAILED,
                message="BATTERY_REMAINING_LOW",
                details=details,
            )

        return HealthResult(
            name="Battery",
            status=HealthStatus.OK,
            message="Battery telemetry healthy",
            details=details,
        )

    except Exception as exc:
        return HealthResult(
            name="Battery",
            status=HealthStatus.FAILED,
            message=f"BATTERY_CHECK_FAILED: {exc}",
        )


def check_gps(master) -> HealthResult:
    try:
        request_message_interval(
            master,
            mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
            2.0,
        )

        message = wait_message(
            master,
            "GPS_RAW_INT",
            MESSAGE_WAIT_SEC,
        )

        if message is None:
            return HealthResult(
                name="GPS",
                status=HealthStatus.STALE,
                message="GPS_TELEMETRY_TIMEOUT",
            )

        details = {
            "fix_type": message.fix_type,
            "satellites": message.satellites_visible,
            "latitude": message.lat / 1e7,
            "longitude": message.lon / 1e7,
            "altitude_m": message.alt / 1000.0,
        }

        if message.fix_type < MIN_GPS_FIX_TYPE:
            return HealthResult(
                name="GPS",
                status=HealthStatus.FAILED,
                message="GPS_NO_3D_FIX",
                details=details,
            )

        if message.satellites_visible < MIN_GPS_SATELLITES:
            return HealthResult(
                name="GPS",
                status=HealthStatus.DEGRADED,
                message="GPS_LOW_SATELLITES",
                details=details,
            )

        return HealthResult(
            name="GPS",
            status=HealthStatus.OK,
            message="GPS 3D fix available",
            details=details,
        )

    except Exception as exc:
        return HealthResult(
            name="GPS",
            status=HealthStatus.FAILED,
            message=f"GPS_CHECK_FAILED: {exc}",
        )


def unknown_check(name: str, reason: str) -> HealthResult:
    return HealthResult(
        name=name,
        status=HealthStatus.UNKNOWN,
        message=reason,
    )


# ----------------------------------------------------------------------
# System check
# ----------------------------------------------------------------------

def run_system_check() -> SystemCheckReport:
    checks: list[HealthResult] = []

    # Companion computer
    checks.append(check_pi5())

    # Pixhawk + MAVLink
    master, pixhawk_result = connect_pixhawk()
    checks.append(pixhawk_result)

    if master is None:
        checks.extend(
            [
                HealthResult(
                    "Heartbeat",
                    HealthStatus.FAILED,
                    "PIXHAWK_UNAVAILABLE",
                ),
                HealthResult(
                    "Battery",
                    HealthStatus.UNKNOWN,
                    "PIXHAWK_UNAVAILABLE",
                ),
                HealthResult(
                    "GPS",
                    HealthStatus.UNKNOWN,
                    "PIXHAWK_UNAVAILABLE",
                ),
            ]
        )

    else:
        checks.append(check_heartbeat(master))
        checks.append(check_battery(master))
        checks.append(check_gps(master))

    # --------------------------------------------------------------
    # Sensors not implemented yet.
    #
    # UNKNOWN is intentional.
    # Do NOT report OK until we actually verify the hardware.
    # --------------------------------------------------------------

    checks.extend(
        [
            unknown_check("IMU", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("Compass", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("Optical Flow", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("LiDAR Front", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("LiDAR Up", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("ELRS", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("SiK", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("RealSense", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("Pi Camera", "CHECK_NOT_IMPLEMENTED"),
            unknown_check("PreArm", "CHECK_NOT_IMPLEMENTED"),
        ]
    )

    if master is not None:
        try:
            master.close()
        except Exception:
            pass

    return SystemCheckReport(
        vehicle=VEHICLE_NAME,
        host=socket.gethostname(),
        checks=checks,
    )


# ----------------------------------------------------------------------
# Console report
# ----------------------------------------------------------------------

def print_report(report: SystemCheckReport) -> None:
    print()
    print("=" * 60)
    print(" SDFM SYSTEM CHECK")
    print("=" * 60)
    print(f" Vehicle : {report.vehicle}")
    print(f" Host    : {report.host}")
    print("-" * 60)

    for check in report.checks:
        print(
            f" {check.name:<16}"
            f"{check.status.value:<12}"
            f"{check.message}"
        )

        if check.details:
            for key, value in check.details.items():
                print(f"     {key:<18}: {value}")

    print("-" * 60)

    if report.ready:
        print(" SYSTEM STATUS : READY")
    else:
        print(" SYSTEM STATUS : NOT READY")

    print("=" * 60)
    print()


def main() -> int:
    report = run_system_check()
    print_report(report)

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())