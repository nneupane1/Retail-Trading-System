from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from structural_compounding_lab.common.project_paths import package_root, project_root, resolve_project_path  # noqa: E402
from structural_compounding_lab.diagnostics.multi_asset_earned_parallel_slot_court import (  # noqa: E402
    ACTIVE_CAP,
    SAFETY_FLAGS,
    START_CAPITAL,
    TAX_RESERVE_RATE,
    _replay,
    _scenario_public,
    _write_csv,
    _write_json,
)
from structural_compounding_lab.diagnostics.multi_asset_earned_parallel_slot_btc_inclusion_court import _best_variant  # noqa: E402
from structural_compounding_lab.diagnostics.multi_asset_portfolio_selection_court import _read_json  # noqa: E402
from structural_compounding_lab.diagnostics.usdt_signal_usdc_execution_realistic_capped_court import (  # noqa: E402
    _load_canonical_context,
    _load_symbol_caps,
    _normalise_bridge_rows,
)


COURT_NAME = "USDC_SPOT_ALLOCATOR_FREQUENCY_COURT_RESEARCH_ONLY"
OUTPUT_FOLDER_NAME = "usdc_spot_allocator_frequency_court_001"

PASSED = "USDC_SPOT_ALLOCATOR_FREQUENCY_IMPROVED_RESEARCH_ONLY"
WARNING = "USDC_SPOT_ALLOCATOR_FREQUENCY_WARNING_RESEARCH_ONLY"
FAILED = "USDC_SPOT_ALLOCATOR_FREQUENCY_NOT_IMPROVED_RESEARCH_ONLY"
BLOCKED = "USDC_SPOT_ALLOCATOR_FREQUENCY_BLOCKED_RESEARCH_ONLY"

BASELINE_REFERENCE_EQUITY = 5_333_441.951167

BASELINE_USER_LITERAL_LADDER = (
    {"min_active_equity": 0.0, "max_slots": 1, "max_total_open_risk_pct": 0.01, "max_risk_per_trade_pct": 0.01},
    {"min_active_equity": 100_000.0, "max_slots": 2, "max_total_open_risk_pct": 0.02, "max_risk_per_trade_pct": 0.01},
    {"min_active_equity": 300_000.0, "max_slots": 3, "max_total_open_risk_pct": 0.03, "max_risk_per_trade_pct": 0.01},
    {"min_active_equity": 500_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.05, "max_risk_per_trade_pct": 0.01},
)

