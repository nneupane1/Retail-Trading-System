"""Build a reversible 6H sleeve symbol-policy recommendation from current validation artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import AppConfig


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h6_symbol_policy_current"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _current_9_symbols(base: AppConfig) -> list[str]:
    return [str(symbol).upper() for symbol in base.require("backtest", "portfolio_replay", "symbols")]


def _moonshot_keep_symbols(base: AppConfig) -> list[str]:
    summary = _load_json(
        Path(base.require("backtest", "output_dir"))
        / "h6_moonshot_holdout_current"
        / "summary.json"
    )
    return [str(symbol).upper() for symbol in summary["training_symbol_curation"]["keep_symbols"]]


def _comparison_summary(base: AppConfig) -> dict:
    return _load_json(
        Path(base.require("backtest", "output_dir"))
        / "h6_standard_vs_moonshot_current"
        / "summary.json"
    )


def main():
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)

    current_symbols = _current_9_symbols(base)
    keep_symbols = _moonshot_keep_symbols(base)
    comparison = _comparison_summary(base)
    blocked_symbols = [symbol for symbol in current_symbols if symbol not in keep_symbols]

    policy_rows = []
    for strategy_key in ("h6_moonshot", "h6_standard"):
        holdout_metrics = comparison["engines"][strategy_key]["holdout_metrics"]
        training_metrics = comparison["engines"][strategy_key]["training_metrics"]
        for symbol in current_symbols:
            status = "allow" if symbol in keep_symbols else "block"
            policy_rows.append(
                {
                    "strategy_type": strategy_key,
                    "symbol": symbol,
                    "status": status,
                    "rationale": (
                        "kept in current 6H curated sleeve"
                        if status == "allow"
                        else "excluded from 6H sleeve pending future revalidation"
                    ),
                    "holdout_trade_count": int(holdout_metrics["trade_count"]),
                    "holdout_avg_R": float(holdout_metrics["avg_R"]),
                    "holdout_profit_factor": float(holdout_metrics["profit_factor"]),
                    "training_trade_count": int(training_metrics["trade_count"]),
                    "training_avg_R": float(training_metrics["avg_R"]),
                    "training_profit_factor": float(training_metrics["profit_factor"]),
                }
            )

    policy_df = pd.DataFrame(policy_rows).sort_values(["strategy_type", "status", "symbol"]).reset_index(drop=True)
    policy_df.to_csv(report_root / "h6_symbol_policy.csv", index=False)

    payload = {
        "report_root": str(report_root),
        "current_9_symbols": current_symbols,
        "recommended_keep_symbols": keep_symbols,
        "recommended_block_symbols": blocked_symbols,
        "strategies": {
            "h6_moonshot": {
                "allowed_symbols": keep_symbols,
                "blocked_symbols": blocked_symbols,
                "holdout_metrics": comparison["engines"]["h6_moonshot"]["holdout_metrics"],
            },
            "h6_standard": {
                "allowed_symbols": keep_symbols,
                "blocked_symbols": blocked_symbols,
                "holdout_metrics": comparison["engines"]["h6_standard"]["holdout_metrics"],
            },
        },
        "policy_is_conditional": True,
        "revalidation_note": (
            "These exclusions are sleeve-specific and reversible. Symbols blocked here remain eligible in other "
            "system sleeves and should be reconsidered when new 6H validation data supports re-entry."
        ),
    }
    (report_root / "h6_symbol_policy.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
