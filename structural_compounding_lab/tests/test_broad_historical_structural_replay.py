import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from structural_compounding_lab.diagnostics.broad_historical_structural_replay import (
    BroadHistoricalStructuralReplayConfig,
    write_broad_historical_structural_replay,
)


def _write_source_csv(path: Path, *, start: str, periods: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    index = pd.date_range(start=start, periods=periods, freq="1min")
    price = 10000.0
    rows = ["timestamp,open,high,low,close,volume"]
    for stamp in index:
        open_price = price
        close_price = price + 2.0 if stamp.minute % 2 == 0 else price - 1.0
        high_price = max(open_price, close_price) + 0.5
        low_price = min(open_price, close_price) - 0.5
        volume = 10.0 + (stamp.minute % 5)
        rows.append(
            f"{stamp.isoformat()},{open_price:.2f},{high_price:.2f},{low_price:.2f},{close_price:.2f},{volume:.2f}"
        )
        price = close_price
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


class BroadHistoricalStructuralReplayTests(unittest.TestCase):
    def test_empty_or_short_source_writes_safe_insufficient_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            config_root = package_root / "config"
            data_root = root / "data_storage" / "BTCUSDT" / "1m"
            output_root.mkdir(parents=True, exist_ok=True)
            config_root.mkdir(parents=True, exist_ok=True)
            data_root.mkdir(parents=True, exist_ok=True)

            source_path = data_root / "BTCUSDT_1m_2019-01-01_to_2019-01-02.csv"
            _write_source_csv(source_path, start="2019-01-01 00:00:00", periods=300)

            config_path = config_root / "structural_compounding_settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "data": {
                            "base_path": str(root / "data_storage"),
                            "default_interval": "1m",
                            "history_start_date": "2018-01-01",
                            "history_end_date": "2026-06-13",
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = write_broad_historical_structural_replay(
                BroadHistoricalStructuralReplayConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_historical_structural_replay_001",
                    source_history_path=source_path,
                    config_path=config_path,
                )
            )

            status = json.loads(result["status"].read_text(encoding="utf-8"))
            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            coverage = json.loads((output_root / "broad_historical_structural_replay_001" / "diagnostics" / "source_data_coverage.json").read_text(encoding="utf-8"))

            self.assertEqual("insufficient_data", status["state"])
            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertFalse(summary["coverage_sufficient_for_frozen_patch_validation"])
            self.assertEqual("BTCUSDT", coverage["symbol_used"])
            self.assertIn("source_does_not_reach_2018_start_boundary", " / ".join(summary["warnings"]))

    def test_successful_replay_produces_isolated_ledger_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / "structural_compounding_lab"
            output_root = package_root / "output"
            config_root = package_root / "config"
            data_root = root / "data_storage" / "BTCUSDT" / "1m"
            output_root.mkdir(parents=True, exist_ok=True)
            config_root.mkdir(parents=True, exist_ok=True)
            data_root.mkdir(parents=True, exist_ok=True)

            (output_root / "summary.json").write_text('{"sentinel":"summary"}', encoding="utf-8")
            (output_root / "trades.csv").write_text("sentinel\n", encoding="utf-8")

            source_path = data_root / "BTCUSDT_1m_2018-01-01_to_2018-01-04.csv"
            _write_source_csv(source_path, start="2018-01-01 00:00:00", periods=60 * 24 * 3)

            config_path = config_root / "structural_compounding_settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "symbol": "BTCUSDT",
                        "execution_timeframe": "1h",
                        "confirmation_timeframes": ["12h", "1d"],
                        "data": {
                            "base_path": str(root / "data_storage"),
                            "default_interval": "1m",
                            "history_start_date": "2018-01-01",
                            "history_end_date": "2018-01-04",
                            "analysis_start_date": "2018-01-01",
                            "analysis_end_date": "2018-01-04",
                        },
                        "output": {"path": str(output_root)},
                    }
                ),
                encoding="utf-8",
            )

            result = write_broad_historical_structural_replay(
                BroadHistoricalStructuralReplayConfig(
                    package_root=package_root,
                    output_root=output_root / "broad_historical_structural_replay_001",
                    source_history_path=source_path,
                    config_path=config_path,
                )
            )

            summary = json.loads(result["summary"].read_text(encoding="utf-8"))
            manifest = json.loads((output_root / "broad_historical_structural_replay_001" / "diagnostics" / "generated_ledger_manifest.json").read_text(encoding="utf-8"))
            health = json.loads((output_root / "broad_historical_structural_replay_001" / "diagnostics" / "replay_health_report.json").read_text(encoding="utf-8"))
            leakage = json.loads((output_root / "broad_historical_structural_replay_001" / "diagnostics" / "no_future_leakage_checks.json").read_text(encoding="utf-8"))
            replay_manifest = json.loads((output_root / "broad_historical_structural_replay_001" / "diagnostics" / "replay_window_manifest.json").read_text(encoding="utf-8"))

            self.assertTrue(summary["research_only"])
            self.assertFalse(summary["real_money_allowed"])
            self.assertEqual("APPLY_FROZEN_PATCH_TO_BROAD_HISTORICAL_LEDGER", summary["next_required_step"])
            self.assertEqual(str(output_root / "broad_historical_structural_replay_001" / "ledger"), summary["ledger_output_path"])
            self.assertTrue(manifest["broad_replay_isolated"])
            self.assertTrue(manifest["current_short_window_artifacts_untouched"])
            self.assertIn("trades.csv", manifest["files"])
            self.assertIn("windows", replay_manifest)
            self.assertTrue(isinstance(health["successful_replay"], bool))
            self.assertIn("checks", leakage)
            self.assertEqual('{"sentinel":"summary"}', (output_root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("sentinel\n", (output_root / "trades.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
