import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from structural_compounding_lab.diagnostics.broad_frozen_patch_validation import (
    BroadFrozenPatchValidationConfig,
    write_broad_frozen_patch_validation,
)
from structural_compounding_lab.diagnostics.broad_patch_accounting_and_short_rescue_audit import (
    BroadPatchAccountingAndShortRescueAuditConfig,
    write_broad_patch_accounting_and_short_rescue_audit,
)
from structural_compounding_lab.diagnostics.broad_patch_bluntness_audit import (
    BroadPatchBluntnessAuditConfig,
    write_broad_patch_bluntness_audit,
)
from structural_compounding_lab.diagnostics.equal_highs_liquidity_sweep_rescue_forensic_audit import (
    EqualHighsLiquiditySweepRescueForensicAuditConfig,
    write_equal_highs_liquidity_sweep_rescue_forensic_audit,
)
from structural_compounding_lab.diagnostics.native_pre_entry_sr_feature_enrichment_audit import (
    NativePreEntrySRFeatureEnrichmentAuditConfig,
    write_native_pre_entry_sr_feature_enrichment_audit,
)
from structural_compounding_lab.diagnostics.rolling_five_year_mission_viability_audit import (
    RollingFiveYearMissionViabilityAuditConfig,
    write_rolling_five_year_mission_viability_audit,
)
from structural_compounding_lab.diagnostics.support_room_short_rescue_repair_audit import (
    SupportRoomShortRescueRepairAuditConfig,
    write_support_room_short_rescue_repair_audit,
)
from structural_compounding_lab.tests.test_broad_frozen_patch_validation import _write_csv


