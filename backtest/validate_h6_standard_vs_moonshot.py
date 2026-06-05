"""Compare research-only 6H standard vs moonshot sleeves on the curated keep set."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pandas as pd

from backtest.validate_h6_holdout import HOLDOUT_START, TRAINING_END, TRAINING_START
from backtest.validate_h6_moonshot import _events_metrics, _validate_symbol
from config import AppConfig
from entry.h6_moonshot import H6MoonshotEngine, H6StandardEngine


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h6_standard_vs_moonshot_current"


def _progress_path(report_root: Path) -> Path:
    return report_root / "progress.json"


def _load_progress(report_root: Path) -> dict:
    path = _progress_path(report_root)
    if not path.exists():
        return {"engines": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"engines": {}}


def _save_progress(report_root: Path, payload: dict) -> None:
    _progress_path(report_root).write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def _clone_config(base: AppConfig) -> AppConfig:
    return AppConfig(
        data=deepcopy(base.data),
        config_path=base.config_path,
        root_dir=base.root_dir,
    )


def _load_keep_symbols(base: AppConfig) -> list[str]:
    summary_path = (
        Path(base.require("backtest", "output_dir"))
        / "h6_moonshot_holdout_current"
        / "summary.json"
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return [str(symbol).upper() for symbol in payload["training_symbol_curation"]["keep_symbols"]]


def _engine_config(base: AppConfig, engine_key: str) -> AppConfig:
    config = _clone_config(base)
    strategy = config.data.setdefault("strategy", {})
    strategy.setdefault("h6_moonshot", {})
    strategy.setdefault("h6_standard", {})
    strategy["h6_moonshot"]["enabled"] = engine_key == "h6_moonshot"
    strategy["h6_standard"]["enabled"] = engine_key == "h6_standard"
    return config


def _build_engine(config: AppConfig, engine_key: str):
    if engine_key == "h6_standard":
        return H6StandardEngine(config=config)
    return H6MoonshotEngine(config=config)


def _events_to_symbol_summary(events_df: pd.DataFrame) -> pd.DataFrame:
    if events_df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "trade_count",
                "net_R",
                "avg_R",
                "median_R",
                "max_R",
                "win_rate",
                "hit_1R_rate",
                "hit_2R_rate",
            ]
        )
    frame = events_df.copy()
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


def _collect_window_events(progress: dict, engine_key: str, window_key: str, symbols: list[str]) -> list[dict]:
    rows = []
    for symbol in symbols:
        symbol_payload = (
            progress.get("engines", {})
            .get(engine_key, {})
            .get("symbols", {})
            .get(symbol, {})
        )
        rows.extend(symbol_payload.get(window_key, {}).get("events", []))
    return rows


def main():
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)

    holdout_end = str(base.require("history", "end_date"))
    symbols = _load_keep_symbols(base)
    progress = _load_progress(report_root)
    progress["symbols_expected"] = symbols
    progress["training_window"] = {"start_date": TRAINING_START, "end_date": TRAINING_END}
    progress["holdout_window"] = {"start_date": HOLDOUT_START, "end_date": holdout_end}

    for engine_key in ("h6_moonshot", "h6_standard"):
        engine_progress = progress.setdefault("engines", {}).setdefault(engine_key, {"symbols": {}})
        config = _engine_config(base, engine_key)
        engine = _build_engine(config, engine_key)
        for symbol in symbols:
            symbol_progress = engine_progress.setdefault("symbols", {}).setdefault(symbol, {})
            if not symbol_progress.get("training", {}).get("completed"):
                payload = _validate_symbol(
                    symbol=symbol,
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
                    symbol=symbol,
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

    summary = {
        "report_root": str(report_root),
        "symbols": symbols,
        "training_window": progress["training_window"],
        "holdout_window": progress["holdout_window"],
        "engines": {},
    }

    for engine_key in ("h6_moonshot", "h6_standard"):
        training_events = _collect_window_events(progress, engine_key, "training", symbols)
        holdout_events = _collect_window_events(progress, engine_key, "holdout", symbols)
        training_df = pd.DataFrame(training_events)
        holdout_df = pd.DataFrame(holdout_events)
        if not training_df.empty:
            training_df.to_csv(report_root / f"{engine_key}_training_trades.csv", index=False)
        if not holdout_df.empty:
            holdout_df.to_csv(report_root / f"{engine_key}_holdout_trades.csv", index=False)

        training_summary = _events_to_symbol_summary(training_df)
        holdout_summary = _events_to_symbol_summary(holdout_df)
        training_summary.to_csv(report_root / f"{engine_key}_training_by_symbol.csv", index=False)
        holdout_summary.to_csv(report_root / f"{engine_key}_holdout_by_symbol.csv", index=False)

        summary["engines"][engine_key] = {
            "training_metrics": _events_metrics(training_df),
            "holdout_metrics": _events_metrics(holdout_df),
            "training_symbol_report": str(report_root / f"{engine_key}_training_by_symbol.csv"),
            "holdout_symbol_report": str(report_root / f"{engine_key}_holdout_by_symbol.csv"),
        }

    moonshot_holdout = summary["engines"]["h6_moonshot"]["holdout_metrics"]
    standard_holdout = summary["engines"]["h6_standard"]["holdout_metrics"]
    moonshot_count = float(moonshot_holdout["trade_count"])
    standard_count = float(standard_holdout["trade_count"])
    summary["comparison"] = {
        "holdout_trade_count_ratio_standard_vs_moonshot": (
            standard_count / moonshot_count if moonshot_count > 0 else 0.0
        ),
        "holdout_net_R_delta_standard_minus_moonshot": float(standard_holdout["net_R"]) - float(moonshot_holdout["net_R"]),
        "holdout_avg_R_delta_standard_minus_moonshot": float(standard_holdout["avg_R"]) - float(moonshot_holdout["avg_R"]),
        "holdout_profit_factor_delta_standard_minus_moonshot": float(standard_holdout["profit_factor"]) - float(moonshot_holdout["profit_factor"]),
    }

    summary_path = report_root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
