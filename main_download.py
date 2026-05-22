"""Command-line entry point for downloading historical Binance market data."""

import argparse
import time

from common.debug import configure_debug
from config import AppConfig
from data.downloader import fetch_full_history


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Download historical Binance OHLCV data into local CSV storage."
    )
    parser.add_argument(
        "--symbol",
        help="Trading pair symbol such as BTCUSDT. Defaults to config value."
    )
    parser.add_argument(
        "--interval",
        help="Binance interval to download. Defaults to config value."
    )
    parser.add_argument(
        "--start-date",
        dest="start_date",
        help="Inclusive UTC start date, for example 2024-01-01."
    )
    parser.add_argument(
        "--end-date",
        dest="end_date",
        help="Inclusive UTC end date, for example 2024-12-31."
    )
    parser.add_argument(
        "--base-path",
        dest="base_path",
        help="Storage root for downloaded CSV files. Defaults to config value."
    )
    return parser


def main():
    """
    Main entry point for historical data downloads.
    """

    print("\nLAUNCHING DOWNLOAD SYSTEM\n")

    start = time.time()
    config = AppConfig.load()
    configure_debug(config=config)
    args = _build_parser().parse_args()

    try:
        df = fetch_full_history(
            symbol=args.symbol,
            interval=args.interval,
            start_date=args.start_date,
            end_date=args.end_date,
            base_path=args.base_path,
        )
    except KeyboardInterrupt:
        print("\nSTOP: Download interrupted by user")
        return

    total_time = time.time() - start

    print("\nDOWNLOAD FINISHED")
    print(f"Rows downloaded: {len(df)}")
    print(f"Total runtime: {total_time/60:.2f} minutes")


if __name__ == "__main__":
    main()
