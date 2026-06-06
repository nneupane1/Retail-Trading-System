import json
import tempfile
import unittest
from pathlib import Path

from backtest.validate_full_routed_stack import _load_monitoring_snapshot


class ValidateFullRoutedStackTests(unittest.TestCase):
    def test_load_monitoring_snapshot_reads_status_and_csvs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "portfolio_status.json").write_text(
                json.dumps(
                    {
                        "cap_pressure_summary": {
                            "cumulative": {"shared_risk_cap_count": 12}
                        },
                        "runtime_policy_states": {
                            "h1_execution": {"label": "boost_active"}
                        },
                        "selection_reason_counts": {"opened": 5},
                        "recent_selection_reason_counts": {"opened": 3},
                        "open_positions": 2,
                        "top_symbols": ["BTCUSDT", "ETHUSDT"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "selection_reason_summary.csv").write_text(
                "selection_reason,count,share_of_decisions,is_cap_pressure\n"
                "opened,5,0.5,False\n",
                encoding="utf-8",
            )
            (root / "selection_reason_by_strategy_summary.csv").write_text(
                "strategy_type,selection_reason,count,share_of_strategy_decisions,is_cap_pressure\n"
                "h1_execution,opened,2,0.4,False\n",
                encoding="utf-8",
            )
            (root / "runtime_policy_summary.csv").write_text(
                "strategy_type,enabled,label,fallback_to_short_only,count,avg_R,profit_factor,min_trades,min_avg_R,min_profit_factor\n"
                "h1_execution,True,boost_active,False,30,0.08,1.6,24,0.02,1.05\n",
                encoding="utf-8",
            )

            snapshot = _load_monitoring_snapshot(root)

            self.assertEqual(
                12,
                snapshot["cap_pressure_summary"]["cumulative"]["shared_risk_cap_count"],
            )
            self.assertEqual(
                "boost_active",
                snapshot["runtime_policy_states"]["h1_execution"]["label"],
            )
            self.assertEqual(5, snapshot["selection_reason_counts"]["opened"])
            self.assertEqual(2, snapshot["open_positions"])
            self.assertEqual("opened", snapshot["top_selection_reasons"][0]["selection_reason"])


if __name__ == "__main__":
    unittest.main()
