from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from backtest.checkpoint import BacktestCheckpointStore
from capital.phase1_diagnostics import diagnostics_report_paths
from common.runtime_readiness import build_runtime_readiness

PHASE_1_EVIDENCE_REVIEW = "phase_1_evidence_review"


def review_output_dir(config) -> Path:
    return diagnostics_report_paths(config)["diagnostics_summary"].parent / "review"


def review_report_paths(config) -> dict[str, Path]:
    root = review_output_dir(config)
    return {
        "json": root / "phase1_evidence_review.json",
        "markdown": root / "phase1_evidence_review.md",
        "phase2_brief": root / "phase2_experiment_brief.md",
        "status": root / "status.json",
        "progress": root / "scenario_progress.json",
    }


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        frame = pd.read_csv(path).fillna(pd.NA)
    except Exception:
        return []
    return frame.to_dict(orient="records")


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip()
    return text or None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return float(number)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def _config_h1_short_override_active(config) -> bool:
    allowed = config.get(
        "live_sim",
        "paper_portfolio",
        "strategy_allowed_sides",
        "h1_execution",
        default=[],
    )
    return "short" in [str(item).lower() for item in list(allowed or [])]


def _config_six_h_enabled(config) -> bool:
    return bool(config.get("strategy", "h6_standard", "enabled", default=False)) or bool(
        config.get("strategy", "h6_moonshot", "enabled", default=False)
    )


