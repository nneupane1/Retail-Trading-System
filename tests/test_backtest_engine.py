import unittest
from tempfile import TemporaryDirectory

import pandas as pd

from backtest.checkpoint import BacktestCheckpointStore
from backtest.engine import BacktestEngine


class DummyAccount:
    def __init__(self):
        self.equity = 1000.0
        self.initial_equity = 1000.0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0

    def summary(self):
        return None


class RecordingSimulator:
    def __init__(self):
        self.calls = []
        self.account = DummyAccount()
        self.current_trade = None

    def step(self, row, df_1h, df_5h, df_12h):
        self.calls.append(
            {
                "time": row.name,
                "df_1h_empty": df_1h.empty,
                "df_5h_empty": df_5h.empty,
                "df_12h_empty": df_12h.empty,
            }
        )

    def summary(self):
        return None

    def snapshot_state(self):
        return {
            "calls": list(self.calls),
            "account": {
                "equity": self.account.equity,
                "initial_equity": self.account.initial_equity,
                "trade_count": self.account.trade_count,
                "win_count": self.account.win_count,
                "loss_count": self.account.loss_count,
            },
        }

    def restore_state(self, snapshot):
        self.calls = list(snapshot.get("calls", []))
        account = snapshot.get("account", {})
        self.account.equity = account.get("equity", self.account.equity)
        self.account.initial_equity = account.get(
            "initial_equity",
            self.account.initial_equity,
        )
        self.account.trade_count = account.get("trade_count", 0)
        self.account.win_count = account.get("win_count", 0)
        self.account.loss_count = account.get("loss_count", 0)


class InterruptingSimulator(RecordingSimulator):
    def __init__(self, interrupt_after):
        super().__init__()
        self.interrupt_after = interrupt_after
        self.step_count = 0

    def step(self, row, df_1h, df_5h, df_12h):
        self.step_count += 1
        if self.step_count == self.interrupt_after:
            raise KeyboardInterrupt
        super().step(row, df_1h, df_5h, df_12h)

    def snapshot_state(self):
        snapshot = super().snapshot_state()
        snapshot["step_count"] = self.step_count
        return snapshot

    def restore_state(self, snapshot):
        super().restore_state(snapshot)
        self.step_count = snapshot.get("step_count", 0)


class BacktestEngineTests(unittest.TestCase):
    def _build_context_frames(self):
        index_15m = pd.date_range("2018-01-01 00:00:00", periods=120, freq="15min")
        df_15m = pd.DataFrame({"close": range(120)}, index=index_15m)

        index_1h = pd.date_range("2018-01-01 12:00:00", periods=20, freq="1h")
        df_1h = pd.DataFrame({"close": range(20)}, index=index_1h)

        index_5h = pd.date_range("2018-01-01 20:00:00", periods=10, freq="5h")
        df_5h = pd.DataFrame({"close": range(10)}, index=index_5h)

        index_12h = pd.date_range("2018-01-02 04:00:00", periods=8, freq="12h")
        df_12h = pd.DataFrame({"close": range(8)}, index=index_12h)
        return df_15m, df_1h, df_5h, df_12h

    def test_engine_starts_after_latest_context_frame_is_available(self):
        df_15m, df_1h, df_5h, df_12h = self._build_context_frames()

        simulator = RecordingSimulator()
        engine = BacktestEngine(
            df_15m=df_15m,
            df_1h=df_1h,
            df_5h=df_5h,
            df_12h=df_12h,
            simulator=simulator,
        )

        engine.run()

        self.assertTrue(simulator.calls)
        self.assertEqual(simulator.calls[0]["time"], pd.Timestamp("2018-01-02 04:00:00"))
        self.assertFalse(simulator.calls[0]["df_1h_empty"])
        self.assertFalse(simulator.calls[0]["df_5h_empty"])
        self.assertFalse(simulator.calls[0]["df_12h_empty"])

    def test_engine_can_disable_fixed_minimum_warmup_when_inputs_are_prewarmed(self):
        df_15m, df_1h, df_5h, df_12h = self._build_context_frames()

        simulator = RecordingSimulator()
        engine = BacktestEngine(
            df_15m=df_15m.iloc[60:],
            df_1h=df_1h,
            df_5h=df_5h,
            df_12h=df_12h,
            simulator=simulator,
            minimum_warmup_bars=0,
        )

        engine.run()

        self.assertTrue(simulator.calls)
        self.assertEqual(
            simulator.calls[0]["time"],
            pd.Timestamp("2018-01-02 04:00:00"),
        )

    def test_engine_saves_checkpoint_on_interrupt_and_resumes_from_next_pending_candle(self):
        df_15m, df_1h, df_5h, df_12h = self._build_context_frames()

        with TemporaryDirectory() as temp_dir:
            checkpoint_store = BacktestCheckpointStore(
                f"{temp_dir}/backtest.checkpoint.json"
            )
            first_simulator = InterruptingSimulator(interrupt_after=2)
            first_engine = BacktestEngine(
                df_15m=df_15m,
                df_1h=df_1h,
                df_5h=df_5h,
                df_12h=df_12h,
                simulator=first_simulator,
                checkpoint_store=checkpoint_store,
                checkpoint_every_steps=10,
                checkpoint_metadata={"symbol": "BTCUSDT"},
            )

            completed = first_engine.run()

            self.assertFalse(completed)
            payload = checkpoint_store.load()
            self.assertIsNotNone(payload)

            resume_index = payload["next_index"]
            self.assertEqual(
                df_15m.index[resume_index],
                pd.Timestamp("2018-01-02 04:15:00"),
            )
            self.assertEqual(
                pd.Timestamp(payload["next_candle_time"]),
                pd.Timestamp("2018-01-02 04:15:00"),
            )

            second_simulator = RecordingSimulator()
            second_simulator.restore_state(payload["simulator_state"])
            second_engine = BacktestEngine(
                df_15m=df_15m,
                df_1h=df_1h,
                df_5h=df_5h,
                df_12h=df_12h,
                simulator=second_simulator,
                checkpoint_store=checkpoint_store,
                checkpoint_every_steps=10,
                resume_index=resume_index,
                checkpoint_metadata={"symbol": "BTCUSDT"},
            )

            resumed_completed = second_engine.run()

            self.assertTrue(resumed_completed)
            self.assertFalse(checkpoint_store.exists())
            self.assertEqual(
                second_simulator.calls[1]["time"],
                pd.Timestamp("2018-01-02 04:15:00"),
            )


if __name__ == "__main__":
    unittest.main()
