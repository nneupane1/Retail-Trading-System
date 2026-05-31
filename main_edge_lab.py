"""Run isolated edge-family diagnostics on the current feature set."""

import argparse
from pathlib import Path

from backtest.edge_lab import run_edge_lab
from common.debug import configure_debug
from config import AppConfig


def _default_symbols(config):
    base_path = Path(config.require("storage", "base_path"))
    if not base_path.exists():
        return [config.require("app", "default_symbol")]
    symbols = sorted(
        path.name for path in base_path.iterdir()
        if path.is_dir()
    )
    return symbols or [config.require("app", "default_symbol")]


def main():
    config = AppConfig.load()
    parser = argparse.ArgumentParser(
        description="Measure isolated edge families from the current feature set."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Symbols to analyze. Defaults to all local symbol folders under data_storage.",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Override start date.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Override end date.",
    )
    parser.add_argument(
        "--fee-rate",
        type=float,
        default=0.001,
        help="Round-trip fee rate deducted from forward returns. Default: 0.001",
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        default=[1, 3, 5],
        help="Forward horizons in execution candles. Default: 1 3 5",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Default: backtest/output/edge_lab",
    )
    parser.add_argument(
        "--bucket-min-count",
        type=int,
        default=300,
        help="Minimum signals required for a bucket to remain valid. Default: 300",
    )
    parser.add_argument(
        "--bucket-min-avg-return-net",
        type=float,
        default=0.0,
        help="Minimum net average return for a bucket to remain valid. Default: 0.0",
    )
    args = parser.parse_args()

    configure_debug(enabled=False)

    symbols = args.symbols or _default_symbols(config)
    result = run_edge_lab(
        symbols=symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
        horizons=tuple(args.horizons),
        round_trip_fee_rate=args.fee_rate,
        bucket_min_count=args.bucket_min_count,
        bucket_min_avg_return_net=args.bucket_min_avg_return_net,
        config=config,
    )

    print("\nEDGE LAB COMPLETE\n")
    print(f"Symbols: {', '.join(result['symbols'])}")
    print(f"Signals CSV: {result['signals_path']}")
    print(f"Summary CSV: {result['summary_path']}")
    print(f"Daily frequency CSV: {result['frequency_path']}")
    print(f"Overview CSV: {result['overview_path']}")
    print(f"Bucket summary CSV: {result['bucket_summary_path']}")
    print(f"Edge table JSON: {result['edge_table_json_path']}")
    print(f"Total isolated signals: {result['signal_count']}")


if __name__ == "__main__":
    main()
