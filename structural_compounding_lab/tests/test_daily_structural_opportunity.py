import csv
import json
import tempfile
import unittest
from pathlib import Path

from structural_compounding_lab.diagnostics.daily_structural_opportunity import (
    DailyStructuralOpportunityConfig,
    write_daily_structural_opportunity,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _history_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for date_prefix, base_price in (
        ("2026-06-01", 100.0),
        ("2026-06-02", 104.0),
        ("2026-06-03", 107.0),
    ):
        for hour in range(4):
            price = base_price + hour * 0.8
            rows.append(
                {
                    "timestamp": f"{date_prefix} {hour:02d}:00:00",
                    "open": price,
                    "high": price + 1.2,
                    "low": price - 0.8,
                    "close": price + 0.5,
                    "volume": 1200 + hour * 100,
                }
            )
    return rows


def _setup_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "BTCUSDT",
        "timestamp": "2026-06-01T02:00:00",
        "side": "long",
        "setup_type": "structural_compounding",
        "setup_class": "A",
        "classification": "A",
        "structure_score": 1.18,
        "liquidity_score": 0.82,
        "ema_score": 0.78,
        "htf_confirmation_score": 0.30,
        "volatility_score": 0.45,
        "risk_reward_score": 1.0,
        "score": 4.10,
        "total_score": 4.10,
        "accepted": True,
        "decision": "opened",
        "entry_reason": "A setup: sweep_low near support with broad structural room.",
        "explanation": "A setup: sweep_low near support with broad structural room.",
        "pattern": "sweep_low",
        "htf_aligned": True,
        "risk_multiplier": 1.15,
        "convexity_label": "strong_convexity",
        "cooldown_fast_clear_eligible": False,
        "execution_timeframe": "1h",
    }
    row.update(overrides)
    return row


def _routed_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "BTCUSDT",
        "time": "2026-06-01T02:00:00",
        "side": "long",
        "archetype": "LIQUIDITY_SWEEP_RECLAIM",
        "personality": "PULLBACK_CONTINUATION",
        "participation_mode": "FULL_SIZE_CANDIDATE",
        "suggested_research_risk_fraction": 1.0,
        "entry_candidate_price": 102.8,
        "stop_price": 101.8,
        "stop_atr_fraction": 0.75,
        "stop_cost_multiple": 3.4,
        "atr_value": 1.8,
        "structure_validity_score": 0.88,
        "pullback_quality_score": 0.72,
        "cost_survival_low": True,
        "cost_survival_normal": True,
        "cost_survival_high": True,
        "survives_stress_cost": True,
        "cost_dominated_flag": False,
        "tiny_stop_flag": False,
        "unrealistic_stop_flag": False,
        "noise_stop_flag": False,
        "runner_label": "normal_swing",
        "runner_eligible_candidate": True,
        "add_on_research_candidate": True,
        "trade_r_multiple": 4.6,
        "refined_gross_r": 5.4,
        "refined_net_r_after_fees": 4.8,
        "refined_net_r_after_fees_slippage": 4.5,
        "macd_warning_flag": False,
        "bb_warning_flag": False,
        "bb_compression": False,
        "bb_expansion": False,
        "exhaustion_warning": False,
        "choppy_warning": False,
        "expected_cost_r": 0.18,
        "scope": "development",
    }
    row.update(overrides)
    return row