def _source_fingerprint(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        payload[key] = {
            "path": str(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else None,
            "mtime_utc": (
                pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").isoformat()
                if path.exists()
                else None
            ),
        }
    return payload


def _distribution(
    rows: list[dict[str, Any]],
    *,
    key: str,
    limit: int = 10,
    value_key: str | None = None,
) -> list[dict[str, Any]]:
    total_rows = len(rows)
    counter: Counter[str] = Counter()
    value_sums: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        bucket = _safe_text(row.get(key)) or "null"
        counter[bucket] += 1
        if value_key is not None:
            value = _safe_float(row.get(value_key))
            if value is not None:
                value_sums[bucket] += value
    payload: list[dict[str, Any]] = []
    for label, count in counter.most_common(limit):
        item = {
            key: label,
            "count": int(count),
            "share": (count / total_rows) if total_rows else 0.0,
        }
        if value_key is not None:
            item[f"total_{value_key}"] = float(value_sums.get(label, 0.0))
        payload.append(item)
    return payload


def _top_winner_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "total_rows": 0,
            "total_pnl": 0.0,
            "total_R": 0.0,
            "top_10_pnl_share": None,
            "largest_strategy_share": None,
            "largest_symbol_share": None,
            "largest_score_bucket_share": None,
        }
    pnl_values = [(_safe_float(row.get("pnl")) or 0.0) for row in rows]
    total_pnl = float(sum(pnl_values))
    total_r = float(sum((_safe_float(row.get("R")) or 0.0) for row in rows))
    top_10_pnl = sum(sorted(pnl_values, reverse=True)[:10])
    strategy_distribution = _distribution(rows, key="strategy_type", limit=1, value_key="pnl")
    symbol_distribution = _distribution(rows, key="symbol", limit=1, value_key="pnl")
    bucket_distribution = _distribution(rows, key="score_bucket", limit=1, value_key="pnl")
    return {
        "total_rows": len(rows),
        "total_pnl": total_pnl,
        "total_R": total_r,
        "top_10_pnl_share": (top_10_pnl / total_pnl) if total_pnl else None,
        "largest_strategy_share": strategy_distribution[0] if strategy_distribution else None,
        "largest_symbol_share": symbol_distribution[0] if symbol_distribution else None,
        "largest_score_bucket_share": bucket_distribution[0] if bucket_distribution else None,
    }


def _strategy_bucket_summary(groups: list[dict[str, Any]]) -> dict[str, Any]:
    groups_with_pf = [row for row in groups if _safe_float(row.get("profit_factor")) is not None]
    groups_with_min_trades = [
        row
        for row in groups_with_pf
        if int(_safe_float(row.get("trade_count")) or 0) >= 20
    ]
    ranked_pf = sorted(
        groups_with_pf,
        key=lambda row: _safe_float(row.get("profit_factor")) or -999999.0,
        reverse=True,
    )
    weakest_pf = sorted(
        groups_with_pf,
        key=lambda row: _safe_float(row.get("profit_factor")) or 999999.0,
    )
    ranked_total_r = sorted(
        groups,
        key=lambda row: _safe_float(row.get("total_R")) or -999999.0,
        reverse=True,
    )
    ranked_avg_r = sorted(
        groups_with_min_trades,
        key=lambda row: _safe_float(row.get("avg_R")) or -999999.0,
        reverse=True,
    )
    return {
        "best_by_profit_factor": ranked_pf[:5],
        "worst_by_profit_factor": weakest_pf[:5],
        "best_by_total_R": ranked_total_r[:5],
        "best_by_avg_R_with_min_20_trades": ranked_avg_r[:5],
        "notes": [
            "groups are descriptive only and do not authorize policy changes",
            "small-sample groups should not be promoted directly into behavior",
        ],
    }


def _opportunity_cost_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [
        value
        for value in (_safe_float(row.get("opportunity_cost_score")) for row in rows)
        if value is not None
    ]
    by_competing_strategy = _distribution(rows, key="competing_strategy_type", limit=6)
    return {
        "observation_count": len(rows),
        "scored_observation_count": len(scores),
        "avg_opportunity_cost_score": (sum(scores) / len(scores)) if scores else None,
        "median_opportunity_cost_score": (median(scores) if scores else None),
        "max_opportunity_cost_score": (max(scores) if scores else None),
        "top_competing_strategies": by_competing_strategy,
        "notes": [
            "opportunity-cost scores are passive comparisons only",
            "no recycling behavior should be inferred from this artifact alone",
        ],
    }


def _review_decision(
    diagnostics_summary: dict[str, Any],
    rejection_rows: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    winner_rows: list[dict[str, Any]],
    strategy_groups: list[dict[str, Any]],
    opportunity_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str]]:
    top_rejection_reasons = _distribution(rejection_rows, key="rejection_reason", limit=8)
    top_blocking_constraints = _distribution(blocked_rows, key="blocking_constraint", limit=8)
    capital_pressure_count = sum(
        int(item["count"])
        for item in top_rejection_reasons
        if item.get("rejection_reason") in {"shared_risk_cap", "direction_cap", "asset_cap", "strategy_sleeve_cap"}
    )
    total_rejections = len(rejection_rows)
    capital_pressure_share = (capital_pressure_count / total_rejections) if total_rejections else 0.0
    scored_opportunity_count = sum(
        1
        for row in opportunity_rows
        if _safe_float(row.get("opportunity_cost_score")) is not None
    )
    hypothetical_support_count = sum(
        1
        for row in rejection_rows
        if _safe_float(row.get("hypothetical_R")) is not None
        or _safe_float(row.get("hypothetical_pnl")) is not None
        or _safe_text(row.get("would_have_won")) is not None
    )

    rationale = []
    not_allowed = []
    recommended = []
    if total_rejections >= 5000 and capital_pressure_share >= 0.20:
        rationale.append(
            "Capital/risk-related rejections are common enough to justify a structural backtest-only allocator experiment."
        )
    else:
        rationale.append(
            "Capital/risk-related rejections are visible, but not yet strong enough for anything beyond further passive study."
        )
    if scored_opportunity_count > 1000:
        rationale.append(
            "Opportunity-cost observations are numerous enough to support a small structural A/B experiment."
        )
    else:
        rationale.append(
            "Opportunity-cost scoring coverage is limited and should not drive behavior changes directly."
        )
    if hypothetical_support_count == 0:
        not_allowed.append(
            "Rejected-candidate artifacts do not contain validated counterfactual outcomes; blocked trades cannot be treated as proven winners."
        )
    if all((_safe_text(row.get("confidence")) or "low").lower() == "low" for row in blocked_rows[: min(len(blocked_rows), 200)]):
        not_allowed.append(
            "Capital-blocked-winner rows are low-confidence diagnostics only and do not justify direct risk or sizing changes."
        )
    not_allowed.append(
        "Phase 2 must not touch live paper runtime, real money, 6H routing, score multipliers, lifecycle logic, add-ons, recycling, or regime scaling."
    )

    phase2_justified = bool(total_rejections and blocked_rows and capital_pressure_share >= 0.20)
    overall = "moderate_backtest_only" if phase2_justified else "weak"
    recommended_next_phase = (
        "phase_2_backtest_only_capital_lane_experiment"
        if phase2_justified
        else "remain_in_phase_1_passive_research"
    )
    if phase2_justified:
        recommended.append(
            {
                "name": "lane_separation_backtest_only_ab_test",
                "recommended_next_phase": recommended_next_phase,
                "justified": True,
                "scope": [
                    "compare baseline routed stack versus one lane-separated candidate in backtest only",
                    "map core+swing_moonshot to core_flow, h1_execution to h1_tactical, and all 12H sleeves to htf_12h_structural",
                    "leave 6H disabled and excluded from the experiment",
                    "preserve the existing 1H short override exactly",
                    "keep total portfolio risk, per-trade sizing, thresholds, and sleeve health logic unchanged",
                    "measure only whether structural protection reduces starvation and improves portfolio metrics on the same validation windows",
                ],
                "success_metrics": [
                    "profit_factor",
                    "avg_R",
                    "median_daily_pnl",
                    "max_drawdown",
                    "change in shared_risk_cap and direction_cap rejection mix",
                    "change in 12H sleeve open-rate and contribution",
                ],
            }
        )
    return (
        {
            "overall": overall,
            "phase2_backtest_only_justified": phase2_justified,
            "recommended_next_phase": recommended_next_phase,
            "rationale": rationale,
        },
        recommended,
        not_allowed,
        [
            "All conclusions remain evidence candidates only.",
            "No trading behavior changed in Phase 1 review.",
        ],
    )


