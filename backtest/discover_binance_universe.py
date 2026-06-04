"""Discover a live Binance spot candidate universe for research workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.binance_universe import (
    discover_binance_candidate_universe,
    write_discovery_reports,
)
from config import AppConfig


def _build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Discover currently trading liquid Binance USDT spot symbols and "
            "write the filtered candidate pool to backtest/output."
        )
    )
    parser.add_argument(
        "--report-root",
        help="Optional output folder. Defaults to backtest/output/binance_universe_discovery_current.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        help="Optional top-N liquidity override.",
    )
    return parser


def main():
    args = _build_parser().parse_args()
    base = AppConfig.load()
    report_root = (
        Path(args.report_root)
        if args.report_root
        else Path(base.require("backtest", "output_dir")) / "binance_universe_discovery_current"
    )
    if not report_root.is_absolute():
        report_root = base.root_dir / report_root

    payload = discover_binance_candidate_universe(base, top_n=args.top_n)
    report = write_discovery_reports(report_root, payload)

    summary = {
        "report_root": str(report_root),
        "candidate_symbol_count": payload["summary"]["candidate_symbol_count"],
        "candidate_symbols": payload["summary"]["candidate_symbols"],
        "top_n": payload["summary"]["top_n"],
        "artifacts": report["artifacts"],
    }
    (report_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("Binance universe discovery complete.")
    print(f"Candidate symbols: {summary['candidate_symbol_count']}")
    print(f"Report root: {report_root}")


if __name__ == "__main__":
    main()
