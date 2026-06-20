import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import math
import pandas as pd

import structural_compounding_lab.diagnostics.native_12h_execution_sleeve_discovery_audit as audit_module
from structural_compounding_lab.diagnostics.native_12h_execution_sleeve_discovery_audit import (
    MAX_PARAMETER_VARIANTS_ALLOWED,
    Native12HExecutionSleeveDiscoveryAuditConfig,
    _select_best_parameter_family,
    write_native_12h_execution_sleeve_discovery_audit,
)
from structural_compounding_lab.tests.test_native_pre_entry_sr_feature_enrichment_audit import (
    _seed_small_fixture,
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


def _write_dynamic_source_csv(path: Path) -> None:
    start = datetime(2020, 9, 1, 0, 0, tzinfo=timezone.utc)
    periods = 60 * 24 * 180
    index = pd.date_range(start=start, periods=periods, freq="1min", tz="UTC")
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[float] = []
    price = 100.0
    for i, _ts in enumerate(index):
        slow_wave = math.sin(i / 720.0) * 1.4
        fast_wave = math.sin(i / 48.0) * 0.45
        drift = 0.00008 if (i // 8000) % 2 == 0 else -0.00005
        open_price = price
        close_price = max(20.0, open_price + slow_wave * 0.03 + fast_wave * 0.02 + drift * open_price)
        wick = 0.35 + abs(math.sin(i / 37.0)) * 0.45
        high_price = max(open_price, close_price) + wick
        low_price = min(open_price, close_price) - wick
        volume = 20.0 + abs(math.sin(i / 19.0)) * 15.0 + abs(math.sin(i / 300.0)) * 25.0
        opens.append(round(open_price, 6))
        highs.append(round(high_price, 6))
        lows.append(round(low_price, 6))
        closes.append(round(close_price, 6))
        volumes.append(round(volume, 6))
        price = close_price
    frame = pd.DataFrame(
        {
            "timestamp": index.tz_convert(None),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _seed_twelve_h_inputs(root: Path, *, with_source: bool) -> Path:
    package_root, _ = _seed_small_fixture(root, with_source=with_source)
    output_root = package_root / "output"
    if with_source:
        broad_summary_path = output_root / "broad_historical_structural_replay_001" / "ledger" / "summary.json"
        broad_summary = json.loads(broad_summary_path.read_text(encoding="utf-8"))
        source_csv = Path(broad_summary["source_csv"])
        _write_dynamic_source_csv(source_csv)

    bridge_root = output_root / "strict_sr_aware_milestone_bridge_monte_carlo_audit_001" / "ledger"
    bridge_root.mkdir(parents=True, exist_ok=True)
    _write_csv(
        bridge_root / "milestone_bridge_trades.csv",
        [
            {
                "trade_id": "B1",
                "timestamp": "2021-01-03T12:00:00Z",
                "risk_multiplier": 1.0,
                "risk_value": 200.0,
                "applied_r": 1.2,
                "pnl": 240.0,
                "equity_after": 20240.0,
                "archetype_key": "strict_core",
                "failure_mode": "target_hit",
            },
            {
                "trade_id": "B2",
                "timestamp": "2021-01-05T12:00:00Z",
                "risk_multiplier": 1.0,
                "risk_value": 202.4,
                "applied_r": -1.0,
                "pnl": -202.4,
                "equity_after": 20037.6,
                "archetype_key": "strict_core",
                "failure_mode": "stop_hit",
            },
            {
                "trade_id": "B3",
                "timestamp": "2021-01-07T12:00:00Z",
                "risk_multiplier": 1.0,
                "risk_value": 200.376,
                "applied_r": 2.0,
                "pnl": 400.752,
                "equity_after": 20438.352,
                "archetype_key": "strict_core",
                "failure_mode": "target_hit",
            },
        ],
    )

    execution_root = output_root / "execution_cost_realism_and_trade_redundancy_audit_001" / "diagnostics"
    execution_root.mkdir(parents=True, exist_ok=True)
    _write_csv(
        execution_root / "execution_cost_band_results.csv",
        [
            {
                "band_name": "NORMAL_MIXED_MAKER_TAKER_COST",
                "rolling_5y_average_ending_equity": 800000.0,
                "rolling_5y_median_ending_equity": 780000.0,
                "hit_1m_windows": 10,
            }
        ],
    )
    (execution_root / "operational_reliability_requirements.json").write_text(
        json.dumps(
            {
                "minimum_signal_capture_rate_pct": 99,
                "minimum_uptime_pct": 99,
                "maximum_candle_delay": "<= 1 closed decision candle",
            }
        ),
        encoding="utf-8",
    )

    redundancy_root = output_root / "cost_resilient_trade_redundancy_expansion_audit_001" / "diagnostics"
    redundancy_root.mkdir(parents=True, exist_ok=True)
    (output_root / "cost_resilient_trade_redundancy_expansion_audit_001" / "cost_resilient_trade_redundancy_expansion_summary.json").parent.mkdir(parents=True, exist_ok=True)
    (output_root / "cost_resilient_trade_redundancy_expansion_audit_001" / "cost_resilient_trade_redundancy_expansion_summary.json").write_text(
        json.dumps({"final_classification": "REDUNDANCY_EXPANSION_NEEDS_MULTI_ASSET_OR_NEW_SLEEVE", "research_only": True}),
        encoding="utf-8",
    )
    (redundancy_root / "stochastic_budget_reliability_check.json").write_text(
        json.dumps({"random_repeat_count_used": 8, "minimum_repeat_count_required_for_gate": 32, "scout_mode": True, "stochastic_results_reliable_for_final_gate": False}),
        encoding="utf-8",
    )
    return package_root


def _align_expected_baseline_to_first_run(package_root: Path) -> None:
    output_root = package_root / "output"
    audit_output = output_root / "native_12h_execution_sleeve_discovery_audit_001"
    write_native_12h_execution_sleeve_discovery_audit(
        Native12HExecutionSleeveDiscoveryAuditConfig(
            package_root=package_root,
            output_root=audit_output,
            random_repeat_count=8,
        )
    )
    combined_path = audit_output / "diagnostics" / "combined_1h_12h_portfolio_results.csv"
    with combined_path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    one_h = next(row for row in rows if row["variant_name"] == "1H_BASE_ONLY")
    execution_root = output_root / "execution_cost_realism_and_trade_redundancy_audit_001" / "diagnostics"
    _write_csv(
        execution_root / "execution_cost_band_results.csv",
        [
            {
                "band_name": "NORMAL_MIXED_MAKER_TAKER_COST",
                "rolling_5y_average_ending_equity": float(one_h["normal_cost_rolling_5y_average"]),
                "rolling_5y_median_ending_equity": float(one_h["normal_cost_rolling_5y_median"]),
                "hit_1m_windows": int(one_h["normal_cost_hit_1m_windows"]),
            }
        ],
    )


class Native12HExecutionSleeveDiscoveryAuditTests(unittest.TestCase):
    def test_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = _seed_twelve_h_inputs(Path(tmpdir), with_source=True)
            output_root = package_root / "output"
            result = write_native_12h_execution_sleeve_discovery_audit(
                Native12HExecutionSleeveDiscoveryAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_12h_execution_sleeve_discovery_audit_001",
                    random_repeat_count=8,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertTrue(summary["scout_mode"])
            self.assertIn(
                summary["final_classification"],
                {
                    "NATIVE_12H_EXECUTION_BLOCKED_MISSING_DATA",
                    "NATIVE_12H_EXECUTION_REJECTED",
                    "NATIVE_12H_EXECUTION_WEAK",
                    "NATIVE_12H_EXECUTION_IMPROVES_BUT_NOT_GATE_PASSING",
                    "NATIVE_12H_EXECUTION_1M_PROMISING_RESEARCH_ONLY",
                    "NATIVE_12H_EXECUTION_3M_PROMISING_RESEARCH_ONLY",
                    "NATIVE_12H_EXECUTION_READY_FOR_COMBINED_NATIVE_REPLAY_RESEARCH_ONLY",
                    "NATIVE_12H_EXECUTION_NEEDS_MULTI_ASSET_CONFIRMATION",
                },
            )

            diagnostics_root = output_root / "native_12h_execution_sleeve_discovery_audit_001" / "diagnostics"
            ledger_root = output_root / "native_12h_execution_sleeve_discovery_audit_001" / "ledger"
            for path in (
                diagnostics_root / "timeframe_availability_audit.json",
                diagnostics_root / "12h_candle_quality_report.json",
                diagnostics_root / "12h_baseline_reconciliation_check.json",
                diagnostics_root / "native_12h_candidate_inventory.csv",
                diagnostics_root / "native_12h_candidate_inventory.json",
                diagnostics_root / "native_12h_no_leakage_check.json",
                diagnostics_root / "native_12h_candidate_performance.csv",
                diagnostics_root / "12h_parameter_family_summary.json",
                diagnostics_root / "combined_1h_12h_portfolio_results.csv",
                diagnostics_root / "12h_cost_band_rolling_5y_results.csv",
                diagnostics_root / "12h_missed_trade_resilience.csv",
                diagnostics_root / "12h_stochastic_budget_reliability_check.json",
                diagnostics_root / "implementation_self_audit.json",
                ledger_root / "native_12h_trade_candidates.csv",
                ledger_root / "native_12h_equity_curves.csv",
            ):
                self.assertTrue(path.exists(), str(path))

            leakage = json.loads((diagnostics_root / "native_12h_no_leakage_check.json").read_text(encoding="utf-8"))
            self.assertTrue(leakage["all_candidates_clean"])
            reconciliation = json.loads((diagnostics_root / "12h_baseline_reconciliation_check.json").read_text(encoding="utf-8"))
            self.assertFalse(reconciliation["baseline_reconciliation_pass"])
            reliability = json.loads((diagnostics_root / "12h_stochastic_budget_reliability_check.json").read_text(encoding="utf-8"))
            self.assertTrue(reliability["scout_mode"])
            self.assertFalse(reliability["stochastic_results_reliable_for_final_gate"])
            self.assertIn("12H candidate inventory", reliability["deterministic_metrics_still_usable"])
            self_audit = json.loads((diagnostics_root / "implementation_self_audit.json").read_text(encoding="utf-8"))
            self.assertEqual("timestamp", self_audit["timestamp_field_used"])
            self.assertFalse(self_audit["real_money_allowed"])
            self.assertTrue(self_audit["future_field_usage_check"])
            self.assertFalse(self_audit["stochastic_results_reliable_for_final_gate"])
            self.assertFalse(summary["final_classification_reliable"])
            self.assertEqual("BLOCKED_BASELINE_RECONCILIATION_FAIL", summary["parameter_family_status"])
            with (diagnostics_root / "native_12h_candidate_performance.csv").open("r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(rows)

    def test_missing_12h_data_blocks_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = _seed_twelve_h_inputs(Path(tmpdir), with_source=False)
            output_root = package_root / "output"
            result = write_native_12h_execution_sleeve_discovery_audit(
                Native12HExecutionSleeveDiscoveryAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_12h_execution_sleeve_discovery_audit_001",
                    random_repeat_count=8,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("NATIVE_12H_EXECUTION_BLOCKED_MISSING_DATA", summary["final_classification"])

    def test_baseline_reconciliation_pass_runs_parameter_family_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = _seed_twelve_h_inputs(Path(tmpdir), with_source=True)
            _align_expected_baseline_to_first_run(package_root)
            output_root = package_root / "output"
            result = write_native_12h_execution_sleeve_discovery_audit(
                Native12HExecutionSleeveDiscoveryAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_12h_execution_sleeve_discovery_audit_001",
                    random_repeat_count=8,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            diagnostics_root = output_root / "native_12h_execution_sleeve_discovery_audit_001" / "diagnostics"
            reconciliation = json.loads((diagnostics_root / "12h_baseline_reconciliation_check.json").read_text(encoding="utf-8"))
            parameter_summary = json.loads((diagnostics_root / "12h_parameter_family_summary.json").read_text(encoding="utf-8"))
            with (diagnostics_root / "12h_parameter_family_results.csv").open("r", encoding="utf-8") as handle:
                parameter_rows = list(csv.DictReader(handle))
            self.assertTrue(reconciliation["baseline_reconciliation_pass"])
            self.assertEqual("COMPLETE", parameter_summary["parameter_family_status"])
            self.assertLessEqual(parameter_summary["total_parameter_variants_tested"], MAX_PARAMETER_VARIANTS_ALLOWED)
            self.assertTrue(parameter_rows)
            self.assertTrue(summary["final_classification_reliable"])
            self.assertTrue(summary["deterministic_12h_conclusion_usable"])

    def test_promising_parameter_family_softens_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = _seed_twelve_h_inputs(Path(tmpdir), with_source=True)
            _align_expected_baseline_to_first_run(package_root)
            output_root = package_root / "output"
            mocked_summary = {
                "research_only": True,
                "paper_allowed": False,
                "live_allowed": False,
                "real_money_allowed": False,
                "behavior_change_allowed": False,
                "parameter_family_status": "COMPLETE",
                "total_parameter_variants_tested": 4,
                "max_parameter_variants_allowed": MAX_PARAMETER_VARIANTS_ALLOWED,
                "best_parameter_family_id": "BALANCED_12H_TREND_02",
                "best_family_name": "BALANCED_12H_TREND",
                "best_parameters": {"ema_fast": 20, "ema_slow": 50, "ema_regime_filter": True, "atr_stop_multiplier": 1.2, "target_r": 3.0, "max_hold_bars": 10},
                "best_12h_only_normal_cost_rolling_5y_average": 300000.0,
                "best_12h_only_normal_cost_rolling_5y_median": 280000.0,
                "best_12h_only_hit_1m_windows": 0,
                "best_12h_only_hit_3m_windows": 0,
                "best_12h_only_hit_5m_windows": 0,
                "best_1h_plus_12h_normal_cost_rolling_5y_average": 1100000.0,
                "best_1h_plus_12h_normal_cost_rolling_5y_median": 980000.0,
                "best_1h_plus_12h_hit_1m_windows": 3,
                "best_1h_plus_12h_hit_3m_windows": 0,
                "best_1h_plus_12h_hit_5m_windows": 0,
                "overlap_with_1h_verdict": "LOWER_OVERLAP_THAN_FIRST_PASS",
                "independent_cluster_verdict": "INDEPENDENT_PROFITABLE_CLUSTERS_FOUND",
                "parameter_search_overfit_risk": "disciplined_small_grid_under_30_variants",
                "whether_any_12h_family_deserves_freeze_and_confirm": True,
                "whether_original_12h_rejection_should_be_softened": True,
            }
            with patch.object(
                audit_module,
                "_evaluate_parameter_families",
                return_value=(
                    [{"parameter_family_id": "BALANCED_12H_TREND_02", "profit_factor": 1.2, "best_combined_normal_cost_rolling_5y_average": 1100000.0, "simulated_trade_count": 20, "overlap_with_1h_ratio": 0.2, "independent_positive_month_count": 4, "monthly_distribution_score": 0.2}],
                    mocked_summary,
                    [{"variant_name": "1H_BASE_PLUS_BEST_12H_PARAMETER_FAMILY", "normal_cost_rolling_5y_average": 1100000.0, "normal_cost_rolling_5y_median": 980000.0, "normal_cost_hit_1m_windows": 3, "normal_cost_hit_3m_windows": 0, "normal_cost_hit_5m_windows": 0, "normal_cost_max_drawdown_pct": 0.2, "trade_count": 600}],
                    [],
                ),
            ):
                result = write_native_12h_execution_sleeve_discovery_audit(
                    Native12HExecutionSleeveDiscoveryAuditConfig(
                        package_root=package_root,
                        output_root=output_root / "native_12h_execution_sleeve_discovery_audit_001",
                        random_repeat_count=8,
                    )
                )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["whether_original_12h_rejection_should_be_softened"])
            self.assertTrue(summary["whether_any_12h_family_deserves_freeze_and_confirm"])
            self.assertIn(summary["final_classification"], {"NATIVE_12H_EXECUTION_1M_PROMISING_RESEARCH_ONLY", "NATIVE_12H_EXECUTION_IMPROVES_BUT_NOT_GATE_PASSING"})

    def test_best_family_not_selected_by_profit_factor_alone(self) -> None:
        selected = _select_best_parameter_family(
            [
                {
                    "parameter_family_id": "PF_ONLY",
                    "best_combined_normal_cost_rolling_5y_average": 100000.0,
                    "best_combined_hit_1m_windows": 0,
                    "overlap_with_1h_ratio": 0.9,
                    "independent_positive_month_count": 0,
                    "profit_factor": 4.0,
                    "simulated_trade_count": 20,
                    "monthly_distribution_score": 0.2,
                },
                {
                    "parameter_family_id": "MISSION_FIRST",
                    "best_combined_normal_cost_rolling_5y_average": 400000.0,
                    "best_combined_hit_1m_windows": 1,
                    "overlap_with_1h_ratio": 0.2,
                    "independent_positive_month_count": 3,
                    "profit_factor": 1.1,
                    "simulated_trade_count": 20,
                    "monthly_distribution_score": 0.2,
                },
            ]
        )
        self.assertEqual("MISSION_FIRST", selected["parameter_family_id"])


if __name__ == "__main__":
    unittest.main()