def _build_review_payload(config) -> dict[str, Any]:
    diag_paths = diagnostics_report_paths(config)
    diagnostics_summary = _read_json(diag_paths["diagnostics_summary"], {})
    rejection_rows = _read_csv(diag_paths["rejection_shadow_book"])
    blocked_rows = _read_csv(diag_paths["capital_blocked_winners"])
    winner_rows = _read_csv(diag_paths["top_winner_forensics"])
    strategy_bucket_payload = _read_json(diag_paths["strategy_bucket_capital_efficiency"], {})
    opportunity_payload = _read_json(diag_paths["opportunity_cost_report"], {})
    strategy_groups = list(strategy_bucket_payload.get("groups") or [])
    opportunity_rows = list(opportunity_payload.get("observations") or [])

    counts = {
        "rejection_shadow_book": len(rejection_rows),
        "capital_blocked_winners": len(blocked_rows),
        "top_winner_forensics": len(winner_rows),
        "strategy_bucket_capital_efficiency_groups": len(strategy_groups),
        "opportunity_cost_observations": len(opportunity_rows),
    }

    rejection_hypothetical_supported = sum(
        1
        for row in rejection_rows
        if _safe_float(row.get("hypothetical_R")) is not None
        or _safe_float(row.get("hypothetical_pnl")) is not None
        or _safe_text(row.get("would_have_won")) is not None
    )
    blocked_estimate_supported = sum(
        1
        for row in blocked_rows
        if _safe_float(row.get("estimated_R_available")) is not None
        or _safe_float(row.get("estimated_pnl_available")) is not None
    )
    top_pf_summary = _strategy_bucket_summary(strategy_groups)
    evidence_strength, recommendations, not_allowed, review_warnings = _review_decision(
        diagnostics_summary,
        rejection_rows,
        blocked_rows,
        winner_rows,
        strategy_groups,
        opportunity_rows,
    )

    winner_strategy_distribution = _distribution(winner_rows, key="strategy_type", limit=10, value_key="pnl")
    winner_score_bucket_distribution = _distribution(winner_rows, key="score_bucket", limit=10, value_key="pnl")

    return {
        "generated_at_utc": _now_utc(),
        "phase": PHASE_1_EVIDENCE_REVIEW,
        "source_artifacts": {
            key: str(path)
            for key, path in diag_paths.items()
        },
        "diagnostics_counts": counts,
        "data_quality": {
            "rejection_shadow_book": {
                "rows": len(rejection_rows),
                "rows_with_hypothetical_support": rejection_hypothetical_supported,
                "rows_without_hypothetical_support": len(rejection_rows) - rejection_hypothetical_supported,
                "notes": [
                    "rejected trades are not proven winners unless hypothetical outcome fields exist",
                ],
            },
            "capital_blocked_winners": {
                "rows": len(blocked_rows),
                "estimated_outcome_rows": blocked_estimate_supported,
                "low_confidence_rows": sum(
                    1 for row in blocked_rows if (_safe_text(row.get("confidence")) or "low").lower() == "low"
                ),
                "high_confidence_rows": sum(
                    1 for row in blocked_rows if (_safe_text(row.get("confidence")) or "").lower() == "high"
                ),
                "notes": [
                    "estimated blocked-winner outcomes are not present in the current artifact set",
                ],
            },
            "top_winner_forensics": {
                "rows": len(winner_rows),
                "rows_with_mfe": sum(1 for row in winner_rows if _safe_float(row.get("max_favorable_excursion")) is not None),
                "rows_with_mae": sum(1 for row in winner_rows if _safe_float(row.get("max_adverse_excursion")) is not None),
                "rows_with_add_on_points": sum(1 for row in winner_rows if (_safe_float(row.get("possible_add_on_points")) or 0.0) > 0.0),
                "rows_with_early_exit_flag_true": sum(1 for row in winner_rows if _truthy(row.get("early_exit_flag"))),
                "notes": [
                    "MFE/MAE/add-on/early-exit fields are mostly unavailable in the current passive artifact set",
                ],
            },
            "strategy_bucket_capital_efficiency": {
                "groups": len(strategy_groups),
                "groups_with_profit_factor": sum(1 for row in strategy_groups if _safe_float(row.get("profit_factor")) is not None),
            },
            "opportunity_cost_report": {
                "rows": len(opportunity_rows),
                "scored_rows": sum(1 for row in opportunity_rows if _safe_float(row.get("opportunity_cost_score")) is not None),
            },
        },
        "top_rejection_reasons": _distribution(rejection_rows, key="rejection_reason", limit=10),
        "rejection_shadow_book_breakdown": {
            "by_strategy": _distribution(rejection_rows, key="strategy_type", limit=10),
            "by_side": _distribution(rejection_rows, key="side", limit=10),
            "by_symbol": _distribution(rejection_rows, key="symbol", limit=10),
            "by_score_bucket": _distribution(rejection_rows, key="score_bucket", limit=10),
        },
        "top_blocking_constraints": _distribution(blocked_rows, key="blocking_constraint", limit=10),
        "capital_blocked_winner_breakdown": {
            "by_strategy": _distribution(blocked_rows, key="strategy_type", limit=10),
            "by_side": _distribution(blocked_rows, key="side", limit=10),
            "by_symbol": _distribution(blocked_rows, key="symbol", limit=10),
            "by_confidence": _distribution(blocked_rows, key="confidence", limit=10),
        },
        "top_winner_concentration": _top_winner_concentration(winner_rows),
        "winner_strategy_distribution": winner_strategy_distribution,
        "winner_score_bucket_distribution": winner_score_bucket_distribution,
        "winner_symbol_distribution": _distribution(winner_rows, key="symbol", limit=10, value_key="pnl"),
        "strategy_bucket_efficiency_summary": top_pf_summary,
        "opportunity_cost_summary": _opportunity_cost_summary(opportunity_rows),
        "evidence_strength": evidence_strength,
        "phase2_candidate_recommendations": recommendations,
        "phase2_not_allowed_yet_reasoning": not_allowed,
        "behavior_change_allowed": False,
        "real_money_allowed": False,
        "allocator_behavior_changed": False,
        "risk_behavior_changed": False,
        "sizing_behavior_changed": False,
        "entry_behavior_changed": False,
        "exit_behavior_changed": False,
        "thresholds_changed": False,
        "sleeves_changed": False,
        "six_h_enabled": _config_six_h_enabled(config),
        "h1_short_override_active": _config_h1_short_override_active(config),
        "warnings": list(dict.fromkeys([*list(diagnostics_summary.get("warnings") or []), *review_warnings])),
    }


