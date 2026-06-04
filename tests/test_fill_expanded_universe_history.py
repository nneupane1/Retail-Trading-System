import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backtest.fill_expanded_universe_history import (
    _build_target_rows,
    _find_latest_validation_root,
    _write_status_reports,
)


class _ConfigStub:
    def __init__(self, universe_sets):
        self._universe_sets = universe_sets

    def get(self, *keys, default=None):
        if keys == ("universe", "symbol_sets"):
            return self._universe_sets
        return default


class FillExpandedUniverseHistoryTests(unittest.TestCase):
    def test_find_latest_validation_root_prefers_latest_named_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            older = base / "expanded_universe_allocator_validation_20260603"
            newer = base / "expanded_universe_allocator_validation_20260604"
            older.mkdir(parents=True, exist_ok=True)
            newer.mkdir(parents=True, exist_ok=True)
            (older / "expanded_universe_rejected_symbols.csv").write_text("symbol,reject_reason\n")
            (newer / "expanded_universe_rejected_symbols.csv").write_text("symbol,reject_reason\n")

            resolved = _find_latest_validation_root(base)

            self.assertEqual(newer, resolved)

    def test_build_target_rows_uses_missing_history_rejections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rejected = pd.DataFrame(
                [
                    {"symbol": "ADAUSDT", "reject_reason": "missing_local_history"},
                    {"symbol": "DOGEUSDT", "reject_reason": "missing_local_history"},
                    {"symbol": "SOLUSDT", "reject_reason": "high_recent_spread_proxy"},
                ]
            )
            rejected.to_csv(root / "expanded_universe_rejected_symbols.csv", index=False)

            config = _ConfigStub(
                {
                    "current_9": ["BTCUSDT", "ETHUSDT"],
                    "expanded_liquid_28": ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOGEUSDT"],
                }
            )

            rows = _build_target_rows(
                base_config=config,
                validation_root=root,
                universe_name="expanded_liquid_28",
                symbol_override=[],
            )

            self.assertEqual(["ADAUSDT", "DOGEUSDT"], [row["symbol"] for row in rows])
            self.assertTrue(all(row["target_reason"] == "missing_local_history" for row in rows))

    def test_build_target_rows_can_use_binance_discovery(self):
        config = _ConfigStub(
            {
                "current_9": ["BTCUSDT", "ETHUSDT"],
                "expanded_liquid_28": ["BTCUSDT", "ETHUSDT", "ADAUSDT"],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "backtest.fill_expanded_universe_history.discover_binance_candidate_universe",
            return_value={"candidate_symbols": ["BTCUSDT", "DOTUSDT", "ADAUSDT"]},
        ), patch(
            "backtest.fill_expanded_universe_history.write_discovery_reports",
            return_value={"ok": True},
        ):
            rows = _build_target_rows(
                base_config=config,
                validation_root=None,
                universe_name="expanded_liquid_28",
                symbol_override=[],
                report_root=Path(tmpdir),
                use_binance_discovery=True,
            )

        self.assertEqual(["DOTUSDT", "ADAUSDT"], [row["symbol"] for row in rows])
        self.assertTrue(all(row["source"] == "binance_discovery" for row in rows))

    def test_write_status_reports_summarizes_progress(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target_rows = [
                {"symbol": "ADAUSDT", "source": "x", "target_reason": "missing_local_history", "in_current_9": False},
                {"symbol": "DOGEUSDT", "source": "x", "target_reason": "missing_local_history", "in_current_9": False},
            ]
            progress = {
                "symbols": {
                    "ADAUSDT": {"symbol": "ADAUSDT", "status": "completed"},
                    "DOGEUSDT": {"symbol": "DOGEUSDT", "status": "pending"},
                }
            }

            summary = _write_status_reports(
                report_root=root,
                progress=progress,
                target_rows=target_rows,
                context={
                    "validation_report_root": "report",
                    "universe_name": "expanded_liquid_28",
                    "start_date": "2018-01-01",
                    "end_date": "2026-05-22",
                    "base_path": "data_storage",
                },
            )

            self.assertEqual(2, summary["target_symbol_count"])
            self.assertEqual({"completed": 1, "pending": 1}, summary["status_counts"])
            self.assertEqual(["ADAUSDT"], summary["completed_symbols"])
            self.assertEqual(["DOGEUSDT"], summary["pending_symbols"])
            saved = json.loads((root / "history_fill_summary.json").read_text())
            self.assertEqual(summary["status_counts"], saved["status_counts"])


if __name__ == "__main__":
    unittest.main()
