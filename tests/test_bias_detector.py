import unittest

import pandas as pd

from bias.bias_detector import BiasDetector, _compute_slope


class DummyConfig:
    def __init__(self, data):
        self.data = data

    def require(self, *keys):
        value = self.data

        for key in keys:
            value = value[key]

        return value

    def get(self, *keys, default=None):
        value = self.data

        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]

        return value


def make_config(slope_threshold=0.0005):
    return DummyConfig({
        "strategy": {
            "bias": {
                "ema_column": "ema50",
                "slope_lookback": 3,
                "slope_threshold": slope_threshold,
            }
        }
    })


class ComputeSlopeTests(unittest.TestCase):
    def test_compute_slope_returns_relative_change_over_requested_window(self):
        series = pd.Series([100.0, 101.0, 102.0, 103.0])

        slope = _compute_slope(series, lookback=3)

        self.assertAlmostEqual(slope, 0.03)

    def test_compute_slope_returns_zero_for_zero_base_value(self):
        series = pd.Series([0.0, 1.0, 2.0, 3.0])

        slope = _compute_slope(series, lookback=3)

        self.assertEqual(slope, 0.0)


class BiasDetectorTests(unittest.TestCase):
    def test_bias_stays_neutral_when_slope_is_positive_but_below_threshold(self):
        df = pd.DataFrame(
            {
                "close": [100.01, 100.02, 100.02, 100.05],
                "ema50": [100.0, 100.01, 100.02, 100.03],
            }
        )

        bias = BiasDetector(config=make_config(slope_threshold=0.0005)).get_bias(df)

        self.assertEqual(bias, "neutral")

    def test_bias_is_bullish_when_price_is_above_ema_and_slope_is_clear(self):
        df = pd.DataFrame(
            {
                "close": [100.5, 100.8, 101.0, 101.5],
                "ema50": [100.0, 100.2, 100.4, 100.8],
            }
        )

        bias = BiasDetector(config=make_config(slope_threshold=0.0005)).get_bias(df)

        self.assertEqual(bias, "bullish")

    def test_bias_is_bearish_when_price_is_below_ema_and_slope_is_clear(self):
        df = pd.DataFrame(
            {
                "close": [99.5, 99.2, 99.0, 98.5],
                "ema50": [100.0, 99.8, 99.6, 99.2],
            }
        )

        bias = BiasDetector(config=make_config(slope_threshold=0.0005)).get_bias(df)

        self.assertEqual(bias, "bearish")

    def test_bias_snapshot_includes_continuous_strength_fields(self):
        df = pd.DataFrame(
            {
                "close": [100.5, 100.8, 101.0, 101.5],
                "ema50": [100.0, 100.2, 100.4, 100.8],
            }
        )

        snapshot = BiasDetector(config=make_config(slope_threshold=0.0005)).get_bias_snapshot(df)

        self.assertEqual(snapshot["label"], "bullish")
        self.assertGreater(snapshot["price_vs_ema_ratio"], 0.0)
        self.assertGreater(snapshot["ema_slope"], 0.0)
        self.assertGreater(snapshot["directional_strength"], 0.0)
        self.assertIn("distance_strength", snapshot)
        self.assertIn("slope_strength", snapshot)

    def test_bias_snapshot_can_express_negative_directional_strength(self):
        df = pd.DataFrame(
            {
                "close": [99.5, 99.2, 99.0, 98.5],
                "ema50": [100.0, 99.8, 99.6, 99.2],
            }
        )

        snapshot = BiasDetector(config=make_config(slope_threshold=0.0005)).get_bias_snapshot(df)

        self.assertEqual(snapshot["label"], "bearish")
        self.assertLess(snapshot["directional_strength"], 0.0)


if __name__ == "__main__":
    unittest.main()
