# sdfm/safety/monitor.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
import time
from typing import Any

from sdfm.flight.telemetry import TelemetryState


class SafetySeverity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class SafetyIssue:
    code: str
    severity: SafetySeverity
    message: str
    details: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class SafetyStatus:
    timestamp: float
    safe: bool
    severity: SafetySeverity
    issues: list[SafetyIssue] = field(
        default_factory=list
    )


class SafetyMonitor:
    """
    Runtime safety monitor for DR01.

    IMPORTANT:
    This class only DETECTS safety problems.

    It does NOT:
        - ARM / DISARM
        - change flight mode
        - LAND
        - RTL

    Actions will be handled later by:
        policy.py
        failsafe.py
    """

    def __init__(
        self,
        telemetry: TelemetryState,
        *,
        heartbeat_timeout_sec: float = 3.0,
        battery_warning_percent: int = 30,
        battery_critical_percent: int = 20,
        gps_min_fix_type: int = 3,
        rc_timeout_sec: float = 2.0,
    ) -> None:

        self.telemetry = telemetry

        self.heartbeat_timeout_sec = (
            heartbeat_timeout_sec
        )

        self.battery_warning_percent = (
            battery_warning_percent
        )

        self.battery_critical_percent = (
            battery_critical_percent
        )

        self.gps_min_fix_type = gps_min_fix_type

        self.rc_timeout_sec = rc_timeout_sec

        self._lock = threading.Lock()

        self._last_status = SafetyStatus(
            timestamp=time.monotonic(),
            safe=False,
            severity=SafetySeverity.CRITICAL,
            issues=[
                SafetyIssue(
                    code="SAFETY_NOT_EVALUATED",
                    severity=SafetySeverity.CRITICAL,
                    message=(
                        "Safety monitor has not "
                        "evaluated telemetry yet"
                    ),
                )
            ],
        )

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def evaluate(self) -> SafetyStatus:
        """
        Evaluate current telemetry and return safety status.

        This method performs NO flight commands.
        """

        issues: list[SafetyIssue] = []

        self._check_heartbeat(
            issues
        )

        self._check_battery(
            issues
        )

        self._check_gps(
            issues
        )

        self._check_rc(
            issues
        )

        severity = self._highest_severity(
            issues
        )

        status = SafetyStatus(
            timestamp=time.monotonic(),
            safe=(
                severity != SafetySeverity.CRITICAL
            ),
            severity=severity,
            issues=issues,
        )

        with self._lock:
            self._last_status = status

        return status

    def last_status(self) -> SafetyStatus:

        with self._lock:
            return self._last_status

    # ----------------------------------------------------------
    # Heartbeat
    # ----------------------------------------------------------

    def _check_heartbeat(
        self,
        issues: list[SafetyIssue],
    ) -> None:

        received = getattr(
            self.telemetry,
            "heartbeat_received",
            False,
        )

        if not received:

            issues.append(
                SafetyIssue(
                    code="PIXHAWK_HEARTBEAT_MISSING",
                    severity=SafetySeverity.CRITICAL,
                    message=(
                        "Pixhawk heartbeat "
                        "has not been received"
                    ),
                )
            )

            return

        age = self._get_age(
            "heartbeat_age",
            "heartbeat_timestamp",
            "last_heartbeat_time",
        )

        if age is None:
            return

        if age > self.heartbeat_timeout_sec:

            issues.append(
                SafetyIssue(
                    code="PIXHAWK_LOST",
                    severity=SafetySeverity.CRITICAL,
                    message="Pixhawk heartbeat stale",
                    details={
                        "age_sec": round(age, 3),
                        "timeout_sec":
                            self.heartbeat_timeout_sec,
                    },
                )
            )

    # ----------------------------------------------------------
    # Battery
    # ----------------------------------------------------------

    def _check_battery(
        self,
        issues: list[SafetyIssue],
    ) -> None:

        remaining = self._first_value(
            "battery_remaining_percent",
            "battery_remaining",
        )

        if remaining is None:
            return

        try:
            remaining = int(
                remaining
            )
        except (TypeError, ValueError):
            return

        # MAVLink can use -1 for unknown battery percentage.
        if remaining < 0:
            return

        if remaining <= self.battery_critical_percent:

            issues.append(
                SafetyIssue(
                    code="BATTERY_CRITICAL",
                    severity=SafetySeverity.CRITICAL,
                    message=(
                        "Battery remaining is critical"
                    ),
                    details={
                        "remaining_percent":
                            remaining,
                        "threshold_percent":
                            self.battery_critical_percent,
                    },
                )
            )

            return

        if remaining <= self.battery_warning_percent:

            issues.append(
                SafetyIssue(
                    code="BATTERY_LOW",
                    severity=SafetySeverity.WARNING,
                    message="Battery remaining is low",
                    details={
                        "remaining_percent":
                            remaining,
                        "threshold_percent":
                            self.battery_warning_percent,
                    },
                )
            )

    # ----------------------------------------------------------
    # GPS
    # ----------------------------------------------------------

    def _check_gps(
        self,
        issues: list[SafetyIssue],
    ) -> None:

        fix_type = self._first_value(
            "gps_fix_type",
            "fix_type",
        )

        if fix_type is None:
            return

        try:
            fix_type = int(
                fix_type
            )
        except (TypeError, ValueError):
            return

        if fix_type < self.gps_min_fix_type:

            severity = (
                SafetySeverity.CRITICAL
                if self._is_armed()
                else SafetySeverity.WARNING
            )

            issues.append(
                SafetyIssue(
                    code="GPS_LOST",
                    severity=severity,
                    message="GPS fix is insufficient",
                    details={
                        "fix_type": fix_type,
                        "required_fix_type":
                            self.gps_min_fix_type,
                        "armed": self._is_armed(),
                    },
                )
            )

    # ----------------------------------------------------------
    # RC / ELRS
    # ----------------------------------------------------------

    def _check_rc(
        self,
        issues: list[SafetyIssue],
    ) -> None:

        channels = []

        for name in (
            "rc_ch1",
            "rc_ch2",
            "rc_ch3",
            "rc_ch4",
        ):

            value = getattr(
                self.telemetry,
                name,
                None,
            )

            if value is not None:
                channels.append(
                    value
                )

        if channels:

            try:
                invalid = any(
                    int(value) <= 0
                    for value in channels
                )
            except (TypeError, ValueError):
                invalid = True

            if invalid:

                severity = (
                    SafetySeverity.CRITICAL
                    if self._is_armed()
                    else SafetySeverity.WARNING
                )

                issues.append(
                    SafetyIssue(
                        code="RC_INPUT_INVALID",
                        severity=severity,
                        message=(
                            "RC / ELRS input invalid"
                        ),
                        details={
                            "channels": channels,
                            "armed": self._is_armed(),
                        },
                    )
                )

        age = self._get_age(
            "rc_age",
            "rc_timestamp",
            "last_rc_time",
        )

        if (
            age is not None
            and age > self.rc_timeout_sec
        ):

            severity = (
                SafetySeverity.CRITICAL
                if self._is_armed()
                else SafetySeverity.WARNING
            )

            issues.append(
                SafetyIssue(
                    code="RC_LOST",
                    severity=severity,
                    message="RC / ELRS telemetry stale",
                    details={
                        "age_sec": round(age, 3),
                        "timeout_sec":
                            self.rc_timeout_sec,
                        "armed": self._is_armed(),
                    },
                )
            )

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _is_armed(self) -> bool:

        method = getattr(
            self.telemetry,
            "is_armed",
            None,
        )

        if callable(method):

            try:
                return bool(
                    method()
                )
            except Exception:
                pass

        return bool(
            getattr(
                self.telemetry,
                "armed",
                False,
            )
        )

    def _first_value(
        self,
        *names: str,
    ):

        for name in names:

            if hasattr(
                self.telemetry,
                name,
            ):
                value = getattr(
                    self.telemetry,
                    name,
                )

                if value is not None:
                    return value

        return None

    def _get_age(
        self,
        age_name: str,
        timestamp_name: str,
        alternate_timestamp_name: str,
    ) -> float | None:

        value = getattr(
            self.telemetry,
            age_name,
            None,
        )

        if callable(value):

            try:
                return float(
                    value()
                )
            except Exception:
                pass

        elif value is not None:

            try:
                return float(
                    value
                )
            except (TypeError, ValueError):
                pass

        for name in (
            timestamp_name,
            alternate_timestamp_name,
        ):

            timestamp = getattr(
                self.telemetry,
                name,
                None,
            )

            if timestamp is None:
                continue

            try:
                return max(
                    0.0,
                    time.monotonic()
                    - float(timestamp),
                )
            except (TypeError, ValueError):
                continue

        return None

    @staticmethod
    def _highest_severity(
        issues: list[SafetyIssue],
    ) -> SafetySeverity:

        if any(
            issue.severity
            == SafetySeverity.CRITICAL
            for issue in issues
        ):
            return SafetySeverity.CRITICAL

        if any(
            issue.severity
            == SafetySeverity.WARNING
            for issue in issues
        ):
            return SafetySeverity.WARNING

        return SafetySeverity.OK