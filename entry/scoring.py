import time


def compute_score(row, bias):
    """
    Compute trade quality score.

    Combines:
    - bias
    - trend alignment
    - compression
    - breakout
    - candle strength
    """

    start = time.time()

    print("\n🧠 Computing entry score...")

    score = 0

    # ✅ ----------------------------------
    # 1. BIAS (direction alignment)
    # ✅ ----------------------------------

    if bias == "bullish":
        score += 2
        print("✅ Bias bullish (+2)")

    elif bias == "bearish":
        print("⚠️ Bearish bias (no score for long)")

    else:
        print("❌ Neutral bias")

    # ✅ ----------------------------------
    # 2. TREND CONFIRMATION (15m)
    # ✅ ----------------------------------

    if row["close"] > row["ema20"]:
        score += 1
        print("✅ Price above EMA20 (+1)")
    else:
        print("❌ Price below EMA20")

    # ✅ ----------------------------------
    # 3. COMPRESSION (setup quality)
    # ✅ ----------------------------------

    if row["compression"]:
        score += 1
        print("✅ Compression detected (+1)")
    else:
        print("❌ No compression")

    # ✅ ----------------------------------
    # 4. BREAKOUT (core trigger)
    # ✅ ----------------------------------

    if row["breakout"]:
        score += 2
        print("✅ Breakout confirmed (+2)")
    else:
        print("❌ No breakout")

    # ✅ ----------------------------------
    # 5. MOMENTUM (candle quality)
    # ✅ ----------------------------------

    if row["body_strength"] > 1.3:
        score += 1
        print("✅ Strong body (+1)")
    else:
        print("❌ Weak body")

    if row["close_position"] > 0.6:
        score += 1
        print("✅ Strong close position (+1)")
    else:
        print("❌ Weak close")

    if row["upper_wick_ratio"] < 1:
        score += 1
        print("✅ Low rejection (+1)")
    else:
        print("❌ High rejection wick")

    # ✅ ----------------------------------
    # FINAL OUTPUT
    # ✅ ----------------------------------

    elapsed = time.time() - start

    print(f"\n🎯 Final Score: {score}")
    print(f"⏱ Time taken: {elapsed:.4f}s")

    # ✅ quality interpretation
    if score >= 6:
        print("🔥 High-quality setup")
    elif score >= 5:
        print("✅ Tradable setup")
    else:
        print("❌ Weak setup")

    return score
