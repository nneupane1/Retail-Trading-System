"""Contains low-level indicator helpers used by the feature pipeline."""

import time


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
