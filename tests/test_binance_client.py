import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

import requests

from data.binance_client import BinanceClient


class DummyResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class DummyConfig:
    def __init__(self, data, root_dir=None):
        self.data = data
        self.root_dir = Path(root_dir or ".").resolve()

    def require(self, *keys):
        value = self.data
        for key in keys:
            value = value[key]
        return value

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


def make_config(**binance_overrides):
    return DummyConfig({
        "app": {
            "default_symbol": "BTCUSDT",
        },
        "binance": {
            "base_url": "https://api.binance.com",
            "klines_path": "/api/v3/klines",
            "default_interval": "1m",
            "historical_limit": 1000,
            "request_timeout_seconds": 20,
            "retry_attempts": 1,
            "retry_backoff_seconds": 1,
            "retry_status_codes": [418, 429, 500, 502, 503, 504],
            "retry_logging_enabled": True,
            "ssl_verify": True,
            "ca_bundle_path": None,
            **binance_overrides,
        },
    })


class BinanceClientTlsTests(unittest.TestCase):
    def setUp(self):
        self._env_patcher = patch.dict(
            os.environ,
            {
                "BINANCE_CA_BUNDLE_PATH": "",
                "REQUESTS_CA_BUNDLE": "",
                "SSL_CERT_FILE": "",
            },
        )
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    @patch("data.binance_client.requests.get")
    def test_requests_use_boolean_ssl_verify_setting(self, mock_get):
        mock_get.return_value = DummyResponse([])
        client = BinanceClient(config=make_config(ssl_verify=False))

        client.get_klines(verbose=False)

        self.assertFalse(mock_get.call_args.kwargs["verify"])

    @patch("data.binance_client.requests.get")
    def test_requests_use_resolved_custom_ca_bundle(self, mock_get):
        mock_get.return_value = DummyResponse([])

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir) / "corp-root.pem"
            bundle.write_text("dummy cert", encoding="utf-8")

            config = make_config(ca_bundle_path="corp-root.pem")
            config.root_dir = Path(temp_dir)
            client = BinanceClient(config=config)

            client.get_klines(verbose=False)

            self.assertEqual(mock_get.call_args.kwargs["verify"], str(bundle))

    def test_missing_custom_ca_bundle_raises_clear_error(self):
        config = make_config(ca_bundle_path="missing.pem")
        config.root_dir = Path(tempfile.gettempdir())
        client = BinanceClient(config=config)

        with self.assertRaises(FileNotFoundError):
            client.get_klines(verbose=False)

    @patch("data.binance_client.requests.get")
    def test_retry_callback_receives_retry_metadata(self, mock_get):
        events = []
        config = make_config(
            retry_attempts=2,
            retry_backoff_seconds=1.5,
        )
        client = BinanceClient(
            config=config,
            retry_callback=lambda **payload: events.append(payload),
        )
        mock_get.side_effect = requests.RequestException("network down")

        with self.assertRaises(Exception):
            client.get_klines(verbose=False)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["attempt"], 1)
        self.assertEqual(events[0]["total_attempts"], 2)
        self.assertEqual(events[0]["delay"], 1.5)
        self.assertIn("network down", str(events[0]["reason"]))


if __name__ == "__main__":
    unittest.main()
