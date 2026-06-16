import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.pullback_archetype_redesign import (
    PullbackArchetypeRedesignConfig,
    classify_pullback_archetype,
    write_pullback_archetype_redesign,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "window": "smoke",
        "trade_id": "trade-1",
        "symbol": "BTCUSDT",
        "side": "long",
        "entry_time": "2026-06-01T04:00:00",
        "personality_label": "PULLBACK_CONTINUATION",
        "runner_label": "normal_swing",
        "moonshot_state": "normal",
        "pullback_type": "HEALTHY_CONTINUATION_PULLBACK",
        "pullback_quality_score": 0.72,
        "pullback_detected": True,
        "missed_due_to_waiting": False,
        "trade_pnl": 120.0,
        "trade_r_multiple": 2.4,
        "entry_score": 4.3,
        "original_entry_price": 100.0,
        "original_stop": 96.0,
        "refined_entry_price": 99.4,
        "refined_stop": 97.9,
        "target_price_same": 107.0,
        "original_risk_distance": 4.0,
        "refined_stop_distance": 1.5,
        "refined_stop_atr_fraction": 0.55,
        "refined_stop_cost_multiple": 3.2,
        "atr_value": 2.7,
        "recent_candle_noise": 1.2,
        "local_wick_noise": 0.7,
        "tick_size_estimate": 0.1,
        "tiny_stop_flag": False,
        "unrealistic_stop_flag": False,
        "noise_stop_flag": False,
        "cost_dominated_stop_flag": False,
        "original_gross_r": 1.8,
        "refined_gross_r": 4.9,
        "original_net_r_after_fees": 1.6,
        "refined_net_r_after_fees": 4.4,
        "original_net_r_after_fees_slippage": 1.4,
        "refined_net_r_after_fees_slippage": 4.1,
        "cost_drag_in_r": 0.8,
        "refined_improves_after_costs": True,
        "cost_destroys_refined_advantage": False,
        "minimum_required_move_after_costs": 0.3,
        "net_reward_to_cost_ratio": 4.5,
        "expected_cost_r": 0.18,
        "survives_low_cost": True,
        "survives_normal_cost": True,
        "survives_high_cost": True,
        "survives_stress_cost": False,
        "cost_aware_pullback_candidate": True,
        "reason_not_cost_aware": "",
        "tiny_stop_outlier": False,
        "improved_r_delta": 3.1,
        "pullback_depth_atr": 0.58,
        "pattern": "sweep_low",
        "liquidity_event_type": "sweep_low",
        "liquidity_event_age_bars": 2.0,
        "level_distance_atr": 0.75,
        "htf_aligned": True,
        "execution_timeframe": "1h",
        "macd_confirmation_flag": True,
        "macd_warning_flag": False,
        "bb_compression": False,
        "bb_expansion": False,
        "bb_warning_flag": False,
        "micro_pullback_detected": False,
        "runner_eligible_candidate": True,
        "add_on_research_candidate": False,
        "structure_validity_score": 0.75,
    }
    row.update(overrides)
    return row


def _setup_from_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "symbol": row["symbol"],
        "timestamp": row["entry_time"],
        "side": row["side"],
        "pattern": row["pattern"],
        "pullback_type": row["pullback_type"],
        "liquidity_event_type": row["liquidity_event_type"],
        "liquidity_event_age_bars": row["liquidity_event_age_bars"],
        "level_distance_atr": row["level_distance_atr"],
        "htf_aligned": row["htf_aligned"],
        "execution_timeframe": row["execution_timeframe"],
        "personality_label": row["personality_label"],
        "macd_confirmation_flag": row["macd_confirmation_flag"],
        "macd_warning_flag": row["macd_warning_flag"],
        "bb_compression": row["bb_compression"],
        "bb_expansion": row["bb_expansion"],
        "bb_warning_flag": row["bb_warning_flag"],
        "micro_pullback_detected": row["micro_pullback_detected"],
        "runner_eligible_candidate": row["runner_eligible_candidate"],
        "add_on_research_candidate": row["add_on_research_candidate"],
    }


