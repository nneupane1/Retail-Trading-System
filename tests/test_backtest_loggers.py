import os
import csv
import tempfile
import unittest
from types import SimpleNamespace

from backtest.equity_logger import EquityLogger
from backtest.logger import TradeLogger


class DummyConfig:
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def require(self, *keys):
        if keys == ("backtest", "output_dir"):
            return self.output_dir
        raise KeyError(f"Unexpected config lookup: {keys}")


class BacktestLoggerTests(unittest.TestCase):
    def test_trade_logger_creates_default_directory_and_extended_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = TradeLogger(config=DummyConfig(output_dir=output_dir))

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

    def test_trade_logger_appends_completed_trade_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = TradeLogger(config=DummyConfig(output_dir=output_dir))
            trade = SimpleNamespace(
                entry_time="2026-01-01 00:00:00",
                exit_time="2026-01-01 01:00:00",
                entry_price=100.0,
                exit_price=110.0,
                pnl=12.5,
                pnl_R=1.25,
                pnl_R_total=1.25,
                pnl_R_initial=2.5,
                initial_risk_amount=5.0,
                total_risk_amount=10.0,
                bias="bullish",
                regime_score=3,
                regime_class="strong",
                entry_threshold=4,
                exit_reason="trend weakness",
                entry_layer_count=2,
                pyramid_level=1,
                conditions={
                    "score": 6,
                    "body_strength": 1.2,
                    "close_position": 0.9,
                    "upper_wick_ratio": 0.4,
                    "compression": True,
                    "breakout": True,
                }
            )

            logger.log_trade(trade)

            with open(logger.filepath, "r", newline="") as file_handle:
                rows = list(csv.DictReader(file_handle))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["entry_time"], "2026-01-01 00:00:00")
            self.assertEqual(rows[0]["exit_time"], "2026-01-01 01:00:00")
            self.assertEqual(float(rows[0]["pnl"]), 12.5)
            self.assertEqual(float(rows[0]["pnl_R_total"]), 1.25)
            self.assertEqual(float(rows[0]["pnl_R_initial"]), 2.5)
            self.assertEqual(float(rows[0]["initial_risk_amount"]), 5.0)
            self.assertEqual(float(rows[0]["total_risk_amount"]), 10.0)
            self.assertEqual(rows[0]["bias"], "bullish")
            self.assertEqual(rows[0]["regime_score"], "3")
            self.assertEqual(rows[0]["regime_class"], "strong")
            self.assertEqual(rows[0]["entry_threshold"], "4")
            self.assertEqual(rows[0]["exit_reason"], "trend weakness")
            self.assertEqual(rows[0]["entry_layer_count"], "2")
            self.assertEqual(rows[0]["pyramid_level"], "1")
            self.assertEqual(rows[0]["compression"], "True")
            self.assertEqual(rows[0]["breakout"], "True")

    def test_equity_logger_creates_default_directory_and_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = EquityLogger(config=DummyConfig(output_dir=output_dir))

            self.assertTrue(os.path.isdir(output_dir))
            self.assertTrue(os.path.exists(logger.filepath))

            with open(logger.filepath, "r", newline="") as file_handle:
                header = file_handle.readline().strip()

            self.assertEqual(header, "timestamp,equity")

    def test_equity_logger_appends_equity_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "backtest_output")
            logger = EquityLogger(config=DummyConfig(output_dir=output_dir))

            logger.log("2026-01-01 00:00:00", 1000.0)
            logger.log("2026-01-01 00:15:00", 1012.5)

            with open(logger.filepath, "r", newline="") as file_handle:
                rows = list(csv.DictReader(file_handle))

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["timestamp"], "2026-01-01 00:00:00")
            self.assertEqual(float(rows[0]["equity"]), 1000.0)
            self.assertEqual(rows[1]["timestamp"], "2026-01-01 00:15:00")
            self.assertEqual(float(rows[1]["equity"]), 1012.5)


if __name__ == "__main__":
    unittest.main()
