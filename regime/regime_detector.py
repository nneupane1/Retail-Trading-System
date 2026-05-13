import time


def _compute_slope(series, lookback=5):
    """
    Simple slope calculation over last N points.
    """

    if len(series) < lookback + 1:
        return 0

    return series.iloc[-1] - series.iloc[-lookback]


def compute_regime(df_5h, df_12h):
    """
    Multi-timeframe regime detection.

    Uses:
    - 12H → macro trend
    - 5H → confirmation

    Returns:
    - regime_score (0–4)
    """

    start = time.time()

    print("\n🌊 Computing market regime (5H + 12H)...")

    score = 0

    # ✅ ------------------------------
    # 12H (macro trend)
    # ✅ ------------------------------

    close_12h = df_12h["close"].iloc[-1]
    ema_12h = df_12h["ema50"].iloc[-1]

    if close_12h > ema_12h:
        score += 2
        print("✅ 12H bullish (price > EMA50)")

    else:
        print("❌ 12H not bullish")

    # ✅ slope (trend strength)
    slope_12h = _compute_slope(df_12h["ema50"], lookback=5)

    if slope_12h > 0:
        score += 1
        print(f"✅ 12H EMA slope positive (+{slope_12h:.4f})")
    else:
        print("❌ 12H EMA slope not positive")

    # ✅ ------------------------------
    # 5H (confirmation)
    # ✅ ------------------------------

    close_5h = df_5h["close"].iloc[-1]
    ema_5h = df_5h["ema50"].iloc[-1]

    if close_5h > ema_5h:
        score += 1
        print("✅ 5H confirms uptrend (price > EMA50)")
    else:
        print("❌ 5H not confirming trend")

    # ✅ ------------------------------
    # FINAL OUTPUT
    # ✅ ------------------------------

    elapsed = time.time() - start

    print(f"\n📊 Regime Score: {score}/4")
    print(f"⏱ Time taken: {elapsed:.2f}s")

    # ✅ interpretation hint (optional but useful)
    if score >= 3:
        print("🔥 Strong trending environment")
    elif score == 2:
        print("⚠️ Moderate trend")
    else:
        print("❌ Weak / choppy market")

    return score
