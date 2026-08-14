from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class RealSenseConfig:
    width: int = 640
    height: int = 480
    fps: int = 30
    roi_x_min: float = 0.25
    roi_x_max: float = 0.75
    roi_y_min: float = 0.25
    roi_y_max: float = 0.75
    minimum_depth_m: float = 0.15
    maximum_depth_m: float = 8.0
    frame_timeout_ms: int = 1000

    def __post_init__(self) -> None:
        if not (0 <= self.roi_x_min < self.roi_x_max <= 1):
            raise ValueError("invalid horizontal ROI")
        if not (0 <= self.roi_y_min < self.roi_y_max <= 1):
            raise ValueError("invalid vertical ROI")
        if not 0 < self.minimum_depth_m < self.maximum_depth_m:
            raise ValueError("invalid depth range")


@dataclass(frozen=True, slots=True)
class DepthObservation:
    roi_depth_m: np.ndarray
    captured_monotonic: float
    frame_number: int


class RealSenseDepthSensor:
    """Lifecycle owner for D435i depth streaming and front ROI extraction."""

    def __init__(self, config: RealSenseConfig | None = None, rs_module: Any = None) -> None:
        self.config = config or RealSenseConfig()
        if rs_module is None:
            try:
                import pyrealsense2 as rs_module  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError("pyrealsense2 is required for the D435i") from exc
        self._rs = rs_module
        self._pipeline = None
        self._depth_scale = None

    @property
    def running(self) -> bool:
        return self._pipeline is not None

    def start(self) -> None:
        if self.running:
            return
        pipeline = self._rs.pipeline()
        stream_config = self._rs.config()
        stream_config.enable_stream(
            self._rs.stream.depth,
            self.config.width,
            self.config.height,
            self._rs.format.z16,
            self.config.fps,
        )
        profile = pipeline.start(stream_config)
        self._depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()
        self._pipeline = pipeline

    def stop(self) -> None:
        pipeline, self._pipeline = self._pipeline, None
        if pipeline is not None:
            pipeline.stop()

    def read(self) -> DepthObservation:
        if self._pipeline is None or self._depth_scale is None:
            raise RuntimeError("REALSENSE_NOT_STARTED")
        frames = self._pipeline.wait_for_frames(self.config.frame_timeout_ms)
        depth_frame = frames.get_depth_frame()
        if not depth_frame:
            raise RuntimeError("REALSENSE_DEPTH_FRAME_MISSING")
        captured = time.monotonic()
        depth_m = np.asanyarray(depth_frame.get_data()).astype(np.float32) * self._depth_scale
        y0 = int(depth_m.shape[0] * self.config.roi_y_min)
        y1 = int(depth_m.shape[0] * self.config.roi_y_max)
        x0 = int(depth_m.shape[1] * self.config.roi_x_min)
        x1 = int(depth_m.shape[1] * self.config.roi_x_max)
        roi = depth_m[y0:y1, x0:x1].copy()
        invalid = (
            ~np.isfinite(roi)
            | (roi < self.config.minimum_depth_m)
            | (roi > self.config.maximum_depth_m)
        )
        roi[invalid] = np.nan
        return DepthObservation(roi, captured, int(depth_frame.get_frame_number()))

    def __enter__(self) -> "RealSenseDepthSensor":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()
