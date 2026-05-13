import pandas as pd
import time
from .binance_client import get_klines


def _klines_to_df(raw):
    """
    Internal helper: Convert raw Binance response to clean DataFrame
    """

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


# ✅ ------------------------------------------
# ✅ 1. Fetch latest candles (near-live use)
# ✅ ------------------------------------------

def fetch_recent(symbol="BTCUSDT", interval="1m", limit=1000):
    """
    Fetch most recent candles.
    Used in live / near-live mode.
    """

    raw = get_klines(symbol, interval, limit=limit)
    return _klines_to_df(raw)


# ✅ ------------------------------------------
# ✅ 2. Fetch full historical data (paginated)
# ✅ ------------------------------------------

def fetch_full_history(
    symbol="BTCUSDT",
    interval="1m",
    start_date="2017-01-01",
    end_date="2026-05-12"
):
    """
    Fetch full historical data using pagination.

    WARNING:
        1m data over many years = millions of rows.
    """

    start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
    end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)

    all_data = []
    current_start = start_ts

    while current_start < end_ts:

        raw = get_klines(
            symbol=symbol,
            interval=interval,
            limit=1000,
            startTime=current_start
        )

        if not raw:
            break

        all_data.extend(raw)

        # move forward
        last_ts = raw[-1][0]
        current_start = last_ts + 1

        print(f"Fetched up to: {pd.to_datetime(last_ts, unit='ms')}")

        # avoid rate limits
        time.sleep(0.2)

    df = _klines_to_df(all_data)

    # keep only within requested range
    df = df.loc[start_date:end_date]

    return df


# ✅ ------------------------------------------
# ✅ 3. Save data to CSV (optional helper)
# ✅ ------------------------------------------

def save_to_csv(df, filename):
    """
    Save dataframe to CSV safely.
    """

    df.to_csv(filename)
    print(f"Saved data to {filename}")


# ✅ ------------------------------------------
# ✅ 4. Load CSV (for fast backtesting)
# ✅ ------------------------------------------

def load_from_csv(filename):
    """
    Reload stored data quickly.
    """

    df = pd.read_csv(filename, parse_dates=["timestamp"])
    df.set_index("timestamp", inplace=True)

    return df
