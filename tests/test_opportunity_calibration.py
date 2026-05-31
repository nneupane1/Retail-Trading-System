import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.opportunity_calibration import run_opportunity_calibration


class OpportunityCalibrationTests(unittest.TestCase):
    def test_run_opportunity_calibration_links_opportunities_to_trades(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            opportunities_path = temp_path / "opportunities.csv"
            trades_path = temp_path / "trades.csv"
            output_dir = temp_path / "calibration"

            pd.DataFrame(
                [
                    {
                        "opportunity_id": "opp_a",
                        "timestamp": "2026-01-01 00:00:00",
                        "side": "long",
                        "signal_family": "trend",
                        "bias": "bullish",
                        "regime_score": 3,
                        "regime_class": "strong",
                        "raw_score": 6,
                        "score_norm": 0.75,
                        "score_max": 9.0,
                        "momentum_strength": 0.60,
                        "signal_strength": 0.70,
                        "bias_weight": 1.15,
                        "regime_weight": 1.25,
                        "event_bonus": 1.12,
                        "final_strength": 0.98,
                        "entry_risk_multiplier": 0.98,
                        "entry_role": "core",
                        "eligible": True,
                        "rejection_reason": None,
                        "structural_floor_passed": True,
                        "breakout_event": True,
                        "price_to_fast_ema_ratio": 0.005,
                        "ema_gap_ratio": 0.004,
                        "vwap_distance_ratio": 0.003,
                        "atr_rising": True,
                        "macd_hist": 0.4,
                        "bias_directional_strength": 0.8,
                        "bias_price_vs_ema_ratio": 0.006,
                        "bias_ema_slope": 0.004,
                        "regime_max_score": 4,
                        "regime_normalized_strength": 0.75,
                        "regime_macro_aligned": True,
                        "regime_slope_aligned": True,
                        "regime_trend_aligned": True,
                        "bias_points": 2.0,
                        "trend_points": 1.0,
                        "vwap_points": 0.0,
                        "compression_points": 1.0,
                        "event_points": 2.0,
                        "body_strength_points": 1.0,
                        "close_position_points": 1.0,
                        "wick_points": 1.0,
                        "atr_points": 0.0,
                        "macd_points": 0.0,
                        "bollinger_points": 0.0,
                    },
                    {
                        "opportunity_id": "opp_b",
                        "timestamp": "2026-01-02 00:00:00",
                        "side": "short",
                        "signal_family": "trend",
                        "bias": "bearish",
                        "regime_score": 2,
                        "regime_class": "moderate",
                        "raw_score": 4,
                        "score_norm": 0.50,
                        "score_max": 9.0,
                        "momentum_strength": 0.40,
                        "signal_strength": 0.48,
                        "bias_weight": 1.15,
                        "regime_weight": 1.0,
                        "event_bonus": 1.0,
                        "final_strength": 0.55,
                        "entry_risk_multiplier": 0.55,
                        "entry_role": "core",
                        "eligible": True,
                        "rejection_reason": None,
                        "structural_floor_passed": True,
                        "breakout_event": False,
                        "price_to_fast_ema_ratio": -0.003,
                        "ema_gap_ratio": -0.002,
                        "vwap_distance_ratio": -0.001,
                        "atr_rising": False,
                        "macd_hist": -0.1,
                        "bias_directional_strength": 0.5,
                        "bias_price_vs_ema_ratio": -0.003,
                        "bias_ema_slope": -0.002,
                        "regime_max_score": 4,
                        "regime_normalized_strength": 0.50,
                        "regime_macro_aligned": True,
                        "regime_slope_aligned": False,
                        "regime_trend_aligned": True,
                        "bias_points": 2.0,
                        "trend_points": 1.0,
                        "vwap_points": 0.0,
                        "compression_points": 0.0,
                        "event_points": 0.0,
                        "body_strength_points": 1.0,
                        "close_position_points": 0.0,
                        "wick_points": 0.0,
                        "atr_points": 0.0,
                        "macd_points": 0.0,
                        "bollinger_points": 0.0,
                    },
                ]
            ).to_csv(opportunities_path, index=False)

            pd.DataFrame(
                [
                    {
                        "trade_id": "long_2026-01-01T00:00:00",
                        "opportunity_id": "opp_a",
                        "entry_time": "2026-01-01 00:00:00",
                        "exit_time": "2026-01-01 03:00:00",
                        "entry_price": 100.0,
                        "exit_price": 106.0,
                        "pnl": 6.0,
                        "pnl_R_total": 1.2,
                        "pnl_R_initial": 1.2,
                        "equity_return_fraction": 0.006,
                        "entry_risk_multiplier": 0.98,
                        "entry_threshold": 0.28,
                        "exit_reason": "trend weakness",
                        "side": "long",
                        "signal_family": "trend",
                        "score": 6,
                    }
                ]
            ).to_csv(trades_path, index=False)

            result = run_opportunity_calibration(
                opportunities_path=opportunities_path,
                trades_path=trades_path,
                output_dir=output_dir,
                bucket_count=2,
            )

            self.assertTrue(Path(result["joined_path"]).exists())
            self.assertTrue(Path(result["strength_summary_path"]).exists())
            self.assertTrue(Path(result["signal_family_summary_path"]).exists())
            self.assertTrue(Path(result["daily_summary_path"]).exists())
            self.assertTrue(Path(result["overview_path"]).exists())

            joined = pd.read_csv(result["joined_path"])
            overview = pd.read_csv(result["overview_path"])

            self.assertEqual(len(joined), 2)
            self.assertEqual(int(joined["executed"].sum()), 1)
            self.assertEqual(joined.loc[0, "trade_trade_id"], "long_2026-01-01T00:00:00")
            self.assertEqual(overview.loc[0, "match_method"], "opportunity_id")
            self.assertEqual(int(overview.loc[0, "executed_trade_count"]), 1)
            self.assertAlmostEqual(float(overview.loc[0, "avg_opportunities_per_day"]), 1.0)


if __name__ == "__main__":
    unittest.main()
