import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

# Tests are runnable from either ~/smartfarm or ~/smartfarm/sdfm.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sdfm.ros.adapters.depth_image import DepthImageAdapter, DepthImageFormatError
from sdfm.sensors.realsense import RealSenseConfig


def image(data, *, encoding, width, height, step=None, bigendian=False):
    return SimpleNamespace(
        data=data,
        encoding=encoding,
        width=width,
        height=height,
        step=step or width * (2 if encoding == "16UC1" else 4),
        is_bigendian=bigendian,
        header=SimpleNamespace(stamp=SimpleNamespace(nanosec=123)),
    )


class DepthImageAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = DepthImageAdapter(RealSenseConfig(
            roi_x_min=0.0, roi_x_max=1.0, roi_y_min=0.0, roi_y_max=1.0
        ))

    def test_converts_16uc1_millimetres_and_invalid_values(self):
        values = np.array([[1000, 0], [2500, 9000]], dtype="<u2")
        result = self.adapter.convert(image(values.tobytes(), encoding="16UC1", width=2, height=2), received_monotonic=10.0)
        np.testing.assert_allclose(result.roi_depth_m[0, 0], 1.0)
        np.testing.assert_allclose(result.roi_depth_m[1, 0], 2.5)
        self.assertTrue(np.isnan(result.roi_depth_m[0, 1]))
        self.assertTrue(np.isnan(result.roi_depth_m[1, 1]))

    def test_converts_32fc1_metres(self):
        values = np.array([[0.5, 3.0]], dtype="<f4")
        result = self.adapter.convert(image(values.tobytes(), encoding="32FC1", width=2, height=1))
        np.testing.assert_allclose(result.roi_depth_m, values)

    def test_rejects_non_depth_encoding_and_short_data(self):
        with self.assertRaises(DepthImageFormatError):
            self.adapter.convert(image(b"1234", encoding="rgb8", width=1, height=1))
        with self.assertRaises(DepthImageFormatError):
            self.adapter.convert(image(b"\0", encoding="16UC1", width=1, height=1))


if __name__ == "__main__":
    unittest.main()

