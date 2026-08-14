import unittest

import numpy as np

from sdfm.debug.safety import WalkSafetyInterlock, WalkSafetyViolation
from sdfm.perception.obstacle import ObstacleConfig, ObstacleDetector
from sdfm.perception.state import ObstacleLevel


class ObstacleDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = ObstacleDetector(ObstacleConfig(stale_after_sec=0.5))

    def test_clear_warning_and_blocked(self):
        for distance, expected in ((2.0, ObstacleLevel.CLEAR), (1.0, ObstacleLevel.WARNING), (0.5, ObstacleLevel.BLOCKED)):
            state = self.detector.evaluate(np.full((10, 10), distance), captured_monotonic=10.0, now_monotonic=10.1)
            self.assertEqual(state.obstacle_level, expected)

    def test_invalid_or_stale_depth_is_unknown(self):
        invalid = self.detector.evaluate(np.full((4, 4), np.nan), captured_monotonic=10.0, now_monotonic=10.1)
        stale = self.detector.evaluate(np.ones((4, 4)), captured_monotonic=10.0, now_monotonic=10.6)
        self.assertEqual(invalid.obstacle_level, ObstacleLevel.UNKNOWN)
        self.assertEqual(stale.obstacle_level, ObstacleLevel.UNKNOWN)

    def test_single_bad_pixel_does_not_create_false_block(self):
        depths = np.full((10, 10), 2.0)
        depths[0, 0] = 0.2
        state = self.detector.evaluate(depths, captured_monotonic=10.0, now_monotonic=10.1)
        self.assertEqual(state.obstacle_level, ObstacleLevel.CLEAR)

    def test_arm_and_takeoff_are_unconditionally_denied(self):
        with self.assertRaises(WalkSafetyViolation):
            WalkSafetyInterlock.arm()
        with self.assertRaises(WalkSafetyViolation):
            WalkSafetyInterlock.takeoff()

if __name__ == "__main__":
    unittest.main()
