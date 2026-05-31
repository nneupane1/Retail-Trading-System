import os
import csv
import tempfile
import unittest
from types import SimpleNamespace

from backtest.equity_logger import EquityLogger
from backtest.logger import TradeLogger
from backtest.opportunity_logger import OpportunityLogger


class DummyConfig:
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def require(self, *keys):
        if keys == ("backtest", "output_dir"):
            return self.output_dir
        raise KeyError(f"Unexpected config lookup: {keys}")


class BacktestLoggerTests(unittest.TestCase):
    def test_trade_logger_creates_default_directory_and_extended_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = TradeLogger(config=DummyConfig(output_dir=output_dir))

            self.assertTrue(os.path.isdir(output_dir))
            self.assertTrue(os.path.exists(logger.filepath))

            with open(logger.filepath, "r", newline="") as file_handle:
                header = file_handle.readline().strip()

            self.assertEqual(
                header,
                "trade_id,opportunity_id,side,signal_family,entry_time,exit_time,entry_price,exit_price,stop_price,active_stop_price,pnl,pnl_R,"
                "pnl_R_total,pnl_R_initial,initial_risk_amount,total_risk_amount,"
                "equity_at_entry,entry_risk_multiplier,intended_risk_per_trade,effective_risk_fraction,equity_return_fraction,bias,"
                "regime_score,regime_class,entry_threshold,exit_reason,pressure_score,score_norm,momentum_strength,final_strength,bias_weight,"
                "regime_weight,event_bonus,trail_state,trail_anchor_column,trail_anchor_price,"
                "trail_open_r_multiple,trail_momentum_score,trail_decay_score,entry_layer_count,"
                "pyramid_level,score,body_strength,close_position,upper_wick_ratio,"
                "lower_wick_ratio,compression,breakout,breakdown,session_vwap,"
                "vwap_distance_ratio,ema_gap_ratio,atr,macd_hist",
            )

    def test_trade_logger_appends_completed_trade_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = TradeLogger(config=DummyConfig(output_dir=output_dir))
            trade = SimpleNamespace(
                trade_id="long_2026-01-01T00:00:00",
                opportunity_id="opp_2026-01-01T00-00-00_long_trend_000001",
                side="long",
                signal_family="exploratory",
                entry_time="2026-01-01 00:00:00",
                exit_time="2026-01-01 01:00:00",
                entry_price=100.0,
                exit_price=110.0,
                stop=95.0,
                active_stop=104.0,
                pnl=12.5,
                pnl_R=1.25,
                pnl_R_total=1.25,
                pnl_R_initial=2.5,
                initial_risk_amount=5.0,
                total_risk_amount=10.0,
                equity_at_entry=1000.0,
                entry_risk_multiplier=0.5,
                intended_risk_per_trade=0.01,
                effective_risk_fraction=0.005,
                equity_return_fraction=0.0125,
                bias="bullish",
                regime_score=3,
                regime_class="strong",
                entry_threshold=4,
                exit_reason="trend weakness",
                pressure_score=5,
                score_norm=0.75,
                momentum_strength=0.60,
                final_strength=0.92,
                bias_weight=1.15,
                regime_weight=1.25,
                event_bonus=1.12,
                trail_state="decay",
                trail_anchor_column="ema20",
                trail_anchor_price=108.0,
                trail_open_r_multiple=2.0,
                trail_momentum_score=4,
                trail_decay_score=2,
                entry_layer_count=2,
                pyramid_level=1,
                conditions={
                    "score": 6,
                    "body_strength": 1.2,
                    "close_position": 0.9,
                    "upper_wick_ratio": 0.4,
                    "lower_wick_ratio": 0.1,
                    "compression": True,
                    "breakout": True,
                    "breakdown": False,
                    "session_vwap": 99.5,
                    "vwap_distance_ratio": 0.01,
                    "ema_gap_ratio": 0.02,
                    "atr": 12.0,
                    "macd_hist": 0.8,
                }
            )

            logger.log_trade(trade)

            with open(logger.filepath, "r", newline="") as file_handle:
                rows = list(csv.DictReader(file_handle))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["trade_id"], "long_2026-01-01T00:00:00")
            self.assertEqual(rows[0]["opportunity_id"], "opp_2026-01-01T00-00-00_long_trend_000001")
            self.assertEqual(rows[0]["side"], "long")
            self.assertEqual(rows[0]["signal_family"], "exploratory")
            self.assertEqual(rows[0]["entry_time"], "2026-01-01 00:00:00")
            self.assertEqual(rows[0]["exit_time"], "2026-01-01 01:00:00")
            self.assertEqual(float(rows[0]["pnl"]), 12.5)
            self.assertEqual(float(rows[0]["active_stop_price"]), 104.0)
            self.assertEqual(float(rows[0]["pnl_R_total"]), 1.25)
            self.assertEqual(float(rows[0]["pnl_R_initial"]), 2.5)
            self.assertEqual(float(rows[0]["initial_risk_amount"]), 5.0)
            self.assertEqual(float(rows[0]["total_risk_amount"]), 10.0)
            self.assertEqual(float(rows[0]["equity_at_entry"]), 1000.0)
            self.assertEqual(float(rows[0]["entry_risk_multiplier"]), 0.5)
            self.assertEqual(float(rows[0]["intended_risk_per_trade"]), 0.01)
            self.assertEqual(float(rows[0]["effective_risk_fraction"]), 0.005)
            self.assertEqual(float(rows[0]["equity_return_fraction"]), 0.0125)
            self.assertEqual(rows[0]["bias"], "bullish")
            self.assertEqual(rows[0]["regime_score"], "3")
            self.assertEqual(rows[0]["regime_class"], "strong")
            self.assertEqual(rows[0]["entry_threshold"], "4")
            self.assertEqual(rows[0]["exit_reason"], "trend weakness")
            self.assertEqual(rows[0]["pressure_score"], "5")
            self.assertEqual(float(rows[0]["score_norm"]), 0.75)
            self.assertEqual(float(rows[0]["momentum_strength"]), 0.6)
            self.assertEqual(float(rows[0]["final_strength"]), 0.92)
            self.assertEqual(float(rows[0]["bias_weight"]), 1.15)
            self.assertEqual(float(rows[0]["regime_weight"]), 1.25)
            self.assertEqual(float(rows[0]["event_bonus"]), 1.12)
            self.assertEqual(rows[0]["trail_state"], "decay")
            self.assertEqual(rows[0]["trail_anchor_column"], "ema20")
            self.assertEqual(float(rows[0]["trail_anchor_price"]), 108.0)
            self.assertEqual(float(rows[0]["trail_open_r_multiple"]), 2.0)
            self.assertEqual(rows[0]["trail_momentum_score"], "4")
            self.assertEqual(rows[0]["trail_decay_score"], "2")
            self.assertEqual(rows[0]["entry_layer_count"], "2")
            self.assertEqual(rows[0]["pyramid_level"], "1")
            self.assertEqual(rows[0]["compression"], "True")
            self.assertEqual(rows[0]["breakout"], "True")

    def test_equity_logger_creates_default_directory_and_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = EquityLogger(config=DummyConfig(output_dir=output_dir))

            self.assertTrue(os.path.isdir(output_dir))
            self.assertTrue(os.path.exists(logger.filepath))

            with open(logger.filepath, "r", newline="") as file_handle:
                header = file_handle.readline().strip()

            self.assertEqual(header, "timestamp,equity")

    def test_equity_logger_appends_equity_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = EquityLogger(config=DummyConfig(output_dir=output_dir))

            logger.log("2026-01-01 00:00:00", 1000.0)
            logger.log("2026-01-01 00:15:00", 1012.5)

            with open(logger.filepath, "r", newline="") as file_handle:
                rows = list(csv.DictReader(file_handle))

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["timestamp"], "2026-01-01 00:00:00")
            self.assertEqual(float(rows[0]["equity"]), 1000.0)
            self.assertEqual(rows[1]["timestamp"], "2026-01-01 00:15:00")
            self.assertEqual(float(rows[1]["equity"]), 1012.5)

    def test_opportunity_logger_writes_weighted_opportunity_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = OpportunityLogger(config=DummyConfig(output_dir=output_dir))

            logger.log_opportunity(
                {
                    "opportunity_id": "opp_2026-01-01T00-00-00_long_trend_000001",
                    "timestamp": "2026-01-01 00:00:00",
                    "side": "long",
                    "signal_family": "trend",
                    "bias": "bullish",
                    "regime_score": 3,
                    "regime_class": "strong",
                    "raw_score": 6,
                    "score_norm": 0.75,
                    "score_max": 9.0,
                    "momentum_strength": 0.62,
                    "signal_strength": 0.71,
                    "bias_weight": 1.15,
                    "regime_weight": 1.25,
                    "event_bonus": 1.12,
                    "final_strength": 1.02,
                    "entry_risk_multiplier": 1.02,
                    "entry_role": "core",
                    "eligible": True,
                    "rejection_reason": None,
                    "structural_floor_passed": True,
                    "breakout_event": True,
                    "price_to_fast_ema_ratio": 0.005,
                    "ema_gap_ratio": 0.004,
                    "vwap_distance_ratio": 0.003,
                    "atr_rising": True,
                    "macd_hist": 0.5,
                    "bias_snapshot": {
                        "directional_strength": 0.8,
                        "price_vs_ema_ratio": 0.006,
                        "ema_slope": 0.004,
                    },
                    "regime_snapshot": {
                        "max_score": 4,
                        "normalized_strength": 0.75,
                        "macro_aligned": True,
                        "slope_aligned": True,
                        "trend_aligned": False,
                    },
                    "score_components": {
                        "bias": {"points": 2.0},
                        "trend": {"points": 1.0},
                        "vwap": {"points": 0.0},
                        "compression": {"points": 1.0},
                        "event": {"points": 2.0},
                        "body_strength": {"points": 1.0},
                        "close_position": {"points": 1.0},
                        "wick": {"points": 1.0},
                        "atr": {"points": 0.0},
                        "macd": {"points": 0.0},
                        "bollinger": {"points": 0.0},
                    },
                }
            )

            with open(logger.filepath, "r", newline="", encoding="utf-8") as file_handle:
                rows = list(csv.DictReader(file_handle))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["opportunity_id"], "opp_2026-01-01T00-00-00_long_trend_000001")
            self.assertEqual(rows[0]["side"], "long")
            self.assertEqual(rows[0]["eligible"], "True")
            self.assertEqual(float(rows[0]["final_strength"]), 1.02)
            self.assertEqual(float(rows[0]["score_max"]), 9.0)
            self.assertEqual(float(rows[0]["bias_directional_strength"]), 0.8)
            self.assertEqual(float(rows[0]["regime_normalized_strength"]), 0.75)
            self.assertEqual(rows[0]["regime_trend_aligned"], "False")
            self.assertEqual(float(rows[0]["event_points"]), 2.0)


if __name__ == "__main__":
    unittest.main()
