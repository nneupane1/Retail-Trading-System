import time


def calculate_position_size(
    equity,
    risk_per_trade,
    entry_price,
    stop_price
):
    """
    Calculate position size based on risk.

    Parameters:
    - equity: total account value
    - risk_per_trade: fraction (e.g. 0.01 for 1%)
    - entry_price: trade entry price
    - stop_price: stop loss price

    Returns:
    - position_size (units)
    """

    start = time.time()

    print("\n💰 Calculating position size...")

    # ✅ absolute risk in $ terms
    risk_amount = equity * risk_per_trade

    # ✅ distance between entry and stop
    risk_per_unit = abs(entry_price - stop_price)

    if risk_per_unit == 0:
        print("❌ Invalid stop distance (zero)")
        return 0

    # ✅ final size
    position_size = risk_amount / risk_per_unit

    # ✅ debug info
    print(f"   Equity: {equity:.2f}")
    print(f"   Risk per trade: {risk_per_trade * 100:.2f}%")
    print(f"   Risk amount: {risk_amount:.2f}")

    print(f"\n   Entry: {entry_price:.2f}")
    print(f"   Stop:  {stop_price:.2f}")
    print(f"   Risk per unit: {risk_per_unit:.2f}")

    print(f"\n✅ Position size: {position_size:.4f} units")

    elapsed = time.time() - start
    print(f"⏱ Time taken: {elapsed:.4f}s")

    return position_size
