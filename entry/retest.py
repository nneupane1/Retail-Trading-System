import time


def is_retest(row):
    """
    Detect a valid retest setup.

    Logic (for long trades):
    1. Price previously broke out
    2. Price pulls back near breakout level (HH_20)
    3. Holds above EMA20
    4. Shows continuation (close back above prior HH zone)

    NOTE:
    Requires:
    - row["hh20"]
    - row["hh20_prev"]
    - row["ema20"]
    """

    start = time.time()

    print("\n🔁 Checking retest condition...")

    price = row["close"]
    hh = row["hh20"]
    prev_hh = row["hh20_prev"]
    ema20 = row["ema20"]

    # ✅ Step 1: pullback into zone (near previous HH)
    pullback = price <= prev_hh

    # ✅ Step 2: holds above EMA20 (trend intact)
    hold = price > ema20

    # ✅ Step 3: continuation attempt
    continuation = price > prev_hh

    retest = pullback and hold and continuation

    # ✅ Debug prints
    print(f"   Price: {price:.2f}")
    print(f"   Prev HH: {prev_hh:.2f}")
    print(f"   EMA20: {ema20:.2f}")

    print(f"   Pullback: {'✅' if pullback else '❌'}")
    print(f"   Hold above EMA20: {'✅' if hold else '❌'}")
    print(f"   Continuation: {'✅' if continuation else '❌'}")

    if retest:
        print("✅ Retest setup confirmed")
    else:
        print("❌ No valid retest")

    elapsed = time.time() - start
    print(f"⏱ Time taken: {elapsed:.4f}s")

    return retest
