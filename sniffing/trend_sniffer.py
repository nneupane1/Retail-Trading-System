import time


def is_trend_alive(row):
    """
    Determine if trend is still strong (15m timeframe).

    Logic:
    - Price stays above EMA20
    - Momentum is not weak
    - No strong rejection (upper wick)

    Returns:
    - True → HOLD
    - False → EXIT warning
    """

    start = time.time()

    print("\n👃 Sniffing trend strength...")

    price = row["close"]
    ema20 = row["ema20"]
    body_strength = row["body_strength"]
    upper_wick = row["upper_wick_ratio"]
    close_pos = row["close_position"]

    # ✅ Conditions
    above_ema = price > ema20
    strong_body = body_strength > 0.8
    low_rejection = upper_wick < 1.5
    strong_close = close_pos > 0.4

    trend_alive = above_ema and strong_body and low_rejection and strong_close

    # ✅ Debug prints
    print(f"   Price: {price:.2f}")
    print(f"   EMA20: {ema20:.2f}")

    print(f"\n   Above EMA20: {'✅' if above_ema else '❌'}")
    print(f"   Body strength: {body_strength:.2f} {'✅' if strong_body else '❌'}")
    print(f"   Upper wick: {upper_wick:.2f} {'✅' if low_rejection else '❌'}")
    print(f"   Close position: {close_pos:.2f} {'✅' if strong_close else '❌'}")

    if trend_alive:
        print("\n✅ Trend is alive → HOLD")
    else:
        print("\n❌ Trend weakening → consider EXIT")

    elapsed = time.time() - start
    print(f"⏱ Time taken: {elapsed:.4f}s")

    return trend_alive
