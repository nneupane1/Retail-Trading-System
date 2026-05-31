import tempfile
import unittest
from pathlib import Path

import pandas as pd

from entry.opportunity_ranking import OpportunityScorer
from live_sim.paper_portfolio import LivePaperPortfolio


class DummyConfig:
    def __init__(self, output_dir):
        self.data = {
            "account": {
                "initial_equity": 1000.0,
            },
            "position": {
                "min_stop_distance_ratio": 0.0001,
                "min_stop_distance_absolute": 0.0,
                "max_position_size_units": None,
                "max_notional_equity_multiple": None,
            },
            "features": {
                "ema_periods": {"fast": 2, "slow": 3},
                "structure": {"high_period": 2, "low_period": 2},
                "compression": {"slow_range_period": 3},
                "candle_metrics": {"average_body_period": 2},
                "indicators": {
                    "atr_period": 2,
                    "macd_fast_period": 2,
                    "macd_slow_period": 3,
                    "macd_signal_period": 2,
                    "bollinger_period": 2,
                    "bollinger_std_dev": 2.0,
                },
            },
            "strategy": {
                "sniffing": {
                    "body_strength_min": 0.8,
                    "close_position_min": 0.4,
                    "close_position_max": 0.6,
                    "upper_wick_max": 1.5,
                    "lower_wick_max": 1.5,
                    "min_confirmations": 1,
                    "relax_after_r": 1.0,
                    "relaxed_min_confirmations": 0,
                    "require_short_vwap_alignment": True,
                    "support_alpha": {},
                    "by_side": {},
                    "trailing": {
                        "strong_body_min": 1.0,
                        "clean_wick_max": 1.0,
                        "min_vwap_distance": 0.0,
                        "min_ema_gap": 0.0,
                        "vwap_decay_threshold": 0.0015,
                        "ema_gap_decay_threshold": 0.0010,
                        "macd_decay_threshold": 0.0,
                        "body_decay_max": 0.8,
                        "wick_decay_min": 1.5,
                        "decay_close_position_max": 0.45,
                        "strong_close_position_min": 0.65,
                        "init_max_r": 0.5,
                        "confirmation_max_r": 1.5,
                        "expansion_min_momentum_signals": 4,
                        "decay_signal_threshold": 2,
                        "force_exit_decay_signal_threshold": 4,
                        "init_atr_buffer": 1.2,
                        "confirmation_atr_buffer": 0.9,
                        "expansion_atr_buffer": 1.8,
                        "decay_atr_buffer": 0.35,
                        "exit_atr_buffer": 0.15,
                        "expansion_anchor": "slow_ema",
                        "decay_anchor": "fast_ema",
                        "confirmation_anchor": "fast_ema",
                        "by_side": {},
                    },
                }
            },
            "live_sim": {
                "output_dir": output_dir,
                "opportunity_scoring": {
                    "weights": {
                        "body_strength": 0.35,
                        "close_position": 0.25,
                        "vwap_score": 0.25,
                        "momentum": 0.15,
                    }
                },
                "paper_portfolio": {
                    "allowed_sides": ["long"],
                    "allowed_edge_types": ["impulse_breakout"],
                    "min_trades_per_day": 10,
                    "target_trades_per_day": 10,
                    "max_trades_per_day": 15,
                    "base_threshold": 0.65,
                    "min_threshold": 0.50,
                    "max_threshold": 0.90,
                    "pacing_relax_step": 0.05,
                    "pacing_tighten_step": 0.03,
                    "threshold_smoothing": 0.20,
                    "min_profitable_bucket_count": 2,
                    "min_risk_per_trade": 0.0025,
                    "max_risk_per_trade": 0.0060,
                    "max_total_risk_fraction": 0.04,
                    "max_trades_per_asset": 2,
                    "max_same_direction_positions": 6,
                    "trailing_activation_r": 1.2,
                    "breakeven_trigger_r": 1.0,
                    "slow_grind_max_bars": 8,
                    "slow_grind_open_r_max": 1.0,
                    "weight_update_min_trades": 2,
                },
            },
        }

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def require(self, *keys):
        value = self.data
        for key in keys:
            value = value[key]
        return value


class OpportunityScorerTests(unittest.TestCase):
    def test_compute_score_returns_bucket_and_bounded_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scorer = OpportunityScorer(config=DummyConfig(output_dir=temp_dir))
            row = pd.Series(
                {
                    "body_strength": 2.4,
                    "close_position": 0.85,
                }
            )

            result = scorer.compute_score(
                row=row,
                momentum_rank=0.9,
                vwap_bucket="far",
                edge_type="impulse_breakout",
                is_top_mover=True,
            )

            self.assertGreaterEqual(result["score"], 0.0)
            self.assertLessEqual(result["score"], 1.0)
            self.assertEqual(result["score_bucket"], "0.9-1.0")


class LivePaperPortfolioTests(unittest.TestCase):
    def test_portfolio_opens_high_score_candidate_and_tracks_symbol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series(
                {
                    "close": 105.0,
                    "low": 104.0,
                    "high": 106.0,
                    "ll2": 100.0,
                    "ema2": 104.0,
                    "ema3": 103.0,
                    "atr": 1.5,
                },
                name=timestamp,
            )

            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.select_and_open(
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": timestamp,
                        "side": "long",
                        "row": row,
                        "bias": "neutral",
                        "edge_type": "impulse_breakout",
                        "body_bucket": "strong",
                        "vwap_bucket": "far",
                        "bucket_key_text": "impulse_breakout|neutral|strong|far",
                        "bucket_valid": True,
                        "bucket_expected_return": 0.000212,
                        "bucket_risk_mult": 1.1,
                        "risk_mult": 1.1,
                        "momentum_rank": 0.95,
                        "is_top_mover": True,
                        "score": 0.92,
                        "score_bucket": "0.9-1.0",
                        "feature_values": {
                            "body_strength": 0.9,
                            "close_position": 0.9,
                            "vwap_score": 1.0,
                            "momentum": 0.95,
                        },
                    }
                ],
                timestamp,
            )

            self.assertEqual(len(portfolio.open_positions), 1)
            trade = portfolio.open_positions[0]
            self.assertEqual(trade.symbol, "BTCUSDT")
            self.assertEqual(trade.score_bucket, "0.9-1.0")
            self.assertGreater(trade.intended_risk_per_trade, 0.0)

    def test_adaptive_threshold_relaxes_when_day_is_behind_schedule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            timestamp = pd.Timestamp("2026-01-01 18:00:00")
            portfolio.reset_daily_state_if_needed(timestamp)

            threshold = portfolio.adaptive_threshold(timestamp)

            self.assertLess(threshold, portfolio.current_threshold)
            self.assertGreaterEqual(threshold, portfolio.min_threshold)


if __name__ == "__main__":
    unittest.main()
