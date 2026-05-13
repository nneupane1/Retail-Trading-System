import time


def _compute_slope(series, lookback=3):
    """
    Simple slope calculation for EMA direction.
    """

    if len(series) < lookback + 1:
        return 0

    return series.iloc[-1] - series.iloc[-lookback]


def get_bias(df_1h):
    """
    Determine market bias using 1H timeframe.

    Outputs:
    - "bullish"
    - "bearish"
    - "neutral"
    """

    start = time.time()

    print("\n🧭 Determining market bias (1H)...")

    close = df_1h["close"].iloc[-1]
    ema50 = df_1h["ema50"].iloc[-1]

    slope = _compute_slope(df_1h["ema50"], lookback=3)

    # ✅ ------------------------------
    # BIAS LOGIC
    # ✅ ------------------------------

    if close > ema50 and slope > 0:
        bias = "bullish"
        print("✅ Bullish bias: price > EMA50 and slope > 0")

    elif close < ema50 and slope < 0:
        bias = "bearish"
        print("✅ Bearish bias: price < EMA50 and slope < 0")

    else:
        bias = "neutral"
        print("⚠️ Neutral bias: no clear direction")

    # ✅ ------------------------------
    # DEBUG INFO
    # ✅ ------------------------------

    print(f"   Close: {close:.2f}")
    print(f"   EMA50: {ema50:.2f}")
    print(f"   EMA slope: {slope:.4f}")

    elapsed = time.time() - start

    print(f"⏱ Time taken: {elapsed:.2f}s")

    return bias
``
