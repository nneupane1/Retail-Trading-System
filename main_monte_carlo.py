"""Run Monte Carlo robustness analysis on a completed trade log."""

import argparse

from backtest.robustness import run_monte_carlo_analysis


def main():
    parser = argparse.ArgumentParser(
        description="Run Monte Carlo robustness analysis on a completed trade log."
    )
    parser.add_argument(
        "--config",
        default="config/baselines/baseline_v3_compound_strong.json",
        help="Config snapshot that defines initial equity and risk per trade.",
    )
    parser.add_argument(
        "--trades",
        default="backtest/output/trades.csv",
        help="Trade log CSV to analyze.",
    )
    parser.add_argument(
        "--analysis-name",
        default="baseline_v3_compound_strong_full_range",
        help="Name used for robustness output folders.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5000,
        help="Monte Carlo iterations for each random method.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic RNG seed.",
    )
    parser.add_argument(
        "--target-equity",
        type=float,
        default=100000.0,
        help="Target ending equity used for probability reporting.",
    )
    args = parser.parse_args()

    result = run_monte_carlo_analysis(
        trades_path=args.trades,
        config_path=args.config,
        analysis_name=args.analysis_name,
        iterations=args.iterations,
        seed=args.seed,
        target_equity=args.target_equity,
    )

    print("\nMONTE CARLO ROBUSTNESS COMPLETE\n")
    print(f"Trades CSV: {result['trades_path']}")
    print(f"Summary CSV: {result['summary_path']}")
    print(f"Samples CSV: {result['samples_path']}")
    print(f"Concentration CSV: {result['concentration_path']}")
    print(f"Side Contribution CSV: {result['side_contribution_path']}")
    print(f"Channel Contribution CSV: {result['channel_contribution_path']}")
    print(f"Entry Role Contribution CSV: {result['role_contribution_path']}")
    print(f"Trade Audit CSV: {result['trade_audit_path']}")
    print(f"Top Trades CSV: {result['top_trades_path']}\n")

    print("Trade concentration:")
    print(f"  Trade count: {result['concentration']['trade_count']}")
    print(f"  Top 10 net profit share %: {result['concentration']['top10_net_pct']:.2f}")
    print(f"  Top 20 net profit share %: {result['concentration']['top20_net_pct']:.2f}")
    print(f"  Top 10 gross profit share %: {result['concentration']['top10_gross_pct']:.2f}")
    print(f"  Top 20 gross profit share %: {result['concentration']['top20_gross_pct']:.2f}\n")

    if result["side_contribution"]:
        print("Side contribution:")
        for row in result["side_contribution"]:
            print(row["side"])
            print(f"  Trades: {row['trade_count']}")
            print(f"  Net PnL: {row['net_pnl']:.2f}")
            print(f"  Profit factor: {row['profit_factor']:.3f}")
            print(f"  Avg risk multiplier: {row['avg_entry_risk_multiplier']:.3f}")
            print(f"  Avg equity return: {row['avg_equity_return_fraction']:.4f}")
            print(f"  Avg effective risk: {row['avg_effective_risk_fraction']:.4f}")
            print(f"  Pyramided trade %: {row['pyramided_trade_pct']:.2f}")
        print()

    if result["portfolio_channel_contribution"]:
        print("Channel contribution:")
        for row in result["portfolio_channel_contribution"]:
            print(row["portfolio_channel"])
            print(f"  Trades: {row['trade_count']}")
            print(f"  Net PnL: {row['net_pnl']:.2f}")
            print(f"  Profit factor: {row['profit_factor']:.3f}")
            print(f"  Avg equity return: {row['avg_equity_return_fraction']:.4f}")
            print(f"  Pyramided trade %: {row['pyramided_trade_pct']:.2f}")
        print()

    for summary in result["summary_rows"]:
        print(summary["method"])
        print(f"  Median final equity: {summary['median_final_equity']:.2f}")
        print(f"  P05/P95 final equity: {summary['p05_final_equity']:.2f} / {summary['p95_final_equity']:.2f}")
        print(f"  Median peak equity: {summary['median_peak_equity']:.2f}")
        print(f"  Median CAGR %: {summary['median_cagr_pct']:.2f}")
        print(
            "  P05/Median/P95 max drawdown %: "
            f"{summary['p05_max_drawdown_pct']:.2f} / "
            f"{summary['median_max_drawdown_pct']:.2f} / "
            f"{summary['p95_max_drawdown_pct']:.2f}"
        )
        print(f"  Double / Triple equity %: {summary['double_equity_pct']:.2f} / {summary['triple_equity_pct']:.2f}")
        print(f"  Half equity or worse %: {summary['half_equity_or_worse_pct']:.2f}")
        print(f"  End above target %: {summary['end_above_target_pct']:.2f}")
        print(f"  Peak above target %: {summary['peak_above_target_pct']:.2f}\n")


if __name__ == "__main__":
    main()
