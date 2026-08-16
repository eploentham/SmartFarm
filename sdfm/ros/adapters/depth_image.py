from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from sdfm.sensors.realsense import DepthObservation, RealSenseConfig


class DepthImageFormatError(ValueError):
    """The ROS Image cannot safely be interpreted as a depth image."""


@dataclass(frozen=True, slots=True)
class DepthImageAdapter:
    """Convert a sensor_msgs/Image-like object into the existing SDFM model.

    Keeping this duck-typed and free of rclpy/sensor_msgs makes conversion and
    perception testable on a development machine and during offline replay.
    """

    config: RealSenseConfig = RealSenseConfig()

    def convert(
        self,
        message: Any,
        *,
        received_monotonic: float | None = None,
    ) -> DepthObservation:
        encoding = str(message.encoding).upper()
        if encoding == "16UC1":
            dtype = np.dtype(">u2" if message.is_bigendian else "<u2")
            scale = 0.001  # sensor_msgs convention: unsigned depth in millimetres
        elif encoding == "32FC1":
            dtype = np.dtype(">f4" if message.is_bigendian else "<f4")
            scale = 1.0  # sensor_msgs convention: floating depth in metres
        else:
            raise DepthImageFormatError(
                f"unsupported depth encoding {message.encoding!r}; expected 16UC1 or 32FC1"
            )

        height, width, step = int(message.height), int(message.width), int(message.step)
        if height <= 0 or width <= 0 or step < width * dtype.itemsize:
            raise DepthImageFormatError("invalid depth image dimensions or row step")
        raw = memoryview(message.data)
        required = height * step
        if len(raw) < required:
            raise DepthImageFormatError("depth image data is shorter than height * step")

        # Respect row padding instead of assuming tightly packed ROS images.
        row_items = step // dtype.itemsize
        if step % dtype.itemsize:
            raise DepthImageFormatError("depth image row step is not item-aligned")
        depth = np.frombuffer(raw[:required], dtype=dtype).reshape(height, row_items)
        depth_m = depth[:, :width].astype(np.float32) * scale

        c = self.config
        y0, y1 = int(height * c.roi_y_min), int(height * c.roi_y_max)
        x0, x1 = int(width * c.roi_x_min), int(width * c.roi_x_max)
        roi = depth_m[y0:y1, x0:x1].copy()
        invalid = (
            ~np.isfinite(roi)
            | (roi < c.minimum_depth_m)
            | (roi > c.maximum_depth_m)
        )
        roi[invalid] = np.nan

        header = getattr(message, "header", None)
        stamp = getattr(header, "stamp", None)
        frame_number = int(getattr(stamp, "nanosec", 0))
        captured = time.monotonic() if received_monotonic is None else received_monotonic
        return DepthObservation(roi, captured, frame_number)

