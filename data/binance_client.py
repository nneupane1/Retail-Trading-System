"""Provides a small Binance REST client for public market data and future authenticated endpoints."""

import requests
import time
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from common.debug import debug_print as print
from config import AppConfig, EnvLoader


class BinanceClient:
    """
    Binance REST client.

    Public market data works without keys; keys are loaded for future
    authenticated endpoints and never printed. Network, timeout, rate-limit,
    and server-side failures are retried according to the JSON configuration so
    long-running data jobs can recover from transient Binance/API issues.
    """

    def __init__(self, config=None, retry_callback=None):
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
        self.retry_status_codes = set(
            self.config.require("binance", "retry_status_codes")
        )
        self.retry_logging_enabled = self.config.require(
            "binance",
            "retry_logging_enabled"
        )
        self.ssl_verify = self.config.get(
            "binance",
            "ssl_verify",
            default=True
        )
        self.ca_bundle_path = self.config.get(
            "binance",
            "ca_bundle_path",
            default=None
        )
        self._warnings_configured = False
        self.retry_callback = retry_callback

    def _verify_setting(self):
        if self.ca_bundle_path:
            bundle_path = Path(self.ca_bundle_path)
            if not bundle_path.is_absolute():
                bundle_path = self.config.root_dir / bundle_path

            if not bundle_path.exists():
                raise FileNotFoundError(
                    f"Configured CA bundle not found: {bundle_path}"
                )

            return str(bundle_path)

        return bool(self.ssl_verify)

    def _configure_tls_warning_behavior(self, verify_setting):
        if self._warnings_configured:
            return

        if verify_setting is False:
            disable_warnings(InsecureRequestWarning)

        self._warnings_configured = True

    def describe_verify_mode(self):
        verify_setting = self._verify_setting()

        if isinstance(verify_setting, str):
            return f"custom CA bundle ({verify_setting})"
        if verify_setting:
            return "enabled"
        return "disabled"

    def _retry_delay(self, attempt):
        return self.retry_backoff * attempt

    def _emit_retry_event(self, attempt, delay, reason):
        if not callable(self.retry_callback):
            return

        self.retry_callback(
            attempt=attempt,
            total_attempts=self.retry_attempts,
            delay=delay,
            reason=reason,
        )

    def _log_retry(self, attempt, delay, reason):
        self._emit_retry_event(attempt, delay, reason)

        if self.retry_callback is not None:
            return

        if not self.retry_logging_enabled:
            return

        print(
            "Binance request failed "
            f"(attempt {attempt}/{self.retry_attempts}): {reason}"
        )
        print(f"Retrying in {delay:.2f}s...")

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
        verify_setting = self._verify_setting()
        self._configure_tls_warning_behavior(verify_setting)

        if verbose:
            print(f"\nFetching {symbol} | {interval}")
            if startTime is not None:
                print(f"  From: {_format_time(startTime)}")
            if endTime is not None:
                print(f"  To:   {_format_time(endTime)}")
            if isinstance(verify_setting, str):
                print(f"  TLS verify: custom CA bundle -> {verify_setting}")
            elif verify_setting:
                print("  TLS verify: enabled")
            else:
                print("  TLS verify: DISABLED")

        last_error = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = requests.get(
                    self.klines_url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                    verify=verify_setting
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

                if response.status_code not in self.retry_status_codes:
                    raise last_error

            except requests.RequestException as exc:
                last_error = exc

            if attempt < self.retry_attempts:
                delay = self._retry_delay(attempt)
                self._log_retry(attempt, delay, last_error)
                time.sleep(delay)

        raise Exception(
            f"Binance request failed after {self.retry_attempts} attempts: {last_error}"
        )


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