class PullbackArchetypeRedesignTests(unittest.TestCase):
    def test_each_archetype_can_be_classified(self) -> None:
        scenarios = {
            "MICRO_PULLBACK_MOMENTUM": _base_row(
                pullback_type="MICRO_PULLBACK_MOMENTUM",
                personality_label="MOMENTUM_BURST",
                liquidity_event_type="",
                pattern="",
                pullback_depth_atr=0.22,
                liquidity_event_age_bars=1.0,
            ),
            "BREAKOUT_RETEST_PULLBACK": _base_row(
                pullback_type="BREAKOUT_RETEST_PULLBACK",
                pattern="retest_after_breakout",
                liquidity_event_type="retest_after_breakout",
                level_distance_atr=0.30,
            ),
            "EMA_VWAP_RECLAIM_PULLBACK": _base_row(
                pullback_type="HEALTHY_CONTINUATION_PULLBACK",
                liquidity_event_type="",
                pattern="",
                level_distance_atr=0.25,
                pullback_depth_atr=0.65,
            ),
            "HEALTHY_CONTINUATION_PULLBACK": _base_row(
                liquidity_event_type="",
                pattern="",
                level_distance_atr=0.90,
                pullback_depth_atr=0.80,
            ),
            "LIQUIDITY_SWEEP_RECLAIM": _base_row(
                liquidity_event_type="sweep_low",
                pattern="sweep_low",
                pullback_depth_atr=0.55,
                liquidity_event_age_bars=1.0,
            ),
            "INSIDE_BAR_CONTINUATION": _base_row(
                liquidity_event_type="",
                pattern="",
                personality_label="COMPRESSION_BREAKOUT",
                bb_compression=True,
                pullback_depth_atr=0.35,
            ),
            "FAILED_BREAKDOWN_REVERSAL": _base_row(
                liquidity_event_type="retest_after_breakdown",
                pattern="retest_after_breakdown",
                pullback_depth_atr=0.90,
            ),
            "STRUCTURE_BREAK_DIP": _base_row(
                pullback_type="STRUCTURE_BREAK_DIP",
                pattern="structure_breakdown",
                liquidity_event_type="",
                pullback_quality_score=0.20,
                structure_validity_score=0.10,
            ),
        }

        for expected, row in scenarios.items():
            classified = classify_pullback_archetype(row)
            self.assertEqual(expected, classified["archetype"])

    def test_required_fields_exist(self) -> None:
        classified = classify_pullback_archetype(_base_row())
        for field in (
            "archetype",
            "archetype_detected",
            "archetype_score",
            "archetype_grade",
            "entry_candidate_time",
            "entry_candidate_price",
            "stop_price",
            "stop_distance",
            "stop_atr_fraction",
            "stop_cost_multiple",
            "confirmation_delay",
            "pullback_depth",
            "structure_validity_score",
            "cost_survival_low",
            "cost_survival_normal",
            "cost_survival_high",
            "tiny_stop_flag",
            "unrealistic_stop_flag",
            "cost_dominated_flag",
            "missed_winner_risk_flag",
            "reject_reasons",
            "explanation",
        ):
            self.assertIn(field, classified)

    def test_structure_break_dip_is_rejected(self) -> None:
        classified = classify_pullback_archetype(
            _base_row(
                pullback_type="STRUCTURE_BREAK_DIP",
                pattern="structure_breakdown",
                structure_validity_score=0.10,
                pullback_quality_score=0.15,
            )
        )
        self.assertEqual("STRUCTURE_BREAK_DIP", classified["archetype"])
        self.assertEqual("REJECT", classified["archetype_grade"])
        self.assertFalse(classified["archetype_pass"])

    def test_tiny_and_cost_dominated_stops_are_flagged(self) -> None:
        classified = classify_pullback_archetype(
            _base_row(
                refined_stop_atr_fraction=0.08,
                refined_stop_cost_multiple=0.8,
                tiny_stop_flag=True,
                unrealistic_stop_flag=True,
                cost_dominated_stop_flag=True,
                survives_normal_cost=False,
            )
        )
        self.assertIn("tiny_stop_flag", classified["reject_reasons"])
        self.assertIn("cost_dominated_flag", classified["reject_reasons"])
        self.assertFalse(classified["archetype_pass"])

    def test_macd_and_bollinger_remain_soft_evidence_only(self) -> None:
        with_flags = classify_pullback_archetype(
            _base_row(
                macd_confirmation_flag=False,
                macd_warning_flag=True,
                bb_compression=True,
                bb_warning_flag=True,
                liquidity_event_type="",
                pattern="",
            )
        )
        without_flags = classify_pullback_archetype(
            _base_row(
                macd_confirmation_flag=False,
                macd_warning_flag=False,
                bb_compression=False,
                bb_warning_flag=False,
                liquidity_event_type="",
                pattern="",
            )
        )
        self.assertTrue(with_flags["soft_evidence_only"])
        self.assertTrue(without_flags["soft_evidence_only"])
        self.assertNotEqual("REJECT", with_flags["archetype_grade"])
        self.assertEqual(with_flags["cost_survival_normal"], without_flags["cost_survival_normal"])

    def test_writer_outputs_artifacts_and_keeps_research_only_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_root = root / "evidence_review_001"
            refinement_root = root / "evidence_refinement_001"
            output_root = root / "pullback_archetype_redesign_001"

            rows = [
                _base_row(window="smoke", trade_id="micro", entry_time="2026-06-01T01:00:00", pullback_type="MICRO_PULLBACK_MOMENTUM", personality_label="MOMENTUM_BURST", pattern="", liquidity_event_type="", pullback_depth_atr=0.22, liquidity_event_age_bars=1.0),
                _base_row(window="smoke", trade_id="breakout", entry_time="2026-06-01T02:00:00", pullback_type="BREAKOUT_RETEST_PULLBACK", pattern="retest_after_breakout", liquidity_event_type="retest_after_breakout", level_distance_atr=0.30),
                _base_row(window="diagnostic_fast", trade_id="ema", entry_time="2026-06-02T01:00:00", liquidity_event_type="", pattern="", level_distance_atr=0.24, pullback_depth_atr=0.60),
                _base_row(window="diagnostic_fast", trade_id="healthy", entry_time="2026-06-02T02:00:00", liquidity_event_type="", pattern="", level_distance_atr=0.92, pullback_depth_atr=0.85),
                _base_row(window="diagnostic_fast", trade_id="liquidity", entry_time="2026-06-02T03:00:00", liquidity_event_type="sweep_low", pattern="sweep_low", liquidity_event_age_bars=1.0),
                _base_row(window="holdout_recent_preview", trade_id="inside", entry_time="2026-06-03T01:00:00", personality_label="COMPRESSION_BREAKOUT", liquidity_event_type="", pattern="", bb_compression=True, pullback_depth_atr=0.35),
                _base_row(window="holdout_recent_preview", trade_id="failed_breakdown", entry_time="2026-06-03T02:00:00", pattern="retest_after_breakdown", liquidity_event_type="retest_after_breakdown", pullback_depth_atr=0.88),
                _base_row(window="holdout_recent_preview", trade_id="reject", entry_time="2026-06-03T03:00:00", pullback_type="STRUCTURE_BREAK_DIP", pattern="structure_breakdown", liquidity_event_type="", pullback_quality_score=0.2, structure_validity_score=0.1),
            ]

            _write_csv(refinement_root / "diagnostics" / "original_vs_pullback_entry_cost_aware.csv", rows)

            for window in ("smoke", "diagnostic_fast", "holdout_recent_preview"):
                window_rows = [_setup_from_row(row) for row in rows if row["window"] == window]
                _write_csv(review_root / window / "setup_log.csv", window_rows)

            paths = write_pullback_archetype_redesign(
                PullbackArchetypeRedesignConfig(
                    review_root=review_root,
                    refinement_root=refinement_root,
                    output_root=output_root,
                )
            )

            self.assertTrue(paths["summary"].exists())
            summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
            self.assertIn(summary["classification"], {"reject", "continue_research", "needs_archetype_refinement", "eligible_for_second_fast_review"})
            self.assertFalse(summary["full_history_started"])
            self.assertFalse(summary["stress_windows_started"])
            self.assertFalse(summary["monte_carlo_started"])
            self.assertFalse(summary["live_behavior_changed"])
            self.assertFalse(summary["paper_behavior_changed"])
            self.assertFalse(summary["config_settings_changed"])
            self.assertFalse(summary["macd_bollinger_hard_gates_enabled"])
            self.assertFalse(summary["pullback_buying_runtime_enabled"])
            self.assertFalse(summary["real_money_allowed"])

            required = [
                output_root / "status.json",
                output_root / "archetype_redesign_summary.json",
                output_root / "archetype_redesign_report.md",
                output_root / "diagnostics" / "archetype_candidates.csv",
                output_root / "diagnostics" / "archetype_profile_comparison.json",
                output_root / "diagnostics" / "archetype_profile_comparison.csv",
                output_root / "diagnostics" / "archetype_reject_reason_distribution.json",
                output_root / "diagnostics" / "archetype_cost_survival_report.json",
                output_root / "diagnostics" / "archetype_missed_winner_risk_report.json",
                output_root / "diagnostics" / "archetype_personality_report.json",
                output_root / "reports" / "next_research_recommendation.json",
                output_root / "reports" / "next_research_recommendation.md",
            ]
            for artifact in required:
                self.assertTrue(artifact.exists(), str(artifact))


if __name__ == "__main__":
    unittest.main()