def _render_review_markdown(payload: dict[str, Any]) -> str:
    counts = dict(payload.get("diagnostics_counts") or {})
    top_rejections = list(payload.get("top_rejection_reasons") or [])
    top_blocks = list(payload.get("top_blocking_constraints") or [])
    winner_concentration = dict(payload.get("top_winner_concentration") or {})
    evidence = dict(payload.get("evidence_strength") or {})
    recommendations = list(payload.get("phase2_candidate_recommendations") or [])
    not_allowed = list(payload.get("phase2_not_allowed_yet_reasoning") or [])
    winner_strategy_distribution = list(payload.get("winner_strategy_distribution") or [])
    winner_score_bucket_distribution = list(payload.get("winner_score_bucket_distribution") or [])
    strategy_efficiency = dict(payload.get("strategy_bucket_efficiency_summary") or {})
    opportunity_summary = dict(payload.get("opportunity_cost_summary") or {})
    data_quality = dict(payload.get("data_quality") or {})

    def _line_items(rows: list[dict[str, Any]], key: str) -> str:
        if not rows:
            return "- none"
        return "\n".join(
            f"- {row.get(key)}: {row.get('count')} ({(row.get('share') or 0.0):.1%})"
            for row in rows[:6]
        )

    brief_scope = recommendations[0]["scope"] if recommendations else []
    brief_scope_text = (
        "\n".join(f"- {item}" for item in brief_scope)
        if brief_scope
        else "- no Phase 2 scope recommended yet"
    )
    not_allowed_text = (
        "\n".join(f"- {item}" for item in not_allowed)
        if not_allowed
        else "- none"
    )

    return f"""# Phase 1 Evidence Review

## Executive summary

Phase 1 remains passive. The review found `{counts.get("rejection_shadow_book", 0)}` rejection-shadow rows and `{counts.get("capital_blocked_winners", 0)}` capital-blocked observations, with capital/risk pressure visible enough to justify a **backtest-only** Phase 2 lane-separation experiment. It does **not** justify live-paper mutation, real-money promotion, score multipliers, lifecycle changes, or recycling behavior.

## What the diagnostics prove

- Shared-cap and direction-related rejections are common in the current routed stack.
- Top winners are concentrated in the strongest score buckets, especially `0.9-1.0`.
- `12H` structural sleeves appear disproportionately represented in the top-winner set relative to their trade count.
- Opportunity-cost observations exist in useful volume for a future structural experiment.

## What the diagnostics do not prove

- Rejected trades are not proven winners unless hypothetical fields are populated.
- Capital-blocked-winner estimates are not high-confidence counterfactual truth.
- MFE, MAE, add-on, and early-exit conclusions are mostly unavailable from the current passive artifact set.
- No artifact authorizes production or live-paper behavior changes.

## Rejection shadow book findings

{_line_items(top_rejections, "rejection_reason")}

## Capital-blocked-winner findings

{_line_items(top_blocks, "blocking_constraint")}

## Top-winner forensics findings

- Top-winner rows reviewed: `{counts.get("top_winner_forensics", 0)}`
- Total top-winner PnL captured in review set: `{winner_concentration.get("total_pnl", 0.0):.2f}`
- Top 10 winners share of top-100 PnL: `{(winner_concentration.get("top_10_pnl_share") or 0.0):.1%}`
- Winner strategy distribution:
{_line_items(winner_strategy_distribution, "strategy_type")}
- Winner score-bucket distribution:
{_line_items(winner_score_bucket_distribution, "score_bucket")}

## Strategy x bucket efficiency findings

- Best by profit factor:
{_line_items(strategy_efficiency.get("best_by_profit_factor") or [], "strategy_type")}
- Worst by profit factor:
{_line_items(strategy_efficiency.get("worst_by_profit_factor") or [], "strategy_type")}

## Opportunity-cost findings

- Observations: `{opportunity_summary.get("observation_count", 0)}`
- Scored observations: `{opportunity_summary.get("scored_observation_count", 0)}`
- Average opportunity-cost score: `{(opportunity_summary.get("avg_opportunity_cost_score") or 0.0):.4f}`
- Median opportunity-cost score: `{(opportunity_summary.get("median_opportunity_cost_score") or 0.0):.4f}`
- Max opportunity-cost score: `{(opportunity_summary.get("max_opportunity_cost_score") or 0.0):.4f}`

## Data-quality limitations

- Rejection rows with hypothetical support: `{data_quality.get("rejection_shadow_book", {}).get("rows_with_hypothetical_support", 0)}`
- Capital-blocked rows with estimated outcomes: `{data_quality.get("capital_blocked_winners", {}).get("estimated_outcome_rows", 0)}`
- Top-winner rows with MFE: `{data_quality.get("top_winner_forensics", {}).get("rows_with_mfe", 0)}`
- Top-winner rows with MAE: `{data_quality.get("top_winner_forensics", {}).get("rows_with_mae", 0)}`

## Whether Phase 2 capital-lane experiment is justified

- Evidence strength: `{evidence.get("overall", "unknown")}`
- Backtest-only Phase 2 justified: `{evidence.get("phase2_backtest_only_justified", False)}`
- Recommended next phase: `{evidence.get("recommended_next_phase", "none")}`

## Exact recommended Phase 2 experiment scope

{brief_scope_text}

## Explicit no-go items

{not_allowed_text}

## Confirmation no behavior changed

- `behavior_change_allowed=false`
- `real_money_allowed=false`
- `allocator_behavior_changed=false`
- `risk_behavior_changed=false`
- `sizing_behavior_changed=false`
- `entry_behavior_changed=false`
- `exit_behavior_changed=false`
- `thresholds_changed=false`
- `sleeves_changed=false`
- `six_h_enabled=false`
- `h1_short_override_active=true`
"""


