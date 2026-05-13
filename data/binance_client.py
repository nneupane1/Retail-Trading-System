import requests
import time
from datetime import datetime


BASE_URL = "https://api.binance.com/api/v3/klines"


def _format_time(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def get_klines(
    symbol="BTCUSDT",
    interval="1m",
    startTime=None,
    endTime=None,
    limit=1000,
    verbose=True
):
    """
    Fetch klines from Binance with timing + progress info.

    Parameters:
    - symbol: trading pair
    - interval: timeframe
    - startTime / endTime: in milliseconds
    - limit: max candles per request (max 1000)
    - verbose: print progress info

    Returns:
    - raw JSON data
    """

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    if startTime:
        params["startTime"] = startTime
    if endTime:
        params["endTime"] = endTime

    start_clock = time.time()

    if verbose:
        print(f"\n📡 Fetching {symbol} | {interval}")
        if startTime:
            print(f"   From: {_format_time(startTime)}")
        if endTime:
            print(f"   To:   {_format_time(endTime)}")

    response = requests.get(BASE_URL, params=params)

    elapsed = time.time() - start_clock

    if response.status_code != 200:
        raise Exception(f"❌ API Error: {response.status_code} | {response.text}")

    data = response.json()

    if verbose:
        print(f"✅ Received {len(data)} candles")
        print(f"⏱ Time taken: {elapsed:.2f} sec")

        if data:
            first = _format_time(data[0][0])
            last  = _format_time(data[-1][0])
            print(f"   Range: {first} → {last}")

    return data