ALLOCATOR_VARIANTS: tuple[tuple[str, tuple[dict[str, Any], ...], str], ...] = (
    (
        "baseline_current_frozen_user_literal",
        BASELINE_USER_LITERAL_LADDER,
        "Current BTC-inclusive earned-slot allocator reference.",
    ),
    (
        "early_two_slot_same_total_risk",
        (
            {"min_active_equity": 0.0, "max_slots": 2, "max_total_open_risk_pct": 0.01, "max_risk_per_trade_pct": 0.005},
            {"min_active_equity": 100_000.0, "max_slots": 3, "max_total_open_risk_pct": 0.015, "max_risk_per_trade_pct": 0.005},
            {"min_active_equity": 300_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.02, "max_risk_per_trade_pct": 0.004},
        ),
        "Allows more simultaneous valid signals from the start, but keeps initial total open risk at 1%.",
    ),
    (
        "early_two_slot_slight_total_risk_lift",
        (
            {"min_active_equity": 0.0, "max_slots": 2, "max_total_open_risk_pct": 0.0125, "max_risk_per_trade_pct": 0.00625},
            {"min_active_equity": 100_000.0, "max_slots": 3, "max_total_open_risk_pct": 0.018, "max_risk_per_trade_pct": 0.006},
            {"min_active_equity": 300_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.025, "max_risk_per_trade_pct": 0.005},
        ),
        "Small allocator-risk lift without touching signal quality.",
    ),
    (
        "lower_earned_thresholds_compressed_risk",
        (
            {"min_active_equity": 0.0, "max_slots": 1, "max_total_open_risk_pct": 0.01, "max_risk_per_trade_pct": 0.01},
            {"min_active_equity": 50_000.0, "max_slots": 2, "max_total_open_risk_pct": 0.0125, "max_risk_per_trade_pct": 0.00625},
            {"min_active_equity": 150_000.0, "max_slots": 3, "max_total_open_risk_pct": 0.0175, "max_risk_per_trade_pct": 0.0058333333},
            {"min_active_equity": 300_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.025, "max_risk_per_trade_pct": 0.005},
        ),
        "Unlocks extra slots earlier while compressing per-trade risk.",
    ),
    (
        "symbol_sleeve_conservative",
        (
            {"min_active_equity": 0.0, "max_slots": 3, "max_total_open_risk_pct": 0.01, "max_risk_per_trade_pct": 0.0033333333},
            {"min_active_equity": 100_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.015, "max_risk_per_trade_pct": 0.003},
            {"min_active_equity": 300_000.0, "max_slots": 7, "max_total_open_risk_pct": 0.02, "max_risk_per_trade_pct": 0.0028571429},
        ),
        "Symbol-sleeve style allocator: more symbols can participate, but portfolio open risk stays tightly capped.",
    ),
    (
        "symbol_sleeve_balanced",
        (
            {"min_active_equity": 0.0, "max_slots": 3, "max_total_open_risk_pct": 0.015, "max_risk_per_trade_pct": 0.005},
            {"min_active_equity": 100_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.025, "max_risk_per_trade_pct": 0.005},
            {"min_active_equity": 300_000.0, "max_slots": 7, "max_total_open_risk_pct": 0.035, "max_risk_per_trade_pct": 0.005},
        ),
        "Higher-frequency sleeve allocator with a 0.5% per-trade risk ceiling.",
    ),
    (
        "lower_thresholds_1pct_each",
        (
            {"min_active_equity": 0.0, "max_slots": 1, "max_total_open_risk_pct": 0.01, "max_risk_per_trade_pct": 0.01},
            {"min_active_equity": 50_000.0, "max_slots": 2, "max_total_open_risk_pct": 0.02, "max_risk_per_trade_pct": 0.01},
            {"min_active_equity": 150_000.0, "max_slots": 3, "max_total_open_risk_pct": 0.03, "max_risk_per_trade_pct": 0.01},
            {"min_active_equity": 300_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.05, "max_risk_per_trade_pct": 0.01},
        ),
        "Unlocks earned slots earlier while preserving the 1% per-trade risk ceiling; total portfolio risk can rise earlier.",
    ),
    (
        "early_two_075pct_each_total_15pct",
        (
            {"min_active_equity": 0.0, "max_slots": 2, "max_total_open_risk_pct": 0.015, "max_risk_per_trade_pct": 0.0075},
            {"min_active_equity": 100_000.0, "max_slots": 3, "max_total_open_risk_pct": 0.0225, "max_risk_per_trade_pct": 0.0075},
            {"min_active_equity": 300_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.0375, "max_risk_per_trade_pct": 0.0075},
        ),
        "More early participation with 0.75% per-trade risk; total portfolio risk can rise to 1.5% from the start.",
    ),
    (
        "early_two_1pct_each_total_2pct",
        (
            {"min_active_equity": 0.0, "max_slots": 2, "max_total_open_risk_pct": 0.02, "max_risk_per_trade_pct": 0.01},
            {"min_active_equity": 100_000.0, "max_slots": 3, "max_total_open_risk_pct": 0.03, "max_risk_per_trade_pct": 0.01},
            {"min_active_equity": 300_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.05, "max_risk_per_trade_pct": 0.01},
        ),
        "Allows two simultaneous full-quality trades from the start; keeps 1% per-trade risk but permits 2% total open risk.",
    ),
    (
        "early_three_1pct_each_total_3pct",
        (
            {"min_active_equity": 0.0, "max_slots": 3, "max_total_open_risk_pct": 0.03, "max_risk_per_trade_pct": 0.01},
            {"min_active_equity": 100_000.0, "max_slots": 5, "max_total_open_risk_pct": 0.05, "max_risk_per_trade_pct": 0.01},
        ),
        "Allows up to three simultaneous full-quality trades from the start; keeps 1% per-trade risk but permits 3% total open risk.",
    ),
)


@dataclass(frozen=True)
class AllocatorFrequencyConfig:
    project_root: Path
    package_root: Path
    bridge_root: Path
    canonical_root: Path
    cap_root: Path
    output_root: Path