def _render_phase2_experiment_brief(payload: dict[str, Any]) -> str:
    recommendations = list(payload.get("phase2_candidate_recommendations") or [])
    scope = list(recommendations[0].get("scope") or []) if recommendations else []
    success_metrics = list(recommendations[0].get("success_metrics") or []) if recommendations else []
    scope_text = (
        "\n".join(f"- {item}" for item in scope)
        if scope
        else "- no candidate scope recommended yet"
    )
    success_metrics_text = (
        "\n".join(f"- {item}" for item in success_metrics)
        if success_metrics
        else "- none yet"
    )
    return f"""# Phase 2 Experiment Brief

This is a draft design brief only. It is not Phase 2 implementation.

## Hard guards

- Phase 2 must be backtest-only first.
- Phase 2 must not touch live paper runtime initially.
- Phase 2 must compare baseline vs capital-lane candidate.
- Phase 2 must not enable real money.
- Phase 2 must not enable 6H.
- Phase 2 must preserve the 1H short override.
- Phase 2 must have rollback safety.
- Phase 2 must not combine score multipliers, lifecycle changes, add-ons, recycling, or regime multipliers in the same run.

## Smallest safe candidate scope

{scope_text}

## Comparison design

- Baseline: current routed stack exactly as validated.
- Candidate: one branch-isolated capital-lane separation variant only.
- Windows: same refreshed full-history and trailing 12-month holdout windows already used by the production gate.
- Decision standard: portfolio improvement must survive both windows without loosening paper-only guards.

## Success metrics

{success_metrics_text}
"""


