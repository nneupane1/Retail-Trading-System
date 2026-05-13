import time


def compute_candle_metrics(df):
    """
    Compute quantitative candle behavior metrics.

    Features:
    - body_strength
    - upper_wick_ratio
    - lower_wick_ratio
    - close_position
    """

    start = time.time()

    print("\n🧮 Computing candle metrics...")

    # ✅ basic components
    body = (df["close"] - df["open"]).abs()
    avg_body = body.rolling(10).mean()

    high = df["high"]
    low = df["low"]
    close = df["close"]
    open_ = df["open"]

    # ✅ full candle range
    candle_range = high - low

    # ✅ wick calculations
    upper_wick = high - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - low

    # ✅ core metrics
    df["body_strength"] = body / (avg_body + 1e-6)

    df["upper_wick_ratio"] = upper_wick / (body + 1e-6)
    df["lower_wick_ratio"] = lower_wick / (body + 1e-6)

    df["close_position"] = (close - low) / (candle_range + 1e-6)

    elapsed = time.time() - start

    print("✅ Candle metrics computed")
    print(f"⏱ Time taken: {elapsed:.2f}s")

    print("\n📊 Sample output:")
    print(df[[
        "body_strength",
        "upper_wick_ratio",
        "lower_wick_ratio",
        "close_position"
    ]].tail(3))

    return df
