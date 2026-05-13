import time
from simulation.trade import Trade


def generate_entry(row, score, bias):
    """
    Final decision engine.

    Converts score → actual trade signal.
    Creates Trade object if conditions are met.
    """

    start = time.time()

    print("\n⚡ Running entry engine...")

    # ✅ Entry threshold
    ENTRY_THRESHOLD = 5

    # ✅ Only trade in bullish direction (for now)
    if bias != "bullish":
        print("❌ No entry: bias not bullish")
        return None

    # ✅ Score check
    if score < ENTRY_THRESHOLD:
        print(f"❌ No entry: score too low ({score} < {ENTRY_THRESHOLD})")
        return None

    # ✅ Breakout must be present (core rule)
    if not row["breakout"]:
        print("❌ No entry: breakout not confirmed")
        return None

    # ✅ Optional: allow retest as alternative (if you want later)
    # if not (row["breakout"] or row["retest"]):
    #     return None

    # ✅ Create trade
    trade = Trade(row, score)

    print("\n✅ ENTRY SIGNAL GENERATED")
    print(f"   Time: {row.name}")
    print(f"   Price: {row['close']:.2f}")
    print(f"   Score: {score}")
    print(f"   Bias: {bias}")

    elapsed = time.time() - start
    print(f"⏱ Time taken: {elapsed:.4f}s")

    return trade
