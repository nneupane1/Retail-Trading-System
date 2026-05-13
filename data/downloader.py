import pandas as pd
import time
import os
from datetime import datetime
from .binance_client import get_klines


# ✅ --------------------------------------------------
# Helper: Convert raw klines to DataFrame
# ✅ --------------------------------------------------

def _klines_to_df(raw):

    df = pd.DataFrame(raw, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])

    df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    df[["open", "high", "low", "close", "volume"]] = df[
        ["open", "high", "low", "close", "volume"]
    ].astype(float)

    df.set_index("timestamp", inplace=True)

    return df


# ✅ --------------------------------------------------
# Helper: Format timestamp
# ✅ --------------------------------------------------

def _fmt(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


# ✅ --------------------------------------------------
# MAIN: Fetch full history with progress + saving
# ✅ --------------------------------------------------

def fetch_full_history(
    symbol="BTCUSDT",
    interval="1m",
    start_date="2017-01-01",
    end_date="2026-05-12",
    base_path="data_storage"
):

    start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
    end_ts   = int(pd.Timestamp(end_date).timestamp() * 1000)

    all_data = []
    current_start = start_ts

    total_batches = 0
    start_clock = time.time()

    print(f"\n🚀 Starting download: {symbol} | {interval}")
    print(f"📅 Range: {start_date} → {end_date}\n")

    while current_start < end_ts:

        batch_start_time = time.time()

        raw = get_klines(
            symbol=symbol,
            interval=interval,
            startTime=current_start,
            endTime=end_ts,
            limit=1000,
            verbose=False
        )

        if not raw:
            print("⚠️ No more data returned. Stopping.")
            break

        all_data.extend(raw)

        last_ts = raw[-1][0]
        current_start = last_ts + 1

        total_batches += 1

        batch_time = time.time() - batch_start_time
        total_time = time.time() - start_clock

        progress_days = (last_ts - start_ts) / (1000 * 60 * 60 * 24)
        total_days = (end_ts - start_ts) / (1000 * 60 * 60 * 24)

        progress_pct = (progress_days / total_days) * 100

        print(f"📦 Batch {total_batches} | "
              f"{_fmt(raw[0][0])} → {_fmt(last_ts)} | "
              f"{progress_pct:.2f}% complete | "
              f"⏱ batch: {batch_time:.2f}s | total: {total_time:.2f}s")

        time.sleep(0.2)  # rate limit safety

    print("\n✅ Download complete. Converting to DataFrame...\n")

    df = _klines_to_df(all_data)

    df = df.loc[start_date:end_date]

    # ✅ --------------------------------------------------
    # SAVE DATA
    # ✅ --------------------------------------------------

    folder = os.path.join(base_path, symbol, interval)
    os.makedirs(folder, exist_ok=True)

    filename = f"{symbol}_{interval}_{start_date}_to_{end_date}.csv"
    filepath = os.path.join(folder, filename)

    save_start = time.time()

    df.to_csv(filepath)

    print(f"💾 Saved to: {filepath}")
    print(f"⏱ Save time: {time.time() - save_start:.2f}s")

    # ✅ FINAL STATS
    total_time = time.time() - start_clock
    print(f"\n🎯 TOTAL TIME: {total_time/60:.2f} minutes")
    print(f"📊 Total candles: {len(df)}")

    return df


# ✅ --------------------------------------------------
# Load existing CSV
# ✅ --------------------------------------------------

def load_from_csv(filepath):

    print(f"📂 Loading: {filepath}")

    start = time.time()

    df = pd.read_csv(filepath, parse_dates=["timestamp"])
    df.set_index("timestamp", inplace=True)

    print(f"✅ Loaded in {time.time() - start:.2f} sec")

    return df
