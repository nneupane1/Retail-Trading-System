from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from structural_compounding_lab.common.project_paths import package_root, project_root
from structural_compounding_lab.shadow_forward.forward_validation_runtime import (
    ForwardValidationRuntimeConfig,
    SAFETY_FLAGS,
    STATUS_RED,
    STATUS_YELLOW,
    _fixture_decisions,
    _paths,
    run_once,
)


def _market_frame(minutes: int = 360) -> pd.DataFrame:
    timestamps = pd.date_range("2026-02-01T00:00:00Z", periods=minutes, freq="1min").tz_convert(None)
    close = pd.Series(range(minutes), dtype=float) + 60000.0
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": close + 4.0,
            "low": close - 4.0,
            "close": close + 1.0,
            "volume": 5.0,
        }
    )


class ForwardValidationRuntimeAlertingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.canonical = self.root / "canonical.csv"
        self.runtime = self.root / "runtime"
        self.full = _market_frame()
        self.local = self.full.iloc[:-30].copy()
        self.local.to_csv(self.canonical, index=False)
        self.now = self.full["timestamp"].max().tz_localize("UTC").to_pydatetime() + timedelta(minutes=1)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _config(self, fetcher, *, reduced_window_minutes: int = 60) -> ForwardValidationRuntimeConfig:
        return ForwardValidationRuntimeConfig(
            project_root=project_root(),
            package_root=package_root(),
            canonical_csv_path=self.canonical,
            output_root=self.runtime,
            scheduler_installed=False,
            now_utc=self.now,
            fetch_function=fetcher,
            decision_function=_fixture_decisions,
            bootstrap_from_watchtower=False,
            retry_delays_seconds=(0.0, 0.0, 0.0),
            reduced_window_minutes=reduced_window_minutes,
            sleep_function=lambda _: None,
        )

    def _slice(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        return self.full.loc[(self.full["timestamp"] >= start) & (self.full["timestamp"] <= end)].copy()

    def test_public_fetch_retries_transient_failure(self) -> None:
        calls = {"count": 0}

        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutError("temporary read timeout")
            return self._slice(start, end)

        status = run_once(self._config(fetch))
        self.assertEqual(status["status"], STATUS_YELLOW)
        self.assertEqual(status["fetch_retry_attempts"], 2)
        self.assertEqual(status["final_reason"], "temporary_fetch_issue_recovered_after_retry")
        self.assertTrue(status["caught_up_to_realtime"])

    def test_public_fetch_rate_limit_backoff(self) -> None:
        calls = {"count": 0}

        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("http_429_rate_limit")
            return self._slice(start, end)

        status = run_once(self._config(fetch))
        failures = [item for item in status["fetch_retry_timeline"] if not item["success"]]
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(item["failure_type"] == "http_429_rate_limit" for item in failures))

    def test_public_fetch_reduces_window_after_failure(self) -> None:
        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            requested = int((end - start).total_seconds() // 60) + 1
            if requested > 10:
                raise RuntimeError("http_503_large_window")
            return self._slice(start, end)

        status = run_once(self._config(fetch, reduced_window_minutes=10))
        self.assertTrue(status["caught_up_to_realtime"])
        self.assertIn("reduce_request_window", status["recovery_actions_succeeded"])

    def test_malformed_response_is_rejected(self) -> None:
        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            return pd.DataFrame({"timestamp": [start], "close": [1.0]})

        with patch.dict(os.environ, {"RTS_ALERT_EMAIL_ENABLED": "false"}, clear=False):
            status = run_once(self._config(fetch))
        self.assertEqual(status["status"], STATUS_RED)
        self.assertIn("malformed", json.dumps(status["fetch_retry_timeline"]).lower())

    def test_unrecoverable_fetch_failure_marks_red(self) -> None:
        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            raise TimeoutError("simulated DNS/network timeout")

        with patch.dict(os.environ, {"RTS_ALERT_EMAIL_ENABLED": "false"}, clear=False):
            status = run_once(self._config(fetch))
        self.assertEqual(status["status"], STATUS_RED)
        self.assertIn(status["fetch_failure_type"], {"dns_failure", "network_timeout"})
        self.assertGreater(status["fetch_retry_attempts"], 1)
        self.assertTrue(status["email_alert_required"])

    def test_red_failure_writes_email_draft_when_smtp_missing(self) -> None:
        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            raise TimeoutError("simulated public fetch timeout")

        with patch.dict(
            os.environ,
            {
                "RTS_ALERT_EMAIL_ENABLED": "false",
                "RTS_ALERT_EMAIL_TO": "nneupane1@gmail.com",
            },
            clear=False,
        ):
            status = run_once(self._config(fetch))
        draft = _paths(self.runtime)["alert_draft"]
        self.assertTrue(status["email_alert_draft_written"])
        self.assertTrue(draft.exists())
        self.assertIn("nneupane1@gmail.com", json.loads(_paths(self.runtime)["alert_state"].read_text())["recipient"])
        self.assertIn("Exact failure reason", draft.read_text())

    def test_alert_throttling_prevents_duplicate_email_spam(self) -> None:
        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            raise TimeoutError("same unresolved timeout")

        environment = {
            "RTS_ALERT_EMAIL_ENABLED": "false",
            "RTS_ALERT_EMAIL_COOLDOWN_HOURS": "6",
        }
        with patch.dict(os.environ, environment, clear=False):
            first = run_once(self._config(fetch))
            second = run_once(self._config(fetch))
        self.assertTrue(first["email_alert_draft_written"])
        self.assertTrue(second["alert_throttled"])
        self.assertFalse(second["email_alert_draft_written"])

    def test_smtp_dry_run_does_not_require_real_credentials(self) -> None:
        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            raise RuntimeError("http_500_binance")

        with patch.dict(
            os.environ,
            {
                "RTS_ALERT_EMAIL_ENABLED": "true",
                "RTS_ALERT_EMAIL_DRY_RUN": "true",
                "RTS_ALERT_SMTP_HOST": "",
                "RTS_ALERT_SMTP_PASSWORD": "",
            },
            clear=False,
        ):
            status = run_once(self._config(fetch))
        self.assertTrue(status["email_alert_draft_written"])
        self.assertFalse(status["email_alert_sent"])

    def test_alerting_does_not_log_secrets(self) -> None:
        secret = "DO_NOT_WRITE_THIS_SECRET"

        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            raise RuntimeError("http_500_binance")

        with patch.dict(
            os.environ,
            {
                "RTS_ALERT_EMAIL_ENABLED": "true",
                "RTS_ALERT_EMAIL_DRY_RUN": "true",
                "RTS_ALERT_SMTP_PASSWORD": secret,
            },
            clear=False,
        ):
            status = run_once(self._config(fetch))
        combined = json.dumps(status) + _paths(self.runtime)["alert_draft"].read_text()
        self.assertNotIn(secret, combined)

    def test_reconnect_layer_preserves_research_only_flags(self) -> None:
        def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            raise RuntimeError("http_503_binance")

        with patch.dict(os.environ, {"RTS_ALERT_EMAIL_ENABLED": "false"}, clear=False):
            status = run_once(self._config(fetch))
        for key, expected in SAFETY_FLAGS.items():
            self.assertEqual(status[key], expected)
        self.assertFalse((self.runtime / "orders").exists())
        self.assertFalse((self.runtime / "broker").exists())


if __name__ == "__main__":
    unittest.main()