def _write_source_csv(path: Path, start: datetime, periods: int = 60 * 24 * 16) -> None:
    index = pd.date_range(start=start, periods=periods, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": index.tz_convert(None),
            "open": 100 + pd.Series(range(len(index))).mul(0.01).to_numpy(),
            "high": 100.5 + pd.Series(range(len(index))).mul(0.01).to_numpy(),
            "low": 99.5 + pd.Series(range(len(index))).mul(0.01).to_numpy(),
            "close": 100 + pd.Series(range(len(index))).mul(0.01).to_numpy(),
            "volume": 10.0,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _seed_small_fixture(root: Path, *, with_source: bool) -> tuple[Path, Path | None]:
    package_root = root / "structural_compounding_lab"
    output_root = package_root / "output"
    broad_root = output_root / "broad_historical_structural_replay_001"
    broad_ledger_root = broad_root / "ledger"
    broad_diag_root = broad_root / "diagnostics"
    broad_report_root = broad_root / "reports"
    frozen_root = output_root / "frozen_patch_validation_audit_001" / "diagnostics"
    broad_diag_root.mkdir(parents=True, exist_ok=True)
    broad_report_root.mkdir(parents=True, exist_ok=True)
    frozen_root.mkdir(parents=True, exist_ok=True)

    base = datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc)
    trades = []
    setups = []
    levels = []
    liquidity = []

    def add_trade(trade_id: str, day: int, side: str, pattern: str, personality: str, r_multiple: float, htf_aligned: bool) -> None:
        entry = base + timedelta(days=day, hours=3)
        exit_ = entry + timedelta(hours=2)
        entry_price = 100.0 + day
        stop = entry_price * (1.01 if side == "short" else 0.99)
        exit_price = entry_price - (r_multiple * (stop - entry_price)) if side == "short" else entry_price + (r_multiple * (entry_price - stop))
        trades.append(
            {
                "trade_id": trade_id,
                "symbol": "BTCUSDT",
                "side": side,
                "entry_time": entry.isoformat(),
                "exit_time": exit_.isoformat(),
                "entry_price": entry_price,
                "exit_price": round(exit_price, 4),
                "initial_stop": round(stop, 4),
                "trail_stop": round(stop, 4),
                "pnl": round(r_multiple * 100.0, 4),
                "r_multiple": round(r_multiple, 4),
                "entry_reason": f"A structural setup: {pattern} near resistance | RR 2.5 | HTF {'aligned' if htf_aligned else 'counter'}",
                "exit_reason": "target_hit" if r_multiple > 0 else "stop_hit",
                "add_on_count": 0,
                "holding_bars": 2,
                "setup_class": "A",
                "strategy_type": "structural_compounding",
                "moonshot_state": "normal",
                "entry_score": 4.5 if r_multiple > 0 else 3.6,
                "risk_multiplier": 1.0,
                "convexity_label": "elite_convexity" if "elite" in personality else "strong_convexity",
                "cooldown_fast_clear_eligible": False,
                "personality_label": personality,
                "personality_confidence": 0.7,
                "pullback_type": "HEALTHY_CONTINUATION_PULLBACK",
                "pullback_quality_score": 0.5,
                "pullback_entry_price": entry_price,
                "pullback_stop_price": round(stop, 4),
                "pullback_r_improvement": 1.0,
                "compounding_readiness_score": 0.4,
                "runner_label": "normal",
                "add_on_research_candidate": False,
                "patience_score": 0.0,
                "de_risk_score": 0.5,
                "equity_after": 20000 + day * 10,
                "cycle_id": "cycle-0",
            }
        )
        setups.append(
            {
                "symbol": "BTCUSDT",
                "timestamp": entry.isoformat(),
                "side": side,
                "setup_type": "structural_compounding",
                "setup_class": "A",
                "classification": "A",
                "structure_score": 1.1,
                "liquidity_score": 0.85,
                "ema_score": 0.55 if htf_aligned else 0.1,
                "htf_confirmation_score": 0.6 if htf_aligned else 0.0,
                "volatility_score": 0.45,
                "risk_reward_score": 1.2,
                "score": 4.4 if r_multiple > 0 else 3.4,
                "total_score": 4.4 if r_multiple > 0 else 3.4,
                "accepted": True,
                "decision": "opened",
                "entry_reason": f"A structural setup: {pattern} near resistance",
                "explanation": f"A structural setup: {pattern} near resistance",
                "pattern": pattern,
                "htf_aligned": htf_aligned,
                "target_price": entry_price - 3.0,
                "level_distance_atr": 0.22 if "equal_highs" in pattern or pattern == "sweep_high" else 0.40,
                "liquidity_event_type": pattern,
                "liquidity_event_age_bars": 2,
                "risk_multiplier": 1.0,
                "convexity_label": "elite_convexity" if "elite" in personality else "strong_convexity",
                "cooldown_fast_clear_eligible": False,
                "execution_timeframe": "1h",
                "story_id": f"{trade_id}-story",
                "personality_label": personality,
                "personality_confidence": 0.7,
                "personality_explanation": "fixture",
                "macd_state": "bearish",
                "macd_confirmation_flag": True,
                "macd_warning_flag": False,
                "bollinger_state": "expansion",
                "bb_compression": False,
                "bb_expansion": True,
                "bb_warning_flag": False,
                "pullback_type": "HEALTHY_CONTINUATION_PULLBACK",
                "micro_pullback_detected": False,
                "pullback_entry_time": entry.isoformat(),
                "pullback_entry_price": entry_price,
                "pullback_stop_price": round(stop, 4),
                "pullback_quality_score": 0.5,
                "pullback_depth_atr": 0.8,
                "pullback_estimated_r": 5.0,
                "pullback_r_improvement": 1.0,
                "pullback_explanation": "fixture",
                "compounding_readiness_score": 0.4,
                "runner_label": "normal",
                "runner_eligible_candidate": False,
                "add_on_research_candidate": False,
                "patience_score": 0.0,
                "de_risk_score": 0.5,
                "opened": True,
            }
        )
        levels.extend(
            [
                {
                    "symbol": "BTCUSDT",
                    "price": entry_price - 0.6,
                    "type": "range_low",
                    "timeframe_source": "1h",
                    "touch_count": 2,
                    "recency": 0.0,
                    "strength": 1.2,
                    "first_seen": (entry - timedelta(hours=8)).isoformat(),
                    "last_touched": (entry - timedelta(hours=1)).isoformat(),
                    "display_only": True,
                    "research_flag": True,
                    "no_future_data": True,
                    "timestamp": (entry - timedelta(hours=1)).isoformat(),
                },
                {
                    "symbol": "BTCUSDT",
                    "price": entry_price + 0.4,
                    "type": "range_high",
                    "timeframe_source": "1h",
                    "touch_count": 3,
                    "recency": 0.0,
                    "strength": 1.5,
                    "first_seen": (entry - timedelta(hours=9)).isoformat(),
                    "last_touched": (entry - timedelta(hours=1)).isoformat(),
                    "display_only": True,
                    "research_flag": True,
                    "no_future_data": True,
                    "timestamp": (entry - timedelta(hours=1)).isoformat(),
                },
            ]
        )
        liquidity.extend(
            [
                {
                    "symbol": "BTCUSDT",
                    "timestamp": (entry - timedelta(hours=2)).isoformat(),
                    "price": entry_price + 0.3,
                    "type": "equal_highs",
                    "side_implication": "bearish_if_swept",
                    "source_timeframe": "1h",
                    "confidence": 0.7,
                    "no_future_data": True,
                },
                {
                    "symbol": "BTCUSDT",
                    "timestamp": (entry - timedelta(hours=1)).isoformat(),
                    "price": entry_price + 0.5,
                    "type": "sweep_high",
                    "side_implication": "short",
                    "source_timeframe": "1h",
                    "confidence": 0.8,
                    "no_future_data": True,
                },
            ]
        )

    add_trade("L1", 1, "long", "sweep_low", "strong_convexity", -1.0, False)
    add_trade("L2", 2, "long", "sweep_low", "strong_convexity", 1.2, True)
    add_trade("S1", 3, "short", "sweep_high", "elite_convexity", 2.5, True)
    add_trade("S2", 4, "short", "sweep_high", "elite_convexity", -1.0, True)
    add_trade("S3", 5, "short", "sweep_high", "elite_convexity", 5.2, True)
    add_trade("S4", 6, "short", "equal_highs", "elite_convexity", 1.8, True)
    add_trade("S5", 7, "short", "equal_highs", "elite_convexity", -0.8, True)
    add_trade("S6", 8, "short", "sweep_high", "strong_convexity", -1.0, False)

    _write_csv(broad_ledger_root / "trades.csv", trades)
    _write_csv(broad_ledger_root / "setup_log.csv", setups)
    _write_csv(broad_ledger_root / "level_log.csv", levels)
    _write_csv(broad_ledger_root / "liquidity_events.csv", liquidity)
    _write_csv(broad_ledger_root / "equity.csv", [{"timestamp": base.isoformat(), "equity": 20000.0}, {"timestamp": (base + timedelta(days=12)).isoformat(), "equity": 26000.0}])

    source_csv = None
    if with_source:
        source_csv = root / "data_storage" / "BTCUSDT" / "1m" / "BTCUSDT_1m_2020-12-25_to_2021-01-20.csv"
        _write_source_csv(source_csv, base - timedelta(days=7))

    summary_payload = {
        "ending_equity": 26000.0,
        "current_equity": 26000.0,
        "active_trading_capital": 21000.0,
        "locked_profit": 5000.0,
        "floating_profit": 0.0,
        "trade_count": len(trades),
        "metrics": {"profit_factor": 1.18, "avg_r": 0.11, "max_drawdown_pct": 0.16},
    }
    if source_csv is not None:
        summary_payload["source_csv"] = str(source_csv)
    (broad_ledger_root / "summary.json").write_text(json.dumps(summary_payload), encoding="utf-8")

    (broad_root / "broad_historical_replay_summary.json").write_text(
        json.dumps(
            {
                "source_data_start": "2020-12-25T00:00:00",
                "source_data_end": "2021-01-20T00:00:00",
                "generated_ledger_start": "2021-01-01T00:00:00",
                "generated_ledger_end": "2021-01-12T00:00:00",
                "trade_count": len(trades),
                "long_trade_count": 2,
                "short_trade_count": 6,
                "coverage_sufficient_for_frozen_patch_validation": True,
            }
        ),
        encoding="utf-8",
    )
    (broad_diag_root / "replay_health_report.json").write_text(json.dumps({"successful_replay": True, "safe_for_frozen_patch_validation": True}), encoding="utf-8")
    (broad_report_root / "next_research_recommendation.json").write_text(json.dumps({"next_step": "APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER"}), encoding="utf-8")
    (frozen_root / "frozen_patch_rules.json").write_text(
        json.dumps(
            {
                "frozen_patch_candidate": "BAD_LONGS_DISABLED_ONLY_PROVEN_SHORTS_KEPT",
                "disabled_long_failure_modes": [
                    "LONG_COST_DOMINATED",
                    "LONG_COUNTER_HTF",
                    "LONG_DANGER_TOO_HIGH",
                    "LONG_EMA_FAKEOUT",
                    "LONG_OVERHEAD_RESISTANCE_TOO_CLOSE",
                    "LONG_TINY_STOP_TRAP",
                    "LONG_VWAP_FAKEOUT",
                    "LONG_WEAK_RECLAIM",
                ],
                "short_bucket_rule": {"matched_archetype_keys": ["short|sweep_high|elite_convexity|resistance|equal_highs"]},
                "frozen_without_retuning": True,
            }
        ),
        encoding="utf-8",
    )

    write_broad_frozen_patch_validation(BroadFrozenPatchValidationConfig(package_root=package_root, output_root=output_root / "broad_frozen_patch_validation_001"))
    write_broad_patch_bluntness_audit(BroadPatchBluntnessAuditConfig(package_root=package_root, output_root=output_root / "broad_patch_bluntness_audit_001"))
    write_broad_patch_accounting_and_short_rescue_audit(BroadPatchAccountingAndShortRescueAuditConfig(package_root=package_root, output_root=output_root / "broad_patch_accounting_and_short_rescue_audit_001"))
    write_rolling_five_year_mission_viability_audit(RollingFiveYearMissionViabilityAuditConfig(package_root=package_root, output_root=output_root / "rolling_five_year_mission_viability_audit_001"))
    write_equal_highs_liquidity_sweep_rescue_forensic_audit(EqualHighsLiquiditySweepRescueForensicAuditConfig(package_root=package_root, output_root=output_root / "equal_highs_liquidity_sweep_rescue_forensic_audit_001"))
    write_support_room_short_rescue_repair_audit(SupportRoomShortRescueRepairAuditConfig(package_root=package_root, output_root=output_root / "support_room_short_rescue_repair_audit_001"))
    return package_root, source_csv


