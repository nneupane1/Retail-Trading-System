import json
import tempfile
import unittest
from pathlib import Path

from common.binance_universe import (
    discover_binance_candidate_universe,
    write_discovery_reports,
)


class _ConfigStub:
    def __init__(self, discovery=None):
        self._discovery = discovery or {}

    def get(self, *keys, default=None):
        if keys == ("universe", "discovery", "enabled"):
            return self._discovery.get("enabled", default)
        if len(keys) >= 2 and keys[:2] == ("universe", "discovery"):
            return self._discovery.get(keys[2], default)
        return default


class _ClientStub:
    def get_exchange_info(self, verbose=False):
        return {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                    "permissions": ["SPOT"],
                },
                {
                    "symbol": "SOLUSDT",
                    "baseAsset": "SOL",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                    "permissions": ["SPOT"],
                },
                {
                    "symbol": "DOGEUSDT",
                    "baseAsset": "DOGE",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                    "permissions": ["SPOT"],
                },
                {
                    "symbol": "ETHDOWNUSDT",
                    "baseAsset": "ETHDOWN",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                    "permissions": ["SPOT"],
                },
                {
                    "symbol": "FDUSDUSDT",
                    "baseAsset": "FDUSD",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                    "permissions": ["SPOT"],
                },
                {
                    "symbol": "ADABTC",
                    "baseAsset": "ADA",
                    "quoteAsset": "BTC",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                    "permissions": ["SPOT"],
                },
                {
                    "symbol": "XRPUSDT",
                    "baseAsset": "XRP",
                    "quoteAsset": "USDT",
                    "status": "BREAK",
                    "isSpotTradingAllowed": True,
                    "permissions": ["SPOT"],
                },
            ]
        }

    def get_ticker_24hr(self, verbose=False):
        return [
            {"symbol": "BTCUSDT", "quoteVolume": "90000000", "count": 100000, "lastPrice": "100000", "weightedAvgPrice": "99000", "priceChangePercent": "1.2"},
            {"symbol": "SOLUSDT", "quoteVolume": "50000000", "count": 70000, "lastPrice": "180", "weightedAvgPrice": "175", "priceChangePercent": "2.1"},
            {"symbol": "DOGEUSDT", "quoteVolume": "30000000", "count": 65000, "lastPrice": "0.2", "weightedAvgPrice": "0.19", "priceChangePercent": "3.0"},
            {"symbol": "ETHDOWNUSDT", "quoteVolume": "10000000", "count": 30000, "lastPrice": "0.01", "weightedAvgPrice": "0.01", "priceChangePercent": "-8.0"},
            {"symbol": "FDUSDUSDT", "quoteVolume": "7000000", "count": 9000, "lastPrice": "1.0", "weightedAvgPrice": "1.0", "priceChangePercent": "0.0"},
            {"symbol": "ADABTC", "quoteVolume": "50000000", "count": 10000, "lastPrice": "0.00001", "weightedAvgPrice": "0.00001", "priceChangePercent": "0.2"},
            {"symbol": "XRPUSDT", "quoteVolume": "80000000", "count": 120000, "lastPrice": "2.0", "weightedAvgPrice": "1.9", "priceChangePercent": "1.0"},
        ]


class BinanceUniverseDiscoveryTests(unittest.TestCase):
    def test_discovery_filters_and_ranks_spot_usdt_symbols(self):
        config = _ConfigStub(
            {
                "enabled": True,
                "top_n": 2,
                "min_quote_volume_24h": 5_000_000.0,
                "min_trade_count_24h": 5_000,
            }
        )

        payload = discover_binance_candidate_universe(config, client=_ClientStub())

        self.assertEqual(["BTCUSDT", "SOLUSDT"], payload["candidate_symbols"])
        rejected = {row["symbol"]: row["reject_reason"] for row in payload["rejected_rows"]}
        self.assertEqual("outside_top_n_liquidity_rank", rejected["DOGEUSDT"])
        self.assertIn("excluded_symbol_suffix", rejected["ETHDOWNUSDT"])
        self.assertIn("excluded_base_asset", rejected["FDUSDUSDT"])
        self.assertIn("quote_asset_mismatch", rejected["ADABTC"])
        self.assertIn("status_not_trading", rejected["XRPUSDT"])

    def test_discovery_reports_are_written(self):
        config = _ConfigStub({"enabled": True, "top_n": 2})
        payload = discover_binance_candidate_universe(config, client=_ClientStub())

        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_discovery_reports(Path(tmpdir), payload)

            self.assertTrue(Path(report["artifacts"]["all_rows_csv"]).exists())
            self.assertTrue(Path(report["artifacts"]["selected_rows_csv"]).exists())
            self.assertTrue(Path(report["artifacts"]["rejected_rows_csv"]).exists())
            summary = json.loads(Path(report["artifacts"]["summary_json"]).read_text(encoding="utf-8"))
            self.assertEqual(2, summary["summary"]["candidate_symbol_count"])


if __name__ == "__main__":
    unittest.main()
