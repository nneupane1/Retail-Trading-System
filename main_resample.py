"""Command-line entry point for rebuilding configured timeframes from local 1m history."""

import argparse
import time
from pathlib import Path

from common.debug import configure_debug
from config import AppConfig
from data.downloader import load_from_csv
from data.resampler import build_timeframes_and_save


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Resample local 1m market data into the configured higher timeframes."
    )
    parser.add_argument(
        "--symbol",
        help="Trading pair symbol such as BTCUSDT. Defaults to config value.",
    )
    parser.add_argument(
        "--start-date",
        dest="start_date",
        help="Inclusive UTC start date matching the local 1m CSV, for example 2018-01-01.",
    )
    parser.add_argument(
        "--end-date",
        dest="end_date",
        help="Inclusive UTC end date matching the local 1m CSV, for example 2026-05-12.",
    )
    parser.add_argument(
        "--base-path",
        dest="base_path",
        help="Storage root containing the local 1m CSV and output timeframe folders.",
    )
    return parser


def main():
    """
    Main entry point for local timeframe rebuilding.
    """

    print("\nLAUNCHING RESAMPLE SYSTEM\n")

    start = time.time()
    config = AppConfig.load()
    configure_debug(config=config)
    args = _build_parser().parse_args()

    symbol = args.symbol or config.require("app", "default_symbol")
    start_date = args.start_date or config.require("history", "start_date")
    end_date = args.end_date or config.require("history", "end_date")
    base_path = args.base_path or config.require("storage", "base_path")
    base_label = config.require("timeframes", "base", "label")

    path_1m = Path(base_path) / symbol / base_label / (
        f"{symbol}_{base_label}_{start_date}_to_{end_date}.csv"
    )

    print(f"Loading source 1m CSV: {path_1m}")

    df_1m = load_from_csv(path_1m)
    df_15m, df_1h, df_5h, df_12h = build_timeframes_and_save(
        df_1m,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_path=base_path,
    )

    total_time = time.time() - start

    print("\nRESAMPLE FINISHED")
    print(f"15m rows: {len(df_15m)}")
    print(f"1h rows:  {len(df_1h)}")
    print(f"5h rows:  {len(df_5h)}")
    print(f"12h rows: {len(df_12h)}")
    print(f"Total runtime: {total_time/60:.2f} minutes")


if __name__ == "__main__":
    main()
