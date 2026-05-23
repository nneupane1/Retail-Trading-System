"""Contains low-level indicator helpers used by the feature pipeline."""

import time

from common.debug import debug_print as print


# ------------------------------------------
# EMA
# ------------------------------------------

def ema(series, period=20):

    start = time.time()

    print(f"Computing EMA{period}...")

    result = series.ewm(span=period, adjust=False).mean()

    elapsed = time.time() - start

    print(f"EMA{period} computed | Time: {elapsed:.2f}s")

    return result


# ------------------------------------------
# Rolling High
# ------------------------------------------

def rolling_high(series, period=20):

    start = time.time()

    print(f"Computing Rolling High ({period})...")

    result = series.rolling(period).max()

    elapsed = time.time() - start

    print(f"Rolling High ({period}) ready | Time: {elapsed:.2f}s")

    return result


# ------------------------------------------
# Rolling Low
# ------------------------------------------

def rolling_low(series, period=10):

    start = time.time()

    print(f"Computing Rolling Low ({period})...")

    result = series.rolling(period).min()

    elapsed = time.time() - start

    print(f"Rolling Low ({period}) ready | Time: {elapsed:.2f}s")

    return result


def atr(df, period=14):
    start = time.time()

    print(f"Computing ATR({period})...")

    previous_close = df["close"].shift(1)
    true_range = (
        df[["high", "low"]]
        .assign(
            intrabar=df["high"] - df["low"],
            high_gap=(df["high"] - previous_close).abs(),
            low_gap=(df["low"] - previous_close).abs(),
        )[["intrabar", "high_gap", "low_gap"]]
        .max(axis=1)
    )
    result = true_range.rolling(period).mean()

    elapsed = time.time() - start

    print(f"ATR({period}) ready | Time: {elapsed:.2f}s")

    return result


def session_vwap(df):
    start = time.time()

    print("Computing session VWAP...")

    session_key = df.index.normalize()
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    turnover = typical_price * df["volume"]
    cumulative_turnover = turnover.groupby(session_key).cumsum()
    cumulative_volume = df["volume"].groupby(session_key).cumsum()
    result = cumulative_turnover / (cumulative_volume + 1e-9)

    elapsed = time.time() - start

    print(f"Session VWAP ready | Time: {elapsed:.2f}s")

    return result


def macd(series, fast_period=12, slow_period=26, signal_period=9):
    start = time.time()

    print(
        "Computing MACD "
        f"({fast_period}, {slow_period}, {signal_period})..."
    )

    fast = series.ewm(span=fast_period, adjust=False).mean()
    slow = series.ewm(span=slow_period, adjust=False).mean()
    macd_line = fast - slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    elapsed = time.time() - start

    print(f"MACD ready | Time: {elapsed:.2f}s")

    return macd_line, signal_line, histogram


def bollinger_bands(series, period=20, std_dev=2.0):
    start = time.time()

    print(f"Computing Bollinger Bands ({period}, {std_dev})...")

    mid = series.rolling(period).mean()
    rolling_std = series.rolling(period).std()
    upper = mid + (rolling_std * std_dev)
    lower = mid - (rolling_std * std_dev)

    elapsed = time.time() - start

    print(f"Bollinger Bands ready | Time: {elapsed:.2f}s")

    return mid, upper, lower