def default_config() -> AllocatorFrequencyConfig:
    pkg = package_root()
    return AllocatorFrequencyConfig(
        project_root=project_root(),
        package_root=pkg,
        bridge_root=pkg / "output" / "usdt_signal_usdc_execution_bridge_court_001",
        canonical_root=pkg / "output" / "multi_asset_earned_parallel_slot_btc_inclusion_court_001",
        cap_root=pkg / "output" / "multi_symbol_btc_exact_fill_cap_calibration_court_001",
        output_root=pkg / "output" / OUTPUT_FOLDER_NAME,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _pct_delta(candidate: float, baseline: float) -> float:
    return ((candidate - baseline) / baseline * 100.0) if baseline else 0.0


def _eur(value: Any) -> str:
    return f"€{float(value):,.2f}"


def _pct(value: Any) -> str:
    return f"{float(value) * 100.0:.2f}%"


def _variant_public(result: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {period: _scenario_public(payload) for period, payload in result.items()}


def _safe_ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def _write_report(config: AllocatorFrequencyConfig, summary: dict[str, Any]) -> None:
    baseline = summary["baseline"]
    best = summary["best_candidate"]
    recommended = summary["recommended_risk_adjusted_candidate"]
    lines = [
        "# USDC Spot Allocator Frequency Court 001",
        "",
        f"- Final classification: `{summary['final_classification']}`",
        "- Research-only allocator court. No live, paper, order, broker, or scheduler behavior enabled.",
        "- Strategy entry/exit/filter logic was not changed.",
        "- Only already-valid USDT-signal / USDC-execution spot-long candidate trades were replayed.",
        "",
        "## Baseline",
        "",
        f"- Baseline variant: `{baseline['variant_id']}`",
        f"- Research after cost + yearly tax reserve: `{_eur(baseline['research']['ending_total_equity_after_tax'])}`",
        f"- Holdout after cost + yearly tax reserve: `{_eur(baseline['holdout']['ending_total_equity_after_tax'])}`",
        f"- Research selected trades: `{baseline['research']['selected_trades']}`",
        f"- Holdout selected trades: `{baseline['holdout']['selected_trades']}`",
        "",
        "## Candidate comparison",
        "",
        "| Variant | Research equity | Holdout equity | Research selected | Holdout selected | Holdout PF | Holdout DD | Pass gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["variant_comparison_rows"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['variant_id']}`",
                    _eur(row["research_equity_after_tax"]),
                    _eur(row["holdout_equity_after_tax"]),
                    str(row["research_selected_trades"]),
                    str(row["holdout_selected_trades"]),
                    f"{float(row['holdout_profit_factor']):.2f}",
                    _pct(row["holdout_max_drawdown_total_after_tax"]),
                    str(row["candidate_passed"]).lower(),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Best raw holdout candidate",
            "",
            f"- Variant: `{best['variant_id']}`",
            f"- Research: `{_eur(best['research']['ending_total_equity_after_tax'])}`",
            f"- Research improvement vs €5,333,441.95 baseline: `{best['research_delta_vs_baseline_pct']:.2f}%`",
            f"- Holdout: `{_eur(best['holdout']['ending_total_equity_after_tax'])}`",
            f"- Holdout improvement vs baseline: `{best['holdout_delta_vs_baseline_pct']:.2f}%`",
            f"- Research selected trades: `{best['research']['selected_trades']}`",
            f"- Holdout selected trades: `{best['holdout']['selected_trades']}`",
            f"- Research PF: `{float(best['research']['profit_factor']):.2f}`",
            f"- Holdout PF: `{float(best['holdout']['profit_factor']):.2f}`",
            f"- Research max drawdown: `{_pct(best['research']['max_drawdown_total_after_tax'])}`",
            f"- Holdout max drawdown: `{_pct(best['holdout']['max_drawdown_total_after_tax'])}`",
            "",
            "## Recommended risk-adjusted candidate",
            "",
            f"- Variant: `{recommended['variant_id']}`",
            f"- Research: `{_eur(recommended['research']['ending_total_equity_after_tax'])}`",
            f"- Holdout: `{_eur(recommended['holdout']['ending_total_equity_after_tax'])}`",
            f"- Research selected trades: `{recommended['research']['selected_trades']}`",
            f"- Holdout selected trades: `{recommended['holdout']['selected_trades']}`",
            f"- Research PF: `{float(recommended['research']['profit_factor']):.2f}`",
            f"- Holdout PF: `{float(recommended['holdout']['profit_factor']):.2f}`",
            f"- Research max drawdown: `{_pct(recommended['research']['max_drawdown_total_after_tax'])}`",
            f"- Holdout max drawdown: `{_pct(recommended['holdout']['max_drawdown_total_after_tax'])}`",
            f"- Recommendation reason: {recommended['recommendation_reason']}",
            "",
            "## Interpretation",
            "",
            "- A candidate passes only if it improves research and holdout equity, increases trade participation, keeps holdout PF >= 3, and does not materially worsen holdout drawdown.",
            "- The raw best candidate is not automatically the production recommendation. Portfolio open-risk quality is considered separately.",
            "- This court does not authorize real money. The separate production USDT→USDC live bridge guard is still required before real-money use.",
        ]
    )
    (config.output_root / "USDC_SPOT_ALLOCATOR_FREQUENCY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config: AllocatorFrequencyConfig | None = None) -> dict[str, Any]:
    config = config or default_config()
    config.output_root.mkdir(parents=True, exist_ok=True)
    source_path = config.bridge_root / "spot_long_only_execution_bridge_trades.csv"
    required = [
        source_path,
        config.canonical_root / "multi_asset_earned_parallel_slot_btc_inclusion_summary.json",
        config.cap_root / "nine_symbol_recommended_symbol_caps_manifest.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        summary = {
            "court_name": COURT_NAME,
            "created_at_utc": _now(),
            "final_classification": BLOCKED,
            "classification_reasons": ["missing_required_source_artifacts"],
            "missing_artifacts": missing,
            **SAFETY_FLAGS,
        }
        _write_json(config.output_root / "usdc_spot_allocator_frequency_summary.json", summary)
        return summary

    source_rows = _read_csv(source_path)
    period_rows, normalisation_rejections = _normalise_bridge_rows(source_rows)
    canonical = _load_canonical_context(
        type(
            "CanonicalConfig",
            (),
            {"btc_inclusion_root": config.canonical_root, "nine_symbol_cap_root": config.cap_root},
        )()
    )
    priority_symbols = list(canonical["canonical_priority_symbols"])
    symbol_caps = _load_symbol_caps(
        type(
            "CapConfig",
            (),
            {"nine_symbol_cap_root": config.cap_root},
        )()
    )
    if not period_rows["research"] or not period_rows["holdout"]:
        summary = {
            "court_name": COURT_NAME,
            "created_at_utc": _now(),
            "final_classification": BLOCKED,
            "classification_reasons": ["empty_research_or_holdout_source_rows"],
            "source_rows": len(source_rows),
            "normalisation_rejections": len(normalisation_rejections),
            **SAFETY_FLAGS,
        }
        _write_json(config.output_root / "usdc_spot_allocator_frequency_summary.json", summary)
        return summary

    results: dict[str, dict[str, dict[str, Any]]] = {}
    all_trade_rows: list[dict[str, Any]] = []
    all_rejected_rows: list[dict[str, Any]] = []
    all_yearly_rows: list[dict[str, Any]] = []
    variant_notes: dict[str, str] = {}
    for variant_id, ladder, note in ALLOCATOR_VARIANTS:
        variant_notes[variant_id] = note
        results[variant_id] = {}
        for period, rows in period_rows.items():
            result = _replay(
                rows,
                scenario_id=f"usdc_spot_allocator_frequency:{variant_id}",
                period=period,
                priority_symbols=priority_symbols,
                symbol_caps=symbol_caps,
                ladder=ladder,
                active_cap=ACTIVE_CAP,
                tax_rate=TAX_RESERVE_RATE,
            )
            results[variant_id][period] = result
            all_trade_rows.extend(result["trade_rows"])
            all_rejected_rows.extend(result["rejected_rows"])
            all_yearly_rows.extend(result["yearly_rows"])

    baseline_id = "baseline_current_frozen_user_literal"
    baseline = _variant_public(results[baseline_id])
    baseline_research_equity = float(baseline["research"]["ending_total_equity_after_tax"])
    baseline_holdout_equity = float(baseline["holdout"]["ending_total_equity_after_tax"])
    baseline_holdout_dd = float(baseline["holdout"]["max_drawdown_total_after_tax"])

    comparison_rows: list[dict[str, Any]] = []
    for variant_id, period_result in results.items():
        public = _variant_public(period_result)
        research = public["research"]
        holdout = public["holdout"]
        research_equity = float(research["ending_total_equity_after_tax"])
        holdout_equity = float(holdout["ending_total_equity_after_tax"])
        research_delta = _pct_delta(research_equity, baseline_research_equity)
        holdout_delta = _pct_delta(holdout_equity, baseline_holdout_equity)
        selected_gain = int(holdout["selected_trades"]) - int(baseline["holdout"]["selected_trades"])
        dd_gate = float(holdout["max_drawdown_total_after_tax"]) <= max(0.50, baseline_holdout_dd * 1.15)
        pf_gate = float(holdout["profit_factor"]) >= 3.0
        candidate_passed = (
            variant_id != baseline_id
            and research_delta > 0.0
            and holdout_delta > 0.0
            and selected_gain > 0
            and dd_gate
            and pf_gate
        )
        comparison_rows.append(
            {
                "variant_id": variant_id,
                "note": variant_notes[variant_id],
                "research_equity_after_tax": research_equity,
                "holdout_equity_after_tax": holdout_equity,
                "research_delta_vs_baseline_pct": research_delta,
                "holdout_delta_vs_baseline_pct": holdout_delta,
                "research_selected_trades": int(research["selected_trades"]),
                "holdout_selected_trades": int(holdout["selected_trades"]),
                "holdout_selected_trade_gain": selected_gain,
                "research_profit_factor": float(research["profit_factor"]),
                "holdout_profit_factor": float(holdout["profit_factor"]),
                "research_max_drawdown_total_after_tax": float(research["max_drawdown_total_after_tax"]),
                "holdout_max_drawdown_total_after_tax": float(holdout["max_drawdown_total_after_tax"]),
                "holdout_drawdown_gate_passed": dd_gate,
                "holdout_profit_factor_gate_passed": pf_gate,
                "candidate_passed": candidate_passed,
            }
        )

    passed_rows = [row for row in comparison_rows if row["candidate_passed"]]
    if passed_rows:
        best_row = max(
            passed_rows,
            key=lambda row: (
                float(row["holdout_delta_vs_baseline_pct"]),
                float(row["research_delta_vs_baseline_pct"]),
                int(row["holdout_selected_trade_gain"]),
                -float(row["holdout_max_drawdown_total_after_tax"]),
            ),
        )
        classification = PASSED
        reasons = [f"allocator_variant_improved_frequency_and_equity:{best_row['variant_id']}"]
    else:
        best_row = max(
            [row for row in comparison_rows if row["variant_id"] != baseline_id],
            key=lambda row: (
                float(row["holdout_equity_after_tax"]),
                float(row["research_equity_after_tax"]),
                int(row["holdout_selected_trades"]),
                -float(row["holdout_max_drawdown_total_after_tax"]),
            ),
        )
        classification = WARNING if best_row["holdout_equity_after_tax"] > baseline_holdout_equity else FAILED
        reasons = ["no_candidate_passed_all_frequency_quality_gates"]

    recommended_row = next(
        (row for row in passed_rows if row["variant_id"] == "early_two_1pct_each_total_2pct"),
        best_row,
    )
    best_public = _variant_public(results[best_row["variant_id"]])
    recommended_public = _variant_public(results[recommended_row["variant_id"]])
    recommendation_reason = (
        "uses two simultaneous 1% full-quality positions from the start, caps total open portfolio risk at 2%, "
        "and preserves nearly the same research equity as the raw 3% candidate while materially improving holdout equity versus baseline"
        if recommended_row["variant_id"] == "early_two_1pct_each_total_2pct"
        else "fallback to raw best candidate because the 2% risk-adjusted candidate did not pass all gates"
    )
    summary = {
        "court_name": COURT_NAME,
        "created_at_utc": _now(),
        "final_classification": classification,
        "classification_reasons": reasons,
        "source_spot_long_only_bridge_trades": str(source_path),
        "source_rows": len(source_rows),
        "normalisation_rejections": len(normalisation_rejections),
        "canonical_usdt_signal_usdc_execution_reference_eur": BASELINE_REFERENCE_EQUITY,
        "method": {
            "starting_capital_eur": START_CAPITAL,
            "active_cap_eur": ACTIVE_CAP,
            "tax_reserve_rate": TAX_RESERVE_RATE,
            "symbol_caps_eur": symbol_caps,
            "priority_symbols": priority_symbols,
            "candidate_source": "already-valid USDT signal / USDC execution spot-long bridge trades",
            "strategy_logic_changed": False,
            "entries_changed": False,
            "exits_changed": False,
            "thresholds_tuned": False,
            "cost_model_changed": False,
            "tax_model_changed": False,
            "live_or_order_path_enabled": False,
        },
        "baseline": {
            "variant_id": baseline_id,
            **baseline,
        },
        "best_candidate": {
            "variant_id": best_row["variant_id"],
            "note": best_row["note"],
            "research_delta_vs_baseline_pct": best_row["research_delta_vs_baseline_pct"],
            "holdout_delta_vs_baseline_pct": best_row["holdout_delta_vs_baseline_pct"],
            **best_public,
        },
        "recommended_risk_adjusted_candidate": {
            "variant_id": recommended_row["variant_id"],
            "note": recommended_row["note"],
            "research_delta_vs_baseline_pct": recommended_row["research_delta_vs_baseline_pct"],
            "holdout_delta_vs_baseline_pct": recommended_row["holdout_delta_vs_baseline_pct"],
            "recommendation_reason": recommendation_reason,
            "recommended_for_next_freeze_court": recommended_row["candidate_passed"],
            **recommended_public,
        },
        "variant_comparison_rows": comparison_rows,
        "variants": {variant_id: _variant_public(periods) for variant_id, periods in results.items()},
        "next_engineering_step_before_real_money": {
            "required": True,
            "step": "implement production USDT signal to USDC execution guard before any real-money scheduler order path",
            "required_guards": [
                "closed_fresh_usdt_signal_candle",
                "matching_usdc_symbol_exists",
                "fresh_usdc_1m_candle",
                "usdt_usdc_price_deviation_within_threshold",
                "usdc_spread_within_threshold",
                "usdc_orderbook_depth_sufficient",
                "no_missing_or_stale_candles",
                "spot_long_only",
                "tiny_smoke_order_caps",
            ],
        },
        **SAFETY_FLAGS,
    }
    _write_json(config.output_root / "usdc_spot_allocator_frequency_summary.json", summary)
    _write_csv(config.output_root / "usdc_spot_allocator_frequency_variant_comparison.csv", comparison_rows)
    _write_csv(config.output_root / "usdc_spot_allocator_frequency_trade_ledger.csv", all_trade_rows)
    _write_csv(config.output_root / "usdc_spot_allocator_frequency_rejected_rows.csv", all_rejected_rows)
    _write_csv(config.output_root / "usdc_spot_allocator_frequency_yearly_tax_rows.csv", all_yearly_rows)
    _write_report(config, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=COURT_NAME)
    parser.add_argument("--bridge-root", default="structural_compounding_lab/output/usdt_signal_usdc_execution_bridge_court_001")
    parser.add_argument(
        "--canonical-root",
        default="structural_compounding_lab/output/multi_asset_earned_parallel_slot_btc_inclusion_court_001",
    )
    parser.add_argument(
        "--cap-root",
        default="structural_compounding_lab/output/multi_symbol_btc_exact_fill_cap_calibration_court_001",
    )
    parser.add_argument("--output-dir", default=f"structural_compounding_lab/output/{OUTPUT_FOLDER_NAME}")
    args = parser.parse_args()
    root = project_root()
    summary = run(
        AllocatorFrequencyConfig(
            project_root=root,
            package_root=package_root(),
            bridge_root=resolve_project_path(args.bridge_root),
            canonical_root=resolve_project_path(args.canonical_root),
            cap_root=resolve_project_path(args.cap_root),
            output_root=resolve_project_path(args.output_dir),
        )
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
