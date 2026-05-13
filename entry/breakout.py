import time


def is_breakout(row):
    """
    Determine if current candle is a valid breakout.

    Rule:
    - CLOSE must break previous HH (not wick)
    """

    start = time.time()

    print("\n🚀 Checking breakout condition...")

    # ✅ breakout condition (strict: close-based)
    breakout = row["close"] > row["hh20_prev"]

    if breakout:
        print("✅ Breakout detected (close > previous HH)")
    else:
        print("❌ No breakout")

    print(f"   Close: {row['close']:.2f}")
    print(f"   Prev HH: {row['hh20_prev']:.2f}")

    elapsed = time.time() - start
    print(f"⏱ Time taken: {elapsed:.4f}s")

    return breakout
