import unittest

import pandas as pd

from regime.regime_detector import RegimeDetector, _compute_slope


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
            "regime": {
                "ema_column": "ema50",
                "macro_weight": 2,
                "macro_slope_weight": 1,
                "trend_weight": 1,
                "slope_lookback": 3,
                "slope_threshold": slope_threshold,
                "strong_score": 3,
                "moderate_score": 2,
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


class RegimeDetectorTests(unittest.TestCase):
    def test_regime_does_not_award_macro_slope_for_tiny_positive_noise(self):
        df_12h = pd.DataFrame(
            {
                "close": [100.02, 100.03, 100.04, 100.05],
                "ema50": [100.0, 100.01, 100.02, 100.03],
            }
        )
        df_5h = pd.DataFrame(
            {
                "close": [99.8, 99.9, 99.95, 99.97],
                "ema50": [100.0, 100.0, 100.0, 100.0],
            }
        )

        regime = RegimeDetector(config=make_config(slope_threshold=0.0005)).compute_regime(
            df_5h,
            df_12h
        )

        self.assertEqual(regime, 2)

    def test_classification_uses_ranges_not_exact_match(self):
        detector = RegimeDetector(config=make_config())

        self.assertEqual(detector.classify(4), "strong")
        self.assertEqual(detector.classify(2), "moderate")
        self.assertEqual(detector.classify(1), "weak")

    def test_allows_entries_requires_moderate_or_better(self):
        detector = RegimeDetector(config=make_config())

        self.assertTrue(detector.allows_entries(2))
        self.assertFalse(detector.allows_entries(1))


if __name__ == "__main__":
    unittest.main()
