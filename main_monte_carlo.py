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
    print(f"Top Trades CSV: {result['top_trades_path']}\n")

    print("Trade concentration:")
    print(f"  Trade count: {result['concentration']['trade_count']}")
    print(f"  Top 10 net profit share %: {result['concentration']['top10_net_pct']:.2f}")
    print(f"  Top 20 net profit share %: {result['concentration']['top20_net_pct']:.2f}")
    print(f"  Top 10 gross profit share %: {result['concentration']['top10_gross_pct']:.2f}")
    print(f"  Top 20 gross profit share %: {result['concentration']['top20_gross_pct']:.2f}\n")

    for summary in result["summary_rows"]:
        print(summary["method"])
        print(f"  Median final equity: {summary['median_final_equity']:.2f}")
        print(f"  P05/P95 final equity: {summary['p05_final_equity']:.2f} / {summary['p95_final_equity']:.2f}")
        print(f"  Median CAGR %: {summary['median_cagr_pct']:.2f}")
        print(f"  Median max drawdown %: {summary['median_max_drawdown_pct']:.2f}")
        print(f"  End above target %: {summary['end_above_target_pct']:.2f}")
        print(f"  Peak above target %: {summary['peak_above_target_pct']:.2f}\n")


if __name__ == "__main__":
    main()
