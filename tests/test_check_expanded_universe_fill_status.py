import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.check_expanded_universe_fill_status import build_fill_readiness_summary


class ExpandedUniverseFillReadinessTests(unittest.TestCase):
    def test_summary_stays_not_ready_while_symbols_remain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fill_root = root / "fill"
            validation_root = root / "validation"
            fill_root.mkdir(parents=True, exist_ok=True)
            validation_root.mkdir(parents=True, exist_ok=True)

            (fill_root / "history_fill_summary.json").write_text(
                json.dumps(
                    {
                        "completed_symbols": ["ADAUSDT"],
                        "validation_report_root": str(validation_root),
                    }
                ),
                encoding="utf-8",
            )
            (fill_root / "history_fill_progress.json").write_text(
                json.dumps(
                    {
                        "updated_at": "2026-06-04T06:51:23+00:00",
                        "symbols": {
                            "ADAUSDT": {
                                "status": "completed",
                                "final_csv_path": str(fill_root / "ADAUSDT.csv"),
                            },
                            "APTUSDT": {
                                "status": "in_progress",
                                "final_csv_path": str(fill_root / "APTUSDT.csv"),
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                [
                    {"symbol": "ADAUSDT", "target_reason": "missing_local_history"},
                    {"symbol": "APTUSDT", "target_reason": "missing_local_history"},
                ]
            ).to_csv(fill_root / "history_fill_targets.csv", index=False)
            pd.DataFrame([{"symbol": "ADAUSDT"}, {"symbol": "APTUSDT"}]).to_csv(
                validation_root / "expanded_universe_rejected_symbols.csv",
                index=False,
            )
            (validation_root / "expanded_universe_summary.json").write_text(
                json.dumps({"accepted_symbol_count": 9}),
                encoding="utf-8",
            )
            (fill_root / "ADAUSDT.csv").write_text("ok", encoding="utf-8")

            summary = build_fill_readiness_summary(
                fill_report_root=fill_root,
                validation_report_root=validation_root,
            )

            self.assertFalse(summary["ready_for_rerun"])
            self.assertEqual("continue_history_fill", summary["next_action"])
            self.assertEqual(["ADAUSDT"], summary["recovered_symbols"])
            self.assertEqual(["APTUSDT"], summary["remaining_rejected_symbols"])

    def test_summary_becomes_ready_when_all_rejected_symbols_are_recovered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fill_root = root / "fill"
            validation_root = root / "validation"
            fill_root.mkdir(parents=True, exist_ok=True)
            validation_root.mkdir(parents=True, exist_ok=True)

            completed_symbols = ["ADAUSDT", "APTUSDT"]
            (fill_root / "history_fill_summary.json").write_text(
                json.dumps(
                    {
                        "completed_symbols": completed_symbols,
                        "validation_report_root": str(validation_root),
                    }
                ),
                encoding="utf-8",
            )
            (fill_root / "history_fill_progress.json").write_text(
                json.dumps(
                    {
                        "updated_at": "2026-06-04T07:00:00+00:00",
                        "symbols": {
                            symbol: {
                                "status": "completed",
                                "final_csv_path": str(fill_root / f"{symbol}.csv"),
                            }
                            for symbol in completed_symbols
                        },
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                [{"symbol": symbol, "target_reason": "missing_local_history"} for symbol in completed_symbols]
            ).to_csv(fill_root / "history_fill_targets.csv", index=False)
            pd.DataFrame([{"symbol": symbol} for symbol in completed_symbols]).to_csv(
                validation_root / "expanded_universe_rejected_symbols.csv",
                index=False,
            )
            (validation_root / "expanded_universe_summary.json").write_text(
                json.dumps({"accepted_symbol_count": 9}),
                encoding="utf-8",
            )
            for symbol in completed_symbols:
                (fill_root / f"{symbol}.csv").write_text("ok", encoding="utf-8")

            summary = build_fill_readiness_summary(
                fill_report_root=fill_root,
                validation_report_root=validation_root,
            )

            self.assertTrue(summary["ready_for_rerun"])
            self.assertEqual("rerun_expanded_universe_allocator", summary["next_action"])
            self.assertEqual(11, summary["expected_accepted_symbol_count_after_rerun"])
            self.assertEqual(
                "python -m backtest.validate_expanded_universe_allocator",
                summary["recommended_command"],
            )


if __name__ == "__main__":
    unittest.main()