class DailyStructuralOpportunityTests(unittest.TestCase):
    def test_writer_outputs_refined_daily_summary_with_actual_trade_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            (package_root / "config").mkdir(parents=True, exist_ok=True)
            output_root.mkdir(parents=True, exist_ok=True)

            history_path = root / "btc_1m.csv"
            _write_csv(history_path, _history_rows())

            (package_root / "config" / "structural_compounding_settings.json").write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "execution_timeframe": "1h",
                        "data": {"default_interval": "1m"},
                    }
                ),
                encoding="utf-8",
            )
            (output_root / "daily_structural_opportunity_001").mkdir(parents=True, exist_ok=True)
            (output_root / "daily_structural_opportunity_001" / "daily_structural_opportunity_summary.json").write_text(
                json.dumps({"missed_high_R_opportunity_count": 99, "too_tight_day_count": 20}),
                encoding="utf-8",
            )
            _write_csv(
                output_root / "setup_log.csv",
                [
                    _setup_row(),
                    _setup_row(
                        timestamp="2026-06-02T02:00:00",
                        accepted=False,
                        decision="wait",
                        structure_score=1.20,
                        liquidity_score=0.82,
                        explanation="High-quality day that waited for confirmation.",
                    ),
                ],
            )
            _write_csv(
                output_root / "level_log.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "price": 102.0,
                        "type": "support",
                        "timeframe_source": "1h",
                        "touch_count": 3,
                        "recency": 0.0,
                        "strength": 2.1,
                        "first_seen": "2026-05-31T00:00:00",
                        "last_touched": "2026-06-01T01:00:00",
                        "timestamp": "2026-06-01T01:00:00",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "price": 108.9,
                        "type": "resistance",
                        "timeframe_source": "1h",
                        "touch_count": 4,
                        "recency": 0.0,
                        "strength": 2.2,
                        "first_seen": "2026-05-31T00:00:00",
                        "last_touched": "2026-06-02T01:00:00",
                        "timestamp": "2026-06-02T01:00:00",
                    },
                ],
            )
            _write_csv(
                output_root / "liquidity_events.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-06-01T01:00:00",
                        "price": 102.1,
                        "type": "sweep_low",
                        "side_implication": "bullish_if_swept",
                        "source_timeframe": "1h",
                        "confidence": 0.8,
                    },
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-06-02T02:00:00",
                        "price": 106.4,
                        "type": "retest_after_breakout",
                        "side_implication": "long",
                        "source_timeframe": "1h",
                        "confidence": 0.82,
                    },
                ],
            )
            _write_csv(
                output_root / "trades.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "entry_time": "2026-06-01T02:00:00",
                        "exit_time": "2026-06-01T03:00:00",
                        "side": "long",
                        "pnl": 120.0,
                        "r_multiple": 4.2,
                    }
                ],
            )
            _write_csv(
                output_root / "cooldown_log.csv",
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-06-03T01:00:00",
                        "reason": "danger_sniffed",
                        "cooldown_bars": 4,
                        "minimum_bars": 2,
                        "event_type": "cooldown_start",
                    }
                ],
            )
            _write_csv(
                output_root / "pyramiding_log.csv",
                [
                    {
                        "event_type": "profit_lock",
                        "reason": "danger_sniffed",
                        "locked_profit": 300.0,
                        "active_trading_capital": 20000.0,
                        "cycle_id": "cycle-1",
                        "timestamp": "2026-06-01T03:00:00",
                        "symbol": "BTCUSDT",
                    }
                ],
            )
            _write_csv(
                output_root / "equity.csv",
                [
                    {"timestamp": "2026-06-01T00:00:00", "equity": 20000.0, "active_capital": 20000.0, "locked_profit": 0.0},
                    {"timestamp": "2026-06-01T03:00:00", "equity": 20120.0, "active_capital": 20000.0, "locked_profit": 300.0},
                ],
            )
            (output_root / "profit_vault.json").write_text(
                json.dumps(
                    {
                        "base_capital": 20000.0,
                        "active_trading_capital": 20000.0,
                        "locked_profit": 300.0,
                        "floating_profit": 120.0,
                    }
                ),
                encoding="utf-8",
            )
            (output_root / "participation_routing_001" / "participation_routing_summary.json").parent.mkdir(parents=True, exist_ok=True)
            (output_root / "participation_routing_001" / "participation_routing_summary.json").write_text(json.dumps({}), encoding="utf-8")
            _write_csv(
                output_root / "participation_routing_001" / "diagnostics" / "routed_candidates.csv",
                [
                    _routed_row(),
                    _routed_row(
                        time="2026-06-02T02:00:00",
                        participation_mode="WAIT_FOR_CONFIRMATION",
                        structure_validity_score=0.90,
                        stop_atr_fraction=0.85,
                        stop_cost_multiple=3.5,
                        refined_net_r_after_fees_slippage=6.1,
                        pullback_quality_score=0.76,
                    ),
                ],
            )
            (output_root / "project_direction_review_001" / "project_direction_summary.json").parent.mkdir(parents=True, exist_ok=True)
            (output_root / "project_direction_review_001" / "project_direction_summary.json").write_text(
                json.dumps({"current_best_insight": "Daily opportunity should lead pullback logic."}),
                encoding="utf-8",
            )

            result = write_daily_structural_opportunity(
                DailyStructuralOpportunityConfig(
                    package_root=package_root,
                    output_root=output_root / "daily_opportunity_definition_refinement_001",
                    source_history_path=history_path,
                )
            )

            self.assertTrue(result["summary"].exists())
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual(3, summary["days_analyzed"])
            self.assertEqual(1, summary["actual_trade_frequency"]["actual_trade_count"])
            self.assertEqual(1, summary["actual_trade_frequency"]["actual_trade_days"])
            self.assertEqual(1, summary["missed_high_R_opportunity_count"])
            self.assertEqual(0, summary["high_R_probe_day_count"])
            self.assertEqual(99, summary["old_daily_opportunity_baseline"]["missed_high_R_opportunity_count"])
            self.assertFalse(summary["strategy_behavior_changed"])
            self.assertFalse(summary["paper_behavior_changed"])
            self.assertFalse(summary["real_money_allowed"])

            with (output_root / "daily_opportunity_definition_refinement_001" / "diagnostics" / "top_opportunity_by_day.csv").open(
                "r", encoding="utf-8"
            ) as handle:
                top_rows = list(csv.DictReader(handle))
            day1 = next(row for row in top_rows if row["date"] == "2026-06-01")
            day2 = next(row for row in top_rows if row["date"] == "2026-06-02")
            self.assertEqual("1", day1["actual_trade_count"])
            self.assertEqual("WAIT_FOR_CONFIRMATION", day2["participation_mode"])
            self.assertEqual("True", day2["missed_high_R_opportunity_flag"])
            self.assertEqual("TRUE_MISSED_HIGH_R_OPPORTUNITY", day2["missed_high_r_audit_category"])

    def test_probe_and_noise_days_do_not_count_as_true_missed_high_r(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            (package_root / "config").mkdir(parents=True, exist_ok=True)
            output_root.mkdir(parents=True, exist_ok=True)
            history_path = root / "btc_1m.csv"
            _write_csv(history_path, _history_rows())

            (package_root / "config" / "structural_compounding_settings.json").write_text(
                json.dumps({"symbol": "BTCUSDT", "execution_timeframe": "1h", "data": {"default_interval": "1m"}}),
                encoding="utf-8",
            )
            (output_root / "daily_structural_opportunity_001").mkdir(parents=True, exist_ok=True)
            (output_root / "daily_structural_opportunity_001" / "daily_structural_opportunity_summary.json").write_text(
                json.dumps({"missed_high_R_opportunity_count": 8, "too_tight_day_count": 4}),
                encoding="utf-8",
            )
            _write_csv(
                output_root / "setup_log.csv",
                [
                    _setup_row(timestamp="2026-06-02T02:00:00", accepted=False, decision="wait"),
                    _setup_row(timestamp="2026-06-03T02:00:00", accepted=False, decision="reject"),
                ],
            )
            _write_csv(output_root / "level_log.csv", [])
            _write_csv(output_root / "liquidity_events.csv", [])
            _write_csv(output_root / "trades.csv", [])
            _write_csv(output_root / "cooldown_log.csv", [])
            _write_csv(output_root / "pyramiding_log.csv", [])
            _write_csv(output_root / "equity.csv", [])
            (output_root / "profit_vault.json").write_text("{}", encoding="utf-8")
            (output_root / "participation_routing_001" / "participation_routing_summary.json").parent.mkdir(parents=True, exist_ok=True)
            (output_root / "participation_routing_001" / "participation_routing_summary.json").write_text(json.dumps({}), encoding="utf-8")
            _write_csv(
                output_root / "participation_routing_001" / "diagnostics" / "routed_candidates.csv",
                [
                    _routed_row(
                        time="2026-06-02T02:00:00",
                        participation_mode="PROBE_CANDIDATE",
                        structure_validity_score=0.86,
                        stop_atr_fraction=0.8,
                        stop_cost_multiple=3.2,
                        refined_net_r_after_fees_slippage=5.4,
                    ),
                    _routed_row(
                        time="2026-06-03T02:00:00",
                        participation_mode="REJECT_INVALID",
                        structure_validity_score=0.82,
                        stop_atr_fraction=0.10,
                        stop_cost_multiple=0.35,
                        refined_net_r_after_fees_slippage=20.0,
                        tiny_stop_flag=True,
                        unrealistic_stop_flag=True,
                        noise_stop_flag=True,
                        cost_dominated_flag=True,
                        choppy_warning=True,
                    ),
                ],
            )
            (output_root / "project_direction_review_001" / "project_direction_summary.json").parent.mkdir(parents=True, exist_ok=True)
            (output_root / "project_direction_review_001" / "project_direction_summary.json").write_text(json.dumps({}), encoding="utf-8")

            write_daily_structural_opportunity(
                DailyStructuralOpportunityConfig(
                    package_root=package_root,
                    output_root=output_root / "daily_opportunity_definition_refinement_001",
                    source_history_path=history_path,
                )
            )

            with (output_root / "daily_opportunity_definition_refinement_001" / "diagnostics" / "top_opportunity_by_day.csv").open(
                "r", encoding="utf-8"
            ) as handle:
                top_rows = list(csv.DictReader(handle))
            probe_day = next(row for row in top_rows if row["date"] == "2026-06-02")
            noise_day = next(row for row in top_rows if row["date"] == "2026-06-03")
            self.assertEqual("True", probe_day["high_R_probe_day_flag"])
            self.assertEqual("False", probe_day["missed_high_R_opportunity_flag"])
            self.assertEqual("VALID_PROBE_NOT_MISSED", probe_day["missed_high_r_audit_category"])
            self.assertEqual("True", noise_day["tiny_wiggle_flag"])
            self.assertEqual("False", noise_day["missed_high_R_opportunity_flag"])
            self.assertEqual("TINY_STOP_OR_NOISE", noise_day["missed_high_r_audit_category"])

            missed_report = json.loads(
                (output_root / "daily_opportunity_definition_refinement_001" / "diagnostics" / "missed_daily_opportunity_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(0, len(missed_report["missed_high_r_opportunities"]))
            self.assertEqual(1, len(missed_report["high_r_probe_days"]))


if __name__ == "__main__":
    unittest.main()
