from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from common.runtime_readiness import build_runtime_readiness

from .opportunity_cost import OpportunityCostInput, evaluate_opportunity_cost

PHASE_1_DIAGNOSTICS = "phase_1_diagnostics_only"
DIAGNOSTICS_WARNING = "diagnostics_only_no_trading_behavior_change"

REJECTION_SHADOW_BOOK = "rejection_shadow_book"
CAPITAL_BLOCKED_WINNERS = "capital_blocked_winners"
TOP_WINNER_FORENSICS = "top_winner_forensics"
STRATEGY_BUCKET_CAPITAL_EFFICIENCY = "strategy_bucket_capital_efficiency"
OPPORTUNITY_COST_REPORT = "opportunity_cost_report"
DIAGNOSTICS_SUMMARY = "diagnostics_summary"

DIAGNOSTIC_REPORT_FILENAMES = {
    REJECTION_SHADOW_BOOK: "rejection_shadow_book.csv",
    CAPITAL_BLOCKED_WINNERS: "capital_blocked_winners.csv",
    TOP_WINNER_FORENSICS: "top_winner_forensics.csv",
    STRATEGY_BUCKET_CAPITAL_EFFICIENCY: "strategy_bucket_capital_efficiency.json",
    OPPORTUNITY_COST_REPORT: "opportunity_cost_report.json",
    DIAGNOSTICS_SUMMARY: "diagnostics_summary.json",
}

CAPITAL_REJECTION_REASONS = {
    "shared_risk_cap",
    "strategy_sleeve_cap",
    "asset_cap",
    "direction_cap",
    "same_symbol_same_side_cap",
    "strategy_position_cap",
    "strategy_step_cap",
    "step_position_cap",
    "daily_trade_cap",
}


def _capital_refactor_enabled(config) -> bool:
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    return bool(getter("capital_refactor", "enabled", default=False))


def _behavior_change_allowed(config) -> bool:
    return False


def diagnostics_output_dir(config) -> Path:
    return Path(config.require("backtest", "output_dir")) / "capital_refactor" / "diagnostics"


def diagnostics_report_paths(config) -> dict[str, Path]:
    root = diagnostics_output_dir(config)
    return {
        key: root / filename
        for key, filename in DIAGNOSTIC_REPORT_FILENAMES.items()
    }


def diagnostics_summary_path(config) -> Path:
    return diagnostics_report_paths(config)[DIAGNOSTICS_SUMMARY]


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna(pd.NA)
    except Exception:
        return pd.DataFrame()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value is pd.NA:
            return None
    except Exception:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    if number is None:
        return None
    return int(number)


def _safe_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if str(value).strip() == "":
        return None
    try:
        timestamp = pd.Timestamp(value)
    except Exception:
        return None
    if pd.isna(timestamp):
        return None
    return timestamp


def _duration_hours(start: Any, end: Any) -> float | None:
    start_ts = _safe_timestamp(start)
    end_ts = _safe_timestamp(end)
    if start_ts is None or end_ts is None:
        return None
    return max(0.0, float((end_ts - start_ts).total_seconds()) / 3600.0)


