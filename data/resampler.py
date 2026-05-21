import os
import time

from config import AppConfig


def _ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)


class TimeframeBuilder:
    """
    Builds configured OHLCV timeframes from the base 1m DataFrame.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.timeframes = self.config.require("timeframes")
        self.resample_config = self.timeframes.get("resample", {})

    def resample(self, df, rule):
        start = time.time()

        print(f"\n⏳ Resampling → {rule}")

        df_resampled = df.resample(
            rule,
            closed=self.resample_config.get("closed", "left"),
            label=self.resample_config.get("label", "right")
        ).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna()

        elapsed = time.time() - start

        print(f"✅ Done: {rule} | rows: {len(df_resampled)} | ⏱ {elapsed:.2f}s")

        return df_resampled

    def build_timeframes_and_save(
        self,
        df_1m,
        symbol=None,
        start_date=None,
        end_date=None,
        base_path=None
    ):
        symbol = symbol or self.config.require("app", "default_symbol")
        start_date = start_date or self.config.require("history", "start_date")
        end_date = end_date or self.config.require("history", "end_date")
        base_path = base_path or self.config.require("storage", "base_path")

        overall_start = time.time()

        print(f"\n📊 Starting resampling pipeline for {symbol}")
        print(f"📅 Range: {start_date} → {end_date}\n")

        base_tf = self.timeframes["base"]
        folder_1m = os.path.join(base_path, symbol, base_tf["label"])
        _ensure_folder(folder_1m)

        path_1m = os.path.join(
            folder_1m,
            f"{symbol}_{base_tf['label']}_{start_date}_to_{end_date}.csv"
        )

        t0 = time.time()
        df_1m.to_csv(path_1m)
        print(f"💾 Saved {base_tf['label']} → {path_1m} | ⏱ {time.time() - t0:.2f}s")

        execution_tf = self.timeframes["execution"]
        direction_tf = self.timeframes["direction"]
        trend_tf = self.timeframes["trend"]
        macro_tf = self.timeframes["macro"]

        df_15m = self.resample(df_1m, execution_tf["rule"])
        df_1h = self.resample(df_1m, direction_tf["rule"])
        df_5h = self.resample(df_1m, trend_tf["rule"])
        df_12h = self.resample(df_1m, macro_tf["rule"])

        def save_tf(df, tf):
            folder = os.path.join(base_path, symbol, tf["label"])
            _ensure_folder(folder)

            filepath = os.path.join(
                folder,
                f"{symbol}_{tf['label']}_{start_date}_to_{end_date}.csv"
            )

            t0 = time.time()
            df.to_csv(filepath)

            print(f"💾 Saved {tf['label']} → {filepath} | ⏱ {time.time() - t0:.2f}s")

        save_tf(df_15m, execution_tf)
        save_tf(df_1h, direction_tf)
        save_tf(df_5h, trend_tf)
        save_tf(df_12h, macro_tf)

        total_time = time.time() - overall_start

        print(f"\n🎯 Resampling pipeline completed in {total_time:.2f}s")
        print(f"📊 Final rows:")
        print(f"   {base_tf['label']}:  {len(df_1m)}")
        print(f"   {execution_tf['label']}: {len(df_15m)}")
        print(f"   {direction_tf['label']}:  {len(df_1h)}")
        print(f"   {trend_tf['label']}:  {len(df_5h)}")
        print(f"   {macro_tf['label']}: {len(df_12h)}\n")

        return df_15m, df_1h, df_5h, df_12h


def resample(df, rule, builder=None):
    builder = builder or TimeframeBuilder()
    return builder.resample(df, rule)


def build_timeframes_and_save(
    df_1m,
    symbol=None,
    start_date=None,
    end_date=None,
    base_path=None,
    builder=None
):
    builder = builder or TimeframeBuilder()
    return builder.build_timeframes_and_save(
        df_1m=df_1m,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_path=base_path
    )
