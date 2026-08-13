# sdfm/core/result.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ResultCode(str, Enum):
    """
    Standard SDFM operation result codes.
    """

    SUCCESS = "SUCCESS"

    # MAVLink / Pixhawk
    PIXHAWK_LOST = "PIXHAWK_LOST"
    ACK_TIMEOUT = "ACK_TIMEOUT"
    COMMAND_DENIED = "COMMAND_DENIED"
    COMMAND_FAILED = "COMMAND_FAILED"

    # Flight
    MODE_CHANGE_FAILED = "MODE_CHANGE_FAILED"
    ARM_FAILED = "ARM_FAILED"
    DISARM_FAILED = "DISARM_FAILED"
    TAKEOFF_FAILED = "TAKEOFF_FAILED"
    ALTITUDE_TIMEOUT = "ALTITUDE_TIMEOUT"
    LAND_FAILED = "LAND_FAILED"
    RTL_FAILED = "RTL_FAILED"

    # Navigation
    GPS_LOST = "GPS_LOST"
    POSITION_TIMEOUT = "POSITION_TIMEOUT"

    # Sensors
    SENSOR_FAILED = "SENSOR_FAILED"
    SENSOR_STALE = "SENSOR_STALE"

    # System
    TIMEOUT = "TIMEOUT"
    NOT_READY = "NOT_READY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class OperationResult:
    """
    Standard result returned by SDFM operations.

    Commands should return an OperationResult instead of
    returning only True / False.
    """

    success: bool
    code: ResultCode
    message: str = ""

    details: dict[str, Any] = field(
        default_factory=dict
    )

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def ok(
        cls,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> "OperationResult":

        return cls(
            success=True,
            code=ResultCode.SUCCESS,
            message=message,
            details=details or {},
        )

    @classmethod
    def failed(
        cls,
        code: ResultCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "OperationResult":

        if code == ResultCode.SUCCESS:
            raise ValueError(
                "Failed result cannot use SUCCESS code"
            )

        return cls(
            success=False,
            code=code,
            message=message,
            details=details or {},
        )

    def to_dict(self) -> dict[str, Any]:

        return {
            "success": self.success,
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }