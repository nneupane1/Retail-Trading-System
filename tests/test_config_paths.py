"""Regression tests for config path resolution."""

import json
import tempfile
import unittest
from pathlib import Path

from config import AppConfig


class AppConfigPathTests(unittest.TestCase):
    def test_nested_config_snapshot_keeps_repo_root_for_relative_paths(self):
        repo_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temp_dir:
            nested_dir = Path(temp_dir) / "config" / "baselines"
            nested_dir.mkdir(parents=True, exist_ok=True)
            config_path = nested_dir / "snapshot.json"
            config_path.write_text(json.dumps({
                "backtest": {"output_dir": "backtest/output"},
            }))

            config = AppConfig.load(config_path=config_path)

        self.assertEqual(
            config.path("backtest", "output_dir"),
            repo_root / "backtest" / "output",
        )


if __name__ == "__main__":
    unittest.main()
