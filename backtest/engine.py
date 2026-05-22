"""Runs the historical event loop over prepared strategy candles and delegates each step to the simulator."""

import time

from common.debug import debug_print as print


class BacktestEngine:
    """
    Runs the simulator over historical data.

    Iterates through 15m candles and feeds data
    to the simulator step-by-step.
    """

    def __init__(self, df_15m, df_1h, df_5h, df_12h, simulator, progress_display=None):

        print("\nInitializing Backtest Engine...")

        self.df_15m = df_15m
        self.df_1h = df_1h
        self.df_5h = df_5h
        self.df_12h = df_12h

        self.sim = simulator
        self.progress_display = progress_display

        print("Backtest engine ready")

    # --------------------------------------------------
    # RUN BACKTEST
    # --------------------------------------------------

    def run(self):

        print("\nStarting backtest...\n")

        start_time = time.time()

        total_candles = len(self.df_15m)
        start_index = 50
        total_steps = max(0, total_candles - start_index)

        if self.progress_display and self.progress_display.enabled:
            self.progress_display.set_total_steps(total_steps)
            self.progress_display.update_phase(
                "Running strategy loop",
                f"Processing {total_steps:,} execution candles",
            )

        for i in range(start_index, total_candles):
            row = self.df_15m.iloc[i]

            # Slice higher timeframe data up to current time
            df1h_slice = self.df_1h.loc[:row.name]
            df5h_slice = self.df_5h.loc[:row.name]
            df12h_slice = self.df_12h.loc[:row.name]

            # Run strategy step
            self.sim.step(row, df1h_slice, df5h_slice, df12h_slice)

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

        total_time = time.time() - start_time

        if self.progress_display and self.progress_display.enabled:
            self.progress_display.complete(total_time)

        print("\nBACKTEST COMPLETE")
        print(f"Total time: {total_time:.2f}s")
        print(f"Candles processed: {total_candles}")

        # Final summary
        print("\nFINAL ACCOUNT SUMMARY")
        self.sim.summary()
