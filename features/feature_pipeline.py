import time

from .indicators import ema, atr, rolling_high, rolling_low
from .candle_metrics import compute_candle_metrics


def compute_features(df):
    """
    Full feature pipeline:
    - Trend (EMA)
    - Volatility (ATR)
    - Structure (HH/LL)
    - Compression
    - Breakout
    - Candle metrics
    """

    overall_start = time.time()

    print("\n🚀 Starting feature pipeline...\n")

    # ✅ ------------------------------
    # 1. TREND (EMA)
    # ✅ ------------------------------

    t0 = time.time()

    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)

    print(f"✅ Trend features done | ⏱ {time.time() - t0:.2f}s\n")

    # ✅ ------------------------------
    # 2. VOLATILITY (ATR)
    # ✅ ------------------------------

    t0 = time.time()

    df["atr"] = atr(df, 14)

    print(f"✅ Volatility (ATR) done | ⏱ {time.time() - t0:.2f}s\n")

    # ✅ ------------------------------
    # 3. STRUCTURE (HH / LL)
    # ✅ ------------------------------

    t0 = time.time()

    df["hh20"] = rolling_high(df["high"], 20)
    df["ll10"] = rolling_low(df["low"], 10)

    print(f"✅ Structure (HH/LL) done | ⏱ {time.time() - t0:.2f}s\n")

    # ✅ ------------------------------
    # 4. COMPRESSION
    # ✅ ------------------------------

    t0 = time.time()

    df["range_10"] = (
        df["high"].rolling(10).max() -
        df["low"].rolling(10).min()
    )

    df["range_30"] = (
        df["high"].rolling(30).max() -
        df["low"].rolling(30).min()
    )

    df["compression"] = df["range_10"] < (0.7 * df["range_30"])

    print(f"✅ Compression computed | ⏱ {time.time() - t0:.2f}s\n")

    # ✅ ------------------------------
    # 5. BREAKOUT (CLOSE-based)
    # ✅ ------------------------------

    t0 = time.time()

    df["breakout"] = df["close"] > df["hh20"].shift(1)

    print(f"✅ Breakout logic applied | ⏱ {time.time() - t0:.2f}s\n")

    # ✅ ------------------------------
    # 6. CANDLE METRICS (IMPORTANT)
    # ✅ ------------------------------

    df = compute_candle_metrics(df)

    # ✅ ------------------------------
    # FINAL SUMMARY
    # ✅ ------------------------------

    total_time = time.time() - overall_start

    print("\n🎯 Feature pipeline completed")
    print(f"⏱ Total time: {total_time:.2f}s")

    print("\n📊 Final columns:")
    print(df.columns.tolist())

    return df
