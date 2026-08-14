# sdfm/flight/pixhawk.py

from __future__ import annotations

import glob
import os
import threading
import time
from typing import Any

from pymavlink import mavutil


DEFAULT_BAUD = 115200
DEFAULT_HEARTBEAT_TIMEOUT_SEC = 5.0


class PixhawkConnection:
    """
    Owns the MAVLink connection between SDFM and Pixhawk.

    Responsibilities:
    - discover Pixhawk serial device
    - open / close MAVLink connection
    - wait for initial heartbeat
    - expose connection state
    - provide controlled MAVLink send / receive access

    This class does NOT implement:
    - ARM
    - TAKEOFF
    - LAND
    - RTL
    - flight mode changes
    - mission logic
    """

    def __init__(
        self,
        device: str | None = None,
        baud: int = DEFAULT_BAUD,
        heartbeat_timeout_sec: float = DEFAULT_HEARTBEAT_TIMEOUT_SEC,
    ) -> None:

        self.device = device
        self.baud = baud
        self.heartbeat_timeout_sec = heartbeat_timeout_sec

        self.master = None

        self.system_id: int | None = None
        self.component_id: int | None = None

        self.last_heartbeat_monotonic: float | None = None

        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    @staticmethod
    def find_device() -> str | None:
        """
        Find Pixhawk USB serial device.

        Prefer persistent /dev/serial/by-id path.
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

        # Development fallback.
        for device in (
            "/dev/ttyACM0",
            "/dev/ttyACM1",
        ):
            if os.path.exists(device):
                return device

        return None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Open MAVLink connection and verify initial heartbeat.

        Raises:
            RuntimeError:
                Pixhawk device not found or heartbeat unavailable.
        """

        with self._lock:

            if self.master is not None:
                return

            if self.device is None:
                self.device = self.find_device()

            if self.device is None:
                raise RuntimeError(
                    "PIXHAWK_DEVICE_NOT_FOUND"
                )

            try:
                master = mavutil.mavlink_connection(
                    self.device,
                    baud=self.baud,
                    autoreconnect=True,
                )

                heartbeat = master.wait_heartbeat(
                    timeout=self.heartbeat_timeout_sec,
                )

                if heartbeat is None:
                    try:
                        master.close()
                    except Exception:
                        pass

                    raise RuntimeError(
                        "PIXHAWK_HEARTBEAT_TIMEOUT"
                    )

                self.master = master

                self.system_id = master.target_system
                self.component_id = master.target_component

                self.last_heartbeat_monotonic = (
                    time.monotonic()
                )

            except Exception:
                self.master = None
                self.system_id = None
                self.component_id = None
                self.last_heartbeat_monotonic = None

                raise

    def close(self) -> None:
        """
        Close MAVLink connection.
        """

        with self._lock:

            if self.master is not None:

                try:
                    self.master.close()
                finally:
                    self.master = None

            self.system_id = None
            self.component_id = None
            self.last_heartbeat_monotonic = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.master is not None

    def heartbeat_age(self) -> float | None:
        """
        Return seconds since last heartbeat observed by this object.
        """

        if self.last_heartbeat_monotonic is None:
            return None

        return (
            time.monotonic()
            - self.last_heartbeat_monotonic
        )

    # ------------------------------------------------------------------
    # MAVLink receive
    # ------------------------------------------------------------------

    def recv_match(
        self,
        *,
        type: str | list[str] | None = None,
        blocking: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """
        Controlled wrapper around pymavlink recv_match().
        """

        with self._lock:

            if self.master is None:
                raise RuntimeError(                    "PIXHAWK_NOT_CONNECTED"                )

            message = self.master.recv_match(
                type=type,
                blocking=blocking,
                timeout=timeout,
            )

            if (
                message is not None
                and message.get_type() == "HEARTBEAT"
            ):
                self.last_heartbeat_monotonic = (                    time.monotonic()                )

            return message

    # ------------------------------------------------------------------
    # Telemetry configuration
    # ------------------------------------------------------------------

    def request_message_interval(
        self,
        message_id: int,
        frequency_hz: float,
    ) -> None:
        """
        Request MAVLink telemetry message frequency.

        This does not ARM or move the aircraft.
        """

        with self._lock:

            if self.master is None:
                raise RuntimeError(
                    "PIXHAWK_NOT_CONNECTED"
                )

            if frequency_hz <= 0:
                interval_us = -1
            else:
                interval_us = int(
                    1_000_000 / frequency_hz
                )

            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                0,
                message_id,
                interval_us,
                0,                0,                0,                0,                0,
            )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "PixhawkConnection":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()