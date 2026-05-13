import time


def check_pyramiding(price, entry_price, R, current_level):
    """
    Determine if we should add to the position.

    Logic:
    - Add at +1R → level 1
    - Add at +2R → level 2

    Parameters:
    - price: current market price
    - entry_price: initial entry
    - R: risk unit (entry - stop)
    - current_level: current pyramid level (0,1,2)

    Returns:
    - new_level
    """

    start = time.time()

    print("\n📈 Checking pyramiding levels...")

    new_level = current_level

    # ✅ Level 1: +1R
    if current_level == 0 and price >= entry_price + R:
        new_level = 1
        print("✅ Triggered Level 1 (>= +1R)")

    # ✅ Level 2: +2R
    elif current_level == 1 and price >= entry_price + 2 * R:
        new_level = 2
        print("✅ Triggered Level 2 (>= +2R)")

    else:
        print("❌ No pyramiding condition met")

    print(f"   Price: {price:.2f}")
    print(f"   Entry: {entry_price:.2f}")
    print(f"   R: {R:.2f}")
    print(f"   Level: {current_level} → {new_level}")

    elapsed = time.time() - start
    print(f"⏱ Time taken: {elapsed:.4f}s")

    return new_level


def get_pyramid_size(base_size, level):
    """
    Define how much to add at each level.

    Simple rule:
    - Level 1 → +50% of base
    - Level 2 → +50% of base
    """

    print("\n💰 Calculating pyramid position size...")

    if level == 1:
        size = base_size * 0.5
        print(f"✅ Add size (Level 1): {size:.4f}")

    elif level == 2:
        size = base_size * 0.5
        print(f"✅ Add size (Level 2): {size:.4f}")

    else:
        size = 0
        print("❌ No additional position")

    return size