def _safe_text(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    text = str(value).strip()
    return text or None


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


def _resolve_gate_sources(config) -> dict[str, Any]:
    backtest_root = Path(config.require("backtest", "output_dir"))
    live_root = Path(config.require("live_sim", "output_dir"))
    gate_root = backtest_root / "production_validation_gate_current"
    summary_path = gate_root / "summary.json"
    report_path = gate_root / "promotion_readiness_report.json"
    status_path = gate_root / "status.json"
    summary = _read_json(summary_path, {})
    scenario_payloads = dict(summary.get("scenarios") or {})
    scenario_roots: dict[str, dict[str, str]] = {}
    for scenario_key, payload in scenario_payloads.items():
        payload = dict(payload or {})
        explicit_path = _safe_text(payload.get("output_dir") or payload.get("scenario_output_dir"))
        name = _safe_text(payload.get("name"))
        candidates = []
        if explicit_path:
            candidates.append(Path(explicit_path))
        if name:
            candidates.append(gate_root / name)
        for candidate in candidates:
            if candidate.exists():
                scenario_roots[scenario_key] = {
                    "name": name or scenario_key,
                    "path": str(candidate),
                }
                break
    return {
        "gate_root": str(gate_root),
        "summary_path": str(summary_path),
        "promotion_readiness_report_path": str(report_path),
        "status_path": str(status_path),
        "scenario_roots": scenario_roots,
        "live_output_root": str(live_root),
        "paper_soak_status_path": str(live_root / "paper_soak_status.json"),
        "paper_runtime_events_path": str(live_root / "paper_runtime_events.jsonl"),
        "portfolio_runtime_state_path": str(live_root / "portfolio_runtime_state.json"),
        "portfolio_status_path": str(live_root / "portfolio_status.json"),
    }


def _load_scenario_bundle(label: str, path_text: str) -> dict[str, Any]:
    root = Path(path_text)
    trades = _read_csv(root / "trades.csv")
    signals = _read_csv(root / "signals.csv")
    allocator = _read_csv(root / "allocator_decisions.csv")
    validation_window = _read_json(root / "validation_window.json", {})
    portfolio_status = _read_json(root / "portfolio_status.json", {})

    for frame in (trades, signals, allocator):
        if not frame.empty:
            frame["scenario_label"] = label
            frame["source_artifact"] = str(root)

    return {
        "label": label,
        "path": str(root),
        "trades": trades,
        "signals": signals,
        "allocator": allocator,
        "validation_window": validation_window,
        "portfolio_status": portfolio_status,
    }


def _load_scenario_bundles(config) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    source_artifacts = _resolve_gate_sources(config)
    warnings: list[str] = []
    bundles: list[dict[str, Any]] = []
    for scenario_key, payload in dict(source_artifacts.get("scenario_roots") or {}).items():
        scenario_name = str(payload.get("name") or scenario_key)
        scenario_path = _safe_text(payload.get("path"))
        if not scenario_path:
            warnings.append(f"missing_scenario_path:{scenario_key}")
            continue
        bundle = _load_scenario_bundle(scenario_name, scenario_path)
        if bundle["trades"].empty and bundle["signals"].empty and bundle["allocator"].empty:
            warnings.append(f"empty_scenario_artifacts:{scenario_name}")
        bundles.append(bundle)
    if not bundles:
        warnings.append("no_scenario_artifacts_available")
    return bundles, source_artifacts, warnings


def _opened_trade_lookup(trades: pd.DataFrame) -> dict[tuple[str | None, str | None, str | None, str | None], dict[str, Any]]:
    lookup: dict[tuple[str | None, str | None, str | None, str | None], dict[str, Any]] = {}
    if trades.empty:
        return lookup
    for row in trades.to_dict(orient="records"):
        key = (
            _safe_text(row.get("entry_time")),
            _safe_text(row.get("symbol")),
            _safe_text(row.get("side")),
            _safe_text(row.get("strategy_type")),
        )
        if key not in lookup:
            lookup[key] = row
    return lookup


def _build_rejection_shadow_book(bundles: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for bundle in bundles:
        allocator = bundle["allocator"]
        trades = bundle["trades"]
        trade_lookup = _opened_trade_lookup(trades)
        if not allocator.empty:
            for row in allocator.to_dict(orient="records"):
                reason = _safe_text(row.get("final_reason") or row.get("initial_reason"))
                if reason == "opened":
                    continue
                if not reason:
                    continue
                key = (
                    bundle["label"],
                    "allocator_decisions",
                    _safe_text(row.get("timestamp")),
                    _safe_text(row.get("symbol")),
                    _safe_text(row.get("side")),
                    _safe_text(row.get("strategy_type")),
                    reason,
                )
                if key in seen:
                    continue
                seen.add(key)
                trade = trade_lookup.get(
                    (
                        _safe_text(row.get("timestamp")),
                        _safe_text(row.get("symbol")),
                        _safe_text(row.get("side")),
                        _safe_text(row.get("strategy_type")),
                    )
                )
                rows.append(
                    {
                        "timestamp": _safe_text(row.get("timestamp")),
                        "symbol": _safe_text(row.get("symbol")),
                        "strategy_type": _safe_text(row.get("strategy_type")),
                        "side": _safe_text(row.get("side")),
                        "score": _safe_float(row.get("selection_score") or row.get("score")),
                        "score_bucket": _safe_text(row.get("score_bucket")),
                        "rejection_reason": reason,
                        "rejection_source": "allocator_decisions",
                        "candidate_rank": _safe_int(row.get("allocation_rank")),
                        "accepted_trade_id_if_any": _safe_text((trade or {}).get("trade_id")),
                        "hypothetical_entry": None,
                        "hypothetical_stop": None,
                        "hypothetical_exit": None,
                        "hypothetical_R": None,
                        "hypothetical_pnl": None,
                        "would_have_won": None,
                        "source_artifact": bundle["path"],
                        "notes": "hypothetical outcome not computed safely from existing artifacts",
                    }
                )
        signals = bundle["signals"]
        if not signals.empty:
            for row in signals.to_dict(orient="records"):
                reason = _safe_text(row.get("selection_reason"))
                if reason == "opened" or _truthy(row.get("selected")):
                    continue
                if not reason:
                    continue
                key = (
                    bundle["label"],
                    "signals",
                    _safe_text(row.get("timestamp")),
                    _safe_text(row.get("symbol")),
                    _safe_text(row.get("side")),
                    _safe_text(row.get("strategy_type")),
                    reason,
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "timestamp": _safe_text(row.get("timestamp")),
                        "symbol": _safe_text(row.get("symbol")),
                        "strategy_type": _safe_text(row.get("strategy_type")),
                        "side": _safe_text(row.get("side")),
                        "score": _safe_float(row.get("score")),
                        "score_bucket": _safe_text(row.get("score_bucket")),
                        "rejection_reason": reason,
                        "rejection_source": "signals",
                        "candidate_rank": None,
                        "accepted_trade_id_if_any": None,
                        "hypothetical_entry": None,
                        "hypothetical_stop": None,
                        "hypothetical_exit": None,
                        "hypothetical_R": None,
                        "hypothetical_pnl": None,
                        "would_have_won": None,
                        "source_artifact": bundle["path"],
                        "notes": "signal rejection captured without allocator-side hypothetical outcome reconstruction",
                    }
                )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "symbol",
                "strategy_type",
                "side",
                "score",
                "score_bucket",
                "rejection_reason",
                "rejection_source",
                "candidate_rank",
                "accepted_trade_id_if_any",
                "hypothetical_entry",
                "hypothetical_stop",
                "hypothetical_exit",
                "hypothetical_R",
                "hypothetical_pnl",
                "would_have_won",
                "source_artifact",
                "notes",
            ]
        )
    return frame.sort_values(
        by=["timestamp", "strategy_type", "symbol", "rejection_source"],
        kind="stable",
    ).reset_index(drop=True)


