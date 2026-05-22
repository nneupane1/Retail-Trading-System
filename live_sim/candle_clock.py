"""Detects whether a new execution-timeframe candle is available for near-live simulation."""

import time

from common.debug import debug_print as print


def is_new_15m_candle(df_15m, last_candle_time):
    """
    Detect if a new 15m candle has formed.

    Parameters:
    - df_15m: resampled 15m dataframe
    - last_candle_time: previously seen candle timestamp

    Returns:
    - (is_new: bool, updated_last_time)
    """

    start = time.time()

    if df_15m.empty:
        print("\nChecking 15m candle...")
        print("No 15m candles available yet")
        print(f"Elapsed: {time.time() - start:.4f}s")
        return False, last_candle_time

    current_time = df_15m.index[-1]

    print("\nChecking 15m candle...")

    if last_candle_time is None:
        print("First run -> initializing candle clock")
        print(f"  Current candle: {current_time}")

        return True, current_time

    if current_time != last_candle_time:
        print("New 15m candle detected")
        print(f"  Previous: {last_candle_time}")
        print(f"  Current:  {current_time}")

        return True, current_time

    print("No new candle yet")

    print(f"Elapsed: {time.time() - start:.4f}s")

    return False, last_candle_time