class NativePreEntrySRFeatureEnrichmentAuditTests(unittest.TestCase):
    def test_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, _ = _seed_small_fixture(Path(tmpdir), with_source=True)
            output_root = package_root / "output"
            result = write_native_pre_entry_sr_feature_enrichment_audit(
                NativePreEntrySRFeatureEnrichmentAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_pre_entry_sr_feature_enrichment_audit_001",
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["paper_allowed"])
            self.assertFalse(summary["live_allowed"])
            self.assertFalse(summary["behavior_change_allowed"])
            self.assertIn(
                summary["final_classification"],
                {
                    "SR_ENRICHMENT_BLOCKED_BY_MISSING_DATA",
                    "SR_ENRICHMENT_AVAILABLE_BUT_WEAK",
                    "SR_ENRICHMENT_IMPROVES_BUT_NOT_MISSION_MOVING",
                    "SR_ENRICHMENT_PROMISING_RESEARCH_ONLY",
                    "SR_ENRICHMENT_READY_FOR_NATIVE_REPLAY_RESEARCH_ONLY",
                    "SR_ENRICHMENT_REJECTED",
                },
            )

            diagnostics_root = output_root / "native_pre_entry_sr_feature_enrichment_audit_001" / "diagnostics"
            self.assertTrue((diagnostics_root / "candle_source_discovery.json").exists())
            self.assertTrue((diagnostics_root / "pre_entry_data_availability_report.json").exists())
            self.assertTrue((diagnostics_root / "pre_entry_sr_feature_no_leakage_check.json").exists())
            self.assertTrue((diagnostics_root / "enriched_rescue_prototype_definitions.json").exists())
            self.assertTrue((diagnostics_root / "enriched_rescue_prototype_results.json").exists())

            leakage = json.loads((diagnostics_root / "pre_entry_sr_feature_no_leakage_check.json").read_text(encoding="utf-8"))
            self.assertTrue(leakage["final_no_leakage_verdict"])

            with (diagnostics_root / "enriched_trade_pre_entry_sr_features.csv").open("r", encoding="utf-8") as handle:
                self.assertTrue(list(csv.DictReader(handle)))
            with (diagnostics_root / "enriched_removed_short_pre_entry_sr_features.csv").open("r", encoding="utf-8") as handle:
                self.assertTrue(list(csv.DictReader(handle)))
            with (diagnostics_root / "enriched_rescue_prototype_results.csv").open("r", encoding="utf-8") as handle:
                self.assertTrue(list(csv.DictReader(handle)))

    def test_missing_candle_source_produces_safe_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root, _ = _seed_small_fixture(Path(tmpdir), with_source=False)
            output_root = package_root / "output"
            result = write_native_pre_entry_sr_feature_enrichment_audit(
                NativePreEntrySRFeatureEnrichmentAuditConfig(
                    package_root=package_root,
                    output_root=output_root / "native_pre_entry_sr_feature_enrichment_audit_001",
                )
            )
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            self.assertEqual("SR_ENRICHMENT_BLOCKED_BY_MISSING_DATA", summary["final_classification"])


if __name__ == "__main__":
    unittest.main()