def _find_competing_opened_row(
    allocator: pd.DataFrame,
    *,
    timestamp: str | None,
) -> dict[str, Any] | None:
    if allocator.empty or not timestamp:
        return None
    opened = allocator[
        allocator["timestamp"].astype(str).eq(str(timestamp))
        & allocator["final_reason"].astype(str).eq("opened")
    ]
    if opened.empty:
        return None
    if "allocation_priority" in opened.columns:
        priorities = pd.to_numeric(opened["allocation_priority"], errors="coerce").fillna(0.0)
        opened = opened.assign(_priority=priorities).sort_values(
            by=["_priority", "selection_score", "score"],
            ascending=False,
            kind="stable",
        )
    return opened.iloc[0].to_dict()


def _build_capital_blocked_winners(bundles: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        allocator = bundle["allocator"]
        trades = bundle["trades"]
        trade_lookup = _opened_trade_lookup(trades)
        if allocator.empty:
            continue
        for row in allocator.to_dict(orient="records"):
            reason = _safe_text(row.get("final_reason") or row.get("initial_reason"))
            if reason not in CAPITAL_REJECTION_REASONS:
                continue
            competing = _find_competing_opened_row(
                allocator,
                timestamp=_safe_text(row.get("timestamp")),
            )
            competing_trade = None
            if competing is not None:
                competing_trade = trade_lookup.get(
                    (
                        _safe_text(competing.get("timestamp")),
                        _safe_text(competing.get("symbol")),
                        _safe_text(competing.get("side")),
                        _safe_text(competing.get("strategy_type")),
                    )
                )
            rows.append(
                {
                    "timestamp": _safe_text(row.get("timestamp")),
                    "symbol": _safe_text(row.get("symbol")),
                    "strategy_type": _safe_text(row.get("strategy_type")),
                    "side": _safe_text(row.get("side")),
                    "score_bucket": _safe_text(row.get("score_bucket")),
                    "rejection_reason": reason,
                    "blocking_constraint": reason,
                    "competing_position_or_trade": _safe_text(
                        (competing_trade or {}).get("trade_id")
                        or (
                            f"{_safe_text((competing or {}).get('symbol'))}:"
                            f"{_safe_text((competing or {}).get('strategy_type'))}:"
                            f"{_safe_text((competing or {}).get('side'))}"
                            if competing is not None
                            else None
                        )
                    ),
                    "later_price_move_available": None,
                    "estimated_R_available": None,
                    "estimated_pnl_available": None,
                    "confidence": "low",
                    "source_artifact": bundle["path"],
                    "notes": "capital/risk suppression captured from allocator artifacts only; later outcome not reconstructed safely",
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "symbol",
                "strategy_type",
                "side",
                "score_bucket",
                "rejection_reason",
                "blocking_constraint",
                "competing_position_or_trade",
                "later_price_move_available",
                "estimated_R_available",
                "estimated_pnl_available",
                "confidence",
                "source_artifact",
                "notes",
            ]
        )
    return frame.sort_values(
        by=["timestamp", "strategy_type", "symbol"],
        kind="stable",
    ).reset_index(drop=True)


def _build_top_winner_forensics(bundles: list[dict[str, Any]], limit: int = 100) -> pd.DataFrame:
    trade_frames = [bundle["trades"] for bundle in bundles if not bundle["trades"].empty]
    if not trade_frames:
        return pd.DataFrame(
            columns=[
                "trade_id",
                "symbol",
                "strategy_type",
                "side",
                "entry_time",
                "exit_time",
                "score",
                "score_bucket",
                "pnl",
                "R",
                "holding_time",
                "max_favorable_excursion",
                "max_adverse_excursion",
                "exit_reason",
                "possible_add_on_points",
                "early_exit_flag",
                "source_artifact",
                "notes",
            ]
        )
    trades = pd.concat(trade_frames, ignore_index=True)
    trades["_pnl"] = pd.to_numeric(trades.get("pnl"), errors="coerce").fillna(0.0)
    winners = trades.sort_values("_pnl", ascending=False, kind="stable").head(limit)
    rows: list[dict[str, Any]] = []
    for row in winners.to_dict(orient="records"):
        rows.append(
            {
                "trade_id": _safe_text(row.get("trade_id")),
                "symbol": _safe_text(row.get("symbol")),
                "strategy_type": _safe_text(row.get("strategy_type")),
                "side": _safe_text(row.get("side")),
                "entry_time": _safe_text(row.get("entry_time")),
                "exit_time": _safe_text(row.get("exit_time")),
                "score": _safe_float(row.get("selection_score") or row.get("score")),
                "score_bucket": _safe_text(row.get("score_bucket")),
                "pnl": _safe_float(row.get("pnl")),
                "R": _safe_float(row.get("pnl_R_total") or row.get("pnl_R")),
                "holding_time": _duration_hours(row.get("entry_time"), row.get("exit_time")),
                "max_favorable_excursion": None,
                "max_adverse_excursion": None,
                "exit_reason": _safe_text(row.get("exit_reason")),
                "possible_add_on_points": _safe_int(row.get("convexity_add_count")) or 0,
                "early_exit_flag": False,
                "source_artifact": _safe_text(row.get("source_artifact")),
                "notes": "MFE/MAE and early-exit reconstruction unavailable from existing artifacts",
            }
        )
    return pd.DataFrame(rows)


def _profit_factor_from_values(values: pd.Series) -> float | None:
    profits = float(values[values > 0].sum())
    losses = float((-values[values < 0]).sum())
    if losses <= 0:
        return None
    return profits / losses


def _build_strategy_bucket_capital_efficiency(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    trade_frames = [bundle["trades"] for bundle in bundles if not bundle["trades"].empty]
    if not trade_frames:
        return {
            "generated_at_utc": _now_utc(),
            "source_artifacts": [],
            "groups": [],
        }
    trades = pd.concat(trade_frames, ignore_index=True).copy()
    trades["strategy_type"] = trades.get("strategy_type", pd.Series(dtype=str)).fillna("unknown")
    trades["score_bucket"] = trades.get("score_bucket", pd.Series(dtype=str)).fillna("unknown")
    trades["side"] = trades.get("side", pd.Series(dtype=str)).fillna("unknown")
    trades["regime"] = trades.get("regime_class", pd.Series(dtype=str)).fillna("unknown")
    trades["_pnl"] = pd.to_numeric(trades.get("pnl"), errors="coerce").fillna(0.0)
    r_column = "pnl_R_total" if "pnl_R_total" in trades.columns else "pnl_R"
    trades["_r"] = pd.to_numeric(trades.get(r_column), errors="coerce").fillna(0.0)

    groups: list[dict[str, Any]] = []
    grouped = trades.groupby(["strategy_type", "score_bucket", "side", "regime"], dropna=False)
    for (strategy_type, score_bucket, side, regime), frame in grouped:
        pnl_series = frame["_pnl"]
        r_series = frame["_r"]
        trade_count = int(len(frame))
        win_count = int((pnl_series > 0).sum())
        loss_count = int((pnl_series < 0).sum())
        groups.append(
            {
                "strategy_type": str(strategy_type),
                "score_bucket": str(score_bucket),
                "side": str(side),
                "regime": str(regime),
                "trade_count": trade_count,
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": (win_count / trade_count) if trade_count else 0.0,
                "total_R": float(r_series.sum()),
                "avg_R": float(r_series.mean()) if trade_count else 0.0,
                "median_R": float(r_series.median()) if trade_count else 0.0,
                "total_pnl": float(pnl_series.sum()),
                "avg_pnl": float(pnl_series.mean()) if trade_count else 0.0,
                "profit_factor": _profit_factor_from_values(pnl_series),
                "max_loss_R": float(r_series.min()) if trade_count else None,
                "max_win_R": float(r_series.max()) if trade_count else None,
                "notes": "passive aggregation from historical trade artifacts only",
            }
        )
    groups.sort(
        key=lambda row: (
            row["strategy_type"],
            row["score_bucket"],
            row["side"],
            row["regime"],
        )
    )
    return {
        "generated_at_utc": _now_utc(),
        "source_artifacts": [bundle["path"] for bundle in bundles],
        "groups": groups,
    }


def _build_opportunity_cost_report(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for bundle in bundles:
        allocator = bundle["allocator"]
        trades = bundle["trades"]
        trade_lookup = _opened_trade_lookup(trades)
        if allocator.empty:
            continue
        for row in allocator.to_dict(orient="records"):
            reason = _safe_text(row.get("final_reason") or row.get("initial_reason"))
            if reason not in CAPITAL_REJECTION_REASONS:
                continue
            competing = _find_competing_opened_row(
                allocator,
                timestamp=_safe_text(row.get("timestamp")),
            )
            if competing is None:
                observations.append(
                    {
                        "timestamp": _safe_text(row.get("timestamp")),
                        "held_symbol": None,
                        "held_strategy_type": None,
                        "held_side": None,
                        "capital_locked_duration": None,
                        "unrealized_R": None,
                        "competing_symbol": _safe_text(row.get("symbol")),
                        "competing_strategy_type": _safe_text(row.get("strategy_type")),
                        "competing_side": _safe_text(row.get("side")),
                        "candidate_score": _safe_float(row.get("selection_score") or row.get("score")),
                        "competing_signal_priority": None,
                        "opportunity_cost_score": None,
                        "source_artifact": bundle["path"],
                        "notes": "capital-blocked candidate had no matching competing opened trade in allocator artifact",
                    }
                )
                continue
            competing_trade = trade_lookup.get(
                (
                    _safe_text(competing.get("timestamp")),
                    _safe_text(competing.get("symbol")),
                    _safe_text(competing.get("side")),
                    _safe_text(competing.get("strategy_type")),
                )
            )
            locked_duration = _duration_hours(
                (competing_trade or {}).get("entry_time"),
                (competing_trade or {}).get("exit_time"),
            )
            evaluation = evaluate_opportunity_cost(
                OpportunityCostInput(
                    current_position_score=float(
                        _safe_float(competing.get("selection_score") or competing.get("score")) or 0.0
                    ),
                    candidate_score=float(
                        _safe_float(row.get("selection_score") or row.get("score")) or 0.0
                    ),
                    capital_locked_duration_hours=float(locked_duration or 0.0),
                    unrealized_r=0.0,
                    competing_signal_priority=float(
                        _safe_float(competing.get("allocation_priority")) or 0.0
                    ),
                )
            )
            observations.append(
                {
                    "timestamp": _safe_text(row.get("timestamp")),
                    "held_symbol": _safe_text((competing_trade or competing).get("symbol")),
                    "held_strategy_type": _safe_text((competing_trade or competing).get("strategy_type")),
                    "held_side": _safe_text((competing_trade or competing).get("side")),
                    "capital_locked_duration": locked_duration,
                    "unrealized_R": None,
                    "competing_symbol": _safe_text(row.get("symbol")),
                    "competing_strategy_type": _safe_text(row.get("strategy_type")),
                    "competing_side": _safe_text(row.get("side")),
                    "candidate_score": _safe_float(row.get("selection_score") or row.get("score")),
                    "competing_signal_priority": _safe_float(competing.get("allocation_priority")),
                    "opportunity_cost_score": float(evaluation.opportunity_cost_score),
                    "source_artifact": bundle["path"],
                    "notes": "opportunity-cost score uses passive score and hold-duration evidence only; no runtime behavior changed",
                }
            )
    return {
        "generated_at_utc": _now_utc(),
        "source_artifacts": [bundle["path"] for bundle in bundles],
        "observations": observations,
    }


def _layer_statuses(
    rejection_shadow_book: pd.DataFrame,
    capital_blocked_winners: pd.DataFrame,
    top_winner_forensics: pd.DataFrame,
    strategy_bucket_capital_efficiency: dict[str, Any],
    opportunity_cost_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        "shadow_rejection_book": {
            "present": True,
            "diagnostics_only": True,
            "records": int(len(rejection_shadow_book)),
        },
        "capital_blocked_winners": {
            "present": True,
            "diagnostics_only": True,
            "records": int(len(capital_blocked_winners)),
        },
        "winner_forensics": {
            "present": True,
            "diagnostics_only": True,
            "records": int(len(top_winner_forensics)),
        },
        "strategy_bucket_capital_efficiency": {
            "present": True,
            "diagnostics_only": True,
            "records": int(len(list(strategy_bucket_capital_efficiency.get("groups") or []))),
        },
        "opportunity_cost": {
            "present": True,
            "diagnostics_only": True,
            "records": int(len(list(opportunity_cost_report.get("observations") or []))),
        },
    }


def write_phase1_diagnostics(config, readiness: dict[str, Any] | None = None) -> dict[str, Path]:
    readiness = dict(readiness or build_runtime_readiness(config, mode="portfolio_paper"))
    bundles, source_artifacts, warnings = _load_scenario_bundles(config)
    paths = diagnostics_report_paths(config)
    paths[DIAGNOSTICS_SUMMARY].parent.mkdir(parents=True, exist_ok=True)

    rejection_shadow_book = _build_rejection_shadow_book(bundles)
    rejection_shadow_book.to_csv(paths[REJECTION_SHADOW_BOOK], index=False)

    capital_blocked_winners = _build_capital_blocked_winners(bundles)
    capital_blocked_winners.to_csv(paths[CAPITAL_BLOCKED_WINNERS], index=False)

    top_winner_forensics = _build_top_winner_forensics(bundles)
    top_winner_forensics.to_csv(paths[TOP_WINNER_FORENSICS], index=False)

    strategy_bucket_capital_efficiency = _build_strategy_bucket_capital_efficiency(bundles)
    paths[STRATEGY_BUCKET_CAPITAL_EFFICIENCY].write_text(
        json.dumps(strategy_bucket_capital_efficiency, indent=2),
        encoding="utf-8",
    )

    opportunity_cost_report = _build_opportunity_cost_report(bundles)
    paths[OPPORTUNITY_COST_REPORT].write_text(
        json.dumps(opportunity_cost_report, indent=2),
        encoding="utf-8",
    )

    summary_payload = {
        "generated_at_utc": _now_utc(),
        "phase": PHASE_1_DIAGNOSTICS,
        "classification": readiness.get("classification"),
        "paper_runtime_allowed": bool(readiness.get("paper_runtime_allowed")),
        "real_money_allowed": False,
        "capital_refactor_enabled": _capital_refactor_enabled(config),
        "behavior_change_allowed": _behavior_change_allowed(config),
        "diagnostics_only": True,
        "source_artifacts": source_artifacts,
        "reports_written": {key: str(path) for key, path in paths.items()},
        "layer_statuses": _layer_statuses(
            rejection_shadow_book,
            capital_blocked_winners,
            top_winner_forensics,
            strategy_bucket_capital_efficiency,
            opportunity_cost_report,
        ),
        "allocator_behavior_changed": False,
        "risk_behavior_changed": False,
        "sizing_behavior_changed": False,
        "entry_behavior_changed": False,
        "exit_behavior_changed": False,
        "thresholds_changed": False,
        "sleeves_changed": False,
        "six_h_enabled": _config_six_h_enabled(config),
        "h1_short_override_active": _config_h1_short_override_active(config),
        "warnings": [DIAGNOSTICS_WARNING, *warnings],
    }
    paths[DIAGNOSTICS_SUMMARY].write_text(
        json.dumps(summary_payload, indent=2),
        encoding="utf-8",
    )
    return paths


__all__ = [
    "CAPITAL_BLOCKED_WINNERS",
    "DIAGNOSTICS_SUMMARY",
    "DIAGNOSTIC_REPORT_FILENAMES",
    "DIAGNOSTICS_WARNING",
    "OPPORTUNITY_COST_REPORT",
    "PHASE_1_DIAGNOSTICS",
    "REJECTION_SHADOW_BOOK",
    "STRATEGY_BUCKET_CAPITAL_EFFICIENCY",
    "TOP_WINNER_FORENSICS",
    "diagnostics_output_dir",
    "diagnostics_report_paths",
    "diagnostics_summary_path",
    "write_phase1_diagnostics",
]
