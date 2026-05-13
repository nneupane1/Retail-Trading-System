import time


def is_breakout(row):
    """
    PURE breakout definition.

    Rule:
    - CLOSE must break previous HH (no momentum here)
    """

    start = time.time()

    print("\n🚀 Checking breakout...")

    breakout = row["close"] > row["hh20_prev"]

    if breakout:
        print("✅ Breakout (CLOSE > previous HH)")
    else:
        print("❌ No breakout")

    print(f"   Close: {row['close']:.2f}")
    print(f"   Prev HH: {row['hh20_prev']:.2f}")

    print(f"⏱ Time taken: {time.time() - start:.4f}s")

    return breakout
