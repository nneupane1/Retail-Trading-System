from __future__ import annotations

import argparse
import json

from structural_compounding_lab.backtest.engine import StructuralBacktestEngine
from structural_compounding_lab.config import load_structural_lab_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the structural compounding lab backtest.")
    parser.add_argument("--config", default=None, help="Optional json/yaml config path.")
    parser.add_argument("--symbol", default=None, help="Symbol to test, defaults to config symbol.")
    parser.add_argument("--source-csv", default=None, help="Optional explicit local CSV path.")
    parser.add_argument("--output-dir", default=None, help="Optional output subdirectory relative to structural_compounding_lab.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = load_structural_lab_config(args.config)
    engine = StructuralBacktestEngine(config=config)
    summary = engine.run(symbol=args.symbol, source_csv=args.source_csv, output_dir=args.output_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
