"""Command-line entry point for opportunity-to-trade calibration reports."""

import argparse

from config import AppConfig
from backtest.opportunity_calibration import run_opportunity_calibration


def main():
    parser = argparse.ArgumentParser(
        description="Build calibration reports from logged opportunities and trades.",
    )
    parser.add_argument(
        "--opportunities",
        default=None,
        help="Path to the opportunities CSV. Defaults to backtest/output/opportunities.csv.",
    )
    parser.add_argument(
        "--trades",
        default=None,
        help="Path to the trades CSV. Defaults to backtest/output/trades.csv.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for calibration reports. Defaults to backtest/output/calibration.",
    )
    parser.add_argument(
        "--bucket-count",
        type=int,
        default=8,
        help="Number of strength buckets to summarize.",
    )
    args = parser.parse_args()

    config = AppConfig.load()
    try:
        result = run_opportunity_calibration(
            opportunities_path=args.opportunities,
            trades_path=args.trades,
            output_dir=args.output_dir,
            bucket_count=args.bucket_count,
            config=config,
        )
    except FileNotFoundError as exc:
        print(f"\nCALIBRATION ABORTED\n{exc}")
        raise SystemExit(1) from exc

    overview = result["overview"]
    print("\nOPPORTUNITY CALIBRATION COMPLETE\n")
    print(f"Joined CSV: {result['joined_path']}")
    print(f"Strength buckets: {result['strength_summary_path']}")
    print(f"Signal-family summary: {result['signal_family_summary_path']}")
    print(f"Daily frequency summary: {result['daily_summary_path']}")
    print(f"Overview CSV: {result['overview_path']}\n")

    if overview:
        print(f"Opportunities: {int(overview.get('opportunity_count', 0))}")
        print(f"Eligible: {int(overview.get('eligible_count', 0))}")
        print(f"Executed trades: {int(overview.get('executed_trade_count', 0))}")
        print(f"Execution rate: {float(overview.get('execution_rate', 0.0)):.2%}")
        print(
            "Avg opportunities/day: "
            f"{float(overview.get('avg_opportunities_per_day', 0.0)):.2f}"
        )
        print(
            "Avg executed/day: "
            f"{float(overview.get('avg_executed_trades_per_day', 0.0)):.2f}"
        )


if __name__ == "__main__":
    main()
