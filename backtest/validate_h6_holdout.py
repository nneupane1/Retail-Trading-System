"""Lean holdout validation for the research-only 6H bridge sleeve."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backtest.validate_h6_moonshot import _clone_config, _events_metrics, _validate_symbol
from backtest.portfolio_runner import _discover_portfolio_symbols
from config import AppConfig
from entry.h6_moonshot import H6MoonshotEngine


TRAINING_START = "2025-01-01"
TRAINING_END = "2025-12-31"
HOLDOUT_START = "2026-01-01"

MIN_KEEP_TRADE_COUNT = 6
MIN_KEEP_NET_R = 0.0
MIN_KEEP_PROFIT_FACTOR = 1.05


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h6_moonshot_holdout_current"


def _progress_path(report_root: Path) -> Path:
    return report_root / "progress.json"


def _load_progress(report_root: Path) -> dict:
    path = _progress_path(report_root)
    if not path.exists():
        return {"symbols": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"symbols": {}}


def _save_progress(report_root: Path, payload: dict) -> None:
    _progress_path(report_root).write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def _write_status(report_root: Path, payload: dict) -> None:
    (report_root / "status.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def _events_to_summary(events: list[dict]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame()
    frame = pd.DataFrame(events).copy()
    frame["realized_R"] = pd.to_numeric(frame["realized_R"], errors="coerce").fillna(0.0)
    frame["hit_1R"] = frame["hit_1R"].fillna(False).astype(bool)
    frame["hit_2R"] = frame["hit_2R"].fillna(False).astype(bool)
    return (
        frame.groupby("symbol")
        .agg(
            trade_count=("realized_R", "size"),
            net_R=("realized_R", "sum"),
            avg_R=("realized_R", "mean"),
            median_R=("realized_R", "median"),
            max_R=("realized_R", "max"),
            win_rate=("realized_R", lambda s: float((pd.to_numeric(s, errors="coerce").fillna(0.0) > 0).mean())),
            hit_1R_rate=("hit_1R", "mean"),
            hit_2R_rate=("hit_2R", "mean"),
        )
        .reset_index()
        .sort_values(["net_R", "avg_R"], ascending=[False, False])
    )


def _profit_factor_from_events(events_df: pd.DataFrame) -> pd.Series:
    if events_df.empty:
        return pd.Series(dtype=float)

    def _pf(group: pd.DataFrame) -> float:
        realized = pd.to_numeric(group["realized_R"], errors="coerce").fillna(0.0)
        pos = float(realized[realized > 0].sum())
        neg = float(realized[realized < 0].sum())
        if neg == 0.0:
            return float("inf") if pos > 0 else 0.0
        return pos / abs(neg)

    return events_df.groupby("symbol", group_keys=False).apply(_pf)


def _classify_training_symbols(summary_df: pd.DataFrame, events_df: pd.DataFrame) -> list[dict]:
    if summary_df.empty:
        return []

    pf_series = _profit_factor_from_events(events_df)
    rows = []
    for _, row in summary_df.iterrows():
        symbol = str(row["symbol"]).upper()
        trade_count = int(row["trade_count"])
        net_r = float(row["net_R"])
        avg_r = float(row["avg_R"])
        pf = float(pf_series.get(symbol, 0.0))
        if (
            trade_count >= MIN_KEEP_TRADE_COUNT
            and net_r > MIN_KEEP_NET_R
            and avg_r > 0.0
            and pf >= MIN_KEEP_PROFIT_FACTOR
        ):
            status = "keep"
        else:
            status = "drop"
        rows.append(
            {
                "symbol": symbol,
                "trade_count": trade_count,
                "net_R": net_r,
                "avg_R": avg_r,
                "median_R": float(row["median_R"]),
                "max_R": float(row["max_R"]),
                "win_rate": float(row["win_rate"]),
                "hit_1R_rate": float(row["hit_1R_rate"]),
                "hit_2R_rate": float(row["hit_2R_rate"]),
                "profit_factor": pf,
                "status": status,
            }
        )
    return rows


def _filter_events_for_symbols(events: list[dict], symbols: list[str]) -> list[dict]:
    allowed = {str(symbol).upper() for symbol in symbols}
    return [row for row in events if str(row.get("symbol", "")).upper() in allowed]


def main():
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)

    config = _clone_config(base)
    config.data.setdefault("strategy", {}).setdefault("h6_moonshot", {})
    config.data["strategy"]["h6_moonshot"]["enabled"] = True
    engine = H6MoonshotEngine(config=config)

    symbols = _discover_portfolio_symbols(config)
    holdout_end = str(config.require("history", "end_date"))
    progress = _load_progress(report_root)
    progress["symbols_expected"] = [str(symbol).upper() for symbol in symbols]
    progress["training_window"] = {"start_date": TRAINING_START, "end_date": TRAINING_END}
    progress["holdout_window"] = {"start_date": HOLDOUT_START, "end_date": holdout_end}

    _write_status(
        report_root,
        {
            "stage": "running",
            "symbols": [str(symbol).upper() for symbol in symbols],
            "training_window": progress["training_window"],
            "holdout_window": progress["holdout_window"],
        },
    )

    for symbol in symbols:
        symbol_key = str(symbol).upper()
        symbol_progress = progress.setdefault("symbols", {}).setdefault(symbol_key, {})
        if not symbol_progress.get("training", {}).get("completed"):
            payload = _validate_symbol(
                symbol=symbol_key,
                recent_start=TRAINING_START,
                recent_end=TRAINING_END,
                config=config,
                engine=engine,
            )
            symbol_progress["training"] = {
                "completed": True,
                "funnel": payload["funnel"],
                "events": payload["events"],
            }
            _save_progress(report_root, progress)

        if not symbol_progress.get("holdout", {}).get("completed"):
            payload = _validate_symbol(
                symbol=symbol_key,
                recent_start=HOLDOUT_START,
                recent_end=holdout_end,
                config=config,
                engine=engine,
            )
            symbol_progress["holdout"] = {
                "completed": True,
                "funnel": payload["funnel"],
                "events": payload["events"],
            }
            _save_progress(report_root, progress)

    training_events = []
    holdout_events = []
    training_funnels = []
    holdout_funnels = []
    for symbol in symbols:
        payload = progress["symbols"][str(symbol).upper()]
        training_funnels.append(payload["training"]["funnel"])
        holdout_funnels.append(payload["holdout"]["funnel"])
        training_events.extend(payload["training"]["events"])
        holdout_events.extend(payload["holdout"]["events"])

    training_events_df = pd.DataFrame(training_events)
    holdout_events_df = pd.DataFrame(holdout_events)
    training_summary_df = _events_to_summary(training_events)
    holdout_summary_df = _events_to_summary(holdout_events)
    classification_rows = _classify_training_symbols(training_summary_df, training_events_df)
    classification_df = pd.DataFrame(classification_rows).sort_values(["status", "net_R"], ascending=[True, False]).reset_index(drop=True)
    keep_symbols = classification_df.loc[classification_df["status"] == "keep", "symbol"].astype(str).tolist()
    keep_holdout_events = _filter_events_for_symbols(holdout_events, keep_symbols)

    pd.DataFrame(training_funnels).sort_values("symbol").to_csv(
        report_root / "training_h6_funnel_by_symbol.csv",
        index=False,
    )
    pd.DataFrame(holdout_funnels).sort_values("symbol").to_csv(
        report_root / "holdout_h6_funnel_by_symbol.csv",
        index=False,
    )
    training_summary_df.to_csv(report_root / "training_h6_summary_by_symbol.csv", index=False)
    holdout_summary_df.to_csv(report_root / "holdout_h6_summary_by_symbol.csv", index=False)
    classification_df.to_csv(report_root / "training_h6_symbol_curation.csv", index=False)
    if not training_events_df.empty:
        training_events_df.to_csv(report_root / "training_h6_event_trades.csv", index=False)
    if not holdout_events_df.empty:
        holdout_events_df.to_csv(report_root / "holdout_h6_event_trades.csv", index=False)

    holdout_all_metrics = _events_metrics(holdout_events_df)
    holdout_keep_metrics = _events_metrics(pd.DataFrame(keep_holdout_events))
    trade_count_ratio = (
        float(holdout_keep_metrics["trade_count"]) / float(holdout_all_metrics["trade_count"])
        if float(holdout_all_metrics["trade_count"]) > 0
        else 0.0
    )

    summary = {
        "report_root": str(report_root),
        "symbols": [str(symbol).upper() for symbol in symbols],
        "training_window": progress["training_window"],
        "holdout_window": progress["holdout_window"],
        "training_metrics_all_symbols": _events_metrics(training_events_df),
        "holdout_metrics_all_symbols": holdout_all_metrics,
        "training_symbol_curation": {
            "keep_symbols": keep_symbols,
            "drop_symbols": classification_df.loc[classification_df["status"] == "drop", "symbol"].astype(str).tolist(),
            "report": str(report_root / "training_h6_symbol_curation.csv"),
        },
        "holdout_metrics_training_keeps": holdout_keep_metrics,
        "holdout_trade_count_ratio_training_keeps_vs_all": trade_count_ratio,
        "keep_symbol_count": len(keep_symbols),
    }
    (report_root / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    _write_status(
        report_root,
        {
            "stage": "complete",
            "summary_path": str(report_root / "summary.json"),
            "keep_symbols": keep_symbols,
            "holdout_trade_count_ratio_training_keeps_vs_all": trade_count_ratio,
        },
    )


if __name__ == "__main__":
    main()
