import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import structural_compounding_lab.diagnostics.multi_asset_structural_redundancy_discovery_audit as audit_module
from structural_compounding_lab.diagnostics.multi_asset_structural_redundancy_discovery_audit import (
    MultiAssetStructuralRedundancyDiscoveryAuditConfig,
    write_multi_asset_structural_redundancy_discovery_audit,
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


def _write_sparse_multi_year_candles(path: Path, *, seed_offset: float) -> None:
    start = datetime(2018, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    price = 100.0 + seed_offset
    for index in range(260):
        ts = start + timedelta(days=index * 10)
        drift = 0.35 + (0.08 if index % 7 in {0, 1, 2} else -0.04)
        swing = ((index % 9) - 4) * 0.12
        open_price = price
        close_price = max(10.0, open_price + drift + swing)
        high_price = max(open_price, close_price) + 0.9 + (index % 5) * 0.05
        low_price = min(open_price, close_price) - 0.8 - (index % 3) * 0.06
        volume = 1000.0 + (index % 11) * 25.0 + seed_offset * 3.0
        rows.append(
            {
                "timestamp": ts.replace(tzinfo=None).isoformat(sep=" "),
                "open": round(open_price, 6),
                "high": round(high_price, 6),
                "low": round(low_price, 6),
                "close": round(close_price, 6),
                "volume": round(volume, 6),
            }
        )
        price = close_price
    _write_csv(path, rows)


def _seed_fixture(root: Path, *, include_assets: tuple[str, ...]) -> Path:
    package_root = root / "structural_compounding_lab"
    output_root = package_root / "output"
    broad_ledger_root = output_root / "broad_historical_structural_replay_001" / "ledger"
    broad_ledger_root.mkdir(parents=True, exist_ok=True)

    data_root = root / "data_storage"
    btc_source = data_root / "BTCUSDT" / "1m" / "BTCUSDT_1m_2018-01-01_to_2026-06-13.csv"
    _write_sparse_multi_year_candles(btc_source, seed_offset=0.0)
    for offset, asset in enumerate(include_assets, start=1):
        asset_source = data_root / asset / "1m" / f"{asset}_1m_2018-01-01_to_2026-06-13.csv"
        _write_sparse_multi_year_candles(asset_source, seed_offset=float(offset * 10))

    (broad_ledger_root / "summary.json").write_text(
        json.dumps({"source_csv": str(btc_source), "trade_count": 90}),
        encoding="utf-8",
    )

    _write_csv(
        output_root / "execution_cost_realism_and_trade_redundancy_audit_001" / "diagnostics" / "execution_cost_band_results.csv",
        [
            {
                "band_name": "NORMAL_MIXED_MAKER_TAKER_COST",
                "rolling_5y_average_ending_equity": 792824.55832,
                "rolling_5y_median_ending_equity": 786049.44639,
                "hit_1m_windows": 12,
                "hit_3m_windows": 0,
                "hit_5m_windows": 0,
            }
        ],
    )
    (
        output_root
        / "native_12h_execution_sleeve_discovery_audit_001"
        / "diagnostics"
        / "12h_baseline_accounting_repair_diagnostics.json"
    ).parent.mkdir(parents=True, exist_ok=True)
    (
        output_root
        / "native_12h_execution_sleeve_discovery_audit_001"
        / "diagnostics"
        / "12h_baseline_accounting_repair_diagnostics.json"
    ).write_text(
        json.dumps(
            {
                "baseline_reconciliation_pass_after_repair": True,
                "selected_repair_mode": "RECONSTRUCT_STRICT_ROWS_WITH_PRIOR_COST_MODEL",
            }
        ),
        encoding="utf-8",
    )
    return package_root


def _synthetic_btc_context_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = datetime(2018, 1, 31, 12, 0, tzinfo=timezone.utc)
    for index in range(96):
        exit_ts = start + timedelta(days=30 * index)
        entry_ts = exit_ts - timedelta(hours=6)
        entry_price = 10000.0 + index * 40.0
        applied_r = 1.6 if index % 5 not in {0, 3} else -0.9
        side = "long" if index % 2 == 0 else "short"
        stop = entry_price * (0.99 if side == "long" else 1.01)
        exit_price = entry_price + (entry_price - stop) * applied_r if side == "long" else entry_price - (stop - entry_price) * applied_r
        rows.append(
            {
                "trade_id": f"btc-{index}",
                "timestamp": exit_ts.isoformat(),
                "entry_timestamp": entry_ts.isoformat(),
                "entry_price": round(entry_price, 6),
                "exit_price": round(exit_price, 6),
                "initial_stop": round(stop, 6),
                "quantity": 1.0,
                "applied_r": round(applied_r, 6),
                "asset": "BTCUSDT",
                "symbol": "BTCUSDT",
                "side": side,
            }
        )
    return rows


def _fake_generate_asset_candidates(symbol: str, hourly: pd.DataFrame):
    timestamps = list(hourly["candle_close_timestamp"].iloc[60:180:10])
    candidates: list[dict[str, object]] = []
    for index, ts in enumerate(timestamps):
        entry_ts = pd.Timestamp(ts)
        side = "long" if symbol != "SOLUSDT" else ("short" if index % 2 else "long")
        entry_price = float(hourly.iloc[60 + index * 10]["open"])
        stop_distance = max(entry_price * 0.006, 0.5)
        stop_price = entry_price - stop_distance if side == "long" else entry_price + stop_distance
        target_price = entry_price + stop_distance * 3.0 if side == "long" else entry_price - stop_distance * 3.0
        candidates.append(
            {
                "asset": symbol,
                "candidate_family": "STRICT_COMBINED_LONG_SHORT" if symbol != "BNBUSDT" else "BREAK_RETEST_CONTINUATION_LONG",
                "trade_id": f"{symbol}-{index}",
                "signal_timestamp": (entry_ts - timedelta(hours=1)).isoformat(),
                "entry_timestamp": entry_ts.isoformat(),
                "side": side,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "max_hold_bars": 6,
            }
        )
    inventory = [
        {
            "asset": symbol,
            "candidate_family": "STRICT_COMBINED_LONG_SHORT" if symbol != "BNBUSDT" else "BREAK_RETEST_CONTINUATION_LONG",
            "candidate_count": len(candidates),
            "status": "active",
            "selection_fields_used": "synthetic_pre_entry_features_only",
        }
    ]
    leakage = [
        {
            "asset": symbol,
            "candidate_family": inventory[0]["candidate_family"],
            "future_outcome_fields_used": False,
            "selection_fields": ["timestamp", "open", "high", "low", "close", "volume"],
        }
    ]
    return candidates, inventory, leakage


def _fake_simulate_asset_families(symbol: str, candidate_rows: list[dict[str, object]], hourly: pd.DataFrame):
    simulated: list[dict[str, object]] = []
    family = str(candidate_rows[0]["candidate_family"]) if candidate_rows else "STRICT_COMBINED_LONG_SHORT"
    symbol_bonus = {"ETHUSDT": 1.35, "SOLUSDT": 0.9, "BNBUSDT": 0.75, "AVAXUSDT": 0.6}.get(symbol, 0.5)
    for index, candidate in enumerate(candidate_rows):
        entry_ts = pd.Timestamp(str(candidate["entry_timestamp"]))
        exit_ts = entry_ts + timedelta(hours=6)
        base_r = symbol_bonus + (0.45 if index % 6 in {1, 2} else -0.85 if index % 7 == 0 else 0.15)
        side = str(candidate["side"])
        entry_price = float(candidate["entry_price"])
        stop_price = float(candidate["stop_price"])
        risk = abs(entry_price - stop_price)
        if side == "long":
            exit_price = entry_price + risk * base_r
        else:
            exit_price = entry_price - risk * base_r
        simulated.append(
            {
                "asset": symbol,
                "trade_id": str(candidate["trade_id"]),
                "candidate_family": family,
                "side": side,
                "entry_timestamp": entry_ts,
                "exit_timestamp": exit_ts,
                "entry_price": round(entry_price, 6),
                "exit_price": round(exit_price, 6),
                "initial_stop": round(stop_price, 6),
                "quantity": 1.0,
                "r_multiple": round(base_r, 6),
                "gross_r": round(base_r, 6),
                "holding_hours": 6,
                "archetype_key": family,
                "exit_reason": "synthetic_exit",
            }
        )
    rolling = audit_module._rolling_summary(simulated, cost_bps_total=audit_module.NORMAL_COST_BPS)
    r_values = [float(row["r_multiple"]) for row in simulated]
    wins = [value for value in r_values if value > 0.0]
    losses = [abs(value) for value in r_values if value < 0.0]
    pf = sum(wins) / sum(losses) if losses else sum(wins)
    month_counts: dict[str, int] = {}
    month_r: dict[str, float] = {}
    for row in simulated:
        month = row["exit_timestamp"].strftime("%Y-%m")
        month_counts[month] = month_counts.get(month, 0) + 1
        month_r[month] = month_r.get(month, 0.0) + float(row["r_multiple"])
    monthly_rows = [
        {"asset": symbol, "candidate_family": family, "month": month, "trade_count": count, "total_R": round(month_r[month], 6)}
        for month, count in sorted(month_counts.items())
    ]
    cluster_rows = [
        {
            "asset": symbol,
            "candidate_family": family,
            "trade_count": len(simulated),
            "monthly_cluster_concentration": round(max(month_counts.values()) / len(simulated), 6),
            "inactive_month_count": 0,
        }
    ]
    performance_rows = [
        {
            "asset": symbol,
            "candidate_family": family,
            "trade_count": len(simulated),
            "long_count": sum(1 for row in simulated if row["side"] == "long"),
            "short_count": sum(1 for row in simulated if row["side"] == "short"),
            "average_R": round(sum(r_values) / len(r_values), 6),
            "median_R": round(audit_module._median(r_values), 6),
            "win_rate": round(len(wins) / len(r_values), 6),
            "profit_factor": round(pf, 6),
            "average_holding_hours": 6.0,
            "top_5_winner_dependency_R": round(sum(sorted(wins, reverse=True)[:5]), 6),
            "inactive_months": 0,
            "monthly_cluster_concentration": round(max(month_counts.values()) / len(simulated), 6),
            "normal_cost_rolling_5y_average": rolling["average"],
            "normal_cost_rolling_5y_median": rolling["median"],
            "hit_1m_windows": rolling["hit_1m_windows"],
            "hit_3m_windows": rolling["hit_3m_windows"],
            "hit_5m_windows": rolling["hit_5m_windows"],
            "max_drawdown_pct": rolling["max_drawdown_pct"],
        }
    ]
    return simulated, performance_rows, monthly_rows, cluster_rows


class MultiAssetStructuralRedundancyDiscoveryAuditTests(unittest.TestCase):
    def test_missing_asset_data_blocks_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = _seed_fixture(Path(tmpdir), include_assets=("ETHUSDT",))
            output_root = package_root / "output"
            result = write_multi_asset_structural_redundancy_discovery_audit(
                MultiAssetStructuralRedundancyDiscoveryAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "multi_asset_structural_redundancy_discovery_audit_001",
                    random_repeat_count=8,
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("MULTI_ASSET_REDUNDANCY_BLOCKED_INSUFFICIENT_DATA", summary["final_classification"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            diagnostics_root = output_root / "multi_asset_structural_redundancy_discovery_audit_001" / "diagnostics"
            self.assertTrue((diagnostics_root / "multi_asset_data_availability.json").exists())

    def test_runs_and_writes_outputs_with_fallback_baseline_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = _seed_fixture(Path(tmpdir), include_assets=("ETHUSDT", "SOLUSDT", "BNBUSDT"))
            output_root = package_root / "output"
            context = {"rows": _synthetic_btc_context_rows()}
            with patch.object(audit_module, "_load_execution_cost_context", return_value=(context, [], {})), patch.object(
                audit_module,
                "_generate_asset_candidates",
                side_effect=_fake_generate_asset_candidates,
            ), patch.object(
                audit_module,
                "_simulate_asset_families",
                side_effect=_fake_simulate_asset_families,
            ):
                result = write_multi_asset_structural_redundancy_discovery_audit(
                    MultiAssetStructuralRedundancyDiscoveryAuditConfig(
                        package_root=package_root,
                        output_root=output_root / "multi_asset_structural_redundancy_discovery_audit_001",
                        random_repeat_count=8,
                    )
                )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertEqual("ETHUSDT", summary["best_non_btc_asset"])
            self.assertTrue(summary["eligible_assets"])
            self.assertTrue(summary["scout_mode"])
            self.assertIn(
                summary["final_classification"],
                {
                    "MULTI_ASSET_REDUNDANCY_REJECTED",
                    "MULTI_ASSET_REDUNDANCY_WEAK",
                    "MULTI_ASSET_REDUNDANCY_IMPROVES_BUT_NOT_GATE_PASSING",
                    "MULTI_ASSET_REDUNDANCY_1M_PROMISING_RESEARCH_ONLY",
                    "MULTI_ASSET_REDUNDANCY_3M_PROMISING_RESEARCH_ONLY",
                    "MULTI_ASSET_REDUNDANCY_READY_FOR_FREEZE_AND_CONFIRM_RESEARCH_ONLY",
                },
            )

            audit_root = output_root / "multi_asset_structural_redundancy_discovery_audit_001"
            diagnostics_root = audit_root / "diagnostics"
            ledger_root = audit_root / "ledger"
            reports_root = audit_root / "reports"
            for path in (
                diagnostics_root / "multi_asset_data_availability.csv",
                diagnostics_root / "multi_asset_data_availability.json",
                diagnostics_root / "btc_baseline_anchor.json",
                diagnostics_root / "per_asset_candidate_inventory.csv",
                diagnostics_root / "per_asset_no_leakage_check.json",
                diagnostics_root / "per_asset_candidate_performance.csv",
                diagnostics_root / "multi_asset_independent_cluster_audit.csv",
                diagnostics_root / "multi_asset_portfolio_results.csv",
                diagnostics_root / "multi_asset_cost_band_rolling_5y_results.csv",
                diagnostics_root / "multi_asset_missed_trade_resilience.csv",
                diagnostics_root / "multi_asset_stochastic_budget_reliability_check.json",
                diagnostics_root / "implementation_self_audit.json",
                ledger_root / "per_asset_candidate_trades.csv",
                reports_root / "next_research_recommendation.json",
            ):
                self.assertTrue(path.exists(), str(path))

            with (diagnostics_root / "per_asset_candidate_inventory.csv").open("r", encoding="utf-8") as handle:
                inventory_rows = list(csv.DictReader(handle))
            self.assertTrue(inventory_rows)

            leakage = json.loads((diagnostics_root / "per_asset_no_leakage_check.json").read_text(encoding="utf-8"))
            self.assertTrue(leakage["all_candidates_clean"])
            self.assertTrue(all(not row["future_outcome_fields_used"] for row in leakage["rows"]))

            with (diagnostics_root / "multi_asset_portfolio_results.csv").open("r", encoding="utf-8") as handle:
                portfolio_rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["variant_name"] == "BTC_BASE_PLUS_TOP_1_NON_BTC" for row in portfolio_rows))

            reliability = json.loads((diagnostics_root / "multi_asset_stochastic_budget_reliability_check.json").read_text(encoding="utf-8"))
            self.assertEqual(8, reliability["random_repeat_count_used"])
            self.assertTrue(reliability["scout_mode"])
            self.assertFalse(reliability["stochastic_results_reliable_for_final_gate"])
            self.assertTrue(reliability["deterministic_metrics_still_usable"])

            self_audit = json.loads((diagnostics_root / "implementation_self_audit.json").read_text(encoding="utf-8"))
            self.assertEqual("timestamp", self_audit["timestamp_field_used"])
            self.assertEqual("applied_r", self_audit["r_field_used"])
            self.assertTrue(self_audit["future_field_usage_check"])
            self.assertTrue(self_audit["leakage_check"])
            self.assertFalse(self_audit["previous_artifacts_overwritten"])

            baseline_anchor = json.loads((diagnostics_root / "btc_baseline_anchor.json").read_text(encoding="utf-8"))
            self.assertEqual("timestamp", baseline_anchor["baseline_timestamp_field_used"])
            self.assertEqual("applied_r", baseline_anchor["baseline_r_field_used"])
            self.assertEqual(792824.55832, baseline_anchor["rolling_5y_average_ending_equity"])


if __name__ == "__main__":
    unittest.main()
