from __future__ import annotations

import csv
import math
import time
from pathlib import Path
from typing import TextIO

from pymavlink import mavutil

from sdfm import config
from sdfm.debug.safety import WalkSafetyInterlock, WalkSafetyViolation
from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState
from sdfm.indicators.led import LedStatus, StatusLedController, status_for_obstacle
from sdfm.perception.obstacle import ObstacleConfig, ObstacleDetector
from sdfm.perception.state import PerceptionState
from sdfm.sensors.realsense import RealSenseConfig, RealSenseDepthSensor


DEBUG_WALK_MODE = True


class DebugWalkRunner:
    """Run depth perception and read-only flight telemetry while hand-carried."""

    def __init__(
        self,
        *,
        pixhawk: PixhawkConnection | None = None,
        sensor: RealSenseDepthSensor | None = None,
        telemetry: TelemetryState | None = None,
        output: TextIO | None = None,
        csv_path: Path | None = None,
        leds: StatusLedController | None = None,
    ) -> None:
        if not DEBUG_WALK_MODE or not config.DEBUG_WALK_MODE:
            raise WalkSafetyViolation("DEBUG_WALK_MODE_MUST_BE_TRUE")
        self.pixhawk = pixhawk or PixhawkConnection(
            baud=config.MAVLINK_BAUD,
            heartbeat_timeout_sec=config.HEARTBEAT_TIMEOUT_SEC,
        )
        self.telemetry = telemetry or TelemetryState()
        self.router = MavlinkRouter(self.pixhawk, self.telemetry)
        self.sensor = sensor or RealSenseDepthSensor(
            RealSenseConfig(
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
        )
        self.detector = ObstacleDetector(
            ObstacleConfig(
                blocked_distance_m=config.OBSTACLE_BLOCKED_M,
                warning_distance_m=config.OBSTACLE_WARNING_M,
                minimum_valid_ratio=config.DEPTH_MIN_VALID_RATIO,
                stale_after_sec=config.DEPTH_STALE_AFTER_SEC,
            )
        )
        import sys
        self.output = output or sys.stdout
        self.csv_path = csv_path
        self.leds = leds

    def _start_leds(self) -> None:
        if self.leds is None and config.STATUS_LED_ENABLED:
            self.leds = StatusLedController.from_gpiozero(
                config.STATUS_LED_BLUE_GPIO,
                config.STATUS_LED_GREEN_GPIO,
                config.STATUS_LED_ORANGE_GPIO,
            )
        if self.leds is not None:
            self.leds.set_status(LedStatus.STARTING, safety_override=True)

    def _update_leds(self, perception: PerceptionState) -> None:
        if self.leds is None:
            return
        heartbeat_age = self.telemetry.heartbeat_age()
        if heartbeat_age is None or heartbeat_age > config.HEARTBEAT_TIMEOUT_SEC:
            self.leds.set_status(LedStatus.TELEMETRY_LOST)
            return
        self.leds.set_status(
            status_for_obstacle(perception.obstacle_level),
            safety_override=True,
        )

    def _request_telemetry(self) -> None:
        # Message-rate requests are telemetry configuration only; they neither
        # change flight mode nor command actuators.
        for message_id, frequency_hz in (
            (mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT, 2.0),
            (mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT, 2.0),
            (mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 5.0),
            (mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE, 5.0),
            (mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS, 1.0),
        ):
            self.pixhawk.request_message_interval(message_id, frequency_hz)

    @staticmethod
    def _degrees(value: float | None) -> float | None:
        return None if value is None else math.degrees(value)

    @staticmethod
    def _display(value: object, precision: int = 2) -> str:
        if value is None:
            return "--"
        if isinstance(value, float):
            return f"{value:.{precision}f}"
        return str(value)

    def _status_line(self, perception: PerceptionState) -> str:
        telemetry = self.telemetry.snapshot()
        gps, attitude = telemetry["gps"], telemetry["attitude"]
        position, battery = telemetry["position"], telemetry["battery"]
        heartbeat = telemetry["heartbeat"]
        return (
            f"{perception.obstacle_level.value:<7} "
            f"front={self._display(perception.front_distance_m)}m "
            f"median={self._display(perception.median_distance_m)}m "
            f"valid={perception.valid_depth_ratio:.0%} "
            f"frame_age={perception.frame_age_sec:.3f}s | "
            f"GPS={gps['fix_type'] or '--'}/{gps['satellites'] or '--'} "
            f"lat={self._display(gps['latitude'], 7)} "
            f"lon={self._display(gps['longitude'], 7)} "
            f"roll={self._display(self._degrees(attitude['roll_rad']))}deg "
            f"pitch={self._display(self._degrees(attitude['pitch_rad']))}deg "
            f"yaw={self._display(self._degrees(attitude['yaw_rad']))}deg "
            f"rel_alt={self._display(position['relative_altitude_m'])}m "
            f"battery={self._display(battery['voltage_v'])}V/"
            f"{self._display(battery['remaining_percent'], 0)}% "
            f"heartbeat_age={self._display(heartbeat['age_sec'])}s"
        )

    def run(self, *, interval_sec: float = 0.20) -> None:
        csv_file: TextIO | None = None
        writer = None
        try:
            self._start_leds()
            self.pixhawk.connect()
            self.router.start()
            self._request_telemetry()
            self.sensor.start()
            if self.leds is not None:
                self.leds.set_status(LedStatus.READY, safety_override=True)
            if self.csv_path is not None:
                self.csv_path.parent.mkdir(parents=True, exist_ok=True)
                csv_file = self.csv_path.open("a", newline="", encoding="utf-8")
                writer = csv.DictWriter(csv_file, fieldnames=[
                    "timestamp", "level", "front_distance_m", "median_distance_m",
                    "valid_depth_ratio", "frame_age_sec", "latitude", "longitude",
                    "gps_fix", "satellites", "roll_rad", "pitch_rad", "yaw_rad",
                    "relative_altitude_m", "battery_voltage_v", "battery_percent",
                    "heartbeat_age_sec",
                ])
                if csv_file.tell() == 0:
                    writer.writeheader()

            print("DEBUG_WALK_MODE=True | ARM=BLOCKED | TAKEOFF=BLOCKED", file=self.output)
            while True:
                if self.telemetry.is_armed() and self.leds is not None:
                    self.leds.set_status(LedStatus.CRITICAL, safety_override=True)
                WalkSafetyInterlock.assert_disarmed(self.telemetry)
                observation = self.sensor.read()
                perception = self.detector.evaluate(
                    observation.roi_depth_m,
                    captured_monotonic=observation.captured_monotonic,
                )
                self._update_leds(perception)
                print(self._status_line(perception), file=self.output, flush=True)
                if writer is not None:
                    snap = self.telemetry.snapshot()
                    writer.writerow({
                        "timestamp": time.time(), "level": perception.obstacle_level.value,
                        "front_distance_m": perception.front_distance_m,
                        "median_distance_m": perception.median_distance_m,
                        "valid_depth_ratio": perception.valid_depth_ratio,
                        "frame_age_sec": perception.frame_age_sec,
                        "latitude": snap["gps"]["latitude"],
                        "longitude": snap["gps"]["longitude"],
                        "gps_fix": snap["gps"]["fix_type"],
                        "satellites": snap["gps"]["satellites"],
                        "roll_rad": snap["attitude"]["roll_rad"],
                        "pitch_rad": snap["attitude"]["pitch_rad"],
                        "yaw_rad": snap["attitude"]["yaw_rad"],
                        "relative_altitude_m": snap["position"]["relative_altitude_m"],
                        "battery_voltage_v": snap["battery"]["voltage_v"],
                        "battery_percent": snap["battery"]["remaining_percent"],
                        "heartbeat_age_sec": snap["heartbeat"]["age_sec"],
                    })
                    csv_file.flush()
                time.sleep(max(0.0, interval_sec))
        finally:
            self.sensor.stop()
            self.router.stop()
            self.pixhawk.close()
            if self.leds is not None:
                self.leds.close()
            if csv_file is not None:
                csv_file.close()
