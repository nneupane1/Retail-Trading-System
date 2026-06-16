import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from structural_compounding_lab.backtest.engine import StructuralBacktestEngine
from structural_compounding_lab.config import StructuralLabConfig, load_candidate_registry, load_feature_flags
from structural_compounding_lab.features import (
    classify_momentum_personality,
    detect_micro_pullback,
    extract_bollinger_features,
    extract_macd_features,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "btcusdt_structural_fixture_1m.csv"


def _micro_pullback_frame() -> pd.DataFrame:
    index = pd.date_range("2026-06-01T00:00:00Z", periods=12, freq="1min")
    rows = [
        (100, 101, 99.8, 100.8, 100),
        (100.8, 101.8, 100.7, 101.6, 120),
        (101.6, 102.4, 101.4, 102.2, 135),
        (102.2, 103.0, 102.0, 102.8, 140),
        (102.8, 103.2, 102.4, 103.0, 145),
        (103.0, 103.1, 102.5, 102.7, 90),
        (102.7, 102.9, 102.3, 102.5, 82),
        (102.5, 102.8, 102.4, 102.75, 88),
        (102.75, 103.15, 102.7, 103.05, 130),
        (103.05, 103.4, 103.0, 103.3, 150),
        (103.3, 103.6, 103.2, 103.5, 160),
        (103.5, 103.8, 103.4, 103.7, 170),
    ]
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=index)


class StructuralResearchLayerTests(unittest.TestCase):
    def test_candidate_registry_and_feature_flags_are_non_authoritative(self):
        registry = load_candidate_registry()
        self.assertFalse(registry["authoritative"])
        for candidate in registry["candidates"]:
            self.assertFalse(candidate["authoritative"])
            self.assertFalse(candidate["paper_allowed"])
            self.assertFalse(candidate["real_money_allowed"])
        flags = load_feature_flags()
        self.assertFalse(flags["momentum_personality_layer"]["paper_allowed"])
        self.assertFalse(flags["intelligent_pullback_accumulation"]["real_money_allowed"])

    def test_macd_and_bollinger_handle_missing_data(self):
        missing_macd = extract_macd_features(pd.DataFrame())
        missing_bollinger = extract_bollinger_features(pd.DataFrame())
        self.assertEqual("missing", missing_macd["macd_state"])
        self.assertEqual("missing", missing_bollinger["bb_state"])

    def test_personality_layer_is_soft_not_hard_gate(self):
        personality = classify_momentum_personality(
            candidate={"side": "long"},
            ema_context={"ema_aligned": True},
            volume_context={"volume_expansion": True, "volume_dryup": False, "distribution_warning": False},
            vwap_context={"vwap_supportive": True},
            macd_features={"macd_confirmation_flag": False, "macd_warning_flag": True, "missing_data_fields": []},
            bollinger_features={"bb_confirmation_flag": False, "bb_warning_flag": True, "bb_compression": False, "bb_expansion": False, "missing_data_fields": []},
            pullback_features={"pullback_type": "HEALTHY_CONTINUATION_PULLBACK", "missing_data_fields": []},
            htf_context={"htf_supportive": True, "htf_aligned": True, "htf_bias": "bullish"},
        )
        self.assertIn("Warnings do not invalidate the core setup", personality["explanation_text"])
        self.assertNotEqual("", personality["personality_label"])

    def test_micro_pullback_detector_finds_valid_pullback(self):
        frame = _micro_pullback_frame()
        result = detect_micro_pullback(
            lower_timeframe_frame=frame,
            current_time=frame.index[-1],
            candidate={"side": "long", "atr": 0.55, "target_price": 106.0, "risk_reward": 2.8, "level_price": 102.4, "pattern": "retest_after_breakout", "volume_dryup": True},
            macd_features={"macd_warning_flag": False},
            bollinger_features={"bb_warning_flag": False},
        )
        self.assertTrue(result["micro_pullback_detected"])
        self.assertIn(result["pullback_type"], {"MICRO_PULLBACK_MOMENTUM", "BREAKOUT_RETEST_PULLBACK", "HEALTHY_CONTINUATION_PULLBACK"})

    def test_micro_pullback_detector_rejects_broken_structure(self):
        frame = _micro_pullback_frame().copy()
        frame.iloc[-3:, frame.columns.get_loc("low")] = [99.0, 98.6, 98.2]
        result = detect_micro_pullback(
            lower_timeframe_frame=frame,
            current_time=frame.index[-1],
            candidate={"side": "long", "atr": 0.55, "target_price": 106.0, "risk_reward": 2.8, "level_price": 102.4, "pattern": "retest_after_breakout", "volume_dryup": False},
            macd_features={"macd_warning_flag": True},
            bollinger_features={"bb_warning_flag": True},
        )
        self.assertFalse(result["micro_pullback_detected"])
        self.assertEqual("STRUCTURE_BREAK_DIP", result["pullback_type"])

    def test_smoke_backtest_writes_research_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "structural_artifacts"
            config_path = Path(tmpdir) / "structural_test_settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "execution_timeframe": "15m",
                        "confirmation_timeframes": ["1h", "4h"],
                        "visual_timeframes": ["15m", "1h", "4h"],
                        "base_capital": 20000,
                        "risk": {"risk_per_trade_pct": 0.01, "max_concurrent_positions": 1, "max_hold_bars": 24, "minimum_rr": 1.05},
                        "ema": {"fast": 3, "mid": 5, "slow": 8},
                        "atr": {"period": 3, "shock_multiple": 2.0},
                        "sr": {"pivot_left": 1, "pivot_right": 1, "touch_tolerance_pct": 0.003, "rolling_range_bars": 12, "zone_width_pct": 0.002},
                        "liquidity": {"equal_level_tolerance_pct": 0.002, "sweep_lookback_bars": 6, "reclaim_tolerance_pct": 0.001},
                        "pyramiding": {"enabled": True, "max_add_ons": 1, "add_on_trigger_r": 0.8, "size_fraction": 0.2},
                        "cooldown": {"enabled": True, "bars": 2, "requires_danger_clear": False},
                        "profit_vault": {"enabled": True, "lock_on_danger": True, "reset_active_capital_to_base": True, "minimum_lock_profit": 0.0}
                    }
                ),
                encoding="utf-8",
            )
            engine = StructuralBacktestEngine(config=StructuralLabConfig.load(config_path))
            summary = engine.run(symbol="BTCUSDT", source_csv=FIXTURE, output_dir=output_dir)

            self.assertIn("research_diagnostics", summary)
            self.assertTrue((output_dir / "master_lab_plan.json").exists())
            self.assertTrue((output_dir / "candidate_registry.json").exists())
            self.assertTrue((output_dir / "diagnostics" / "pullback_quality_report.json").exists())
            self.assertTrue((output_dir / "diagnostics" / "original_vs_pullback_entry.csv").exists())
            self.assertTrue((output_dir / "execution_realism" / "execution_cost_sensitivity.json").exists())


if __name__ == "__main__":
    unittest.main()
