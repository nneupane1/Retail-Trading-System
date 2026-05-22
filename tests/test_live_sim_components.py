import os
import tempfile
import unittest

import pandas as pd

from live_sim.candle_clock import is_new_15m_candle
from live_sim.logger import LiveTradeLogger


class DummyConfig:
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def require(self, *keys):
        if keys == ("live_sim", "output_dir"):
            return self.output_dir
        raise KeyError(f"Unexpected config lookup: {keys}")


class CandleClockTests(unittest.TestCase):
    def test_empty_dataframe_does_not_crash_or_advance_clock(self):
        last_candle_time = pd.Timestamp("2026-01-01 00:00:00")
        df = pd.DataFrame()

        is_new, updated_time = is_new_15m_candle(df, last_candle_time)

        self.assertFalse(is_new)
        self.assertEqual(updated_time, last_candle_time)


class LiveTradeLoggerTests(unittest.TestCase):
    def test_default_configured_filepath_creates_directory_and_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "live_output")
            logger = LiveTradeLogger(config=DummyConfig(output_dir=output_dir))

            self.assertTrue(os.path.isdir(output_dir))
            self.assertTrue(os.path.exists(logger.filepath))

            with open(logger.filepath, "r", newline="") as file_handle:
                header = file_handle.readline().strip()

            self.assertEqual(
                header,
                "entry_time,exit_time,entry_price,exit_price,pnl,pnl_R,pnl_R_total,"
                "pnl_R_initial,initial_risk_amount,total_risk_amount,bias,regime_score,"
                "regime_class,entry_threshold,exit_reason,entry_layer_count,pyramid_level,"
                "score,body_strength,close_position,upper_wick_ratio,compression,breakout",
            )


if __name__ == "__main__":
    unittest.main()
