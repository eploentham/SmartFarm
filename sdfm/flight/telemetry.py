# sdfm/flight/telemetry.py

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from pymavlink import mavutil


@dataclass
class TelemetryState:
    """
    Latest known vehicle state received from Pixhawk.

    This class stores state only.
    It does not send flight commands.
    """

    # --------------------------------------------------------------
    # Connection / heartbeat
    # --------------------------------------------------------------

    heartbeat_received: bool = False
    last_heartbeat_monotonic: float | None = None

    armed: bool | None = None
    flight_mode: str | None = None
    system_status: int | None = None

    # --------------------------------------------------------------
    # Battery
    # --------------------------------------------------------------

    battery_voltage_v: float | None = None
    battery_current_a: float | None = None
    battery_remaining_percent: int | None = None
    battery_updated_monotonic: float | None = None

    # --------------------------------------------------------------
    # GPS
    # --------------------------------------------------------------

    gps_fix_type: int | None = None
    gps_satellites: int | None = None

    latitude: float | None = None
    longitude: float | None = None
    gps_altitude_m: float | None = None

    gps_updated_monotonic: float | None = None

    # --------------------------------------------------------------
    # Vehicle position
    # --------------------------------------------------------------

    relative_altitude_m: float | None = None
    position_updated_monotonic: float | None = None

    # --------------------------------------------------------------
    # Attitude
    # --------------------------------------------------------------

    roll_rad: float | None = None
    pitch_rad: float | None = None
    yaw_rad: float | None = None

    attitude_updated_monotonic: float | None = None

    # --------------------------------------------------------------
    # Internal synchronization
    # --------------------------------------------------------------

    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        repr=False,
        compare=False,
    )

    # --------------------------------------------------------------
    # Message update
    # --------------------------------------------------------------

    def update(self, message: Any) -> None:
        """
        Update telemetry state from one MAVLink message.
        """

        if message is None:
            return

        message_type = message.get_type()

        now = time.monotonic()

        with self._lock:

            if message_type == "HEARTBEAT":
                self._update_heartbeat(
                    message,
                    now,
                )

            elif message_type == "SYS_STATUS":
                self._update_sys_status(
                    message,
                    now,
                )

            elif message_type == "BATTERY_STATUS":
                self._update_battery_status(
                    message,
                    now,
                )

            elif message_type == "GPS_RAW_INT":
                self._update_gps(
                    message,
                    now,
                )

            elif message_type == "GLOBAL_POSITION_INT":
                self._update_global_position(
                    message,
                    now,
                )

            elif message_type == "ATTITUDE":
                self._update_attitude(
                    message,
                    now,
                )

    # --------------------------------------------------------------
    # HEARTBEAT
    # --------------------------------------------------------------

    def _update_heartbeat(
        self,
        message: Any,
        now: float,
    ) -> None:

        self.heartbeat_received = True
        self.last_heartbeat_monotonic = now

        self.armed = bool(
            message.base_mode
            & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        )

        try:
            self.flight_mode = (
                mavutil.mode_string_v10(message)
            )
        except Exception:
            self.flight_mode = None

        self.system_status = message.system_status

    # --------------------------------------------------------------
    # SYS_STATUS
    # --------------------------------------------------------------

    def _update_sys_status(
        self,
        message: Any,
        now: float,
    ) -> None:

        if message.voltage_battery != 65535:
            self.battery_voltage_v = (
                message.voltage_battery / 1000.0
            )

        if message.current_battery != -1:
            self.battery_current_a = (
                message.current_battery / 100.0
            )

        if message.battery_remaining >= 0:
            self.battery_remaining_percent = (
                message.battery_remaining
            )

        self.battery_updated_monotonic = now

    # --------------------------------------------------------------
    # BATTERY_STATUS
    # --------------------------------------------------------------

    def _update_battery_status(
        self,
        message: Any,
        now: float,
    ) -> None:
        """
        BATTERY_STATUS can provide battery information in addition
        to SYS_STATUS.

        For now we use remaining percentage when available.
        """

        if message.battery_remaining >= 0:
            self.battery_remaining_percent = (
                message.battery_remaining
            )

        self.battery_updated_monotonic = now

    # --------------------------------------------------------------
    # GPS_RAW_INT
    # --------------------------------------------------------------

    def _update_gps(
        self,
        message: Any,
        now: float,
    ) -> None:

        self.gps_fix_type = message.fix_type
        self.gps_satellites = (
            message.satellites_visible
        )

        self.latitude = message.lat / 1e7
        self.longitude = message.lon / 1e7
        self.gps_altitude_m = message.alt / 1000.0

        self.gps_updated_monotonic = now

    # --------------------------------------------------------------
    # GLOBAL_POSITION_INT
    # --------------------------------------------------------------

    def _update_global_position(
        self,
        message: Any,
        now: float,
    ) -> None:

        self.latitude = message.lat / 1e7
        self.longitude = message.lon / 1e7

        self.relative_altitude_m = (
            message.relative_alt / 1000.0
        )

        self.position_updated_monotonic = now

    # --------------------------------------------------------------
    # ATTITUDE
    # --------------------------------------------------------------

    def _update_attitude(
        self,
        message: Any,
        now: float,
    ) -> None:

        self.roll_rad = message.roll
        self.pitch_rad = message.pitch
        self.yaw_rad = message.yaw

        self.attitude_updated_monotonic = now

    # --------------------------------------------------------------
    # Age / stale helpers
    # --------------------------------------------------------------

    @staticmethod
    def _age(
        timestamp: float | None,
    ) -> float | None:

        if timestamp is None:
            return None

        return time.monotonic() - timestamp

    def heartbeat_age(self) -> float | None:
        with self._lock:
            return self._age(
                self.last_heartbeat_monotonic
            )

    def battery_age(self) -> float | None:
        with self._lock:
            return self._age(
                self.battery_updated_monotonic
            )

    def gps_age(self) -> float | None:
        with self._lock:
            return self._age(
                self.gps_updated_monotonic
            )

    def position_age(self) -> float | None:
        with self._lock:
            return self._age(
                self.position_updated_monotonic
            )

    def attitude_age(self) -> float | None:
        with self._lock:
            return self._age(
                self.attitude_updated_monotonic
            )

    # --------------------------------------------------------------
    # Convenience state queries
    # --------------------------------------------------------------

    def is_armed(self) -> bool:
        with self._lock:
            return self.armed is True

    def gps_has_3d_fix(self) -> bool:
        with self._lock:

            if self.gps_fix_type is None:
                return False

            return self.gps_fix_type >= 3

    # --------------------------------------------------------------
    # Snapshot
    # --------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """
        Return a thread-safe snapshot of current telemetry.
        """

        with self._lock:

            return {
                "heartbeat": {
                    "received": self.heartbeat_received,
                    "age_sec": self._age(
                        self.last_heartbeat_monotonic
                    ),
                },

                "vehicle": {
                    "armed": self.armed,
                    "mode": self.flight_mode,
                    "system_status": self.system_status,
                },

                "battery": {
                    "voltage_v": self.battery_voltage_v,
                    "current_a": self.battery_current_a,
                    "remaining_percent":
                        self.battery_remaining_percent,
                    "age_sec": self._age(
                        self.battery_updated_monotonic
                    ),
                },

                "gps": {
                    "fix_type": self.gps_fix_type,
                    "satellites": self.gps_satellites,
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "altitude_m": self.gps_altitude_m,
                    "age_sec": self._age(
                        self.gps_updated_monotonic
                    ),
                },

                "position": {
                    "relative_altitude_m":
                        self.relative_altitude_m,
                    "age_sec": self._age(
                        self.position_updated_monotonic
                    ),
                },

                "attitude": {
                    "roll_rad": self.roll_rad,
                    "pitch_rad": self.pitch_rad,
                    "yaw_rad": self.yaw_rad,
                    "age_sec": self._age(
                        self.attitude_updated_monotonic
                    ),
                },
            }