import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.detector_tightening import (
    DetectorTighteningConfig,
    ThresholdCalibrationConfig,
    build_detector_tightening_thresholds,
    build_threshold_profiles,
    grade_tightened_candidate,
    write_threshold_calibration,
    write_detector_tightening,
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
        "entry_time": "2026-01-01T04:00:00",
        "pullback_type": "HEALTHY_CONTINUATION_PULLBACK",
        "pullback_quality_score": 0.88,
        "pullback_detected": True,
        "missed_due_to_waiting": False,
        "trade_pnl": 120.0,
        "trade_r_multiple": 2.4,
        "entry_score": 4.6,
        "original_entry_price": 100.0,
        "original_stop": 96.0,
        "refined_entry_price": 99.0,
        "refined_stop": 97.8,
        "target_price_same": 108.0,
        "original_risk_distance": 4.0,
        "refined_stop_distance": 1.2,
        "refined_stop_atr_fraction": 0.55,
        "refined_stop_cost_multiple": 3.4,
        "atr_value": 2.2,
        "recent_candle_noise": 1.7,
        "local_wick_noise": 0.8,
        "tick_size_estimate": 0.01,
        "tiny_stop_flag": False,
        "unrealistic_stop_flag": False,
        "noise_stop_flag": False,
        "cost_dominated_stop_flag": False,
        "original_gross_r": 2.0,
        "refined_gross_r": 6.8,
        "original_net_r_after_fees": 1.8,
        "refined_net_r_after_fees": 6.2,
        "original_net_r_after_fees_slippage": 1.7,
        "refined_net_r_after_fees_slippage": 5.8,
        "cost_drag_in_r": 0.16,
        "refined_improves_after_costs": True,
        "cost_destroys_refined_advantage": False,
        "minimum_required_move_after_costs": 0.7,
        "net_reward_to_cost_ratio": 5.6,
        "expected_cost_r": 0.14,
        "survives_low_cost": True,
        "survives_normal_cost": True,
        "survives_high_cost": True,
        "survives_stress_cost": False,
        "cost_aware_pullback_candidate": True,
        "reason_not_cost_aware": "",
        "tiny_stop_outlier": False,
        "improved_r_delta": 4.8,
        "pullback_depth_atr": 0.32,
    }
    row.update(overrides)
    return row


