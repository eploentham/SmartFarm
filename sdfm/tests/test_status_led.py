import unittest

from sdfm.indicators.led import LedStatus, StatusLedController


class FakeLed:
    def __init__(self):
        self.mode = "off"
        self.closed = False

    def on(self):
        self.mode = "on"

    def off(self):
        self.mode = "off"

    def blink(self, **kwargs):
        self.mode = "blink"

    def close(self):
        self.closed = True


class StatusLedTests(unittest.TestCase):
    def setUp(self):
        self.blue, self.green, self.orange = FakeLed(), FakeLed(), FakeLed()
        self.leds = StatusLedController(self.blue, self.green, self.orange)

    def tearDown(self):
        self.leds.close()

    def test_normal_colour_mapping(self):
        self.leds.set_status(LedStatus.CLEAR)
        self.assertEqual((self.blue.mode, self.green.mode, self.orange.mode), ("off", "on", "off"))
        self.leds.set_status(LedStatus.WARNING)
        self.assertEqual((self.blue.mode, self.green.mode, self.orange.mode), ("off", "off", "on"))

    def test_blocked_flashes_orange_and_cannot_be_cleared_accidentally(self):
        self.leds.set_status(LedStatus.BLOCKED)
        self.assertEqual(self.orange.mode, "blink")
        self.leds.set_status(LedStatus.CLEAR)
        self.assertEqual(self.leds.status, LedStatus.BLOCKED)
        self.leds.clear_safety(LedStatus.CLEAR)
        self.assertEqual(self.green.mode, "on")

    def test_unknown_flashes_green_and_orange(self):
        self.leds.set_status(LedStatus.UNKNOWN)
        self.assertEqual((self.green.mode, self.orange.mode), ("blink", "blink"))


if __name__ == "__main__":
    unittest.main()
