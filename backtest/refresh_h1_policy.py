"""Build a reversible 1H sleeve symbol/side policy recommendation from current artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import AppConfig


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h1_policy_current"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _current_9_symbols(base: AppConfig) -> list[str]:
    return [str(symbol).upper() for symbol in base.require("backtest", "portfolio_replay", "symbols")]


def _holdout_symbol_summary(base: AppConfig) -> pd.DataFrame:
    path = (
        Path(base.require("backtest", "output_dir"))
        / "h1_execution_holdout_current"
        / "holdout_h1_summary_by_symbol.csv"
    )
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _overlay_symbol_deltas(base: AppConfig) -> pd.DataFrame:
    path = (
        Path(base.require("backtest", "output_dir"))
        / "h1_execution_portfolio_validation_current"
        / "competition_symbol_deltas_h1_execution_overlay.csv"
    )
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _side_metrics(base: AppConfig) -> dict:
    path = (
        Path(base.require("backtest", "output_dir"))
        / "h1_execution_validation_current"
        / "h1_event_summary_by_side.csv"
    )
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    metrics = {}
    for _, row in frame.iterrows():
        side = str(row.get("side", "")).lower()
        if not side:
            continue
        metrics[side] = {
            "trade_count": int(float(row.get("trade_count", 0) or 0)),
            "net_R": float(row.get("net_R", 0.0) or 0.0),
            "avg_R": float(row.get("avg_R", 0.0) or 0.0),
            "median_R": float(row.get("median_R", 0.0) or 0.0),
            "win_rate": float(row.get("win_rate", 0.0) or 0.0),
            "hit_1R_rate": float(row.get("hit_1R_rate", 0.0) or 0.0),
            "hit_2R_rate": float(row.get("hit_2R_rate", 0.0) or 0.0),
        }
    return metrics


def _classify_symbol(symbol: str, holdout_row: dict, overlay_row: dict) -> tuple[str, str]:
    holdout_net_r = float(holdout_row.get("net_R", 0.0) or 0.0)
    holdout_avg_r = float(holdout_row.get("avg_R", 0.0) or 0.0)
    overlay_delta = float(overlay_row.get("delta_net_pnl", 0.0) or 0.0)

    if holdout_net_r > 0.0 and overlay_delta > 0.0:
        return "keep", "positive standalone holdout and positive portfolio contribution"
    if holdout_net_r <= 0.0 and overlay_delta <= 0.0:
        return "block", "negative holdout and negative portfolio contribution"
    if holdout_avg_r <= 0.0 and overlay_delta < -150.0:
        return "block", "weak holdout expectancy and strong negative overlay crowding"
    return "review", "mixed standalone and portfolio evidence; keep conditional pending revalidation"


def main() -> None:
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)

    current_symbols = _current_9_symbols(base)
    holdout_df = _holdout_symbol_summary(base)
    overlay_df = _overlay_symbol_deltas(base)
    side_metrics = _side_metrics(base)

    holdout_map = {
        str(row["symbol"]).upper(): dict(row)
        for _, row in holdout_df.iterrows()
    }
    overlay_map = {
        str(row["symbol"]).upper(): dict(row)
        for _, row in overlay_df.iterrows()
    }

    rows = []
    keep_symbols = []
    review_symbols = []
    block_symbols = []
    for symbol in current_symbols:
        holdout_row = holdout_map.get(symbol, {})
        overlay_row = overlay_map.get(symbol, {})
        status, rationale = _classify_symbol(symbol, holdout_row, overlay_row)
        if status == "keep":
            keep_symbols.append(symbol)
        elif status == "review":
            review_symbols.append(symbol)
        else:
            block_symbols.append(symbol)
        rows.append(
            {
                "symbol": symbol,
                "status": status,
                "rationale": rationale,
                "holdout_trade_count": int(float(holdout_row.get("trade_count", 0) or 0)),
                "holdout_net_R": float(holdout_row.get("net_R", 0.0) or 0.0),
                "holdout_avg_R": float(holdout_row.get("avg_R", 0.0) or 0.0),
                "holdout_win_rate": float(holdout_row.get("win_rate", 0.0) or 0.0),
                "overlay_delta_trade_count": int(float(overlay_row.get("delta_trade_count", 0) or 0)),
                "overlay_delta_net_pnl": float(overlay_row.get("delta_net_pnl", 0.0) or 0.0),
            }
        )

    policy_df = pd.DataFrame(rows).sort_values(["status", "overlay_delta_net_pnl"], ascending=[True, False]).reset_index(drop=True)
    policy_df.to_csv(report_root / "h1_symbol_policy.csv", index=False)

    long_metrics = dict(side_metrics.get("long", {}) or {})
    short_metrics = dict(side_metrics.get("short", {}) or {})
    preferred_side_bias = "short" if float(short_metrics.get("avg_R", 0.0) or 0.0) > float(long_metrics.get("avg_R", 0.0) or 0.0) else "balanced"

    payload = {
        "report_root": str(report_root),
        "current_9_symbols": current_symbols,
        "recommended_keep_symbols": keep_symbols,
        "recommended_review_symbols": review_symbols,
        "recommended_block_symbols": block_symbols,
        "allowed_symbols_for_filtered_overlay": keep_symbols + review_symbols,
        "blocked_symbols_for_filtered_overlay": block_symbols,
        "recommended_allowed_sides": ["long", "short"],
        "preferred_side_bias": preferred_side_bias,
        "side_metrics": side_metrics,
        "policy_is_conditional": True,
        "revalidation_note": (
            "These 1H symbol and side decisions are sleeve-specific and reversible. "
            "Blocked symbols remain eligible in other sleeves and should be reconsidered when new 1H holdout or "
            "portfolio-overlay evidence supports re-entry."
        ),
    }
    (report_root / "h1_policy.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
