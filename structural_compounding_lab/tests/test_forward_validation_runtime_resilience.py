from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd

from structural_compounding_lab.common.project_paths import package_root, project_root
from structural_compounding_lab.shadow_forward.forward_validation_runtime import (
    ForwardRuntimeInjectedCrash,
    ForwardValidationRuntimeConfig,
    SAFETY_FLAGS,
    _fixture_decisions,
    _fixture_fetch,
    _paths,
    _read_csv,
    run_once,
)


def _market_frame(minutes: int = 720) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=minutes, freq="1min").tz_convert(None)
    values = pd.Series(range(minutes), dtype=float)
    close = 50000.0 + values
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": close + 5.0,
            "low": close - 5.0,
            "close": close + 1.0,
            "volume": 10.0,
        }
    )


class ForwardValidationRuntimeResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.canonical = self.root / "canonical.csv"
        self.runtime = self.root / "runtime"
        self.full = _market_frame()
        self.now = self.full["timestamp"].max().tz_localize("UTC").to_pydatetime() + timedelta(minutes=1)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _config(
        self,
        local: pd.DataFrame,
        *,
        fault: str | None = None,
        fault_after: int = 1,
        fetch_failure: bool = False,
    ) -> ForwardValidationRuntimeConfig:
        local.to_csv(self.canonical, index=False)
        if fetch_failure:
            def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
                raise TimeoutError("fixture timeout")
        else:
            fetch = _fixture_fetch(self.full)
        return ForwardValidationRuntimeConfig(
            project_root=project_root(),
            package_root=package_root(),
            canonical_csv_path=self.canonical,
            output_root=self.runtime,
            scheduler_installed=False,
            now_utc=self.now,
            fetch_function=fetch,
            decision_function=_fixture_decisions,
            fault_injection=fault,
            fault_after_decisions=fault_after,
            bootstrap_from_watchtower=False,
        )

    def test_forward_runtime_resumes_after_short_outage(self) -> None:
        status = run_once(self._config(self.full.iloc[:-30]))
        self.assertEqual(status["rows_appended"], 30)
        self.assertTrue(status["caught_up_to_realtime"])
        self.assertEqual(status["gaps_after"], 0)

    def test_forward_runtime_resumes_after_multi_hour_outage(self) -> None:
        status = run_once(self._config(self.full.iloc[:-180]))
        self.assertEqual(status["rows_appended"], 180)
        self.assertTrue(status["outage_recovery_used"])

    def test_forward_runtime_idempotent_rerun_no_duplicate_decisions(self) -> None:
        config = self._config(self.full)
        first = run_once(config)
        decision_count = len(_read_csv(_paths(self.runtime)["decision_ledger"]))
        trade_count = len(_read_csv(_paths(self.runtime)["trade_ledger"]))
        second = run_once(config)
        self.assertEqual(len(_read_csv(_paths(self.runtime)["decision_ledger"])), decision_count)
        self.assertEqual(len(_read_csv(_paths(self.runtime)["trade_ledger"])), trade_count)
        self.assertEqual(second["decisions_processed_this_run"], 0)
        self.assertGreaterEqual(first["decisions_processed_this_run"], 1)

    def test_forward_runtime_crash_after_append_resumes_cleanly(self) -> None:
        config = self._config(self.full.iloc[:-120], fault="after_append")
        with self.assertRaises(ForwardRuntimeInjectedCrash):
            run_once(config)
        resumed = ForwardValidationRuntimeConfig(**{**config.__dict__, "fault_injection": None})
        status = run_once(resumed)
        self.assertTrue(status["caught_up_to_realtime"])
        self.assertEqual(status["gaps_after"], 0)

    def test_forward_runtime_crash_after_partial_decision_processing_resumes_cleanly(self) -> None:
        config = self._config(self.full, fault="after_partial_decisions", fault_after=2)
        with self.assertRaises(ForwardRuntimeInjectedCrash):
            run_once(config)
        partial_count = len(_read_csv(_paths(self.runtime)["decision_ledger"]))
        self.assertEqual(partial_count, 2)
        resumed = ForwardValidationRuntimeConfig(**{**config.__dict__, "fault_injection": None})
        run_once(resumed)
        rows = _read_csv(_paths(self.runtime)["decision_ledger"])
        self.assertEqual(len(rows), len({row["decision_id"] for row in rows}))
        self.assertGreater(len(rows), partial_count)

    def test_forward_runtime_rejects_incomplete_current_candle(self) -> None:
        future = self.full.copy()
        extra_times = pd.date_range(
            self.full["timestamp"].max() + pd.Timedelta(minutes=1),
            periods=10,
            freq="1min",
        )
        extra = self.full.tail(10).copy()
        extra["timestamp"] = extra_times
        status = run_once(self._config(pd.concat([future, extra], ignore_index=True)))
        self.assertEqual(status["latest_canonical_timestamp_after"], self.full["timestamp"].max().isoformat())

    def test_forward_runtime_backfills_gap_before_processing(self) -> None:
        local = self.full.drop(self.full.index[-100]).copy()
        status = run_once(self._config(local))
        self.assertEqual(status["gaps_before"], 1)
        self.assertEqual(status["gaps_after"], 0)
        self.assertGreater(status["decisions_processed_this_run"], 0)

    def test_forward_runtime_checkpoint_missing_rebuilds_safely(self) -> None:
        status = run_once(self._config(self.full))
        checkpoint = json.loads(_paths(self.runtime)["checkpoint"].read_text())
        self.assertTrue(status["self_check_passed"])
        self.assertEqual(checkpoint["canonical_row_count"], len(self.full))

    def test_forward_runtime_canonical_ahead_of_checkpoint_resyncs_safely(self) -> None:
        config = self._config(self.full.iloc[:-120])
        run_once(config)
        self.full.to_csv(self.canonical, index=False)
        status = run_once(config)
        self.assertTrue(status["caught_up_to_realtime"])
        rows = _read_csv(_paths(self.runtime)["decision_ledger"])
        self.assertEqual(len(rows), len({row["decision_id"] for row in rows}))

    def test_forward_runtime_duplicate_candles_are_deduped(self) -> None:
        local = pd.concat([self.full, self.full.tail(5)], ignore_index=True)
        status = run_once(self._config(local))
        self.assertEqual(status["duplicates_removed"], 5)
        canonical = pd.read_csv(self.canonical)
        self.assertEqual(canonical["timestamp"].duplicated().sum(), 0)

    def test_forward_runtime_preserves_research_only_safety_flags(self) -> None:
        run_once(self._config(self.full))
        checkpoint = json.loads(_paths(self.runtime)["checkpoint"].read_text())
        self.assertEqual(checkpoint["safety_flags"], SAFETY_FLAGS)

    def test_forward_runtime_never_creates_order_or_broker_path(self) -> None:
        status = run_once(self._config(self.full))
        self.assertFalse(status["order_path_exists"])
        self.assertFalse(status["broker_path_exists"])
        self.assertFalse(status["paper_allowed"])
        self.assertFalse(status["live_allowed"])
        self.assertFalse(status["paper_validation_ready"])
        self.assertFalse((self.runtime / "orders").exists())
        self.assertFalse((self.runtime / "broker").exists())


if __name__ == "__main__":
    unittest.main()
