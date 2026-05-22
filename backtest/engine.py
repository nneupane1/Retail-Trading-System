"""Runs the historical event loop over prepared strategy candles and delegates each step to the simulator."""

import time
from datetime import datetime

from common.debug import debug_print as print


class BacktestEngine:
    """
    Runs the simulator over historical data.

    Iterates through 15m candles and feeds data
    to the simulator step-by-step.
    """

    def __init__(
        self,
        df_15m,
        df_1h,
        df_5h,
        df_12h,
        simulator,
        progress_display=None,
        checkpoint_store=None,
        checkpoint_every_steps=0,
        resume_index=None,
        checkpoint_metadata=None,
    ):

        print("\nInitializing Backtest Engine...")

        self.df_15m = df_15m
        self.df_1h = df_1h
        self.df_5h = df_5h
        self.df_12h = df_12h

        self.sim = simulator
        self.progress_display = progress_display
        self.checkpoint_store = checkpoint_store
        self.checkpoint_every_steps = max(0, int(checkpoint_every_steps or 0))
        self.resume_index = resume_index
        self.checkpoint_metadata = checkpoint_metadata or {}

        print("Backtest engine ready")

    def _start_index(self):
        if self.df_15m.empty:
            return 0

        required_context_start = max(
            self.df_15m.index.min(),
            self.df_1h.index.min(),
            self.df_5h.index.min(),
            self.df_12h.index.min(),
        )
        first_context_index = int(
            self.df_15m.index.searchsorted(required_context_start, side="left")
        )
        return max(50, first_context_index)

    # --------------------------------------------------
    # RUN BACKTEST
    # --------------------------------------------------

    def run(self):

        print("\nStarting backtest...\n")

        start_time = time.time()

        total_candles = len(self.df_15m)
        start_index = self.resume_index if self.resume_index is not None else self._start_index()
        total_steps = max(0, total_candles - start_index)
        last_completed_index = start_index - 1
        last_stable_state = self.sim.snapshot_state()

        if self.progress_display and self.progress_display.enabled:
            self.progress_display.set_total_steps(total_steps)
            self.progress_display.update_phase(
                "Running strategy loop",
                f"Processing {total_steps:,} execution candles from index {start_index:,}",
            )

        if total_steps <= 0:
            if self.checkpoint_store is not None:
                self.checkpoint_store.clear()
            print("\nBACKTEST COMPLETE")
            print("No execution candles available after higher-timeframe warmup.")
            print("\nFINAL ACCOUNT SUMMARY")
            self.sim.summary()
            return True

        try:
            for i in range(start_index, total_candles):
                row = self.df_15m.iloc[i]

                # Slice higher timeframe data up to current time
                df1h_slice = self.df_1h.loc[:row.name]
                df5h_slice = self.df_5h.loc[:row.name]
                df12h_slice = self.df_12h.loc[:row.name]

                if df1h_slice.empty or df5h_slice.empty or df12h_slice.empty:
                    continue

                # Run strategy step
                self.sim.step(row, df1h_slice, df5h_slice, df12h_slice)
                last_completed_index = i
                last_stable_state = self.sim.snapshot_state()

                processed_steps = (i - start_index) + 1

                if self.progress_display and self.progress_display.enabled:
                    if (
                        processed_steps == 1 or
                        processed_steps % 100 == 0 or
                        processed_steps == total_steps
                    ):
                        elapsed = time.time() - start_time
                        remaining_steps = max(0, total_steps - processed_steps)
                        avg_seconds_per_step = elapsed / processed_steps
                        eta_seconds = remaining_steps * avg_seconds_per_step

                        account = self.sim.account
                        self.progress_display.update_backtest_step(
                            processed_steps=processed_steps,
                            total_steps=total_steps,
                            candle_time=row.name,
                            elapsed_seconds=elapsed,
                            eta_seconds=eta_seconds,
                            equity=account.equity,
                            initial_equity=account.initial_equity,
                            trades=account.trade_count,
                            wins=account.win_count,
                            losses=account.loss_count,
                            open_trade=self.sim.current_trade is not None,
                        )
                elif i % 100 == 0:
                    progress = (i / total_candles) * 100
                    elapsed = time.time() - start_time

                    print("\nBACKTEST PROGRESS")
                    print(f"  Candle: {i}/{total_candles}")
                    print(f"  Progress: {progress:.2f}%")
                    print(f"  Elapsed: {elapsed:.2f}s\n")

                if (
                    self.checkpoint_store is not None and
                    self.checkpoint_every_steps > 0 and
                    (
                        processed_steps == 1 or
                        processed_steps % self.checkpoint_every_steps == 0
                    )
                ):
                    self._save_checkpoint(
                        next_index=i + 1,
                        simulator_state=last_stable_state,
                    )
        except KeyboardInterrupt:
            resume_index = max(start_index, last_completed_index + 1)
            self._save_checkpoint(
                next_index=resume_index,
                simulator_state=last_stable_state,
            )
            if self.progress_display and self.progress_display.enabled:
                self.progress_display.add_event(
                    "pause",
                    f"Interrupted by user; checkpoint saved for index {resume_index:,}",
                )
            print("\nBACKTEST PAUSED")
            print("Checkpoint saved. Re-run the same command to resume.")
            return False
        except Exception:
            resume_index = max(start_index, last_completed_index + 1)
            self._save_checkpoint(
                next_index=resume_index,
                simulator_state=last_stable_state,
            )
            if self.progress_display and self.progress_display.enabled:
                self.progress_display.add_event(
                    "error",
                    f"Failure checkpoint saved for index {resume_index:,}",
                )
            raise

        total_time = time.time() - start_time

        if self.progress_display and self.progress_display.enabled:
            self.progress_display.complete(total_time)

        if self.checkpoint_store is not None:
            self.checkpoint_store.clear()

        print("\nBACKTEST COMPLETE")
        print(f"Total time: {total_time:.2f}s")
        print(f"Candles processed: {total_candles}")

        # Final summary
        print("\nFINAL ACCOUNT SUMMARY")
        self.sim.summary()
        return True

    def _save_checkpoint(self, next_index, simulator_state):
        if self.checkpoint_store is None:
            return

        next_candle_time = None
        if 0 <= next_index < len(self.df_15m):
            next_candle_time = self.df_15m.index[next_index]

        payload = {
            "version": 1,
            "updated_at": datetime.utcnow(),
            "next_index": max(0, int(next_index)),
            "next_candle_time": next_candle_time,
            "simulator_state": simulator_state,
            "metadata": dict(self.checkpoint_metadata),
        }
        self.checkpoint_store.save(payload)
