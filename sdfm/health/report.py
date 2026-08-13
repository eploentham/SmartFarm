# sdfm/health/report.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    """
    Standard health states used across SDFM.
    """

    UNKNOWN = "UNKNOWN"
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    STALE = "STALE"
    NOT_READY = "NOT_READY"


@dataclass
class HealthResult:
    """
    Result of a single system or sensor health check.
    """

    name: str
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def healthy(self) -> bool:
        return self.status == HealthStatus.OK

    @property
    def failed(self) -> bool:
        return self.status == HealthStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SystemCheckReport:
    """
    Complete health report for DR01.
    """

    vehicle: str
    host: str

    checks: list[HealthResult] = field(default_factory=list)

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def add(self, result: HealthResult) -> None:
        self.checks.append(result)

    def get(self, name: str) -> HealthResult | None:
        for result in self.checks:
            if result.name == name:
                return result

        return None

    def has_failed(self) -> bool:
        return any(
            result.status == HealthStatus.FAILED
            for result in self.checks
        )

    def has_degraded(self) -> bool:
        return any(
            result.status == HealthStatus.DEGRADED
            for result in self.checks
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vehicle": self.vehicle,
            "host": self.host,
            "timestamp": self.timestamp.isoformat(),
            "checks": [
                result.to_dict()
                for result in self.checks
            ],
        }