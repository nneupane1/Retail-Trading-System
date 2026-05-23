"""Run walk-forward validation on the locked compound baseline."""

import argparse

from common.debug import configure_debug
from backtest.validation import (
    run_branch_walkforward_validation,
    run_walkforward_validation,
)


def main():
    parser = argparse.ArgumentParser(
        description="Run walk-forward validation on a locked strategy baseline."
    )
    parser.add_argument(
        "--config",
        default="config/baselines/baseline_v3_compound_strong.json",
        help="Config snapshot to validate.",
    )
    parser.add_argument(
        "--baseline-name",
        default="baseline_v3_compound_strong",
        help="Name used for validation output folders.",
    )
    parser.add_argument(
        "--scheme",
        choices=["single_split", "multifold"],
        default="multifold",
        help="Validation window scheme.",
    )
    parser.add_argument(
        "--branch-spec",
        default=None,
        help="Optional JSON file that defines controlled branch candidates.",
    )
    parser.add_argument(
        "--min-train-years",
        type=int,
        default=4,
        help="Minimum anchored training years before the first test fold.",
    )
    parser.add_argument(
        "--test-years",
        type=int,
        default=1,
        help="Evaluation fold size in years.",
    )
    args = parser.parse_args()
    configure_debug(enabled=False)

    if args.branch_spec:
        result = run_branch_walkforward_validation(
            config_path=args.config,
            baseline_name=args.baseline_name,
            branch_spec_path=args.branch_spec,
            scheme=args.scheme,
            min_train_years=args.min_train_years,
            test_years=args.test_years,
        )

        print("\nBRANCH WALK-FORWARD VALIDATION COMPLETE\n")
        print(f"Baseline: {result['baseline_name']}")
        print(f"Source 1m CSV: {result['source_path']}")
        print(f"Comparison CSV: {result['comparison_path']}\n")

        for branch in result["branch_results"]:
            aggregate = branch["aggregate"]
            print(branch["branch_name"])
            print(f"  Summary CSV: {branch['summary_path']}")
            print(f"  Drift CSV: {branch['drift_path']}")
            print(f"  Aggregate CSV: {branch['aggregate_path']}")
            print(f"  Mean PF: {aggregate['avg_profit_factor']:.3f}")
            print(f"  Min PF: {aggregate['min_profit_factor']:.3f}")
            print(f"  Mean Avg R: {aggregate['avg_r_mean']:.4f}")
            print(f"  Worst DD %: {aggregate['worst_max_drawdown_pct']:.2f}")
            print(f"  Profitable folds %: {aggregate['profitable_fold_pct']:.2f}\n")
    else:
        result = run_walkforward_validation(
            config_path=args.config,
            baseline_name=args.baseline_name,
            scheme=args.scheme,
            min_train_years=args.min_train_years,
            test_years=args.test_years,
        )

        print("\nWALK-FORWARD VALIDATION COMPLETE\n")
        print(f"Baseline: {result['baseline_name']}")
        print(f"Source 1m CSV: {result['source_path']}")
        print(f"Summary CSV: {result['summary_path']}\n")
        print(f"Drift CSV: {result['drift_path']}")
        print(f"Aggregate CSV: {result['aggregate_path']}\n")

        for window in result["windows"]:
            print(f"{window['label']}: {window['start_date']} -> {window['end_date']}")
            print(f"  Net PnL: {window['net_pnl']:.2f}")
            print(f"  Profit factor: {window['profit_factor']:.3f}")
            print(f"  Avg R: {window['avg_r_initial']:.4f}")
            print(f"  Max drawdown %: {window['max_drawdown_pct']:.2f}")
            print(f"  Top 10 net profit share %: {window['top10_net_pct']:.2f}")
            print(f"  Top 20 net profit share %: {window['top20_net_pct']:.2f}")
            print(f"  Output dir: {window['output_dir']}\n")


if __name__ == "__main__":
    main()
