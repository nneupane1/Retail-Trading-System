import csv
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from structural_compounding_lab.diagnostics.evidence_refinement import (
    EvidenceRefinementConfig,
    write_evidence_refinement,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class StructuralEvidenceRefinementTests(unittest.TestCase):
    def test_refinement_writes_cost_aware_artifacts_and_keeps_research_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_root = root / "evidence_review_001"
            output_root = root / "evidence_refinement_001"
            source_csv = root / "BTCUSDT_1m_test.csv"

            minute_index = pd.date_range("2026-01-01T00:00:00Z", periods=600, freq="1min")
            frame = pd.DataFrame(
                {
                    "timestamp": minute_index.tz_convert(None),
                    "open": [100.0 + (i * 0.02) for i in range(len(minute_index))],
                    "high": [100.4 + (i * 0.02) for i in range(len(minute_index))],
                    "low": [99.7 + (i * 0.02) for i in range(len(minute_index))],
                    "close": [100.1 + (i * 0.02) for i in range(len(minute_index))],
                    "volume": [10.0] * len(minute_index),
                }
            )
            frame.to_csv(source_csv, index=False)

            status = {
                "source_csv": str(source_csv),
                "windows": {
                    "smoke": {"start": "2026-01-01", "end": "2026-01-01"},
                    "diagnostic_fast": {"start": "2026-01-01", "end": "2026-01-01"},
                    "holdout_recent_preview": {"start": "2026-01-01", "end": "2026-01-01"},
                },
            }
            (review_root / "status.json").parent.mkdir(parents=True, exist_ok=True)
            (review_root / "status.json").write_text(json.dumps(status), encoding="utf-8")

            execution_model = {
                "research_only": True,
                "scenarios": {
                    "low_cost": {"fee_bps": 4.0, "slippage_bps": 2.0, "spread_bps": 1.0, "stop_stress_bps": 4.0},
                    "normal_cost": {"fee_bps": 8.0, "slippage_bps": 5.0, "spread_bps": 2.0, "stop_stress_bps": 8.0},
                    "high_cost": {"fee_bps": 12.0, "slippage_bps": 8.0, "spread_bps": 3.5, "stop_stress_bps": 12.0},
                    "stress_cost": {"fee_bps": 16.0, "slippage_bps": 14.0, "spread_bps": 5.0, "stop_stress_bps": 18.0},
                },
            }

            for window in ("smoke", "diagnostic_fast", "holdout_recent_preview"):
                window_root = review_root / window
                trade_rows = [
                    {
                        "trade_id": f"{window}-1",
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "entry_time": "2026-01-01T04:00:00",
                        "exit_time": "2026-01-01T05:00:00",
                        "entry_price": 104.0,
                        "exit_price": 106.0,
                        "initial_stop": 100.0,
                        "trail_stop": 100.0,
                        "pnl": 120.0,
                        "r_multiple": 1.2,
                        "entry_reason": "test",
                        "exit_reason": "danger_sniffed",
                        "add_on_count": 0,
                        "holding_bars": 1,
                        "setup_class": "A",
                        "strategy_type": "structural_compounding",
                        "moonshot_state": "normal",
                        "entry_score": 4.5,
                        "risk_multiplier": 1.0,
                        "convexity_label": "elite_convexity",
                        "cooldown_fast_clear_eligible": False,
                        "personality_label": "PULLBACK_CONTINUATION",
                        "personality_confidence": 0.6,
                        "pullback_type": "MICRO_PULLBACK_MOMENTUM",
                        "pullback_quality_score": 0.9,
                        "pullback_entry_price": 104.0,
                        "pullback_stop_price": 103.9,
                        "pullback_r_improvement": 60.0,
                        "compounding_readiness_score": 0.7,
                        "runner_label": "normal_swing",
                        "add_on_research_candidate": False,
                        "patience_score": 0.5,
                        "de_risk_score": 0.3,
                        "equity_after": 20120.0,
                        "cycle_id": "cycle-0",
                    }
                ]
                setup_rows = [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-01-01T04:00:00",
                        "side": "long",
                        "setup_type": "structural_compounding",
                        "setup_class": "A",
                        "classification": "A",
                        "structure_score": 1.0,
                        "liquidity_score": 1.0,
                        "ema_score": 1.0,
                        "htf_confirmation_score": 0.2,
                        "volatility_score": 0.3,
                        "risk_reward_score": 1.0,
                        "score": 4.5,
                        "total_score": 4.5,
                        "accepted": True,
                        "decision": "opened",
                        "entry_reason": "test",
                        "explanation": "test",
                        "pattern": "retest_after_breakout",
                        "htf_aligned": True,
                        "target_price": 116.0,
                        "level_distance_atr": 0.4,
                        "liquidity_event_type": "sweep_low",
                        "liquidity_event_age_bars": 1,
                        "risk_multiplier": 1.0,
                        "convexity_label": "elite_convexity",
                        "cooldown_fast_clear_eligible": False,
                        "execution_timeframe": "1h",
                        "story_id": "story-1",
                        "personality_label": "PULLBACK_CONTINUATION",
                        "personality_confidence": 0.6,
                        "personality_explanation": "soft",
                        "macd_state": "bullish",
                        "macd_confirmation_flag": True,
                        "macd_warning_flag": False,
                        "bollinger_state": "compression",
                        "bb_compression": True,
                        "bb_expansion": False,
                        "bb_warning_flag": False,
                        "pullback_type": "MICRO_PULLBACK_MOMENTUM",
                        "micro_pullback_detected": False,
                        "pullback_entry_time": "2026-01-01T04:00:00",
                        "pullback_entry_price": 104.0,
                        "pullback_stop_price": 103.9,
                        "pullback_quality_score": 0.9,
                        "pullback_depth_atr": 0.18,
                        "pullback_estimated_r": 120.0,
                        "pullback_r_improvement": 60.0,
                        "pullback_explanation": "tiny-stop test",
                        "compounding_readiness_score": 0.7,
                        "runner_label": "normal_swing",
                        "runner_eligible_candidate": True,
                        "add_on_research_candidate": False,
                        "patience_score": 0.5,
                        "de_risk_score": 0.3,
                        "opened": True,
                    }
                ]
                entry_rows = [
                    {
                        "trade_id": f"{window}-1",
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "original_entry_time": "2026-01-01T04:00:00",
                        "original_entry_price": 104.0,
                        "original_stop": 100.0,
                        "refined_entry_time": "2026-01-01T04:00:00",
                        "refined_entry_price": 104.0,
                        "refined_stop": 103.9,
                        "original_risk_distance": 4.0,
                        "refined_risk_distance": 0.1,
                        "original_R_to_same_target": 3.0,
                        "refined_R_to_same_target": 120.0,
                        "improved_R_delta": 117.0,
                        "worsened_R_delta": 0.0,
                        "missed_due_to_no_pullback": True,
                        "pullback_type": "MICRO_PULLBACK_MOMENTUM",
                        "notes": "tiny-stop test",
                    }
                ]
                _write_csv(window_root / "trades.csv", trade_rows)
                _write_csv(window_root / "setup_log.csv", setup_rows)
                _write_csv(window_root / "diagnostics" / "original_vs_pullback_entry.csv", entry_rows)
                (window_root / "execution_realism").mkdir(parents=True, exist_ok=True)
                (window_root / "execution_realism" / "execution_cost_model.json").write_text(
                    json.dumps(execution_model),
                    encoding="utf-8",
                )

            paths = write_evidence_refinement(
                EvidenceRefinementConfig(source_review_root=review_root, output_root=output_root)
            )

            self.assertTrue(paths["summary"].exists())
            summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["review_scope"]["live_behavior_changed"])
            self.assertIn(summary["classification"], {"continue_research", "needs_detector_tightening", "reject", "eligible_for_second_fast_review"})

            robust = json.loads((output_root / "diagnostics" / "robust_r_metrics.json").read_text(encoding="utf-8"))
            self.assertGreater(robust["combined"]["tiny_stop_outlier_count"], 0)
            self.assertIn("promotion_metric_rule", robust["combined"])

            with (output_root / "diagnostics" / "original_vs_pullback_entry_cost_aware.csv").open("r", encoding="utf-8") as handle:
                cost_aware_rows = list(csv.DictReader(handle))
            self.assertEqual(3, len(cost_aware_rows))
            self.assertIn("tiny_stop_flag", cost_aware_rows[0])
            self.assertIn("refined_net_r_after_fees_slippage", cost_aware_rows[0])
            self.assertIn("cost_aware_pullback_candidate", cost_aware_rows[0])

            missed = json.loads((output_root / "diagnostics" / "missed_winner_penalty_report.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(missed["combined"]["missed_winner_count"], 1)

            personality = json.loads((output_root / "diagnostics" / "personality_net_usefulness_report.json").read_text(encoding="utf-8"))
            self.assertTrue(personality["soft_evidence_only"])


if __name__ == "__main__":
    unittest.main()
