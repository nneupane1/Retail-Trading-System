import time


# ✅ ------------------------------------------
# EMA
# ✅ ------------------------------------------

def ema(series, period=20):

    start = time.time()

    print(f"🧮 Computing EMA{period}...")

    result = series.ewm(span=period, adjust=False).mean()

    elapsed = time.time() - start

    print(f"✅ EMA{period} computed | ⏱ {elapsed:.2f}s")

    return result


# ✅ ------------------------------------------
# ATR (simple version)
# ✅ ------------------------------------------

def atr(df, period=14):

    start = time.time()

    print(f"🧮 Computing ATR{period}...")

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    tr = high_low.combine(high_close, max).combine(low_close, max)

    result = tr.rolling(period).mean()

    elapsed = time.time() - start

    print(f"✅ ATR{period} computed | ⏱ {elapsed:.2f}s")

    return result


# ✅ ------------------------------------------
# Rolling High
# ✅ ------------------------------------------

def rolling_high(series, period=20):

    start = time.time()

    print(f"🧮 Computing Rolling High ({period})...")

    result = series.rolling(period).max()

    elapsed = time.time() - start

    print(f"✅ Rolling High ({period}) ready | ⏱ {elapsed:.2f}s")

    return result


# ✅ ------------------------------------------
# Rolling Low
# ✅ ------------------------------------------

def rolling_low(series, period=10):

    start = time.time()

    print(f"🧮 Computing Rolling Low ({period})...")

    result = series.rolling(period).min()

    elapsed = time.time() - start

    print(f"✅ Rolling Low ({period}) ready | ⏱ {elapsed:.2f}s")

    return result
