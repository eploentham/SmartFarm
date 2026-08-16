from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

from sdfm import config
from sdfm.perception.obstacle import ObstacleConfig, ObstacleDetector
from sdfm.ros.adapters.depth_image import DepthImageAdapter, DepthImageFormatError
from sdfm.sensors.realsense import RealSenseConfig


class SdfmDepthSubscriber(Node):
    """Read D435i depth only; this node has no MAVLink or flight-command path."""

    def __init__(self) -> None:
        super().__init__("sdfm_depth_subscriber")
        topic = self.declare_parameter("depth_topic", "").value
        self._report_period = float(self.declare_parameter("report_period_sec", 0.5).value)
        self._frame_timeout = float(self.declare_parameter("frame_timeout_sec", 2.0).value)
        if not topic:
            raise ValueError(
                "depth_topic is required; inspect `ros2 topic list` and pass "
                "`--ros-args -p depth_topic:=<actual-topic>`"
            )

        sensor_config = RealSenseConfig(
            width=config.REALSENSE_WIDTH,
            height=config.REALSENSE_HEIGHT,
            fps=config.REALSENSE_FPS,
            roi_x_min=config.REALSENSE_ROI_X_MIN,
            roi_x_max=config.REALSENSE_ROI_X_MAX,
            roi_y_min=config.REALSENSE_ROI_Y_MIN,
            roi_y_max=config.REALSENSE_ROI_Y_MAX,
            minimum_depth_m=config.REALSENSE_MIN_DEPTH_M,
            maximum_depth_m=config.REALSENSE_MAX_DEPTH_M,
        )
        self._adapter = DepthImageAdapter(sensor_config)
        self._detector = ObstacleDetector(ObstacleConfig(
            blocked_distance_m=config.OBSTACLE_BLOCKED_M,
            warning_distance_m=config.OBSTACLE_WARNING_M,
            minimum_valid_ratio=config.DEPTH_MIN_VALID_RATIO,
            stale_after_sec=config.DEPTH_STALE_AFTER_SEC,
        ))
        self._last_frame_at: float | None = None
        self._last_report_at = 0.0
        self._timeout_reported = False
        self.create_subscription(Image, topic, self._on_depth, qos_profile_sensor_data)
        self.create_timer(0.5, self._check_stream)
        self.get_logger().info(f"Listening for depth on {topic!r}; flight commands disabled")

    def _on_depth(self, message: Image) -> None:
        now = time.monotonic()
        try:
            observation = self._adapter.convert(message, received_monotonic=now)
            state = self._detector.evaluate(
                observation.roi_depth_m,
                captured_monotonic=observation.captured_monotonic,
                now_monotonic=now,
            )
        except (DepthImageFormatError, ValueError) as exc:
            self.get_logger().error(f"Rejected depth frame: {exc}")
            return
        self._last_frame_at = now
        self._timeout_reported = False
        if now - self._last_report_at >= self._report_period:
            nearest = "N/A" if state.nearest_distance_m is None else f"{state.nearest_distance_m:.2f} m"
            median = "N/A" if state.median_distance_m is None else f"{state.median_distance_m:.2f} m"
            self.get_logger().info(
                f"depth nearest={nearest} median={median} valid={state.valid_depth_ratio:.0%} "
                f"state={state.obstacle_level.value}"
            )
            self._last_report_at = now

    def _check_stream(self) -> None:
        age = None if self._last_frame_at is None else time.monotonic() - self._last_frame_at
        if (age is None or age > self._frame_timeout) and not self._timeout_reported:
            detail = "no frame received" if age is None else f"last frame {age:.1f}s ago"
            self.get_logger().warning(f"DEPTH_STREAM_UNAVAILABLE: {detail}; perception is UNKNOWN")
            self._timeout_reported = True


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = SdfmDepthSubscriber()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

