import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.refresh_h1_policy import _classify_symbol


class RefreshH1PolicyTests(unittest.TestCase):
    def test_classify_symbol_marks_keep_when_holdout_and_overlay_are_positive(self):
        status, rationale = _classify_symbol(
            "BTCUSDT",
            {"net_R": 10.0, "avg_R": 0.2},
            {"delta_net_pnl": 25.0},
        )

        self.assertEqual(status, "keep")
        self.assertIn("positive", rationale)

    def test_classify_symbol_marks_block_when_holdout_and_overlay_are_negative(self):
        status, rationale = _classify_symbol(
            "AVAXUSDT",
            {"net_R": -3.0, "avg_R": -0.1},
            {"delta_net_pnl": -50.0},
        )

        self.assertEqual(status, "block")
        self.assertIn("negative", rationale)

    def test_classify_symbol_marks_review_when_evidence_is_mixed(self):
        status, rationale = _classify_symbol(
            "ETHUSDT",
            {"net_R": 12.0, "avg_R": 0.3},
            {"delta_net_pnl": -90.0},
        )

        self.assertEqual(status, "review")
        self.assertIn("mixed", rationale)


if __name__ == "__main__":
    unittest.main()
