import unittest

from position.sizing import PositionSizer, calculate_position_size


class DummyConfig:
    def __init__(self, data):
        self.data = data

    def get(self, *keys, default=None):
        value = self.data

        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]

        return value


def make_config(
    min_stop_distance_ratio=0.0,
    min_stop_distance_absolute=0.0,
    max_position_size_units=None,
    max_notional_equity_multiple=None
):
    return DummyConfig({
        "position": {
            "min_stop_distance_ratio": min_stop_distance_ratio,
            "min_stop_distance_absolute": min_stop_distance_absolute,
            "max_position_size_units": max_position_size_units,
            "max_notional_equity_multiple": max_notional_equity_multiple,
        }
    })


class PositionSizerTests(unittest.TestCase):
    def test_standard_risk_based_position_size_is_preserved(self):
        sizer = PositionSizer(config=make_config())

        size = sizer.calculate(
            equity=1000.0,
            risk_per_trade=0.01,
            entry_price=100.0,
            stop_price=99.0,
        )

        self.assertEqual(size, 10.0)

    def test_position_is_blocked_when_stop_distance_is_below_ratio_floor(self):
        sizer = PositionSizer(
            config=make_config(min_stop_distance_ratio=0.01)
        )

        size = sizer.calculate(
            equity=1000.0,
            risk_per_trade=0.01,
            entry_price=100.0,
            stop_price=99.5,
        )

        self.assertEqual(size, 0)

    def test_position_size_is_capped_by_unit_limit(self):
        sizer = PositionSizer(
            config=make_config(max_position_size_units=5.0)
        )

        size = sizer.calculate(
            equity=1000.0,
            risk_per_trade=0.01,
            entry_price=100.0,
            stop_price=99.0,
        )

        self.assertEqual(size, 5.0)

    def test_position_size_is_capped_by_notional_multiple(self):
        sizer = PositionSizer(
            config=make_config(max_notional_equity_multiple=2.0)
        )

        size = sizer.calculate(
            equity=1000.0,
            risk_per_trade=0.01,
            entry_price=100.0,
            stop_price=99.9,
        )

        self.assertAlmostEqual(size, 20.0)

    def test_helper_accepts_config_for_safe_direct_calls(self):
        size = calculate_position_size(
            equity=1000.0,
            risk_per_trade=0.01,
            entry_price=100.0,
            stop_price=99.5,
            config=make_config(min_stop_distance_ratio=0.01),
        )

        self.assertEqual(size, 0)


if __name__ == "__main__":
    unittest.main()
