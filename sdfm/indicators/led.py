from __future__ import annotations

import threading
from enum import Enum
from typing import Any, Callable

from sdfm.perception.state import ObstacleLevel


class LedStatus(str, Enum):
    OFF = "OFF"
    STARTING = "STARTING"
    READY = "READY"
    CLEAR = "CLEAR"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    TELEMETRY_LOST = "TELEMETRY_LOST"
    CRITICAL = "CRITICAL"


def status_for_obstacle(level: ObstacleLevel) -> LedStatus:
    return {
        ObstacleLevel.CLEAR: LedStatus.CLEAR,
        ObstacleLevel.WARNING: LedStatus.WARNING,
        ObstacleLevel.BLOCKED: LedStatus.BLOCKED,
        ObstacleLevel.UNKNOWN: LedStatus.UNKNOWN,
    }[level]


class StatusLedController:
    """Drive three active-high LEDs. Safety states override normal states."""

    SAFETY_STATES = {
        LedStatus.BLOCKED,
        LedStatus.UNKNOWN,
        LedStatus.TELEMETRY_LOST,
        LedStatus.CRITICAL,
    }

    def __init__(self, blue: Any, green: Any, orange: Any) -> None:
        self.blue = blue
        self.green = green
        self.orange = orange
        self._status = LedStatus.OFF
        self._lock = threading.RLock()
        self._closed = False
        self._apply(LedStatus.OFF)

    @classmethod
    def from_gpiozero(
        cls,
        blue_gpio: int,
        green_gpio: int,
        orange_gpio: int,
        *,
        led_factory: Callable[..., Any] | None = None,
    ) -> "StatusLedController":
        if len({blue_gpio, green_gpio, orange_gpio}) != 3:
            raise ValueError("status LED GPIO pins must be unique")
        if led_factory is None:
            try:
                from gpiozero import LED as led_factory
            except ImportError as exc:
                raise RuntimeError("gpiozero is required for status LEDs") from exc
        create = lambda pin: led_factory(pin, active_high=True, initial_value=False)
        return cls(create(blue_gpio), create(green_gpio), create(orange_gpio))

    @property
    def status(self) -> LedStatus:
        return self._status

    def set_status(self, status: LedStatus, *, safety_override: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            if self._status in self.SAFETY_STATES and status not in self.SAFETY_STATES:
                if not safety_override:
                    return
            self._apply(status)
            self._status = status

    def clear_safety(self, next_status: LedStatus = LedStatus.READY) -> None:
        self.set_status(next_status, safety_override=True)

    def _all_off(self) -> None:
        # gpiozero off() also stops a previous background blink operation.
        self.blue.off()
        self.green.off()
        self.orange.off()

    def _apply(self, status: LedStatus) -> None:
        self._all_off()
        if status == LedStatus.STARTING:
            self.blue.blink(on_time=0.25, off_time=0.75, background=True)
        elif status == LedStatus.READY:
            self.blue.on()
        elif status == LedStatus.CLEAR:
            self.green.on()
        elif status == LedStatus.WARNING:
            self.orange.on()
        elif status in {LedStatus.BLOCKED, LedStatus.CRITICAL}:
            self.orange.blink(on_time=0.10, off_time=0.10, background=True)
        elif status == LedStatus.UNKNOWN:
            self.green.blink(on_time=0.25, off_time=0.25, background=True)
            self.orange.blink(on_time=0.25, off_time=0.25, background=True)
        elif status == LedStatus.TELEMETRY_LOST:
            self.blue.blink(on_time=0.15, off_time=0.15, background=True)
            self.orange.blink(on_time=0.15, off_time=0.15, background=True)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._all_off()
            for led in (self.blue, self.green, self.orange):
                led.close()
            self._closed = True

    def __enter__(self) -> "StatusLedController":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
