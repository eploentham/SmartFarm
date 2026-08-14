from __future__ import annotations

from typing import Protocol


class _ArmedState(Protocol):
    def is_armed(self) -> bool: ...


class WalkSafetyViolation(RuntimeError):
    pass


class WalkSafetyInterlock:
    """Hard boundary: WALK DEBUG has no path that can arm or take off."""

    @staticmethod
    def arm(*args, **kwargs) -> None:
        raise WalkSafetyViolation("ARM_BLOCKED_IN_DEBUG_WALK_MODE")

    @staticmethod
    def takeoff(*args, **kwargs) -> None:
        raise WalkSafetyViolation("TAKEOFF_BLOCKED_IN_DEBUG_WALK_MODE")

    @staticmethod
    def assert_disarmed(telemetry: _ArmedState) -> None:
        if telemetry.is_armed():
            raise WalkSafetyViolation("PIXHAWK_ARMED_ABORT_DEBUG_WALK")
