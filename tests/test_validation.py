"""Tests for walk-forward validation helpers."""

import json
import tempfile
import unittest
from pathlib import Path

from backtest.validation import (
    build_default_validation_windows,
    build_expanding_yearly_windows,
    load_branch_specs,
)


class ValidationHelpersTests(unittest.TestCase):
    def test_build_default_validation_windows_supports_full_range_scheme(self):
        windows = build_default_validation_windows(
            start_date="2018-01-01",
            end_date="2026-05-22",
            scheme="full_range",
        )

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["label"], "full_range")
        self.assertEqual(windows[0]["start_date"], "2018-01-01")
        self.assertEqual(windows[0]["end_date"], "2026-05-22")

    def test_build_expanding_yearly_windows_generates_expected_folds(self):
        windows = build_expanding_yearly_windows(
            start_date="2018-01-01",
            end_date="2026-05-22",
            min_train_years=4,
            test_years=1,
        )

        self.assertEqual(len(windows), 5)
        self.assertEqual(windows[0]["label"], "train_2018_2021__test_2022")
        self.assertEqual(windows[0]["start_date"], "2022-01-01")
        self.assertEqual(windows[0]["end_date"], "2022-12-31")
        self.assertEqual(windows[-1]["label"], "train_2018_2025__test_2026")
        self.assertEqual(windows[-1]["start_date"], "2026-01-01")
        self.assertEqual(windows[-1]["end_date"], "2026-05-22")

    def test_load_branch_specs_reads_json_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            branch_path = Path(temp_dir) / "branches.json"
            branch_path.write_text(
                json.dumps(
                    {
                        "branches": [
                            {"name": "baseline"},
                            {"name": "candidate", "overrides": {"entry.score_threshold": 8}},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            branches = load_branch_specs(branch_path)

        self.assertEqual(len(branches), 2)
        self.assertEqual(branches[1]["name"], "candidate")
        self.assertEqual(branches[1]["overrides"]["entry.score_threshold"], 8)


if __name__ == "__main__":
    unittest.main()
