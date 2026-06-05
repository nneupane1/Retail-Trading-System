"""Lean holdout validation for the research-only 6H standard bridge sleeve."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backtest.portfolio_runner import _discover_portfolio_symbols
from backtest.validate_h6_holdout import (
    HOLDOUT_START,
    MIN_KEEP_NET_R,
    MIN_KEEP_PROFIT_FACTOR,
    MIN_KEEP_TRADE_COUNT,
    TRAINING_END,
    TRAINING_START,
    _classify_training_symbols,
    _events_to_summary,
    _filter_events_for_symbols,
    _load_progress,
    _save_progress,
    _write_status,
)
from backtest.validate_h6_moonshot import _clone_config, _events_metrics, _validate_symbol
from config import AppConfig
from entry.h6_moonshot import H6StandardEngine


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h6_standard_holdout_current"


def _research_config(base: AppConfig) -> AppConfig:
    config = _clone_config(base)
    strategy = config.data.setdefault("strategy", {})
    strategy.setdefault("h6_standard", {})
    strategy["h6_standard"]["enabled"] = True
    strategy["h6_standard"]["allowed_symbols"] = []
    strategy["h6_standard"]["blocked_symbols"] = []
    return config


def main():
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)

    config = _research_config(base)
    engine = H6StandardEngine(config=config)
    symbols = _discover_portfolio_symbols(config)
    holdout_end = str(config.require("history", "end_date"))
    progress = _load_progress(report_root)
    progress["symbols_expected"] = [str(symbol).upper() for symbol in symbols]
    progress["training_window"] = {"start_date": TRAINING_START, "end_date": TRAINING_END}
    progress["holdout_window"] = {"start_date": HOLDOUT_START, "end_date": holdout_end}
    progress["engine"] = "h6_standard"
    progress["filters_cleared_for_research"] = True

    _write_status(
        report_root,
        {
            "stage": "running",
            "engine": "h6_standard",
            "filters_cleared_for_research": True,
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
    classification_df = (
        pd.DataFrame(classification_rows)
        .sort_values(["status", "net_R"], ascending=[True, False])
        .reset_index(drop=True)
    )
    keep_symbols = classification_df.loc[classification_df["status"] == "keep", "symbol"].astype(str).tolist()
    keep_holdout_events = _filter_events_for_symbols(holdout_events, keep_symbols)

    pd.DataFrame(training_funnels).sort_values("symbol").to_csv(
        report_root / "training_h6_standard_funnel_by_symbol.csv",
        index=False,
    )
    pd.DataFrame(holdout_funnels).sort_values("symbol").to_csv(
        report_root / "holdout_h6_standard_funnel_by_symbol.csv",
        index=False,
    )
    training_summary_df.to_csv(report_root / "training_h6_standard_summary_by_symbol.csv", index=False)
    holdout_summary_df.to_csv(report_root / "holdout_h6_standard_summary_by_symbol.csv", index=False)
    classification_df.to_csv(report_root / "training_h6_standard_symbol_curation.csv", index=False)
    if not training_events_df.empty:
        training_events_df.to_csv(report_root / "training_h6_standard_event_trades.csv", index=False)
    if not holdout_events_df.empty:
        holdout_events_df.to_csv(report_root / "holdout_h6_standard_event_trades.csv", index=False)

    holdout_all_metrics = _events_metrics(holdout_events_df)
    holdout_keep_metrics = _events_metrics(pd.DataFrame(keep_holdout_events))
    trade_count_ratio = (
        float(holdout_keep_metrics["trade_count"]) / float(holdout_all_metrics["trade_count"])
        if float(holdout_all_metrics["trade_count"]) > 0
        else 0.0
    )

    summary = {
        "report_root": str(report_root),
        "engine": "h6_standard",
        "filters_cleared_for_research": True,
        "symbols": [str(symbol).upper() for symbol in symbols],
        "training_window": progress["training_window"],
        "holdout_window": progress["holdout_window"],
        "training_metrics_all_symbols": _events_metrics(training_events_df),
        "holdout_metrics_all_symbols": holdout_all_metrics,
        "training_symbol_curation": {
            "keep_symbols": keep_symbols,
            "drop_symbols": classification_df.loc[classification_df["status"] == "drop", "symbol"].astype(str).tolist(),
            "report": str(report_root / "training_h6_standard_symbol_curation.csv"),
            "min_keep_trade_count": MIN_KEEP_TRADE_COUNT,
            "min_keep_net_R": MIN_KEEP_NET_R,
            "min_keep_profit_factor": MIN_KEEP_PROFIT_FACTOR,
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