class DetectorTighteningTests(unittest.TestCase):
    def test_threshold_profiles_exist(self) -> None:
        profiles = build_threshold_profiles()
        self.assertEqual({"strict", "balanced", "relaxed", "cost_first", "noise_first"}, set(profiles))

    def test_detector_tightening_fields_exist(self) -> None:
        graded = grade_tightened_candidate(_base_row(), build_detector_tightening_thresholds())
        for field in (
            "pullback_depth",
            "expected_cost_R",
            "pullback_depth_impulse_fraction",
            "too_deep_flag",
            "structure_damage_flag",
            "confirmation_delay_candles",
            "confirmation_delay_minutes",
            "stale_confirmation_flag",
            "late_confirmation_flag",
            "survives_low_cost_prefilter",
            "survives_normal_cost_prefilter",
            "cost_prefilter_pass",
            "support_hold_flag",
            "breakout_retest_hold_flag",
            "ema_context_intact",
            "vwap_context_intact",
            "higher_low_intact",
            "pullback_volume_dryup",
            "confirmation_volume_return",
            "structure_validity_score",
            "tightened_pullback_grade",
            "tightened_pullback_score",
            "tightened_reject_reasons",
            "tightened_candidate_pass",
        ):
            self.assertIn(field, graded)

    def test_unrealistic_tiny_stops_are_rejected_or_graded_poorly(self) -> None:
        row = _base_row(
            refined_stop_distance=0.09,
            refined_stop_atr_fraction=0.04,
            refined_stop_cost_multiple=0.7,
            recent_candle_noise=0.4,
            local_wick_noise=0.2,
            tiny_stop_flag=True,
            unrealistic_stop_flag=True,
            noise_stop_flag=True,
            cost_dominated_stop_flag=True,
            expected_cost_r=1.1,
        )
        graded = grade_tightened_candidate(row, build_detector_tightening_thresholds())
        self.assertIn(graded["tightened_pullback_grade"], {"D", "REJECT"})
        self.assertFalse(graded["tightened_candidate_pass"])

    def test_too_deep_pullbacks_are_rejected_or_graded_poorly(self) -> None:
        row = _base_row(
            target_price_same=102.0,
            pullback_depth_atr=2.3,
        )
        graded = grade_tightened_candidate(row, build_detector_tightening_thresholds())
        self.assertTrue(graded["too_deep_flag"])
        self.assertFalse(graded["tightened_candidate_pass"])

    def test_stale_confirmations_are_rejected_or_graded_poorly(self) -> None:
        row = _base_row(liquidity_event_age_bars=11.0)
        graded = grade_tightened_candidate(row, build_detector_tightening_thresholds())
        self.assertTrue(graded["late_confirmation_flag"])
        self.assertFalse(graded["tightened_candidate_pass"])

    def test_cost_dominated_candidates_are_rejected_or_graded_poorly(self) -> None:
        row = _base_row(
            survives_normal_cost=False,
            refined_stop_cost_multiple=1.2,
            net_reward_to_cost_ratio=1.6,
            expected_cost_r=0.6,
            cost_dominated_stop_flag=True,
        )
        graded = grade_tightened_candidate(row, build_detector_tightening_thresholds())
        self.assertFalse(graded["cost_prefilter_pass"])
        self.assertFalse(graded["tightened_candidate_pass"])

    def test_clean_pullbacks_receive_better_grades(self) -> None:
        clean = grade_tightened_candidate(_base_row(), build_detector_tightening_thresholds())
        weak = grade_tightened_candidate(
            _base_row(
                refined_stop_distance=0.25,
                refined_stop_atr_fraction=0.12,
                refined_stop_cost_multiple=1.1,
                net_reward_to_cost_ratio=2.0,
                expected_cost_r=0.5,
                survives_normal_cost=False,
                tiny_stop_flag=True,
                unrealistic_stop_flag=True,
                noise_stop_flag=True,
            ),
            build_detector_tightening_thresholds(),
        )
        self.assertGreater(clean["tightened_pullback_score"], weak["tightened_pullback_score"])
        self.assertGreater(
            {"A": 5, "B": 4, "C": 3, "D": 2, "REJECT": 1}[clean["tightened_pullback_grade"]],
            {"A": 5, "B": 4, "C": 3, "D": 2, "REJECT": 1}[weak["tightened_pullback_grade"]],
        )

    def test_macd_and_bollinger_are_not_hard_gates(self) -> None:
        thresholds = build_detector_tightening_thresholds()
        with_flags = grade_tightened_candidate(
            _base_row(
                macd_confirmation_flag=False,
                macd_warning_flag=True,
                bb_compression=False,
                bb_expansion=False,
                bb_warning_flag=True,
            ),
            thresholds,
        )
        without_flags = grade_tightened_candidate(_base_row(), thresholds)
        self.assertEqual(with_flags["tightened_pullback_grade"], without_flags["tightened_pullback_grade"])
        self.assertEqual(with_flags["tightened_candidate_pass"], without_flags["tightened_candidate_pass"])

    def test_profile_strictness_is_ordered(self) -> None:
        profiles = build_threshold_profiles()
        strict_candidate = grade_tightened_candidate(_base_row(), profiles["strict"])
        balanced_candidate = grade_tightened_candidate(
            _base_row(
                trade_id="balanced",
                refined_stop_distance=0.7,
                refined_stop_atr_fraction=0.26,
                refined_stop_cost_multiple=2.1,
                recent_candle_noise=1.5,
                local_wick_noise=0.72,
                pullback_depth_atr=0.48,
                expected_cost_r=0.18,
                net_reward_to_cost_ratio=4.2,
            ),
            profiles["balanced"],
        )
        strict_rejected = grade_tightened_candidate(
            _base_row(
                trade_id="balanced",
                refined_stop_distance=0.7,
                refined_stop_atr_fraction=0.26,
                refined_stop_cost_multiple=2.1,
                recent_candle_noise=1.5,
                local_wick_noise=0.72,
                pullback_depth_atr=0.48,
                expected_cost_r=0.18,
                net_reward_to_cost_ratio=4.2,
            ),
            profiles["strict"],
        )
        relaxed_only = grade_tightened_candidate(
            _base_row(
                trade_id="relaxed",
                refined_stop_distance=0.5,
                refined_stop_atr_fraction=0.20,
                refined_stop_cost_multiple=1.6,
                recent_candle_noise=1.6,
                local_wick_noise=0.66,
                survives_normal_cost=False,
                expected_cost_r=0.2,
                net_reward_to_cost_ratio=4.4,
                pullback_depth_atr=0.58,
            ),
            profiles["relaxed"],
        )
        balanced_rejected = grade_tightened_candidate(
            _base_row(
                trade_id="relaxed",
                refined_stop_distance=0.5,
                refined_stop_atr_fraction=0.20,
                refined_stop_cost_multiple=1.6,
                recent_candle_noise=1.6,
                local_wick_noise=0.66,
                survives_normal_cost=False,
                expected_cost_r=0.2,
                net_reward_to_cost_ratio=4.4,
                pullback_depth_atr=0.58,
            ),
            profiles["balanced"],
        )
        self.assertTrue(strict_candidate["tightened_candidate_pass"])
        self.assertFalse(strict_rejected["tightened_candidate_pass"])
        self.assertTrue(balanced_candidate["tightened_candidate_pass"])
        self.assertFalse(balanced_rejected["tightened_candidate_pass"])
        self.assertTrue(relaxed_only["tightened_candidate_pass"])

    def test_write_detector_tightening_preserves_research_only_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_root = root / "evidence_review_001"
            refinement_root = root / "evidence_refinement_001"
            output_root = root / "detector_tightening_001"

            setup_rows = [
                {
                    "symbol": "BTCUSDT",
                    "timestamp": "2026-01-01T04:00:00",
                    "side": "long",
                    "pattern": "retest_after_breakout",
                    "level_distance_atr": 0.4,
                    "liquidity_event_age_bars": 2,
                    "macd_confirmation_flag": True,
                    "macd_warning_flag": False,
                    "bb_compression": True,
                    "bb_expansion": False,
                    "bb_warning_flag": False,
                }
            ]
            for window in ("smoke", "diagnostic_fast", "holdout_recent_preview"):
                _write_csv(review_root / window / "setup_log.csv", setup_rows)

            refinement_rows = [
                _base_row(),
                _base_row(
                    trade_id="trade-2",
                    tiny_stop_flag=True,
                    unrealistic_stop_flag=True,
                    noise_stop_flag=True,
                    cost_dominated_stop_flag=True,
                    refined_stop_distance=0.08,
                    refined_stop_atr_fraction=0.04,
                    refined_stop_cost_multiple=0.6,
                    recent_candle_noise=0.4,
                    local_wick_noise=0.2,
                    expected_cost_r=1.1,
                    cost_aware_pullback_candidate=False,
                    survives_normal_cost=False,
                    net_reward_to_cost_ratio=1.3,
                    improved_r_delta=12.0,
                ),
            ]
            _write_csv(refinement_root / "diagnostics" / "original_vs_pullback_entry_cost_aware.csv", refinement_rows)

            paths = write_detector_tightening(
                DetectorTighteningConfig(
                    review_root=review_root,
                    refinement_root=refinement_root,
                    output_root=output_root,
                )
            )

            self.assertTrue(paths["summary"].exists())
            summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["review_scope"]["live_behavior_changed"])
            self.assertFalse(summary["review_scope"]["paper_behavior_changed"])
            self.assertFalse(summary["review_scope"]["macd_bollinger_hard_gates_enabled"])
            self.assertFalse(summary["review_scope"]["pullback_buying_runtime_enabled"])
            self.assertIn(summary["classification"], {"reject", "continue_research", "needs_more_detector_tightening", "eligible_for_second_fast_review"})

            required = [
                output_root / "status.json",
                output_root / "detector_tightening_summary.json",
                output_root / "detector_tightening_report.md",
                output_root / "diagnostics" / "tightened_pullback_candidates.csv",
                output_root / "diagnostics" / "tightened_pullback_quality_report.json",
                output_root / "diagnostics" / "old_vs_tightened_detector_report.json",
                output_root / "diagnostics" / "tightened_cost_survival_report.json",
                output_root / "diagnostics" / "tightened_missed_winner_risk_report.json",
                output_root / "diagnostics" / "reject_reason_distribution.json",
                output_root / "reports" / "next_research_recommendation.json",
                output_root / "reports" / "next_research_recommendation.md",
            ]
            for artifact in required:
                self.assertTrue(artifact.exists(), str(artifact))

    def test_threshold_calibration_writes_profiles_and_stays_research_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_root = root / "evidence_review_001"
            refinement_root = root / "evidence_refinement_001"
            stage2_root = root / "detector_tightening_001"
            output_root = root / "detector_tightening_002"

            setup_rows = [
                {
                    "symbol": "BTCUSDT",
                    "timestamp": "2026-01-01T04:00:00",
                    "side": "long",
                    "pattern": "retest_after_breakout",
                    "level_distance_atr": 0.4,
                    "liquidity_event_age_bars": 2,
                    "macd_confirmation_flag": True,
                    "macd_warning_flag": False,
                    "bb_compression": True,
                    "bb_expansion": False,
                    "bb_warning_flag": False,
                }
            ]
            for window in ("smoke", "diagnostic_fast", "holdout_recent_preview"):
                _write_csv(review_root / window / "setup_log.csv", setup_rows)

            refinement_summary = {
                "robust_r_summary": {"combined": {"count": 3, "median_improved_r_delta": 3.5, "trimmed_mean_improved_r_delta": 3.6, "winsorized_mean_improved_r_delta": 3.7}},
                "tiny_stop_outlier_summary": {"combined": {"tiny_stop_flag_rate": 0.66, "unrealistic_stop_flag_rate": 0.66, "noise_stop_flag_rate": 0.66, "cost_dominated_stop_flag_rate": 0.66, "median_refined_stop_atr_fraction": 0.2, "median_refined_stop_cost_multiple": 0.9}},
                "net_r_after_costs_summary": {"combined_cost_aware_candidate_rate": 0.05, "combined_normal_survival_rate": 0.7},
                "missed_winner_penalty_summary": {"combined": {"missed_winner_rate": 0.2, "miss_reason_distribution": {"missed_due_to_late_confirmation": 1}}},
            }
            (refinement_root / "refinement_summary.json").parent.mkdir(parents=True, exist_ok=True)
            (refinement_root / "refinement_summary.json").write_text(json.dumps(refinement_summary), encoding="utf-8")

            refinement_rows = [
                _base_row(),
                _base_row(
                    trade_id="balanced",
                    refined_stop_distance=0.7,
                    refined_stop_atr_fraction=0.26,
                    refined_stop_cost_multiple=2.1,
                    recent_candle_noise=1.5,
                    local_wick_noise=0.72,
                    pullback_depth_atr=0.48,
                ),
                _base_row(
                    trade_id="relaxed",
                    refined_stop_distance=0.5,
                    refined_stop_atr_fraction=0.20,
                    refined_stop_cost_multiple=1.6,
                    recent_candle_noise=1.6,
                    local_wick_noise=0.66,
                    survives_normal_cost=False,
                    expected_cost_r=0.2,
                    net_reward_to_cost_ratio=4.4,
                    pullback_depth_atr=0.58,
                ),
            ]
            _write_csv(refinement_root / "diagnostics" / "original_vs_pullback_entry_cost_aware.csv", refinement_rows)

            stage2_summary = {
                "old_vs_tightened_detector": {
                    "tightened": {
                        "candidate_count": 1,
                        "tiny_stop_rate": 0.0,
                        "unrealistic_stop_rate": 0.0,
                        "cost_dominated_stop_rate": 0.0,
                        "normal_cost_survival_rate": 1.0,
                        "cost_aware_candidate_rate": 1.0,
                        "median_improved_r_delta": 4.8,
                        "missed_winner_risk_rate": 0.0,
                    }
                }
            }
            stage2_root.mkdir(parents=True, exist_ok=True)
            (stage2_root / "detector_tightening_summary.json").write_text(json.dumps(stage2_summary), encoding="utf-8")

            paths = write_threshold_calibration(
                ThresholdCalibrationConfig(
                    review_root=review_root,
                    refinement_root=refinement_root,
                    stage2_root=stage2_root,
                    output_root=output_root,
                )
            )

            self.assertTrue(paths["summary"].exists())
            summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
            self.assertIn(summary["recommended_profile"], {"balanced", "relaxed", "cost_first", "noise_first", "strict"})
            self.assertFalse(summary["review_scope"]["live_behavior_changed"])
            self.assertFalse(summary["review_scope"]["paper_behavior_changed"])
            self.assertFalse(summary["review_scope"]["replay_started"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["soft_evidence_only"]["macd_bollinger"] is False)
            profiles = summary["profiles"]
            self.assertLessEqual(profiles["strict"]["candidate_count"], profiles["balanced"]["candidate_count"])
            self.assertLessEqual(profiles["balanced"]["candidate_count"], profiles["relaxed"]["candidate_count"])

            required = [
                output_root / "status.json",
                output_root / "threshold_calibration_summary.json",
                output_root / "threshold_calibration_report.md",
                output_root / "diagnostics" / "profile_comparison.json",
                output_root / "diagnostics" / "profile_comparison.csv",
                output_root / "diagnostics" / "calibrated_pullback_candidates.csv",
                output_root / "diagnostics" / "calibrated_reject_reason_distribution.json",
                output_root / "diagnostics" / "stage1_vs_stage2_vs_stage3_comparison.json",
                output_root / "reports" / "next_research_recommendation.json",
                output_root / "reports" / "next_research_recommendation.md",
            ]
            for artifact in required:
                self.assertTrue(artifact.exists(), str(artifact))


if __name__ == "__main__":
    unittest.main()
