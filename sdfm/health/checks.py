# sdfm/health/checks.py

from __future__ import annotations
import time
import glob
import os
import platform
import shutil
import socket

from pymavlink import mavutil
#from sdfm.core.result import CheckResult
from sdfm.health.report import HealthResult, HealthStatus


MAVLINK_BAUD = 115200

HEARTBEAT_TIMEOUT_SEC = 5.0
MESSAGE_WAIT_SEC = 3.0

MIN_BATTERY_VOLTAGE = 14.0
MIN_BATTERY_REMAINING = 30

MIN_GPS_FIX_TYPE = 3
MIN_GPS_SATELLITES = 8


def find_pixhawk_device() -> str | None:
    """
    Find Pixhawk USB serial device.

    Prefer /dev/serial/by-id because it is persistent across reboot.
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

    # Fallback for development / diagnostics.
    for device in ("/dev/ttyACM0", "/dev/ttyACM1"):
        if os.path.exists(device):
            return device

    return None


def check_pi5() -> HealthResult:
    """
    Check basic Raspberry Pi 5 system health.
    """

    try:
        hostname = socket.gethostname()
        machine = platform.machine().lower()

        disk = shutil.disk_usage("/")

        details = {
            "hostname": hostname,
            "machine": machine,
            "python": platform.python_version(),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
        }

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
            message=f"PI5_CHECK_FAILED: {exc}",
        )

def check_imu(
    pixhawk,
    router,
    timeout_sec: float = 3.0,
) -> HealthResult:

    last_message = None
    last_time = None
    message_count = 0

    def on_imu(message):
        nonlocal last_message
        nonlocal last_time
        nonlocal message_count

        last_message = message
        last_time = time.monotonic()
        message_count += 1

    router.subscribe(
        "HIGHRES_IMU",
        on_imu,
    )

    try:
        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_HIGHRES_IMU,
            10.0,
        )

        deadline = time.monotonic() + timeout_sec

        while (
            last_message is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_message is None:
            return HealthResult(
                name="IMU",
                status=HealthStatus.FAILED,
                message="IMU_DATA_TIMEOUT",
                details={
                    "message_type": "HIGHRES_IMU",
                },
            )

        age = time.monotonic() - last_time

        if age > 1.0:
            return HealthResult(
                name="IMU",
                status=HealthStatus.FAILED,
                message="IMU_DATA_STALE",
                details={
                    "age_sec": round(age, 3),
                },
            )

        return HealthResult(
            name="IMU",
            status=HealthStatus.OK,
            message="IMU telemetry healthy",
            details={
                "message_type": "HIGHRES_IMU",
                "messages": message_count,
                "age_sec": round(age, 3),
                "accel_x": round(last_message.xacc, 3),
                "accel_y": round(last_message.yacc, 3),
                "accel_z": round(last_message.zacc, 3),
            },
        )

    finally:
        router.unsubscribe(
            "HIGHRES_IMU",
            on_imu,
        )
def check_compass(
    pixhawk,
    router,
    timeout_sec: float = 3.0,
) -> HealthResult:

    last_message = None
    last_time = None

    def on_imu(message):
        nonlocal last_message
        nonlocal last_time

        last_message = message
        last_time = time.monotonic()

    router.subscribe(
        "HIGHRES_IMU",
        on_imu,
    )

    try:
        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_HIGHRES_IMU,
            10.0,
        )

        deadline = time.monotonic() + timeout_sec

        while (
            last_message is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_message is None:
            return HealthResult(
                name="COMPASS",
                status=HealthStatus.FAILED,
                message="COMPASS_DATA_TIMEOUT",
                details={},
            )

        age = time.monotonic() - last_time

        if age > 1.0:
            return HealthResult(
                name="COMPASS",
                status=HealthStatus.FAILED,
                message="COMPASS_DATA_STALE",
                details={
                    "age_sec": round(age, 3),
                },
            )

        x = float(last_message.xmag)
        y = float(last_message.ymag)
        z = float(last_message.zmag)

        if (
            abs(x) < 0.0001
            and abs(y) < 0.0001
            and abs(z) < 0.0001
        ):
            return HealthResult(
                name="COMPASS",
                status=HealthStatus.FAILED,
                message="COMPASS_NO_VALID_DATA",
                details={
                    "mag_x": x,
                    "mag_y": y,
                    "mag_z": z,
                },
            )

        return HealthResult(
            name="COMPASS",
            status=HealthStatus.OK,
            message="Compass telemetry healthy",
            details={
                "age_sec": round(age, 3),
                "mag_x": round(x, 4),
                "mag_y": round(y, 4),
                "mag_z": round(z, 4),
                "calibration_verified": False,
            },
        )

    finally:
        router.unsubscribe(
            "HIGHRES_IMU",
            on_imu,
        )
def check_elrs(
    pixhawk,
    router,
    timeout_sec: float = 3.0,
) -> HealthResult:

    last_message = None
    last_time = None
    message_count = 0

    def on_rc(message):
        nonlocal last_message
        nonlocal last_time
        nonlocal message_count

        last_message = message
        last_time = time.monotonic()
        message_count += 1

    router.subscribe(
        "RC_CHANNELS",
        on_rc,
    )

    try:
        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_RC_CHANNELS,
            5.0,
        )

        deadline = time.monotonic() + timeout_sec

        while (
            last_message is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_message is None:
            return HealthResult(
                name="ELRS",
                status=HealthStatus.FAILED,
                message="RC_CHANNELS_TIMEOUT",
            )

        age = time.monotonic() - last_time

        channels = [
            last_message.chan1_raw,
            last_message.chan2_raw,
            last_message.chan3_raw,
            last_message.chan4_raw,
        ]

        if age > 1.0:
            return HealthResult(
                name="ELRS",
                status=HealthStatus.STALE,
                message="RC_CHANNELS_STALE",
                details={
                    "age_sec": round(age, 3),
                },
            )

        valid = all(
            800 <= value <= 2200
            for value in channels
        )

        if not valid:
            return HealthResult(
                name="ELRS",
                status=HealthStatus.FAILED,
                message="RC_INPUT_INVALID",
                details={
                    "ch1": channels[0],
                    "ch2": channels[1],
                    "ch3": channels[2],
                    "ch4": channels[3],
                },
            )

        return HealthResult(
            name="ELRS",
            status=HealthStatus.OK,
            message="ELRS RC input healthy",
            details={
                "messages": message_count,
                "age_sec": round(age, 3),
                "ch1": channels[0],
                "ch2": channels[1],
                "ch3": channels[2],
                "ch4": channels[3],
            },
        )

    finally:
        router.unsubscribe(
            "RC_CHANNELS",
            on_rc,
        )
def check_realsense(
    timeout_sec: float = 3.0,
) -> HealthResult:

    try:
        import pyrealsense2 as rs

    except ImportError:
        return HealthResult(
            name="RealSense",
            status=HealthStatus.FAILED,
            message="REALSENSE_LIBRARY_MISSING",
        )

    pipeline = None

    try:
        context = rs.context()
        devices = context.query_devices()

        if len(devices) == 0:
            return HealthResult(
                name="RealSense",
                status=HealthStatus.FAILED,
                message="REALSENSE_NOT_FOUND",
            )

        device = devices[0]

        name = device.get_info(
            rs.camera_info.name
        )

        serial = device.get_info(
            rs.camera_info.serial_number
        )

        firmware = device.get_info(
            rs.camera_info.firmware_version
        )

        pipeline = rs.pipeline()
        config = rs.config()

        config.enable_stream(
            rs.stream.depth,
            640,
            480,
            rs.format.z16,
            30,
        )

        config.enable_stream(
            rs.stream.color,
            640,
            480,
            rs.format.bgr8,
            30,
        )

        pipeline.start(config)

        deadline = time.monotonic() + timeout_sec

        depth_frame = None
        color_frame = None

        while time.monotonic() < deadline:

            try:
                frames = pipeline.wait_for_frames(
                    timeout_ms=500
                )

            except RuntimeError:
                continue

            depth_frame = frames.get_depth_frame()
            color_frame = frames.get_color_frame()

            if depth_frame and color_frame:
                break

        if not depth_frame:
            return HealthResult(
                name="RealSense",
                status=HealthStatus.FAILED,
                message="REALSENSE_DEPTH_TIMEOUT",
                details={
                    "name": name,
                    "serial": serial,
                },
            )

        if not color_frame:
            return HealthResult(
                name="RealSense",
                status=HealthStatus.FAILED,
                message="REALSENSE_COLOR_TIMEOUT",
                details={
                    "name": name,
                    "serial": serial,
                },
            )

        width = depth_frame.get_width()
        height = depth_frame.get_height()

        center_distance = depth_frame.get_distance(
            width // 2,
            height // 2,
        )

        return HealthResult(
            name="RealSense",
            status=HealthStatus.OK,
            message="RealSense D435i operational",
            details={
                "name": name,
                "serial": serial,
                "firmware": firmware,
                "depth": "OK",
                "color": "OK",
                "center_depth_m": round(
                    center_distance,
                    3,
                ),
            },
        )

    except Exception as exc:
        return HealthResult(
            name="RealSense",
            status=HealthStatus.FAILED,
            message="REALSENSE_ERROR",
            details={
                "error": str(exc),
            },
        )

    finally:
        if pipeline is not None:
            try:
                pipeline.stop()
            except Exception:
                pass
def check_prearm(
    pixhawk,
    router,
    timeout_sec: float = 5.0,
) -> HealthResult:

    last_sys_status = None
    last_time = None
    prearm_messages: list[str] = []

    def on_sys_status(message):
        nonlocal last_sys_status
        nonlocal last_time

        last_sys_status = message
        last_time = time.monotonic()

    def on_statustext(message):
        text = message.text

        if isinstance(text, bytes):
            text = text.decode(
                "utf-8",
                errors="replace",
            )

        text = str(text).rstrip("\x00")

        if text.lower().startswith("prearm:"):
            if text not in prearm_messages:
                prearm_messages.append(text)

    router.subscribe(
        "SYS_STATUS",
        on_sys_status,
    )

    router.subscribe(
        "STATUSTEXT",
        on_statustext,
    )

    try:
        pixhawk.request_message_interval(
            mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
            2.0,
        )

        deadline = time.monotonic() + timeout_sec

        while (
            last_sys_status is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)

        if last_sys_status is None:
            return HealthResult(
                name="PreArm",
                status=HealthStatus.STALE,
                message="PREARM_STATUS_TIMEOUT",
            )

        age = time.monotonic() - last_time

        if age > 1.0:
            return HealthResult(
                name="PreArm",
                status=HealthStatus.STALE,
                message="PREARM_STATUS_STALE",
                details={
                    "age_sec": round(age, 3),
                },
            )

        prearm_bit = (
            mavutil.mavlink.MAV_SYS_STATUS_PREARM_CHECK
        )

        enabled = bool(
            last_sys_status.onboard_control_sensors_enabled
            & prearm_bit
        )

        healthy = bool(
            last_sys_status.onboard_control_sensors_health
            & prearm_bit
        )

        details = {
            "enabled": enabled,
            "healthy": healthy,
            "age_sec": round(age, 3),
            "messages": prearm_messages,
        }

        if not enabled:
            return HealthResult(
                name="PreArm",
                status=HealthStatus.DEGRADED,
                message="PREARM_CHECK_NOT_ENABLED",
                details=details,
            )

        if not healthy:
            return HealthResult(
                name="PreArm",
                status=HealthStatus.FAILED,
                message="PREARM_CHECK_FAILED",
                details=details,
            )

        return HealthResult(
            name="PreArm",
            status=HealthStatus.OK,
            message="ArduPilot pre-arm checks healthy",
            details=details,
        )

    finally:
        router.unsubscribe(
            "SYS_STATUS",
            on_sys_status,
        )

        router.unsubscribe(
            "STATUSTEXT",
            on_statustext,
        )
def connect_pixhawk():
    """
    Connect to Pixhawk and wait for heartbeat.

    Returns:
        tuple[master | None, HealthResult]
    """

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
                    details={
                        "device": device,
                    },
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
                details={
                    "device": device,
                },
            ),
        )


def request_message_interval(
    master,
    message_id: int,
    frequency_hz: float,
) -> None:
    """
    Ask Pixhawk to stream a MAVLink message at a given frequency.

    This only changes telemetry message rate.
    It does not arm or move DR01.
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


def wait_message(
    master,
    message_type: str,
    timeout: float = MESSAGE_WAIT_SEC,
):
    """
    Wait for one MAVLink message.
    """

    return master.recv_match(
        type=message_type,
        blocking=True,
        timeout=timeout,
    )


def check_heartbeat(master) -> HealthResult:
    """
    Verify Pixhawk heartbeat and read armed/mode state.
    """

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
    """
    Check battery voltage and remaining percentage.
    """

    try:
        request_message_interval(
            master,
            mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
            2.0,
        )

        message = wait_message(
            master,
            "SYS_STATUS",
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
    """
    Check GPS fix and satellite count.
    """

    try:
        request_message_interval(
            master,
            mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
            2.0,
        )

        message = wait_message(
            master,
            "GPS_RAW_INT",
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


def unknown_check(
    name: str,
    reason: str = "CHECK_NOT_IMPLEMENTED",
) -> HealthResult:
    """
    Placeholder for hardware checks that are not implemented yet.
    """

    return HealthResult(
        name=name,
        status=HealthStatus.UNKNOWN,
        message=reason,
    )