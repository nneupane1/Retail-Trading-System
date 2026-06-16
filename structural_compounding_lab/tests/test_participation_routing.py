import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.participation_routing import (
    ParticipationRoutingConfig,
    route_participation_candidate,
    write_participation_routing,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "BTCUSDT",
        "entry_time": "2026-06-01T04:00:00",
        "side": "long",
        "archetype": "LIQUIDITY_SWEEP_RECLAIM",
        "personality_label": "PULLBACK_CONTINUATION",
        "structure_validity_score": 0.72,
        "archetype_score": 74.0,
        "archetype_grade": "B",
        "cost_survival_low": True,
        "cost_survival_normal": True,
        "cost_survival_high": True,
        "tiny_stop_flag": False,
        "unrealistic_stop_flag": False,
        "cost_dominated_flag": False,
        "missed_winner_risk_flag": False,
        "macd_warning_flag": False,
        "bb_warning_flag": False,
        "macd_confirmation_flag": True,
        "bb_compression": False,
        "bb_expansion": False,
        "runner_label": "normal_swing",
        "runner_eligible_candidate": True,
        "add_on_research_candidate": True,
        "stop_atr_fraction": 0.42,
        "stop_cost_multiple": 2.8,
        "confirmation_delay": 1.0,
        "expected_cost_r": 0.18,
        "scope": "development",
    }
    row.update(overrides)
    return row


class ParticipationRoutingTests(unittest.TestCase):
    def test_all_modes_can_be_produced(self) -> None:
        scenarios = {
            "FULL_SIZE_CANDIDATE": _base_row(),
            "REDUCED_SIZE_CANDIDATE": _base_row(cost_dominated_flag=False, stop_cost_multiple=1.8, archetype_grade="C"),
            "PROBE_CANDIDATE": _base_row(cost_survival_normal=False, cost_survival_low=True, structure_validity_score=0.56, archetype_grade="REJECT", cost_dominated_flag=True, stop_cost_multiple=1.2),
            "WAIT_FOR_CONFIRMATION": _base_row(cost_survival_normal=False, cost_survival_low=False, structure_validity_score=0.45, confirmation_delay=8.0),
            "NO_ADD_ON_MANAGEMENT": _base_row(personality_label="CHOPPY_LOW_TRUST", runner_label="tactical_scalp", add_on_research_candidate=False, stop_cost_multiple=2.5),
            "DE_RISK_FAST_MANAGEMENT": _base_row(personality_label="EXHAUSTION_RISK"),
            "REJECT_INVALID": _base_row(archetype="STRUCTURE_BREAK_DIP", structure_validity_score=0.10),
        }
        for expected_mode, row in scenarios.items():
            routed = route_participation_candidate(row)
            self.assertEqual(expected_mode, routed["participation_mode"])

    def test_structure_break_dip_routes_to_reject_invalid(self) -> None:
        routed = route_participation_candidate(_base_row(archetype="STRUCTURE_BREAK_DIP", structure_validity_score=0.15))
        self.assertEqual("REJECT_INVALID", routed["participation_mode"])

    def test_exhaustion_risk_is_not_full_size_by_default(self) -> None:
        routed = route_participation_candidate(_base_row(personality_label="EXHAUSTION_RISK"))
        self.assertNotEqual("FULL_SIZE_CANDIDATE", routed["participation_mode"])

    def test_liquidity_sweep_can_route_across_confidence_buckets(self) -> None:
        full = route_participation_candidate(_base_row())
        reduced = route_participation_candidate(_base_row(cost_dominated_flag=False, stop_cost_multiple=1.7, archetype_grade="C"))
        probe = route_participation_candidate(_base_row(cost_survival_normal=False, cost_survival_low=True, structure_validity_score=0.56, archetype_grade="REJECT", cost_dominated_flag=True, stop_cost_multiple=1.2))
        self.assertEqual("FULL_SIZE_CANDIDATE", full["participation_mode"])
        self.assertEqual("REDUCED_SIZE_CANDIDATE", reduced["participation_mode"])
        self.assertEqual("PROBE_CANDIDATE", probe["participation_mode"])

    def test_cost_dominated_setup_cannot_route_to_full_size(self) -> None:
        routed = route_participation_candidate(_base_row(cost_dominated_flag=True, stop_cost_multiple=1.6))
        self.assertNotEqual("FULL_SIZE_CANDIDATE", routed["participation_mode"])

    def test_macd_bollinger_do_not_hard_block_valid_setup(self) -> None:
        routed = route_participation_candidate(
            _base_row(
                macd_confirmation_flag=False,
                macd_warning_flag=True,
                bb_compression=True,
                bb_expansion=False,
                bb_warning_flag=True,
            )
        )
        self.assertNotEqual("REJECT_INVALID", routed["participation_mode"])
        self.assertTrue(routed["soft_evidence_only"])

    def test_writer_outputs_reports_and_keeps_research_only_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archetype_root = root / "pullback_archetype_redesign_001"
            output_root = root / "participation_routing_001"
            rows = [
                _base_row(),
                _base_row(entry_time="2026-06-01T05:00:00", cost_dominated_flag=True, stop_cost_multiple=1.8, archetype_grade="C"),
                _base_row(entry_time="2026-06-01T06:00:00", cost_survival_normal=False, cost_survival_low=True, structure_validity_score=0.56, archetype_grade="REJECT"),
                _base_row(entry_time="2026-06-01T07:00:00", personality_label="EXHAUSTION_RISK"),
                _base_row(entry_time="2026-06-01T08:00:00", archetype="STRUCTURE_BREAK_DIP", structure_validity_score=0.1),
            ]
            _write_csv(archetype_root / "diagnostics" / "archetype_candidates.csv", rows)

            for folder in [
                root / "evidence_review_001",
                root / "evidence_refinement_001",
                root / "detector_tightening_001",
                root / "detector_tightening_002",
            ]:
                folder.mkdir(parents=True, exist_ok=True)

            paths = write_participation_routing(
                ParticipationRoutingConfig(
                    evidence_review_root=root / "evidence_review_001",
                    evidence_refinement_root=root / "evidence_refinement_001",
                    detector_tightening_stage1_root=root / "detector_tightening_001",
                    detector_tightening_stage2_root=root / "detector_tightening_002",
                    archetype_root=archetype_root,
                    output_root=output_root,
                )
            )

            self.assertTrue(paths["summary"].exists())
            summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
            self.assertIn(summary["classification"], {"reject", "continue_research", "needs_routing_refinement", "eligible_for_second_fast_review"})
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
                output_root / "participation_routing_summary.json",
                output_root / "participation_routing_report.md",
                output_root / "diagnostics" / "routed_candidates.csv",
                output_root / "diagnostics" / "participation_mode_distribution.json",
                output_root / "diagnostics" / "archetype_to_participation_report.json",
                output_root / "diagnostics" / "personality_to_participation_report.json",
                output_root / "diagnostics" / "probe_candidate_report.json",
                output_root / "diagnostics" / "de_risk_candidate_report.json",
                output_root / "diagnostics" / "reject_invalid_report.json",
                output_root / "diagnostics" / "missed_winner_participation_estimate.json",
                output_root / "reports" / "next_research_recommendation.json",
                output_root / "reports" / "next_research_recommendation.md",
            ]
            for artifact in required:
                self.assertTrue(artifact.exists(), str(artifact))


if __name__ == "__main__":
    unittest.main()
