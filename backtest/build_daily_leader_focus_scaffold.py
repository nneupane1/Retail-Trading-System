"""Build a research-only prior-day leader schedule with no routing changes."""

from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import pandas as pd

from backtest.portfolio_runner import _load_full_history
from common.daily_leader_focus import (
    build_daily_leader_schedule,
    build_daily_leader_summary,
    write_daily_leader_focus_reports,
)
from common.universe import get_named_universe, resolve_symbols_from_config
from config import AppConfig
from data.resampler import TimeframeBuilder


@contextmanager
def _suppress_pipeline_output():
    with open(os.devnull, "w", encoding="utf-8", errors="ignore") as sink:
        with redirect_stdout(sink), redirect_stderr(sink):
            yield


def _report_root(base: AppConfig, explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit)
    else:
        root = Path(base.require("backtest", "output_dir")) / "daily_leader_focus_scaffold_current"
    return root if root.is_absolute() else base.root_dir / root


def _resolve_source_symbols(base: AppConfig, explicit_universe: str | None) -> list[str]:
    if explicit_universe:
        return get_named_universe(base, explicit_universe)

    configured = resolve_symbols_from_config(
        base,
        active_name_paths=[
            ("research", "daily_leader_focus", "source_universe_name"),
            ("backtest", "portfolio_replay", "universe_name"),
            ("universe", "active_set"),
        ],
    )
    return configured


def _load_daily_frames(base: AppConfig, symbols: list[str]) -> dict[str, pd.DataFrame]:
    builder = TimeframeBuilder(config=base)
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df_1m, _ = _load_full_history(symbol, base.require("binance", "default_interval"), base)
        with _suppress_pipeline_output():
            df_1d = builder.resample(df_1m, "1D")
        if df_1d.empty:
            continue
        daily = pd.DataFrame(index=df_1d.index)
        daily["close"] = pd.to_numeric(df_1d["close"], errors="coerce")
        daily["volume"] = pd.to_numeric(df_1d["volume"], errors="coerce").fillna(0.0)
        daily["quote_volume"] = (daily["close"] * daily["volume"]).fillna(0.0)
        frames[str(symbol).upper()] = daily
    return frames


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a research-only daily leader schedule that picks the prior-day "
            "top gainer from a configured universe. This does not route or trade it."
        )
    )
    parser.add_argument("--report-root", help="Optional output folder override.")
    parser.add_argument("--universe-name", help="Optional named universe override.")
    parser.add_argument("--top-n", type=int, help="Optional top-N daily leaders override.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    base = AppConfig.load()
    report_root = _report_root(base, args.report_root)
    raw = base.get("research", "daily_leader_focus", default={}) or {}

    source_symbols = _resolve_source_symbols(base, args.universe_name)
    if not source_symbols:
        raise SystemExit("No source symbols resolved for daily leader focus scaffold.")

    daily_frames = _load_daily_frames(base, source_symbols)
    top_n = int(args.top_n if args.top_n is not None else raw.get("top_n", 1))
    lookback_days = int(raw.get("lookback_days", 1))
    min_history_days = int(raw.get("min_history_days", 90))
    min_daily_quote_volume = float(raw.get("min_daily_quote_volume", 0.0) or 0.0)
    require_positive_return = bool(raw.get("require_positive_return", False))

    schedule, candidates = build_daily_leader_schedule(
        daily_frames,
        top_n=top_n,
        lookback_days=lookback_days,
        min_history_days=min_history_days,
        min_daily_quote_volume=min_daily_quote_volume,
        require_positive_return=require_positive_return,
    )
    summary = build_daily_leader_summary(
        schedule=schedule,
        candidates=candidates,
        top_n=top_n,
        lookback_days=lookback_days,
        source_symbols=source_symbols,
    )
    artifacts = write_daily_leader_focus_reports(
        report_root,
        schedule=schedule,
        candidates=candidates,
        summary=summary,
    )

    payload = {
        "report_root": str(report_root),
        "artifacts": artifacts,
        "summary": summary,
    }
    (report_root / "build_metadata.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    print("Daily leader focus scaffold complete.")
    print(f"Source symbols: {len(source_symbols)}")
    print(f"Selected trade days: {summary['selected_trade_days']}")
    print(f"Report root: {report_root}")


if __name__ == "__main__":
    main()
