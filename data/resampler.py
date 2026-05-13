import os
import time


# ✅ ------------------------------------------
# Helper: ensure folder exists
# ✅ ------------------------------------------

def _ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)


# ✅ ------------------------------------------
# Core resampler
# ✅ ------------------------------------------

def resample(df, rule):

    start = time.time()

    print(f"\n⏳ Resampling → {rule}")

    df_resampled = df.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()

    elapsed = time.time() - start

    print(f"✅ Done: {rule} | rows: {len(df_resampled)} | ⏱ {elapsed:.2f}s")

    return df_resampled


# ✅ ------------------------------------------
# Build all TFs + save
# ✅ ------------------------------------------

def build_timeframes_and_save(
    df_1m,
    symbol="BTCUSDT",
    start_date="2017-01-01",
    end_date="2026-05-12",
    base_path="data_storage"
):

    overall_start = time.time()

    print(f"\n📊 Starting resampling pipeline for {symbol}")
    print(f"📅 Range: {start_date} → {end_date}\n")

    # ✅ 1m save
    folder_1m = os.path.join(base_path, symbol, "1m")
    _ensure_folder(folder_1m)

    path_1m = os.path.join(
        folder_1m,
        f"{symbol}_1m_{start_date}_to_{end_date}.csv"
    )

    t0 = time.time()
    df_1m.to_csv(path_1m)
    print(f"💾 Saved 1m → {path_1m} | ⏱ {time.time() - t0:.2f}s")

    # ✅ resample
    df_15m = resample(df_1m, "15T")
    df_1h  = resample(df_1m, "1H")
    df_5h  = resample(df_1m, "5H")
    df_12h = resample(df_1m, "12H")

    # ✅ save function
    def save_tf(df, tf_name):

        folder = os.path.join(base_path, symbol, tf_name)
        _ensure_folder(folder)

        filepath = os.path.join(
            folder,
            f"{symbol}_{tf_name}_{start_date}_to_{end_date}.csv"
        )

        t0 = time.time()
        df.to_csv(filepath)

        print(f"💾 Saved {tf_name} → {filepath} | ⏱ {time.time() - t0:.2f}s")

    # ✅ save all TFs
    save_tf(df_15m, "15m")
    save_tf(df_1h, "1h")
    save_tf(df_5h, "5h")
    save_tf(df_12h, "12h")

    total_time = time.time() - overall_start

    print(f"\n🎯 Resampling pipeline completed in {total_time:.2f}s")
    print(f"📊 Final rows:")
    print(f"   1m:  {len(df_1m)}")
    print(f"   15m: {len(df_15m)}")
    print(f"   1h:  {len(df_1h)}")
    print(f"   5h:  {len(df_5h)}")
    print(f"   12h: {len(df_12h)}\n")

    return df_15m, df_1h, df_5h, df_12h
