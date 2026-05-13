import requests
import pandas as pd
import time

BASE_URL = "https://api.binance.com/api/v3/klines"


def get_klines(symbol, interval, start_ts, end_ts, limit=1000):
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ts,
        "endTime": end_ts,
        "limit": limit
    }

    response = requests.get(BASE_URL, params=params)

    if response.status_code != 200:
        raise Exception(f"API Error: {response.text}")

    return response.json()


def fetch_full_history(symbol="BTCUSDT", interval="1m"):
    start = pd.Timestamp("2017-01-01").timestamp() * 1000
    end   = pd.Timestamp("2026-05-12").timestamp() * 1000

    all_data = []
    current_start = int(start)

    while current_start < end:

        data = get_klines(
            symbol,
            interval,
            start_ts=current_start,
            end_ts=int(end),
            limit=1000
        )

        if not data:
            break

        all_data.extend(data)

        # move to next batch
        last_timestamp = data[-1][0]
        current_start = last_timestamp + 1

        # avoid rate limits
        time.sleep(0.2)

    # convert to dataframe
    df = pd.DataFrame(all_data, columns=[
        "timestamp","open","high","low","close","volume",
        "close_time","qav","trades","taker_base","taker_quote","ignore"
    ])

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.astype(float)

    df.set_index("timestamp", inplace=True)

    return df[["open","high","low","close","volume"]]
