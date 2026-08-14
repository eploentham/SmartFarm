from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from sdfm.perception.state import ObstacleLevel, PerceptionState


@dataclass(frozen=True, slots=True)
class ObstacleConfig:
    blocked_distance_m: float = 0.8
    warning_distance_m: float = 1.5
    minimum_valid_ratio: float = 0.20
    stale_after_sec: float = 0.50
    nearest_percentile: float = 5.0

    def __post_init__(self) -> None:
        if not 0 < self.blocked_distance_m < self.warning_distance_m:
            raise ValueError("distance thresholds must satisfy 0 < blocked < warning")
        if not 0 <= self.minimum_valid_ratio <= 1:
            raise ValueError("minimum_valid_ratio must be between 0 and 1")


class ObstacleDetector:
    """Convert an ROI depth image (metres, invalid=NaN) into safe state."""

    def __init__(self, config: ObstacleConfig | None = None) -> None:
        self.config = config or ObstacleConfig()

    def evaluate(
        self,
        depth_roi_m: np.ndarray,
        *,
        captured_monotonic: float,
        now_monotonic: float | None = None,
    ) -> PerceptionState:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        age = max(0.0, now - captured_monotonic)
        values = np.asarray(depth_roi_m, dtype=np.float32)
        valid_mask = np.isfinite(values) & (values > 0)
        ratio = float(valid_mask.mean()) if values.size else 0.0
        valid_values = values[valid_mask]
        stale = age > self.config.stale_after_sec
        depth_valid = ratio >= self.config.minimum_valid_ratio and valid_values.size > 0

        nearest = (
            float(np.percentile(valid_values, self.config.nearest_percentile))
            if valid_values.size else None
        )
        median = float(np.median(valid_values)) if valid_values.size else None

        if stale or not depth_valid or nearest is None:
            level = ObstacleLevel.UNKNOWN
            front = None
        elif nearest <= self.config.blocked_distance_m:
            level, front = ObstacleLevel.BLOCKED, nearest
        elif nearest <= self.config.warning_distance_m:
            level, front = ObstacleLevel.WARNING, nearest
        else:
            level, front = ObstacleLevel.CLEAR, nearest

        # Confidence describes coverage and freshness, not semantic certainty.
        freshness = max(0.0, 1.0 - age / self.config.stale_after_sec)
        confidence = min(1.0, ratio / max(self.config.minimum_valid_ratio, 1e-6))
        confidence = confidence * freshness if depth_valid else 0.0

        return PerceptionState(
            front_distance_m=front,
            nearest_distance_m=nearest,
            median_distance_m=median,
            obstacle_detected=level in {ObstacleLevel.WARNING, ObstacleLevel.BLOCKED},
            obstacle_level=level,
            frame_age_sec=age,
            depth_valid=depth_valid,
            valid_depth_ratio=ratio,
            confidence=confidence,
            stale=stale,
            captured_monotonic=captured_monotonic,
        )
