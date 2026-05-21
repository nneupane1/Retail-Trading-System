"""Provides a small Binance REST client for public market data and future authenticated endpoints."""

import requests
import time
import os
from datetime import datetime
from urllib.parse import urljoin

from config import AppConfig, EnvLoader


class BinanceClient:
    """
    Binance REST client.
    Public market data works without keys; keys are loaded for future
    authenticated endpoints and never printed.
    """

    def __init__(self, config=None):
        EnvLoader().load()

        self.config = config or AppConfig.load()
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")

        base_url = self.config.require("binance", "base_url")
        klines_path = self.config.require("binance", "klines_path")

        self.klines_url = urljoin(base_url.rstrip("/") + "/", klines_path.lstrip("/"))
        self.timeout = self.config.require("binance", "request_timeout_seconds")
        self.retry_attempts = self.config.require("binance", "retry_attempts")
        self.retry_backoff = self.config.require("binance", "retry_backoff_seconds")

    def get_klines(
        self,
        symbol=None,
        interval=None,
        startTime=None,
        endTime=None,
        limit=None,
        verbose=True
    ):
        symbol = symbol or self.config.require("app", "default_symbol")
        interval = interval or self.config.require("binance", "default_interval")
        limit = limit or self.config.require("binance", "historical_limit")

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }

        if startTime is not None:
            params["startTime"] = startTime
        if endTime is not None:
            params["endTime"] = endTime

        headers = {}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        start_clock = time.time()

        if verbose:
            print(f"\nFetching {symbol} | {interval}")
            if startTime is not None:
                print(f"  From: {_format_time(startTime)}")
            if endTime is not None:
                print(f"  To:   {_format_time(endTime)}")

        last_error = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = requests.get(
                    self.klines_url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    elapsed = time.time() - start_clock

                    if verbose:
                        print(f"Received {len(data)} candles")
                        print(f"Elapsed: {elapsed:.2f} sec")

                        if data:
                            first = _format_time(data[0][0])
                            last = _format_time(data[-1][0])
                            print(f"  Range: {first} -> {last}")

                    return data

                last_error = Exception(
                    f"Binance API error: {response.status_code} | {response.text}"
                )

            except requests.RequestException as exc:
                last_error = exc

            if attempt < self.retry_attempts:
                time.sleep(self.retry_backoff * attempt)

        raise Exception(f" Binance request failed: {last_error}")


def _format_time(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def get_klines(
    symbol=None,
    interval=None,
    startTime=None,
    endTime=None,
    limit=None,
    verbose=True,
    client=None
):
    """
    Compatibility wrapper around BinanceClient.
    """
    client = client or BinanceClient()
    return client.get_klines(
        symbol=symbol,
        interval=interval,
        startTime=startTime,
        endTime=endTime,
        limit=limit,
        verbose=verbose
    )