def _write_status(path: Path, payload: dict[str, Any]) -> None:
    _write_json(path, payload)


def write_phase1_evidence_review(config, readiness: dict[str, Any] | None = None) -> dict[str, Path]:
    readiness = dict(readiness or build_runtime_readiness(config, mode="portfolio_paper"))
    diag_paths = diagnostics_report_paths(config)
    review_paths = review_report_paths(config)
    review_root = review_paths["json"].parent
    review_root.mkdir(parents=True, exist_ok=True)

    source_fingerprint = _source_fingerprint(diag_paths)
    checkpoint_store = BacktestCheckpointStore(review_paths["progress"])
    progress = checkpoint_store.load() or {}
    if progress.get("source_fingerprint") != source_fingerprint:
        progress = {
            "phase": PHASE_1_EVIDENCE_REVIEW,
            "source_fingerprint": source_fingerprint,
            "completed_steps": [],
            "generated_outputs": {},
            "started_at_utc": _now_utc(),
        }
        checkpoint_store.save(progress)

    completed_steps = set(progress.get("completed_steps") or [])
    _write_status(
        review_paths["status"],
        {
            "phase": PHASE_1_EVIDENCE_REVIEW,
            "stage": "running",
            "started_at_utc": progress.get("started_at_utc"),
            "updated_at_utc": _now_utc(),
            "completed_steps": sorted(completed_steps),
            "source_fingerprint": source_fingerprint,
        },
    )

    if "json" in completed_steps and review_paths["json"].exists():
        payload = _read_json(review_paths["json"], {})
    else:
        payload = _build_review_payload(config)
        _write_json(review_paths["json"], payload)
        completed_steps.add("json")
        progress["completed_steps"] = sorted(completed_steps)
        progress.setdefault("generated_outputs", {})["json"] = str(review_paths["json"])
        progress["updated_at_utc"] = _now_utc()
        checkpoint_store.save(progress)

    if "markdown" not in completed_steps or not review_paths["markdown"].exists():
        review_paths["markdown"].write_text(_render_review_markdown(payload), encoding="utf-8")
        completed_steps.add("markdown")
        progress["completed_steps"] = sorted(completed_steps)
        progress.setdefault("generated_outputs", {})["markdown"] = str(review_paths["markdown"])
        progress["updated_at_utc"] = _now_utc()
        checkpoint_store.save(progress)

    if "phase2_brief" not in completed_steps or not review_paths["phase2_brief"].exists():
        review_paths["phase2_brief"].write_text(_render_phase2_experiment_brief(payload), encoding="utf-8")
        completed_steps.add("phase2_brief")
        progress["completed_steps"] = sorted(completed_steps)
        progress.setdefault("generated_outputs", {})["phase2_brief"] = str(review_paths["phase2_brief"])
        progress["updated_at_utc"] = _now_utc()
        checkpoint_store.save(progress)

    _write_status(
        review_paths["status"],
        {
            "phase": PHASE_1_EVIDENCE_REVIEW,
            "stage": "complete",
            "started_at_utc": progress.get("started_at_utc"),
            "completed_at_utc": _now_utc(),
            "completed_steps": sorted(completed_steps),
            "source_fingerprint": source_fingerprint,
            "outputs": {key: str(path) for key, path in review_paths.items()},
        },
    )
    return review_paths


__all__ = [
    "PHASE_1_EVIDENCE_REVIEW",
    "review_output_dir",
    "review_report_paths",
    "write_phase1_evidence_review",
]
