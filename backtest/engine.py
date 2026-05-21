import time


class BacktestEngine:
    """
    Runs the simulator over historical data.

    Iterates through 15m candles and feeds data
    to the simulator step-by-step.
    """

    def __init__(self, df_15m, df_1h, df_5h, df_12h, simulator):

        print("\n📊 Initializing Backtest Engine...")

        self.df_15m = df_15m
        self.df_1h = df_1h
        self.df_5h = df_5h
        self.df_12h = df_12h

        self.sim = simulator

        print("✅ Backtest engine ready")

    # ✅ --------------------------------------------------
    # RUN BACKTEST
    # ✅ --------------------------------------------------

    def run(self):

        print("\n🚀 Starting backtest...\n")

        start_time = time.time()

        total_candles = len(self.df_15m)

        for i in range(50, total_candles):
            row = self.df_15m.iloc[i]

            # ✅ Slice higher timeframe data up to current time
            df1h_slice = self.df_1h.loc[:row.name]
            df5h_slice = self.df_5h.loc[:row.name]
            df12h_slice = self.df_12h.loc[:row.name]

            # ✅ Run strategy step
            self.sim.step(row, df1h_slice, df5h_slice, df12h_slice)

            # ✅ Progress print every N candles
            if i % 100 == 0:
                progress = (i / total_candles) * 100
                elapsed = time.time() - start_time

                print("\n📈 BACKTEST PROGRESS")
                print(f"   Candle: {i}/{total_candles}")
                print(f"   Progress: {progress:.2f}%")
                print(f"   Elapsed: {elapsed:.2f}s\n")

        total_time = time.time() - start_time

        print("\n🎯 BACKTEST COMPLETE")
        print(f"⏱ Total time: {total_time:.2f}s")
        print(f"📊 Candles processed: {total_candles}")

        # ✅ Final summary
        print("\n📊 FINAL ACCOUNT SUMMARY")
        self.sim.summary()
