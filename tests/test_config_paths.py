"""Regression tests for config path resolution."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config import AppConfig
import config.settings as settings_module


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

    def test_history_end_date_supports_latest_closed_day_token(self):
        repo_root = Path(__file__).resolve().parents[1]
        config = AppConfig(
            data={"history": {"end_date": "latest_closed_day_utc"}},
            config_path=repo_root / "config" / "settings.json",
            root_dir=repo_root,
        )

        with patch.object(
            settings_module,
            "_utc_now",
            return_value=datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc),
        ):
            self.assertEqual(
                config.require("history", "end_date"),
                "2026-06-12",
            )


if __name__ == "__main__":
    unittest.main()
