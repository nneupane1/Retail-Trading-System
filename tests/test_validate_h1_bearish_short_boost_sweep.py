import unittest

from backtest.validate_h1_bearish_short_boost_sweep import (
    SWEEP_VARIANTS,
    _rank_variant,
    _variant_strategy_overrides,
)


class ValidateH1BearishShortBoostSweepTests(unittest.TestCase):
    def test_variant_strategy_overrides_embed_requested_bearish_parameters(self):
        overrides = _variant_strategy_overrides(
            ["BTCUSDT", "ETHUSDT"],
            bearish_offset=-0.05,
            bearish_risk=1.15,
        )

        h1 = overrides["h1_execution"]
        self.assertEqual(h1["allowed_sides"], ["short"])
        self.assertEqual(h1["context_side_policy"]["bearish"]["short_selection_threshold_offset"], -0.05)
        self.assertEqual(h1["context_side_policy"]["bearish"]["short_risk_multiplier"], 1.15)
        self.assertFalse(h1["elite_long_exception"]["enabled"])

    def test_rank_variant_captures_delta_fields(self):
        row = _rank_variant(
            {
                "name": "scenario_demo",
                "metrics": {
                    "final_equity": 20100.0,
                    "profit_factor": 1.15,
                    "median_daily_pnl": -0.2,
                    "max_drawdown": -0.03,
                    "trade_count": 700,
                },
            },
            {
                "delta_final_equity": 50.0,
                "delta_profit_factor": 0.03,
                "delta_median_daily_pnl": 0.2,
                "delta_max_drawdown": 0.01,
                "delta_trade_count": -100,
            },
            {"is_h1_additive_to_portfolio": True},
        )

        self.assertEqual(row["scenario_name"], "scenario_demo")
        self.assertEqual(row["delta_profit_factor_vs_short_only"], 0.03)
        self.assertEqual(row["delta_trade_count_vs_short_only"], -100)
        self.assertTrue(row["is_additive_to_baseline"])

    def test_sweep_variants_defined(self):
        self.assertGreaterEqual(len(SWEEP_VARIANTS), 3)


if __name__ == "__main__":
    unittest.main()
