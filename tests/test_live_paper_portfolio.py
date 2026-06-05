import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from live_sim.logger import LivePortfolioStateLogger
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
                "htf_12h_standard": {
                    "enabled": True,
                    "base_risk_fraction": 0.0020,
                    "max_total_risk_fraction": 0.006,
                    "max_open_positions": 2,
                    "min_score": 5.5,
                    "min_expansion": 1.0,
                    "selection_bonus": 0.02,
                    "signal_event_bonus": 0.03,
                    "top_mover_bonus": 0.02,
                    "long_risk_multiplier": 1.0,
                    "short_risk_multiplier": 0.7,
                    "selection_threshold_offset": -0.18,
                    "selection_min_threshold": 0.58,
                    "selection_max_threshold": 0.84,
                    "vwap_near_threshold": 0.01,
                    "vwap_moderate_threshold": 0.02,
                    "allow_pyramiding": False,
                    "require_weekly_confirmation": False,
                    "max_hold_12h_candles": 36,
                },
                "htf_12h_moonshot": {
                    "enabled": True,
                    "base_risk_fraction": 0.0035,
                    "max_total_risk_fraction": 0.012,
                    "max_open_positions": 2,
                    "min_score": 7,
                    "breakout_lookback": 3,
                    "daily_breakout_lookback": 3,
                    "weekly_breakout_lookback": 2,
                    "compression_lookback": 3,
                    "trailing_lookback": 2,
                    "atr_stop_buffer": 0.5,
                    "max_vwap_distance": 0.03,
                    "max_ema_distance": 0.08,
                    "daily_momentum_lookback": 1,
                    "weekly_momentum_lookback": 1,
                    "max_hold_12h_candles": 120,
                    "allow_pyramiding": False,
                },
                "htf_12h_rotation": {
                    "enabled": True,
                },
                "h6_standard": {
                    "enabled": True,
                    "base_risk_fraction": 0.0018,
                    "max_total_risk_fraction": 0.0055,
                    "max_open_positions": 2,
                    "min_score": 0.68,
                    "max_hold_6h_candles": 18,
                    "selection_bonus": 0.02,
                    "top_mover_bonus": 0.02,
                    "selection_threshold_offset": -0.10,
                    "selection_min_threshold": 0.62,
                    "selection_max_threshold": 0.88,
                },
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
                    "recency_lookback_days": 60,
                    "recency_max_trades": 300,
                    "recency_min_bucket_trades": 2,
                    "recency_min_strategy_trades": 2,
                    "health_reference_avg_r": 0.02,
                    "bucket_negative_risk_multiplier": 0.25,
                    "bucket_positive_floor_multiplier": 0.60,
                    "bucket_positive_cap": 1.20,
                    "strategy_negative_risk_multiplier": 0.30,
                    "strategy_positive_floor_multiplier": 0.75,
                    "strategy_positive_cap": 1.20,
                    "strategy_health_profiles": {
                        "htf_12h_standard": {
                            "recency_lookback_days": 180,
                            "recency_max_trades": 80,
                            "recency_min_trades": 12,
                            "neutral_below_min_trades": True,
                            "disable_when_negative": False,
                            "negative_risk_multiplier": 0.75,
                            "positive_floor_multiplier": 0.90,
                            "positive_cap": 1.10,
                            "emergency_disable_min_trades": 28,
                            "emergency_disable_avg_r": -0.30,
                        },
                        "htf_12h_moonshot": {
                            "recency_lookback_days": 180,
                            "recency_max_trades": 50,
                            "recency_min_trades": 8,
                            "neutral_below_min_trades": True,
                            "disable_when_negative": False,
                            "negative_risk_multiplier": 0.75,
                            "positive_floor_multiplier": 0.90,
                            "positive_cap": 1.10,
                            "emergency_disable_min_trades": 20,
                            "emergency_disable_avg_r": -0.30,
                        },
                        "h6_standard": {
                            "recency_lookback_days": 180,
                            "recency_max_trades": 40,
                            "recency_min_trades": 8,
                            "neutral_below_min_trades": True,
                            "disable_when_negative": False,
                            "negative_risk_multiplier": 0.80,
                            "positive_floor_multiplier": 0.90,
                            "positive_cap": 1.10,
                            "emergency_disable_min_trades": 16,
                            "emergency_disable_avg_r": -0.25,
                        }
                    },
                    "strategy_threshold_offsets": {
                        "htf_12h_standard": -0.18,
                        "htf_12h_moonshot": -0.05,
                        "htf_12h_rotation": -0.04,
                        "h6_standard": -0.10,
                    },
                    "strategy_allowed_sides": {
                        "htf_12h_standard": ["long"],
                        "htf_12h_moonshot": ["long"],
                        "htf_12h_rotation": ["long"],
                        "h6_standard": ["long"],
                    },
                    "strategy_sleeves": {
                        "htf_12h_standard": {
                            "enabled": True,
                            "reserved_risk_fraction": 0.004,
                            "max_new_positions_per_step": 1,
                            "block_if_symbol_has_other_strategy_position": False,
                            "ignore_global_step_cap": False,
                        },
                        "htf_12h_moonshot": {
                            "enabled": True,
                            "reserved_risk_fraction": 0.012,
                            "max_new_positions_per_step": 2,
                            "block_if_symbol_has_other_strategy_position": False,
                            "ignore_global_step_cap": True,
                        },
                        "htf_12h_rotation": {
                            "enabled": True,
                            "reserved_risk_fraction": 0.006,
                            "max_new_positions_per_step": 1,
                            "block_if_symbol_has_other_strategy_position": True,
                            "ignore_global_step_cap": True,
                        },
                        "swing_moonshot": {
                            "enabled": True,
                            "reserved_risk_fraction": 0.003,
                            "max_new_positions_per_step": 1,
                            "block_if_symbol_has_other_strategy_position": False,
                            "ignore_global_step_cap": False,
                        },
                        "h6_standard": {
                            "enabled": True,
                            "reserved_risk_fraction": 0.0025,
                            "max_new_positions_per_step": 1,
                            "block_if_symbol_has_other_strategy_position": False,
                            "ignore_global_step_cap": False,
                        },
                    },
                    "allocator_v2": {
                        "enabled": True,
                        "leader_dominance": {
                            "enabled": True,
                            "min_gap": 0.10,
                            "boost": 0.12,
                        },
                        "agreement_bonus": {
                            "enabled": True,
                            "pairs": [
                                {
                                    "primary": "htf_12h_moonshot",
                                    "secondary": "htf_12h_rotation",
                                    "primary_bonus": 0.06,
                                    "secondary_bonus": 0.0,
                                }
                            ],
                        },
                        "concentration_brake": {
                            "enabled": True,
                            "min_closed_trades": 2,
                            "daily_loss_fraction_trigger": 0.0045,
                            "loss_streak_trigger": 3,
                            "budget_multiplier": 0.80,
                            "core_budget_multiplier": 0.55,
                            "priority_multiplier": 0.92,
                            "core_priority_multiplier": 0.78,
                            "leader_boost_multiplier": 0.45,
                            "uniform_weight_blend": 0.45,
                        },
                        "sleeves": {
                            "core": {
                                "priority_multiplier": 0.78,
                                "rank_weights": [1.0, 0.45, 0.20],
                                "max_candidates": 3,
                                "max_risk_fraction_multiplier": 0.85,
                                "absolute_max_risk_fraction": 0.0025,
                            },
                            "swing_moonshot": {
                                "priority_multiplier": 0.98,
                                "rank_weights": [1.0, 0.35],
                                "max_candidates": 2,
                                "max_risk_fraction_multiplier": 1.20,
                                "absolute_max_risk_fraction": 0.0030,
                            },
                            "htf_12h_standard": {
                                "priority_multiplier": 1.02,
                                "rank_weights": [1.0, 0.40],
                                "max_candidates": 2,
                                "max_risk_fraction_multiplier": 1.35,
                                "absolute_max_risk_fraction": 0.0045,
                            },
                            "htf_12h_moonshot": {
                                "priority_multiplier": 1.24,
                                "rank_weights": [1.0, 0.50, 0.18],
                                "max_candidates": 3,
                                "max_risk_fraction_multiplier": 2.00,
                                "absolute_max_risk_fraction": 0.0085,
                            },
                            "htf_12h_rotation": {
                                "priority_multiplier": 1.08,
                                "rank_weights": [1.0, 0.35],
                                "max_candidates": 2,
                                "max_risk_fraction_multiplier": 1.40,
                                "absolute_max_risk_fraction": 0.0040,
                            },
                            "h6_standard": {
                                "priority_multiplier": 0.92,
                                "rank_weights": [1.0, 0.45],
                                "max_candidates": 2,
                                "max_risk_fraction_multiplier": 1.10,
                                "absolute_max_risk_fraction": 0.0025,
                            },
                        },
                    },
                    "disable_non_core_negative_strategies": True,
                    "strategy_emergency_disable_min_trades": 3,
                    "strategy_emergency_disable_avg_r": -0.20,
                    "performance_history_limit": 5000,
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
                    "convexity": {
                        "enabled": True,
                        "strategy_types": ["core"],
                        "probe_fraction": 0.35,
                        "min_score": 0.82,
                        "promote_trigger_r": 0.6,
                        "promote_target_multiple": 1.0,
                        "add_trigger_r": 1.4,
                        "add_target_multiple": 1.25,
                        "max_target_multiple": 1.25,
                        "max_layers": 3,
                        "min_body_strength": 1.0,
                        "min_close_position": 0.60,
                        "min_expansion": 1.0,
                        "add_min_body_strength": 1.4,
                        "add_min_close_position": 0.72,
                        "add_min_expansion": 1.15,
                        "max_abs_vwap_distance": 0.012,
                        "min_bars_between_adds": 1,
                        "use_active_stop_for_adds": True,
                        "add_min_stop_distance_r_multiple": 0.50,
                        "hold_extension_bars": 4,
                    },
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

    def test_core_convexity_opens_as_probe_but_preserves_full_risk_target(self):
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
                    "ema2": 104.5,
                    "ema3": 104.0,
                    "session_vwap": 104.3,
                    "body_strength": 1.8,
                    "close_position": 0.82,
                    "range_expansion_factor": 1.3,
                    "vwap_distance_ratio": 0.004,
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

            trade = portfolio.open_positions[0]
            self.assertTrue(trade.convexity_enabled)
            self.assertEqual(trade.convexity_state, "probe")
            self.assertAlmostEqual(trade.convexity_probe_fraction, 0.35, places=7)
            self.assertGreater(trade.intended_risk_per_trade, trade.effective_risk_fraction)
            self.assertAlmostEqual(
                trade.initial_risk_amount,
                trade.equity_at_entry * trade.intended_risk_per_trade,
                places=7,
            )

    def test_convexity_promotes_after_trade_proves_itself(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            portfolio = LivePaperPortfolio(config=config)
            entry_time = pd.Timestamp("2026-01-01 12:00:00")
            entry_row = pd.Series(
                {
                    "close": 105.0,
                    "low": 104.0,
                    "high": 106.0,
                    "ll2": 100.0,
                    "ema2": 104.5,
                    "ema3": 104.0,
                    "session_vwap": 104.3,
                    "body_strength": 1.8,
                    "close_position": 0.82,
                    "range_expansion_factor": 1.3,
                    "vwap_distance_ratio": 0.004,
                    "atr": 1.5,
                },
                name=entry_time,
            )

            portfolio.reset_daily_state_if_needed(entry_time)
            portfolio.select_and_open(
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": entry_time,
                        "side": "long",
                        "row": entry_row,
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
                entry_time,
            )

            trade = portfolio.open_positions[0]
            probe_entries = len(trade.entries)
            probe_risk = trade.effective_risk_fraction
            manage_time = pd.Timestamp("2026-01-01 12:15:00")
            manage_row = pd.Series(
                {
                    "close": 108.5,
                    "low": 108.0,
                    "high": 109.0,
                    "ll2": 100.0,
                    "ema2": 107.5,
                    "ema3": 106.5,
                    "session_vwap": 107.2,
                    "body_strength": 2.0,
                    "close_position": 0.86,
                    "range_expansion_factor": 1.35,
                    "vwap_distance_ratio": 0.006,
                    "atr": 1.6,
                },
                name=manage_time,
            )

            portfolio.manage_open_positions({"BTCUSDT": manage_row})

            self.assertEqual(len(portfolio.open_positions), 1)
            trade = portfolio.open_positions[0]
            self.assertEqual(len(trade.entries), probe_entries + 1)
            self.assertEqual(trade.convexity_stage, 1)
            self.assertEqual(trade.convexity_state, "promoted")
            self.assertGreater(trade.effective_risk_fraction, probe_risk)

    def test_adaptive_threshold_relaxes_when_day_is_behind_schedule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            timestamp = pd.Timestamp("2026-01-01 18:00:00")
            portfolio.reset_daily_state_if_needed(timestamp)

            threshold = portfolio.adaptive_threshold(timestamp)

            self.assertLess(threshold, portfolio.current_threshold)
            self.assertGreaterEqual(threshold, portfolio.min_threshold)

    def test_recent_profitable_support_bucket_lowers_threshold_floor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            reference_time = datetime(2026, 1, 10, 12, 0, 0)
            portfolio.performance_history = [
                {
                    "exit_time": reference_time - timedelta(days=1),
                    "strategy_type": "core",
                    "score_bucket": "0.8-0.9",
                    "pnl_R_initial": 0.04,
                    "pnl": 10.0,
                },
                {
                    "exit_time": reference_time,
                    "strategy_type": "core",
                    "score_bucket": "0.8-0.9",
                    "pnl_R_initial": 0.02,
                    "pnl": 8.0,
                },
                {
                    "exit_time": reference_time,
                    "strategy_type": "core",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.01,
                    "pnl": -5.0,
                },
                {
                    "exit_time": reference_time - timedelta(days=2),
                    "strategy_type": "core",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.02,
                    "pnl": -4.0,
                },
            ]
            portfolio._refresh_recent_performance()

            threshold, source = portfolio._derive_threshold_from_history()

            self.assertAlmostEqual(threshold, 0.8, places=7)
            self.assertEqual(source, "recent")

    def test_negative_recent_core_bucket_can_be_disabled_by_strategy_bucket_health(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            config.data["live_sim"]["paper_portfolio"]["strategy_bucket_health_profiles"] = {
                "core": {
                    "enabled": True,
                    "recency_lookback_days": 60,
                    "recency_max_trades": 300,
                    "recency_min_trades": 2,
                    "neutral_below_min_trades": True,
                    "disable_when_negative": True,
                    "negative_risk_multiplier": 0.0,
                    "positive_floor_multiplier": 0.95,
                    "positive_cap": 1.10,
                    "apply_to_threshold_derivation": True,
                }
            }
            portfolio = LivePaperPortfolio(config=config)
            reference_time = datetime(2026, 1, 10, 12, 0, 0)
            portfolio.performance_history = [
                {
                    "exit_time": reference_time - timedelta(days=1),
                    "strategy_type": "core",
                    "score_bucket": "0.8-0.9",
                    "pnl_R_initial": 0.05,
                    "pnl": 10.0,
                },
                {
                    "exit_time": reference_time,
                    "strategy_type": "core",
                    "score_bucket": "0.8-0.9",
                    "pnl_R_initial": 0.03,
                    "pnl": 8.0,
                },
                {
                    "exit_time": reference_time - timedelta(days=2),
                    "strategy_type": "core",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.02,
                    "pnl": -5.0,
                },
                {
                    "exit_time": reference_time,
                    "strategy_type": "core",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.04,
                    "pnl": -6.0,
                },
            ]
            portfolio._refresh_recent_performance()

            positive_multiplier, _ = portfolio._strategy_bucket_health_multiplier(
                "core", "0.8-0.9"
            )
            negative_multiplier, negative_source = portfolio._strategy_bucket_health_multiplier(
                "core", "0.9-1.0"
            )
            threshold, source = portfolio._derive_threshold_from_history()

            self.assertGreater(positive_multiplier, 0.0)
            self.assertEqual(negative_multiplier, 0.0)
            self.assertEqual(negative_source, "recent_window")
            self.assertAlmostEqual(threshold, 0.8, places=7)
            self.assertEqual(source, "recent")

    def test_low_score_bucket_candidate_is_filtered_before_open(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
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
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.75,
                        "is_top_mover": False,
                        "score": 0.72,
                        "score_bucket": "0.7-0.8",
                        "feature_values": {
                            "body_strength": 0.7,
                            "close_position": 0.7,
                            "vwap_score": 1.0,
                            "momentum": 0.75,
                        },
                    }
                ],
                timestamp,
            )

            self.assertEqual(len(portfolio.open_positions), 0)

    def test_max_new_positions_per_step_limits_same_candle_opens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            config.data["live_sim"]["paper_portfolio"]["max_new_positions_per_step"] = 1
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")

            def build_candidate(symbol, score):
                return {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "side": "long",
                    "row": pd.Series(
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
                    ),
                    "bias": "neutral",
                    "edge_type": "impulse_breakout",
                    "body_bucket": "strong",
                    "vwap_bucket": "far",
                    "bucket_key_text": "impulse_breakout|neutral|strong|far",
                    "bucket_valid": True,
                    "bucket_expected_return": 0.000212,
                    "bucket_risk_mult": 1.0,
                    "risk_mult": 1.0,
                    "momentum_rank": 0.95,
                    "is_top_mover": True,
                    "score": score,
                    "score_bucket": "0.9-1.0",
                    "feature_values": {
                        "body_strength": 0.95,
                        "close_position": 0.95,
                        "vwap_score": 1.0,
                        "momentum": 0.95,
                    },
                }

            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.select_and_open(
                [
                    build_candidate("BTCUSDT", 0.95),
                    build_candidate("ETHUSDT", 0.94),
                ],
                timestamp,
            )

            self.assertEqual(len(portfolio.open_positions), 1)

    def test_moonshot_candidate_uses_override_risk_and_strategy_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
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
                    "range_expansion_factor": 2.2,
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
                        "score": 0.90,
                        "selection_score": 0.97,
                        "score_bucket": "0.9-1.0",
                        "strategy_type": "intraday_moonshot",
                        "signal_family": "moonshot",
                        "risk_group": "intraday_moonshot",
                        "group_risk_cap": 0.015,
                        "risk_fraction_override": 0.0045,
                        "moonshot_score": 0.94,
                        "range_expansion_factor": 2.2,
                        "execution_profile": {
                            "disable_pyramiding": True,
                            "profit_lock_trigger_r": 1.0,
                            "profit_lock_stop_r": 0.15,
                            "trailing_activation_r": 1.5,
                            "slow_grind_max_bars": 12,
                            "slow_grind_open_r_max": 0.8,
                        },
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
            self.assertEqual(trade.strategy_type, "intraday_moonshot")
            self.assertEqual(trade.risk_group, "intraday_moonshot")
            self.assertAlmostEqual(trade.intended_risk_per_trade, 0.0045, places=7)
            self.assertAlmostEqual(trade.selection_score, 0.97, places=7)
            self.assertAlmostEqual(trade.range_expansion_factor, 2.2, places=7)
            self.assertAlmostEqual(trade.trailing_activation_r, 1.5, places=7)

    def test_htf_candidate_same_symbol_same_side_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
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

            htf_row = pd.Series(
                {
                    "close": 112.0,
                    "low": 111.0,
                    "high": 113.0,
                    "ll2": 108.0,
                    "ema2": 110.0,
                    "ema3": 109.0,
                    "atr": 2.0,
                },
                name=timestamp,
            )
            portfolio.select_and_open(
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": timestamp,
                        "side": "long",
                        "row": htf_row,
                        "bias": "bullish",
                        "edge_type": "htf_12h_moonshot",
                        "body_bucket": "strong",
                        "vwap_bucket": "near",
                        "bucket_key_text": "htf_12h_moonshot|bullish|strong|near",
                        "bucket_valid": True,
                        "bucket_expected_return": None,
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.97,
                        "is_top_mover": True,
                        "score": 0.91,
                        "selection_score": 0.94,
                        "score_bucket": "0.9-1.0",
                        "strategy_type": "htf_12h_moonshot",
                        "signal_family": "htf_12h_moonshot",
                        "risk_group": "htf_12h_moonshot",
                        "group_risk_cap": 0.012,
                        "max_open_positions_for_strategy": 2,
                        "block_same_symbol_same_side": True,
                        "apply_score_bucket_filters": False,
                        "risk_fraction_override": 0.0035,
                        "moonshot_score": 0.91,
                        "range_expansion_factor": 1.8,
                        "stop_price_override": 107.0,
                        "htf_signal_family": "structure_breakout",
                        "htf_score": 8.0,
                        "htf_context_1d": "bullish",
                        "htf_context_1w": "bullish",
                        "htf_entry_reason": "12h structure breakout",
                        "htf_stop_reason": "12h structural low with ATR buffer",
                        "htf_trailing_state": "confirmation",
                        "htf_decay_reason": None,
                        "htf_candidate_rank": 0.94,
                        "execution_profile": {
                            "disable_pyramiding": True,
                            "disable_trailing": True,
                            "max_hold_candles": 5760,
                        },
                        "feature_values": {
                            "body_strength": 2.0,
                            "close_position": 0.85,
                            "vwap_score": 0.3,
                            "momentum": 0.97,
                        },
                    }
                ],
                timestamp,
            )

            self.assertEqual(len(portfolio.open_positions), 1)

    def test_htf_trade_is_not_exited_by_15m_noise_when_macro_context_holds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series(
                {
                    "close": 112.0,
                    "low": 111.0,
                    "high": 113.0,
                    "ll2": 108.0,
                    "ema2": 110.0,
                    "ema3": 109.0,
                    "atr": 2.0,
                },
                name=timestamp,
            )

            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.select_and_open(
                [
                    {
                        "symbol": "ETHUSDT",
                        "timestamp": timestamp,
                        "side": "long",
                        "row": row,
                        "bias": "bullish",
                        "edge_type": "htf_12h_moonshot",
                        "body_bucket": "strong",
                        "vwap_bucket": "near",
                        "bucket_key_text": "htf_12h_moonshot|bullish|strong|near",
                        "bucket_valid": True,
                        "bucket_expected_return": None,
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.95,
                        "is_top_mover": True,
                        "score": 0.90,
                        "selection_score": 0.93,
                        "score_bucket": "0.9-1.0",
                        "strategy_type": "htf_12h_moonshot",
                        "signal_family": "htf_12h_moonshot",
                        "risk_group": "htf_12h_moonshot",
                        "group_risk_cap": 0.012,
                        "max_open_positions_for_strategy": 2,
                        "block_same_symbol_same_side": True,
                        "apply_score_bucket_filters": False,
                        "risk_fraction_override": 0.0035,
                        "moonshot_score": 0.90,
                        "range_expansion_factor": 1.7,
                        "stop_price_override": 107.0,
                        "htf_signal_family": "structure_breakout",
                        "htf_score": 8.0,
                        "htf_context_1d": "bullish",
                        "htf_context_1w": "bullish",
                        "htf_entry_reason": "12h structure breakout",
                        "htf_stop_reason": "12h structural low with ATR buffer",
                        "htf_trailing_state": "confirmation",
                        "htf_decay_reason": None,
                        "htf_candidate_rank": 0.93,
                        "execution_profile": {
                            "disable_pyramiding": True,
                            "disable_trailing": True,
                            "max_hold_candles": 5760,
                        },
                        "feature_values": {
                            "body_strength": 2.0,
                            "close_position": 0.85,
                            "vwap_score": 0.3,
                            "momentum": 0.95,
                        },
                    }
                ],
                timestamp,
            )
            self.assertEqual(len(portfolio.open_positions), 1)

            noisy_row = pd.Series(
                {
                    "close": 111.2,
                    "low": 110.8,
                    "high": 111.6,
                    "ll2": 109.5,
                    "ema2": 111.8,
                    "ema3": 112.0,
                    "session_vwap": 112.1,
                    "atr": 1.8,
                },
                name=pd.Timestamp("2026-01-01 12:15:00"),
            )
            portfolio.manage_open_positions(
                {"ETHUSDT": noisy_row},
                htf_context_by_symbol={
                    "ETHUSDT": {
                        "htf_context_1d": "bullish",
                        "htf_context_1w": "bullish",
                        "htf_trailing_state_long": "confirmation",
                        "htf_trailing_long": 108.2,
                        "htf_decay_active_long": False,
                        "htf_decay_12h_candles": 3,
                    }
                },
            )

            self.assertEqual(len(portfolio.open_positions), 1)
            trade = portfolio.open_positions[0]
            self.assertEqual(trade.strategy_type, "htf_12h_moonshot")
            self.assertEqual(trade.htf_trailing_state, "confirmation")

    def test_htf_standard_trade_uses_same_htf_management_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series(
                {
                    "close": 112.0,
                    "low": 111.0,
                    "high": 113.0,
                    "ll2": 108.0,
                    "ema2": 110.0,
                    "ema3": 109.0,
                    "atr": 2.0,
                },
                name=timestamp,
            )

            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.select_and_open(
                [
                    {
                        "symbol": "ADAUSDT",
                        "timestamp": timestamp,
                        "side": "long",
                        "row": row,
                        "bias": "bullish",
                        "edge_type": "htf_12h_standard",
                        "body_bucket": "strong",
                        "vwap_bucket": "near",
                        "bucket_key_text": "htf_12h_standard|bullish|strong|near",
                        "bucket_valid": True,
                        "bucket_expected_return": None,
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.91,
                        "is_top_mover": True,
                        "score": 0.78,
                        "selection_score": 0.83,
                        "score_bucket": "0.7-0.8",
                        "strategy_type": "htf_12h_standard",
                        "signal_family": "htf_12h_standard",
                        "risk_group": "htf_12h_standard",
                        "group_risk_cap": 0.006,
                        "max_open_positions_for_strategy": 2,
                        "block_same_symbol_same_side": True,
                        "apply_score_bucket_filters": False,
                        "selection_threshold_offset": -0.18,
                        "selection_min_threshold": 0.58,
                        "selection_max_threshold": 0.84,
                        "risk_fraction_override": 0.0020,
                        "moonshot_score": None,
                        "range_expansion_factor": 1.1,
                        "stop_price_override": 108.0,
                        "htf_signal_family": "trend_pullback",
                        "htf_score": 6.5,
                        "htf_context_1d": "bullish",
                        "htf_context_1w": "neutral",
                        "htf_entry_reason": "12h continuation pullback",
                        "htf_stop_reason": "12h pullback structure low",
                        "htf_trailing_state": "init",
                        "htf_decay_reason": None,
                        "htf_candidate_rank": 0.83,
                        "execution_profile": {
                            "disable_pyramiding": True,
                            "disable_trailing": True,
                            "max_hold_candles": 1728,
                        },
                        "feature_values": {
                            "body_strength": 1.6,
                            "close_position": 0.74,
                            "vwap_score": 0.3,
                            "momentum": 0.91,
                        },
                    }
                ],
                timestamp,
            )
            self.assertEqual(len(portfolio.open_positions), 1)

            noisy_row = pd.Series(
                {
                    "close": 111.4,
                    "low": 111.0,
                    "high": 111.8,
                    "ll2": 109.0,
                    "ema2": 111.7,
                    "ema3": 111.9,
                    "session_vwap": 112.0,
                    "atr": 1.8,
                },
                name=pd.Timestamp("2026-01-01 12:15:00"),
            )
            portfolio.manage_open_positions(
                {"ADAUSDT": noisy_row},
                htf_context_by_symbol={
                    "ADAUSDT": {
                        "htf_context_1d": "bullish",
                        "htf_context_1w": "neutral",
                        "htf_trailing_state_long": "confirmation",
                        "htf_trailing_long": 108.1,
                        "htf_decay_active_long": False,
                        "htf_decay_12h_candles": 3,
                    }
                },
            )

            self.assertEqual(len(portfolio.open_positions), 1)
            trade = portfolio.open_positions[0]
            self.assertEqual(trade.strategy_type, "htf_12h_standard")
            self.assertEqual(trade.htf_trailing_state, "confirmation")

    def test_htf_rotation_trade_uses_same_htf_management_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series(
                {
                    "close": 112.0,
                    "low": 111.0,
                    "high": 113.0,
                    "ll2": 108.0,
                    "ema2": 110.0,
                    "ema3": 109.0,
                    "atr": 2.0,
                },
                name=timestamp,
            )

            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.select_and_open(
                [
                    {
                        "symbol": "SOLUSDT",
                        "timestamp": timestamp,
                        "side": "long",
                        "row": row,
                        "bias": "bullish",
                        "edge_type": "htf_12h_rotation",
                        "body_bucket": "strong",
                        "vwap_bucket": "near",
                        "bucket_key_text": "htf_12h_rotation|bullish|strong|near",
                        "bucket_valid": True,
                        "bucket_expected_return": None,
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.96,
                        "is_top_mover": True,
                        "score": 0.88,
                        "selection_score": 0.91,
                        "score_bucket": "0.8-0.9",
                        "strategy_type": "htf_12h_rotation",
                        "signal_family": "htf_12h_rotation",
                        "risk_group": "htf_12h_rotation",
                        "group_risk_cap": 0.008,
                        "max_open_positions_for_strategy": 2,
                        "block_same_symbol_same_side": True,
                        "apply_score_bucket_filters": False,
                        "risk_fraction_override": 0.0025,
                        "moonshot_score": 0.88,
                        "range_expansion_factor": 1.6,
                        "stop_price_override": 107.0,
                        "htf_signal_family": "leader_acceleration",
                        "htf_score": 8.8,
                        "htf_context_1d": "bullish",
                        "htf_context_1w": "bullish",
                        "htf_entry_reason": "12h rotation leader acceleration",
                        "htf_stop_reason": "12h rotation structural low with ATR buffer",
                        "htf_trailing_state": "confirmation",
                        "htf_decay_reason": None,
                        "htf_candidate_rank": 0.88,
                        "execution_profile": {
                            "disable_pyramiding": True,
                            "disable_trailing": True,
                            "max_hold_candles": 6912,
                        },
                        "feature_values": {
                            "body_strength": 1.8,
                            "close_position": 0.85,
                            "vwap_score": 0.3,
                            "momentum": 0.96,
                        },
                    }
                ],
                timestamp,
            )
            self.assertEqual(len(portfolio.open_positions), 1)

            noisy_row = pd.Series(
                {
                    "close": 111.4,
                    "low": 111.0,
                    "high": 111.8,
                    "ll2": 109.0,
                    "ema2": 111.7,
                    "ema3": 111.9,
                    "session_vwap": 112.0,
                    "atr": 1.8,
                },
                name=pd.Timestamp("2026-01-01 12:15:00"),
            )
            portfolio.manage_open_positions(
                {"SOLUSDT": noisy_row},
                htf_context_by_symbol={
                    "SOLUSDT": {
                        "htf_context_1d": "bullish",
                        "htf_context_1w": "bullish",
                        "htf_trailing_state_long": "confirmation",
                        "htf_trailing_long": 108.1,
                        "htf_decay_active_long": False,
                        "htf_decay_12h_candles": 2,
                    }
                },
            )

            self.assertEqual(len(portfolio.open_positions), 1)
            trade = portfolio.open_positions[0]
            self.assertEqual(trade.strategy_type, "htf_12h_rotation")
            self.assertEqual(trade.htf_trailing_state, "confirmation")

    def test_h6_standard_trade_uses_htf_time_exit_without_context_noise(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series(
                {
                    "close": 112.0,
                    "low": 111.0,
                    "high": 113.0,
                    "ll2": 108.0,
                    "ema2": 110.0,
                    "ema3": 109.0,
                    "atr": 2.0,
                },
                name=timestamp,
            )

            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.select_and_open(
                [
                    {
                        "symbol": "BNBUSDT",
                        "timestamp": timestamp,
                        "side": "long",
                        "row": row,
                        "bias": "bullish",
                        "edge_type": "h6_standard",
                        "body_bucket": "strong",
                        "vwap_bucket": "near",
                        "bucket_key_text": "h6_standard|bullish|strong|near",
                        "bucket_valid": True,
                        "bucket_expected_return": None,
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.90,
                        "is_top_mover": True,
                        "score": 0.84,
                        "selection_score": 0.84,
                        "score_bucket": "0.8-0.9",
                        "strategy_type": "h6_standard",
                        "signal_family": "h6_bridge_breakout",
                        "risk_group": "h6_standard",
                        "group_risk_cap": 0.0055,
                        "max_open_positions_for_strategy": 2,
                        "block_same_symbol_same_side": True,
                        "apply_score_bucket_filters": False,
                        "risk_fraction_override": 0.0020,
                        "moonshot_score": 0.84,
                        "range_expansion_factor": 1.4,
                        "stop_price_override": 108.0,
                        "execution_profile": {
                            "disable_pyramiding": True,
                            "disable_trailing": True,
                            "max_hold_candles": 1,
                        },
                        "feature_values": {
                            "body_strength": 1.5,
                            "close_position": 0.82,
                            "vwap_score": 0.2,
                            "momentum": 0.90,
                        },
                    }
                ],
                timestamp,
            )
            self.assertEqual(len(portfolio.open_positions), 1)

            noisy_row = pd.Series(
                {
                    "close": 112.1,
                    "low": 111.9,
                    "high": 112.2,
                    "ll2": 109.0,
                    "ema2": 112.0,
                    "ema3": 112.1,
                    "session_vwap": 112.2,
                    "atr": 1.8,
                },
                name=pd.Timestamp("2026-01-01 12:15:00"),
            )
            portfolio.manage_open_positions({"BNBUSDT": noisy_row}, htf_context_by_symbol={})

            self.assertEqual(len(portfolio.open_positions), 0)
            self.assertEqual(portfolio.account.trade_count, 1)
            self.assertEqual(portfolio.daily_closed_trades, 1)

    def test_rotation_sleeve_has_reserved_risk_when_shared_pool_is_full(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            config.data["live_sim"]["paper_portfolio"]["max_total_risk_fraction"] = 0.04
            config.data["live_sim"]["paper_portfolio"]["convexity"]["enabled"] = False
            config.data["live_sim"]["paper_portfolio"]["allocator_v2"]["enabled"] = False
            config.data["live_sim"]["paper_portfolio"]["strategy_sleeves"] = {
                "htf_12h_rotation": {
                    "enabled": True,
                    "reserved_risk_fraction": 0.01,
                    "max_new_positions_per_step": 1,
                    "block_if_symbol_has_other_strategy_position": True,
                    "ignore_global_step_cap": True,
                }
            }
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")

            def build_core(symbol, score, risk_fraction):
                return {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "side": "long",
                    "row": pd.Series(
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
                    ),
                    "bias": "neutral",
                    "edge_type": "impulse_breakout",
                    "body_bucket": "strong",
                    "vwap_bucket": "far",
                    "bucket_key_text": "impulse_breakout|neutral|strong|far",
                    "bucket_valid": True,
                    "bucket_expected_return": 0.000212,
                    "bucket_risk_mult": 1.0,
                    "risk_mult": 1.0,
                    "momentum_rank": 0.95,
                    "is_top_mover": True,
                    "score": score,
                    "selection_score": score,
                    "score_bucket": "0.9-1.0",
                    "risk_fraction_override": risk_fraction,
                    "feature_values": {
                        "body_strength": 0.9,
                        "close_position": 0.9,
                        "vwap_score": 1.0,
                        "momentum": 0.95,
                    },
                }

            rotation_candidate = {
                "symbol": "SOLUSDT",
                "timestamp": timestamp,
                "side": "long",
                "row": pd.Series(
                    {
                        "close": 112.0,
                        "low": 111.0,
                        "high": 113.0,
                        "ll2": 108.0,
                        "ema2": 110.0,
                        "ema3": 109.0,
                        "atr": 2.0,
                    },
                    name=timestamp,
                ),
                "bias": "bullish",
                "edge_type": "htf_12h_rotation",
                "body_bucket": "strong",
                "vwap_bucket": "near",
                "bucket_key_text": "htf_12h_rotation|bullish|strong|near",
                "bucket_valid": True,
                "bucket_expected_return": None,
                "bucket_risk_mult": 1.0,
                "risk_mult": 1.0,
                "momentum_rank": 0.96,
                "is_top_mover": True,
                "score": 0.88,
                "selection_score": 0.91,
                "score_bucket": "0.8-0.9",
                "strategy_type": "htf_12h_rotation",
                "signal_family": "htf_12h_rotation",
                "risk_group": "htf_12h_rotation",
                "group_risk_cap": 0.01,
                "max_open_positions_for_strategy": 2,
                "block_same_symbol_same_side": True,
                "apply_score_bucket_filters": False,
                "risk_fraction_override": 0.005,
                "stop_price_override": 107.0,
                "feature_values": {
                    "body_strength": 1.8,
                    "close_position": 0.85,
                    "vwap_score": 0.3,
                    "momentum": 0.96,
                },
            }

            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.select_and_open([build_core("BTCUSDT", 0.95, 0.03)], timestamp)
            portfolio.select_and_open(
                [
                    build_core("ETHUSDT", 0.94, 0.005),
                    rotation_candidate,
                ],
                timestamp,
            )

            self.assertEqual(len(portfolio.open_positions), 2)
            self.assertCountEqual(
                [trade.strategy_type for trade in portfolio.open_positions],
                ["core", "htf_12h_rotation"],
            )

    def test_rotation_sleeve_can_ignore_global_step_cap_with_own_step_lane(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            config.data["live_sim"]["paper_portfolio"]["allocator_v2"]["enabled"] = False
            config.data["live_sim"]["paper_portfolio"]["max_new_positions_per_step"] = 1
            config.data["live_sim"]["paper_portfolio"]["strategy_sleeves"] = {
                "htf_12h_rotation": {
                    "enabled": True,
                    "reserved_risk_fraction": 0.01,
                    "max_new_positions_per_step": 1,
                    "block_if_symbol_has_other_strategy_position": True,
                    "ignore_global_step_cap": True,
                }
            }
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")

            core_candidate = {
                "symbol": "BTCUSDT",
                "timestamp": timestamp,
                "side": "long",
                "row": pd.Series(
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
                ),
                "bias": "neutral",
                "edge_type": "impulse_breakout",
                "body_bucket": "strong",
                "vwap_bucket": "far",
                "bucket_key_text": "impulse_breakout|neutral|strong|far",
                "bucket_valid": True,
                "bucket_expected_return": 0.000212,
                "bucket_risk_mult": 1.0,
                "risk_mult": 1.0,
                "momentum_rank": 0.95,
                "is_top_mover": True,
                "score": 0.95,
                "selection_score": 0.95,
                "score_bucket": "0.9-1.0",
                "feature_values": {
                    "body_strength": 0.9,
                    "close_position": 0.9,
                    "vwap_score": 1.0,
                    "momentum": 0.95,
                },
            }
            rotation_candidate = {
                "symbol": "SOLUSDT",
                "timestamp": timestamp,
                "side": "long",
                "row": pd.Series(
                    {
                        "close": 112.0,
                        "low": 111.0,
                        "high": 113.0,
                        "ll2": 108.0,
                        "ema2": 110.0,
                        "ema3": 109.0,
                        "atr": 2.0,
                    },
                    name=timestamp,
                ),
                "bias": "bullish",
                "edge_type": "htf_12h_rotation",
                "body_bucket": "strong",
                "vwap_bucket": "near",
                "bucket_key_text": "htf_12h_rotation|bullish|strong|near",
                "bucket_valid": True,
                "bucket_expected_return": None,
                "bucket_risk_mult": 1.0,
                "risk_mult": 1.0,
                "momentum_rank": 0.96,
                "is_top_mover": True,
                "score": 0.88,
                "selection_score": 0.91,
                "score_bucket": "0.8-0.9",
                "strategy_type": "htf_12h_rotation",
                "signal_family": "htf_12h_rotation",
                "risk_group": "htf_12h_rotation",
                "group_risk_cap": 0.01,
                "max_open_positions_for_strategy": 2,
                "block_same_symbol_same_side": True,
                "apply_score_bucket_filters": False,
                "risk_fraction_override": 0.005,
                "stop_price_override": 107.0,
                "feature_values": {
                    "body_strength": 1.8,
                    "close_position": 0.85,
                    "vwap_score": 0.3,
                    "momentum": 0.96,
                },
            }

            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.select_and_open([core_candidate, rotation_candidate], timestamp)

            self.assertEqual(len(portfolio.open_positions), 2)
            self.assertCountEqual(
                [trade.strategy_type for trade in portfolio.open_positions],
                ["core", "htf_12h_rotation"],
            )

    def test_rotation_sleeve_blocks_same_symbol_when_other_strategy_is_open(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            config.data["live_sim"]["paper_portfolio"]["strategy_sleeves"] = {
                "htf_12h_rotation": {
                    "enabled": True,
                    "reserved_risk_fraction": 0.01,
                    "max_new_positions_per_step": 1,
                    "block_if_symbol_has_other_strategy_position": True,
                    "ignore_global_step_cap": True,
                }
            }
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            core_row = pd.Series(
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
            rotation_row = pd.Series(
                {
                    "close": 112.0,
                    "low": 111.0,
                    "high": 113.0,
                    "ll2": 108.0,
                    "ema2": 110.0,
                    "ema3": 109.0,
                    "atr": 2.0,
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
                        "row": core_row,
                        "bias": "neutral",
                        "edge_type": "impulse_breakout",
                        "body_bucket": "strong",
                        "vwap_bucket": "far",
                        "bucket_key_text": "impulse_breakout|neutral|strong|far",
                        "bucket_valid": True,
                        "bucket_expected_return": 0.000212,
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.95,
                        "is_top_mover": True,
                        "score": 0.95,
                        "selection_score": 0.95,
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
            portfolio.select_and_open(
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": timestamp,
                        "side": "long",
                        "row": rotation_row,
                        "bias": "bullish",
                        "edge_type": "htf_12h_rotation",
                        "body_bucket": "strong",
                        "vwap_bucket": "near",
                        "bucket_key_text": "htf_12h_rotation|bullish|strong|near",
                        "bucket_valid": True,
                        "bucket_expected_return": None,
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.96,
                        "is_top_mover": True,
                        "score": 0.88,
                        "selection_score": 0.91,
                        "score_bucket": "0.8-0.9",
                        "strategy_type": "htf_12h_rotation",
                        "signal_family": "htf_12h_rotation",
                        "risk_group": "htf_12h_rotation",
                        "group_risk_cap": 0.01,
                        "max_open_positions_for_strategy": 2,
                        "block_same_symbol_same_side": True,
                        "apply_score_bucket_filters": False,
                        "risk_fraction_override": 0.005,
                        "stop_price_override": 107.0,
                        "feature_values": {
                            "body_strength": 1.8,
                            "close_position": 0.85,
                            "vwap_score": 0.3,
                            "momentum": 0.96,
                        },
                    }
                ],
                timestamp,
            )

            self.assertEqual(len(portfolio.open_positions), 1)
            self.assertEqual(portfolio.open_positions[0].strategy_type, "core")

    def test_htf_short_can_open_when_strategy_side_policy_allows_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            config.data["live_sim"]["paper_portfolio"]["strategy_allowed_sides"][
                "htf_12h_moonshot"
            ] = ["long", "short"]
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series(
                {
                    "close": 100.0,
                    "low": 99.0,
                    "high": 101.0,
                    "hh2": 104.0,
                    "ema2": 100.5,
                    "ema3": 101.0,
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
                        "side": "short",
                        "row": row,
                        "bias": "bearish",
                        "edge_type": "htf_12h_moonshot",
                        "body_bucket": "strong",
                        "vwap_bucket": "near",
                        "bucket_key_text": "htf_12h_moonshot|bearish|strong|near",
                        "bucket_valid": True,
                        "bucket_expected_return": None,
                        "bucket_risk_mult": 1.0,
                        "risk_mult": 1.0,
                        "momentum_rank": 0.92,
                        "is_top_mover": True,
                        "score": 0.89,
                        "selection_score": 0.91,
                        "score_bucket": "0.8-0.9",
                        "strategy_type": "htf_12h_moonshot",
                        "signal_family": "htf_12h_moonshot",
                        "risk_group": "htf_12h_moonshot",
                        "group_risk_cap": 0.012,
                        "max_open_positions_for_strategy": 2,
                        "block_same_symbol_same_side": True,
                        "apply_score_bucket_filters": False,
                        "risk_fraction_override": 0.0021,
                        "moonshot_score": 0.89,
                        "range_expansion_factor": 1.7,
                        "stop_price_override": 103.0,
                        "htf_signal_family": "structure_breakout",
                        "htf_score": 8.0,
                        "htf_context_1d": "bearish",
                        "htf_context_1w": "bearish",
                        "htf_entry_reason": "12h structure breakout",
                        "htf_stop_reason": "12h structural high with ATR buffer",
                        "htf_trailing_state": "confirmation",
                        "htf_decay_reason": None,
                        "htf_candidate_rank": 0.91,
                        "execution_profile": {
                            "disable_pyramiding": True,
                            "disable_trailing": True,
                            "max_hold_candles": 5760,
                        },
                        "feature_values": {
                            "body_strength": 2.0,
                            "close_position": 0.15,
                            "vwap_score": 0.3,
                            "momentum": 0.92,
                        },
                    }
                ],
                timestamp,
            )

            self.assertEqual(len(portfolio.open_positions), 1)
            self.assertEqual(portfolio.open_positions[0].side, "short")

    def test_negative_recent_swing_health_blocks_new_swing_trade(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
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
            portfolio.performance_history = [
                {
                    "exit_time": datetime(2025, 12, 31, 12, 0, 0),
                    "strategy_type": "swing_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.20,
                    "pnl": -20.0,
                },
                {
                    "exit_time": datetime(2026, 1, 1, 11, 0, 0),
                    "strategy_type": "swing_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.10,
                    "pnl": -10.0,
                },
            ]
            portfolio._refresh_recent_performance()
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
                        "selection_score": 0.95,
                        "score_bucket": "0.9-1.0",
                        "strategy_type": "swing_moonshot",
                        "signal_family": "swing_moonshot",
                        "risk_group": "swing_moonshot",
                        "group_risk_cap": 0.01,
                        "risk_fraction_override": 0.0015,
                        "moonshot_score": 0.90,
                        "execution_profile": {
                            "disable_pyramiding": True,
                        },
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

            self.assertEqual(len(portfolio.open_positions), 0)

    def test_sparse_negative_recent_htf_window_stays_neutral(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            portfolio.performance_history = [
                {
                    "exit_time": datetime(2026, 1, 1, 9, 0, 0),
                    "strategy_type": "htf_12h_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.40,
                    "pnl": -25.0,
                },
                {
                    "exit_time": datetime(2026, 1, 2, 9, 0, 0),
                    "strategy_type": "htf_12h_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.35,
                    "pnl": -20.0,
                },
                {
                    "exit_time": datetime(2026, 1, 3, 9, 0, 0),
                    "strategy_type": "htf_12h_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.20,
                    "pnl": -10.0,
                },
            ]
            portfolio._refresh_recent_performance()

            multiplier, source = portfolio._strategy_health_multiplier("htf_12h_moonshot")

            self.assertEqual(multiplier, 1.0)
            self.assertEqual(source, "none")

    def test_negative_recent_htf_window_scales_down_without_disable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            portfolio.performance_history = [
                {
                    "exit_time": datetime(2026, 1, 1, 9, 0, 0),
                    "strategy_type": "htf_12h_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.10,
                    "pnl": -8.0,
                }
                for _ in range(8)
            ]
            for index, record in enumerate(portfolio.performance_history):
                record["exit_time"] = datetime(2026, 1, 1, 9, 0, 0) + timedelta(days=index)
            portfolio._refresh_recent_performance()

            multiplier, source = portfolio._strategy_health_multiplier("htf_12h_moonshot")

            self.assertAlmostEqual(multiplier, 0.75, places=7)
            self.assertEqual(source, "recent_window")

    def test_strategy_runtime_policy_state_can_trigger_h1_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            portfolio.performance_history = [
                {
                    "exit_time": datetime(2026, 1, 1, 9, 0, 0),
                    "strategy_type": "h1_execution",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.30,
                    "pnl": -50.0,
                },
                {
                    "exit_time": datetime(2026, 1, 2, 9, 0, 0),
                    "strategy_type": "h1_execution",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": 0.10,
                    "pnl": 20.0,
                },
                {
                    "exit_time": datetime(2026, 1, 3, 9, 0, 0),
                    "strategy_type": "h1_execution",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.25,
                    "pnl": -35.0,
                },
            ]

            state = portfolio.strategy_runtime_policy_state(
                "h1_execution",
                {
                    "enabled": True,
                    "lookback_days": 120,
                    "max_trades": 10,
                    "min_trades": 3,
                    "min_profit_factor": 1.05,
                    "min_avg_R": 0.02,
                },
            )

            self.assertTrue(state["fallback_to_short_only"])
            self.assertEqual("fallback_short_only", state["label"])
            self.assertEqual(3, state["count"])
            self.assertLess(state["profit_factor"], 1.05)

    def test_record_selection_decisions_tracks_cap_pressure_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))

            portfolio._record_selection_decisions(
                [
                    {"id": 1, "strategy_type": "core"},
                    {"id": 2, "strategy_type": "h1_execution"},
                    {"id": 3, "strategy_type": "h1_execution"},
                ],
                {
                    1: "shared_risk_cap",
                    2: "strategy_sleeve_cap",
                    3: "opened",
                },
                pd.Timestamp("2026-01-03 12:00:00"),
            )

            self.assertEqual(1, portfolio.selection_reason_counts["shared_risk_cap"])
            self.assertEqual(1, portfolio.selection_reason_counts["strategy_sleeve_cap"])
            self.assertEqual(1, portfolio.selection_reason_counts["opened"])
            self.assertEqual(
                1,
                portfolio.selection_reason_counts_by_strategy["h1_execution"][
                    "strategy_sleeve_cap"
                ],
            )
            self.assertEqual(3, len(portfolio.selection_reason_history))

    def test_write_state_artifacts_includes_selection_and_runtime_policy_monitoring(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            config.data["strategy"]["h1_execution"] = {
                "runtime_policy_guard": {
                    "enabled": True,
                    "lookback_days": 120,
                    "max_trades": 10,
                    "min_trades": 3,
                    "min_profit_factor": 1.05,
                    "min_avg_R": 0.02,
                }
            }
            state_logger = LivePortfolioStateLogger(
                output_dir=temp_dir,
                config=config,
            )
            portfolio = LivePaperPortfolio(
                config=config,
                state_logger=state_logger,
            )
            portfolio.performance_history = [
                {
                    "exit_time": datetime(2026, 1, 1, 9, 0, 0),
                    "strategy_type": "h1_execution",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.30,
                    "pnl": -50.0,
                },
                {
                    "exit_time": datetime(2026, 1, 2, 9, 0, 0),
                    "strategy_type": "h1_execution",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": 0.10,
                    "pnl": 20.0,
                },
                {
                    "exit_time": datetime(2026, 1, 3, 9, 0, 0),
                    "strategy_type": "h1_execution",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.25,
                    "pnl": -35.0,
                },
            ]
            portfolio._record_selection_decisions(
                [
                    {"id": 1, "strategy_type": "core"},
                    {"id": 2, "strategy_type": "h1_execution"},
                    {"id": 3, "strategy_type": "h1_execution"},
                ],
                {
                    1: "opened",
                    2: "shared_risk_cap",
                    3: "strategy_sleeve_cap",
                },
                pd.Timestamp("2026-01-03 12:00:00"),
            )

            portfolio._write_state_artifacts()

            status = json.loads(
                Path(temp_dir, "portfolio_status.json").read_text(encoding="utf-8")
            )
            self.assertIn("selection_reason_counts", status)
            self.assertIn("cap_pressure_summary", status)
            self.assertIn("runtime_policy_states", status)
            self.assertEqual(1, status["selection_reason_counts"]["shared_risk_cap"])
            self.assertEqual(
                1,
                status["cap_pressure_summary"]["cumulative"]["strategy_sleeve_cap_count"],
            )
            self.assertEqual(
                "fallback_short_only",
                status["runtime_policy_states"]["h1_execution"]["label"],
            )
            self.assertTrue(Path(temp_dir, "selection_reason_summary.csv").exists())
            self.assertTrue(Path(temp_dir, "runtime_policy_summary.csv").exists())

    def test_allocator_cross_sleeve_coordination_boosts_bearish_h1_short(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            raw = config.data["live_sim"]["paper_portfolio"]
            raw["strategy_allowed_sides"]["h1_execution"] = ["short"]
            raw["strategy_sleeves"]["h1_execution"] = {
                "enabled": True,
                "reserved_risk_fraction": 0.0025,
                "max_new_positions_per_step": 2,
                "block_if_symbol_has_other_strategy_position": False,
                "ignore_global_step_cap": False,
            }
            raw["allocator_v2"]["sleeves"]["h1_execution"] = {
                "priority_multiplier": 0.94,
                "rank_weights": [1.0, 0.70, 0.40],
                "max_candidates": 3,
                "max_risk_fraction_multiplier": 1.10,
                "absolute_max_risk_fraction": 0.0025,
            }
            raw["allocator_v2"]["cross_sleeve_coordination"] = {
                "enabled": True,
                "rules": {
                    "h1_bearish_short": {
                        "priority_multiplier": 1.05,
                        "base_risk_multiplier": 1.05,
                        "sleeve_cap_multiplier": 1.05,
                    }
                },
            }
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series({"close": 100.0, "low": 99.0, "high": 101.0}, name=timestamp)

            state = portfolio._build_candidate_selection_state(
                {
                    "symbol": "BTCUSDT",
                    "timestamp": timestamp,
                    "side": "short",
                    "row": row,
                    "score": 0.92,
                    "selection_score": 0.92,
                    "score_bucket": "0.9-1.0",
                    "risk_mult": 1.0,
                    "strategy_type": "h1_execution",
                    "risk_group": "h1_execution",
                    "htf_context_1d": "bearish",
                },
                timestamp,
                candidate_id=1,
            )

            self.assertEqual("h1_bearish_short", state["candidate"]["coordination_rule"])
            self.assertTrue(state["candidate"]["coordination_active"])
            self.assertGreater(state["coordination_priority_multiplier"], 1.0)
            self.assertGreater(
                state["candidate"]["coordination_base_risk_multiplier"],
                1.0,
            )

    def test_allocator_cross_sleeve_coordination_brakes_bearish_core_long(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_config = DummyConfig(output_dir=temp_dir)
            coordinated_config = DummyConfig(output_dir=temp_dir)
            coordinated_config.data["live_sim"]["paper_portfolio"]["allocator_v2"][
                "cross_sleeve_coordination"
            ] = {
                "enabled": True,
                "rules": {
                    "core_bearish_countertrend_long": {
                        "priority_multiplier": 0.94,
                        "base_risk_multiplier": 0.95,
                        "sleeve_cap_multiplier": 1.0,
                    }
                },
            }
            baseline_portfolio = LivePaperPortfolio(config=baseline_config)
            coordinated_portfolio = LivePaperPortfolio(config=coordinated_config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series({"close": 100.0, "low": 99.0, "high": 101.0}, name=timestamp)
            candidate = {
                "symbol": "ETHUSDT",
                "timestamp": timestamp,
                "side": "long",
                "row": row,
                "score": 0.92,
                "selection_score": 0.92,
                "score_bucket": "0.9-1.0",
                "risk_mult": 1.0,
                "strategy_type": "core",
                "risk_group": "core",
                "htf_context_1d": "bearish",
            }

            baseline_state = baseline_portfolio._build_candidate_selection_state(
                dict(candidate),
                timestamp,
                candidate_id=1,
            )
            coordinated_state = coordinated_portfolio._build_candidate_selection_state(
                dict(candidate),
                timestamp,
                candidate_id=1,
            )

            self.assertEqual(
                "core_bearish_countertrend_long",
                coordinated_state["candidate"]["coordination_rule"],
            )
            self.assertLess(
                coordinated_state["base_risk_fraction"],
                baseline_state["base_risk_fraction"],
            )
            self.assertLess(
                coordinated_state["coordination_priority_multiplier"],
                1.0,
            )

    def test_htf_candidate_threshold_uses_strategy_offset_and_bounds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            portfolio = LivePaperPortfolio(config=DummyConfig(output_dir=temp_dir))
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.current_threshold = 0.82
            candidate = {
                "strategy_type": "htf_12h_moonshot",
                "selection_min_threshold": 0.74,
                "selection_max_threshold": 0.88,
            }

            threshold = portfolio._threshold_for_candidate(candidate, timestamp)

            self.assertAlmostEqual(threshold, 0.74, places=7)

    def test_sparse_but_sharply_negative_recent_swing_window_triggers_emergency_disable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            config.data["live_sim"]["paper_portfolio"]["recency_min_strategy_trades"] = 10
            portfolio = LivePaperPortfolio(config=config)
            portfolio.performance_history = [
                {
                    "exit_time": datetime(2026, 1, 1, 9, 0, 0),
                    "strategy_type": "swing_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.30,
                    "pnl": -10.0,
                },
                {
                    "exit_time": datetime(2026, 1, 1, 10, 0, 0),
                    "strategy_type": "swing_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.25,
                    "pnl": -12.0,
                },
                {
                    "exit_time": datetime(2026, 1, 1, 11, 0, 0),
                    "strategy_type": "swing_moonshot",
                    "score_bucket": "0.9-1.0",
                    "pnl_R_initial": -0.35,
                    "pnl": -15.0,
                },
            ]
            portfolio._refresh_recent_performance()

            multiplier, source = portfolio._strategy_health_multiplier("swing_moonshot")

            self.assertEqual(multiplier, 0.0)
            self.assertEqual(source, "recent_emergency")

    def test_snapshot_restore_preserves_recent_performance_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            portfolio = LivePaperPortfolio(config=config)
            portfolio.performance_history = [
                {
                    "exit_time": datetime(2026, 1, 1, 12, 0, 0),
                    "strategy_type": "core",
                    "score_bucket": "0.8-0.9",
                    "pnl_R_initial": 0.03,
                    "pnl": 10.0,
                },
                {
                    "exit_time": datetime(2026, 1, 2, 12, 0, 0),
                    "strategy_type": "core",
                    "score_bucket": "0.8-0.9",
                    "pnl_R_initial": 0.02,
                    "pnl": 8.0,
                },
            ]
            portfolio._refresh_recent_performance()

            restored = LivePaperPortfolio(config=config)
            restored.restore_state(portfolio.snapshot_state())

            self.assertIn("0.8-0.9", restored.recent_score_stats)
            self.assertAlmostEqual(
                restored.recent_score_stats["0.8-0.9"]["avg_R"],
                0.025,
                places=7,
            )
            threshold, source = restored._derive_threshold_from_history()
            self.assertAlmostEqual(threshold, 0.8, places=7)
            self.assertEqual(source, "recent")

    def test_allocator_v2_concentrates_htf_risk_over_core_flow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            portfolio.reset_daily_state_if_needed(timestamp)

            core_row = pd.Series(
                {
                    "close": 105.0,
                    "low": 104.0,
                    "high": 106.0,
                    "ll2": 100.0,
                    "ema2": 104.5,
                    "ema3": 104.0,
                    "session_vwap": 104.3,
                    "body_strength": 1.8,
                    "close_position": 0.82,
                    "range_expansion_factor": 1.3,
                    "vwap_distance_ratio": 0.004,
                    "atr": 1.5,
                },
                name=timestamp,
            )
            htf_row = pd.Series(
                {
                    "close": 205.0,
                    "low": 202.0,
                    "high": 208.0,
                    "ll2": 198.0,
                    "ema2": 203.0,
                    "ema3": 201.0,
                    "session_vwap": 202.8,
                    "body_strength": 1.9,
                    "close_position": 0.86,
                    "range_expansion_factor": 1.5,
                    "vwap_distance_ratio": 0.005,
                    "atr": 2.0,
                },
                name=timestamp,
            )
            core_candidate = {
                "symbol": "BTCUSDT",
                "timestamp": timestamp,
                "side": "long",
                "row": core_row,
                "bias": "neutral",
                "edge_type": "impulse_breakout",
                "body_bucket": "strong",
                "vwap_bucket": "far",
                "bucket_key_text": "impulse_breakout|neutral|strong|far",
                "bucket_valid": True,
                "bucket_expected_return": 0.0002,
                "bucket_risk_mult": 1.1,
                "risk_mult": 1.1,
                "momentum_rank": 0.90,
                "is_top_mover": True,
                "score": 0.94,
                "selection_score": 0.94,
                "score_bucket": "0.9-1.0",
                "strategy_type": "core",
                "signal_family": "core",
                "risk_group": "core",
                "feature_values": {
                    "body_strength": 0.9,
                    "close_position": 0.9,
                    "vwap_score": 1.0,
                    "momentum": 0.90,
                },
            }
            htf_candidate = {
                "symbol": "SOLUSDT",
                "timestamp": timestamp,
                "side": "long",
                "row": htf_row,
                "bias": "bullish",
                "edge_type": "htf_12h_moonshot",
                "body_bucket": "strong",
                "vwap_bucket": "far",
                "bucket_key_text": "htf_12h_moonshot|bullish|strong|far",
                "bucket_valid": True,
                "bucket_expected_return": None,
                "bucket_risk_mult": 1.0,
                "risk_mult": 1.0,
                "momentum_rank": 0.88,
                "is_top_mover": True,
                "score": 0.86,
                "selection_score": 0.90,
                "score_bucket": "0.8-0.9",
                "strategy_type": "htf_12h_moonshot",
                "signal_family": "htf_12h_moonshot",
                "risk_group": "htf_12h_moonshot",
                "group_risk_cap": 0.012,
                "max_open_positions_for_strategy": 2,
                "block_same_symbol_same_side": True,
                "apply_score_bucket_filters": False,
                "selection_threshold_offset": -0.05,
                "selection_min_threshold": 0.70,
                "selection_max_threshold": 0.95,
                "risk_fraction_override": 0.0035,
                "moonshot_score": 0.86,
                "range_expansion_factor": 1.5,
                "execution_profile": {
                    "disable_pyramiding": True,
                },
                "feature_values": {
                    "body_strength": 1.9,
                    "close_position": 0.86,
                    "vwap_score": 1.0,
                    "momentum": 0.88,
                },
            }

            portfolio.select_and_open([core_candidate, htf_candidate], timestamp)

            self.assertEqual(len(portfolio.open_positions), 2)
            by_strategy = {
                trade.strategy_type: trade for trade in portfolio.open_positions
            }
            self.assertGreater(
                by_strategy["htf_12h_moonshot"].effective_risk_fraction,
                by_strategy["core"].effective_risk_fraction,
            )
            self.assertGreater(
                float(htf_candidate.get("allocated_risk_fraction", 0.0) or 0.0),
                float(core_candidate.get("allocated_risk_fraction", 0.0) or 0.0),
            )

    def test_allocator_v2_applies_rank_asymmetry_within_htf_sleeve(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series(
                {
                    "close": 205.0,
                    "low": 202.0,
                    "high": 208.0,
                    "ll2": 198.0,
                    "ema2": 203.0,
                    "ema3": 201.0,
                    "session_vwap": 202.8,
                    "body_strength": 1.9,
                    "close_position": 0.86,
                    "range_expansion_factor": 1.5,
                    "vwap_distance_ratio": 0.005,
                    "atr": 2.0,
                },
                name=timestamp,
            )
            candidates = [
                {
                    "symbol": "SOLUSDT",
                    "timestamp": timestamp,
                    "side": "long",
                    "row": row,
                    "bias": "bullish",
                    "edge_type": "htf_12h_moonshot",
                    "body_bucket": "strong",
                    "vwap_bucket": "far",
                    "bucket_key_text": "htf_12h_moonshot|bullish|strong|far",
                    "bucket_valid": True,
                    "momentum_rank": 0.90,
                    "score": 0.88,
                    "selection_score": 0.92,
                    "score_bucket": "0.8-0.9",
                    "strategy_type": "htf_12h_moonshot",
                    "signal_family": "htf_12h_moonshot",
                    "risk_group": "htf_12h_moonshot",
                    "group_risk_cap": 0.012,
                    "max_open_positions_for_strategy": 2,
                    "block_same_symbol_same_side": True,
                    "apply_score_bucket_filters": False,
                    "selection_threshold_offset": -0.05,
                    "selection_min_threshold": 0.70,
                    "selection_max_threshold": 0.95,
                    "risk_fraction_override": 0.0035,
                },
                {
                    "symbol": "ETHUSDT",
                    "timestamp": timestamp,
                    "side": "long",
                    "row": row,
                    "bias": "bullish",
                    "edge_type": "htf_12h_moonshot",
                    "body_bucket": "strong",
                    "vwap_bucket": "far",
                    "bucket_key_text": "htf_12h_moonshot|bullish|strong|far",
                    "bucket_valid": True,
                    "momentum_rank": 0.84,
                    "score": 0.84,
                    "selection_score": 0.82,
                    "score_bucket": "0.8-0.9",
                    "strategy_type": "htf_12h_moonshot",
                    "signal_family": "htf_12h_moonshot",
                    "risk_group": "htf_12h_moonshot",
                    "group_risk_cap": 0.012,
                    "max_open_positions_for_strategy": 2,
                    "block_same_symbol_same_side": True,
                    "apply_score_bucket_filters": False,
                    "selection_threshold_offset": -0.05,
                    "selection_min_threshold": 0.70,
                    "selection_max_threshold": 0.95,
                    "risk_fraction_override": 0.0035,
                },
            ]

            portfolio.select_and_open(candidates, timestamp)

            self.assertEqual(len(portfolio.open_positions), 2)
            allocations = {
                trade.symbol: trade.effective_risk_fraction
                for trade in portfolio.open_positions
            }
            self.assertGreater(allocations["SOLUSDT"], allocations["ETHUSDT"])

    def test_allocator_v2_agreement_bonus_promotes_confirmed_htf_leader(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            row = pd.Series(
                {
                    "close": 205.0,
                    "low": 202.0,
                    "high": 208.0,
                    "ll2": 198.0,
                    "ema2": 203.0,
                    "ema3": 201.0,
                    "session_vwap": 202.8,
                    "body_strength": 1.9,
                    "close_position": 0.86,
                    "range_expansion_factor": 1.5,
                    "vwap_distance_ratio": 0.005,
                    "atr": 2.0,
                },
                name=timestamp,
            )
            raw_candidates = [
                {
                    "symbol": "SOLUSDT",
                    "timestamp": timestamp,
                    "side": "long",
                    "row": row,
                    "bias": "bullish",
                    "score": 0.84,
                    "selection_score": 0.84,
                    "score_bucket": "0.8-0.9",
                    "strategy_type": "htf_12h_moonshot",
                    "signal_family": "htf_12h_moonshot",
                    "risk_group": "htf_12h_moonshot",
                    "group_risk_cap": 0.012,
                    "apply_score_bucket_filters": False,
                    "selection_threshold_offset": -0.05,
                    "selection_min_threshold": 0.70,
                    "selection_max_threshold": 0.95,
                    "risk_fraction_override": 0.0035,
                },
                {
                    "symbol": "SOLUSDT",
                    "timestamp": timestamp,
                    "side": "long",
                    "row": row,
                    "bias": "bullish",
                    "score": 0.80,
                    "selection_score": 0.80,
                    "score_bucket": "0.8-0.9",
                    "strategy_type": "htf_12h_rotation",
                    "signal_family": "htf_12h_rotation",
                    "risk_group": "htf_12h_rotation",
                    "group_risk_cap": 0.006,
                    "apply_score_bucket_filters": False,
                    "selection_threshold_offset": -0.04,
                    "selection_min_threshold": 0.70,
                    "selection_max_threshold": 0.95,
                    "risk_fraction_override": 0.0025,
                },
                {
                    "symbol": "ETHUSDT",
                    "timestamp": timestamp,
                    "side": "long",
                    "row": row,
                    "bias": "bullish",
                    "score": 0.88,
                    "selection_score": 0.88,
                    "score_bucket": "0.8-0.9",
                    "strategy_type": "htf_12h_moonshot",
                    "signal_family": "htf_12h_moonshot",
                    "risk_group": "htf_12h_moonshot",
                    "group_risk_cap": 0.012,
                    "apply_score_bucket_filters": False,
                    "selection_threshold_offset": -0.05,
                    "selection_min_threshold": 0.70,
                    "selection_max_threshold": 0.95,
                    "risk_fraction_override": 0.0035,
                },
            ]
            states = [
                portfolio._build_candidate_selection_state(candidate, timestamp, index)
                for index, candidate in enumerate(raw_candidates)
            ]
            allocated = portfolio._allocate_candidate_risk_fractions(
                [state for state in states if state["reason"] is None]
            )
            htf_states = [
                state for state in allocated if state["strategy_type"] == "htf_12h_moonshot"
            ]
            ranked_symbols = [state["candidate"]["symbol"] for state in htf_states]

            self.assertEqual(ranked_symbols[0], "SOLUSDT")
            self.assertGreater(
                float(htf_states[0]["agreement_bonus"]),
                0.0,
            )

    def test_allocator_v2_concentration_brake_reduces_core_rank_concentration(self):
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
                    "ema2": 104.5,
                    "ema3": 104.0,
                    "session_vwap": 104.3,
                    "body_strength": 1.8,
                    "close_position": 0.82,
                    "range_expansion_factor": 1.3,
                    "vwap_distance_ratio": 0.004,
                    "atr": 1.5,
                },
                name=timestamp,
            )
            candidates = [
                {
                    "symbol": "BTCUSDT",
                    "timestamp": timestamp,
                    "side": "long",
                    "row": row,
                    "score": 0.95,
                    "selection_score": 0.95,
                    "score_bucket": "0.9-1.0",
                    "strategy_type": "core",
                    "signal_family": "core",
                    "apply_score_bucket_filters": False,
                    "risk_fraction_override": 0.0055,
                },
                {
                    "symbol": "ETHUSDT",
                    "timestamp": timestamp,
                    "side": "long",
                    "row": row,
                    "score": 0.74,
                    "selection_score": 0.74,
                    "score_bucket": "0.8-0.9",
                    "strategy_type": "core",
                    "signal_family": "core",
                    "apply_score_bucket_filters": False,
                    "risk_fraction_override": 0.0055,
                },
            ]
            normal_states = [
                portfolio._build_candidate_selection_state(candidate, timestamp, index)
                for index, candidate in enumerate(candidates)
            ]
            normal_allocated = portfolio._allocate_candidate_risk_fractions(normal_states)
            normal_top_state = max(
                normal_allocated,
                key=lambda state: float(state["allocated_risk_fraction"] or 0.0),
            )

            stressed = LivePaperPortfolio(config=config)
            stressed.reset_daily_state_if_needed(timestamp)
            stressed.daily_closed_trades = 3
            stressed.daily_closed_pnl = -120.0
            stressed.day_start_equity = 20_000.0
            stressed.daily_loss_streak = 3
            stressed_states = [
                stressed._build_candidate_selection_state(candidate.copy(), timestamp, index)
                for index, candidate in enumerate(candidates)
            ]
            stressed_allocated = stressed._allocate_candidate_risk_fractions(
                stressed_states
            )
            stressed_top_state = max(
                stressed_allocated,
                key=lambda state: float(state["allocated_risk_fraction"] or 0.0),
            )

            self.assertLess(
                float(stressed_top_state["leader_dominance_boost"]),
                float(normal_top_state["leader_dominance_boost"]),
            )
            self.assertLess(
                float(stressed_top_state["allocation_priority"]),
                float(normal_top_state["allocation_priority"]),
            )
            self.assertTrue(
                all(
                    bool(state["candidate"].get("allocation_brake_active"))
                    for state in stressed_allocated
                )
            )

    def test_snapshot_restore_preserves_allocator_concentration_brake_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = DummyConfig(output_dir=temp_dir)
            portfolio = LivePaperPortfolio(config=config)
            timestamp = pd.Timestamp("2026-01-01 12:00:00")
            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.day_start_equity = 20_000.0
            portfolio.daily_closed_trades = 4
            portfolio.daily_closed_pnl = -140.0
            portfolio.daily_loss_streak = 4

            restored = LivePaperPortfolio(config=config)
            restored.restore_state(portfolio.snapshot_state())
            state = restored._allocator_concentration_state("core")

            self.assertEqual(restored.daily_loss_streak, 4)
            self.assertTrue(state["active"])
            self.assertGreater(state["severity"], 0.0)


if __name__ == "__main__":
    unittest.main()
