from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ObstacleLevel(str, Enum):
    UNKNOWN = "UNKNOWN"
    CLEAR = "CLEAR"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class PerceptionState:
    """Immutable result of one front-depth observation."""

    front_distance_m: float | None
    nearest_distance_m: float | None
    median_distance_m: float | None
    obstacle_detected: bool
    obstacle_level: ObstacleLevel
    frame_age_sec: float
    depth_valid: bool
    valid_depth_ratio: float
    confidence: float
    stale: bool
    captured_monotonic: float

    def snapshot(self) -> dict[str, Any]:
        return {
            "front_distance_m": self.front_distance_m,
            "nearest_distance_m": self.nearest_distance_m,
            "median_distance_m": self.median_distance_m,
            "obstacle_detected": self.obstacle_detected,
            "obstacle_level": self.obstacle_level.value,
            "frame_age_sec": self.frame_age_sec,
            "depth_valid": self.depth_valid,
            "valid_depth_ratio": self.valid_depth_ratio,
            "confidence": self.confidence,
            "stale": self.stale,
        }
