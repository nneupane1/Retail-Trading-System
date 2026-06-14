"""Downloads, checkpoints, resumes, validates, saves, and loads Binance OHLCV market data."""

import pandas as pd
import time
import os
import json
import shutil
from datetime import datetime
from pathlib import Path

from common.download_progress import DownloadProgressDisplay
from common.debug import debug_print as print
from config import AppConfig
from .binance_client import BinanceClient


def _parse_storage_timestamp(value):
    return pd.Timestamp(str(value).replace("T", " ").replace(".", ":"))


def _fmt(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


def _fmt_duration(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


class MarketDataDownloader:
    """
    Handles all disk-backed market data access.

    The downloader writes historical Binance batches to a partial CSV as soon
    as they arrive, stores JSON checkpoint metadata after each batch, and uses
    those two artifacts to resume safely after interruptions. This makes long
    one-minute history downloads restartable without wasting previously fetched
    data.
    """

    def __init__(self, config=None, client=None):
        self.config = config or AppConfig.load()
        self.client = client or BinanceClient(config=self.config)

    @staticmethod
    def _to_utc_ms(value):
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")

        return int(timestamp.timestamp() * 1000)

    @staticmethod
    def _validate_ohlcv(df):
        required = ["open", "high", "low", "close", "volume"]
        missing = [column for column in required if column not in df.columns]
        if missing:
            raise ValueError(f"Missing OHLCV columns: {missing}")

        if not df.index.is_monotonic_increasing:
            df = df.sort_index()

        if df.index.has_duplicates:
            df = df[~df.index.duplicated(keep="last")]

        df[required] = df[required].apply(pd.to_numeric, errors="raise")

        return df

    @staticmethod
    def klines_to_df(raw, closed_only=True, now_ms=None):
        if not raw:
            raise ValueError("No kline data returned from Binance")

        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])

        if closed_only:
            now_ms = now_ms or int(pd.Timestamp.utcnow().timestamp() * 1000)
            df["close_time"] = pd.to_numeric(df["close_time"], errors="raise")
            before = len(df)
            df = df[df["close_time"] <= now_ms]

            removed = before - len(df)
            if removed:
                print(f"Removed {removed} still-forming Binance candle(s)")

            if df.empty:
                raise ValueError("No closed kline data returned from Binance")

        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        df["timestamp"] = (
            pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            .dt.tz_convert(None)
        )

        df.set_index("timestamp", inplace=True)

        return MarketDataDownloader._validate_ohlcv(df)

    def _history_filename(self, symbol, interval, start_date, end_date):
        return f"{symbol}_{interval}_{start_date}_to_{end_date}.csv"

    def _storage_folder(self, base_path, symbol, interval):
        return Path(base_path) / symbol / interval

    def _history_paths(self, symbol, interval, start_date, end_date, base_path):
        folder = self._storage_folder(base_path, symbol, interval)
        filename = self._history_filename(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date
        )

        download_config = self.config.require("downloads", "history")
        checkpoint_dir = folder / download_config["checkpoint_dir"]

        return {
            "folder": folder,
            "final": folder / filename,
            "partial": folder / f"{filename}{download_config['partial_suffix']}",
            "checkpoint": checkpoint_dir / f"{filename}{download_config['checkpoint_suffix']}"
        }

    def _read_checkpoint(self, checkpoint_path):
        if not checkpoint_path.exists():
            return None

        with checkpoint_path.open() as f:
            return json.load(f)

    def _write_checkpoint(self, checkpoint_path, payload):
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = checkpoint_path.with_suffix(f"{checkpoint_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        last_error = None
        for attempt in range(1, 9):
            try:
                temp_path.replace(checkpoint_path)
                return
            except PermissionError as exc:
                last_error = exc

                if attempt == 8:
                    break

                time.sleep(0.15 * attempt)

        raise PermissionError(
            "Unable to update checkpoint file after multiple attempts. "
            "This is usually caused by a transient Windows/OneDrive file lock: "
            f"{checkpoint_path}"
        ) from last_error

    def _partial_summary(self, partial_path):
        if not partial_path.exists() or partial_path.stat().st_size == 0:
            return {"rows": 0, "last_timestamp_ms": None}

        df = pd.read_csv(partial_path, parse_dates=["timestamp"])
        if df.empty:
            return {"rows": 0, "last_timestamp_ms": None}

        last_timestamp = pd.Timestamp(df["timestamp"].iloc[-1])
        if last_timestamp.tzinfo is None:
            last_timestamp = last_timestamp.tz_localize("UTC")
        else:
            last_timestamp = last_timestamp.tz_convert("UTC")

        return {
            "rows": len(df),
            "last_timestamp_ms": int(last_timestamp.timestamp() * 1000)
        }

    def _append_batch(self, partial_path, batch_df):
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not partial_path.exists() or partial_path.stat().st_size == 0
        batch_df.to_csv(partial_path, mode="a", header=write_header)

    def _load_partial(self, partial_path):
        df = pd.read_csv(partial_path, parse_dates=["timestamp"])
        df.set_index("timestamp", inplace=True)
        return self._validate_ohlcv(df)

    def _find_bootstrap_source(
        self,
        symbol,
        interval,
        start_date,
        end_date,
        base_path
    ):
        folder = self._storage_folder(base_path, symbol, interval)
        if not folder.exists():
            return None

        requested_start = pd.Timestamp(start_date)
        target_end_ts = pd.Timestamp(end_date)
        partial_suffix = self.config.require("downloads", "history")["partial_suffix"]
        prefix = f"{symbol}_{interval}_"

        best_candidate = None
        best_end_ts = None

        for candidate in folder.glob(f"{prefix}*.csv"):
            if candidate.name.endswith(partial_suffix):
                continue

            stem = candidate.stem
            if not stem.startswith(prefix) or "_to_" not in stem:
                continue

            try:
                remainder = stem[len(prefix):]
                candidate_start_text, candidate_end_text = remainder.split("_to_", 1)
                candidate_start_ts = _parse_storage_timestamp(candidate_start_text)
                candidate_end_ts = _parse_storage_timestamp(candidate_end_text)
            except Exception:
                continue

            if candidate_start_ts > requested_start:
                continue
            if candidate_end_ts >= target_end_ts:
                continue

            if best_end_ts is None or candidate_end_ts > best_end_ts:
                best_candidate = candidate
                best_end_ts = candidate_end_ts

        return best_candidate

    def _bootstrap_partial_from_completed_history(
        self,
        paths,
        symbol,
        interval,
        start_date,
        end_date,
        base_path
    ):
        if paths["partial"].exists() or paths["checkpoint"].exists():
            return None

        source_path = self._find_bootstrap_source(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            base_path=base_path
        )

        if source_path is None:
            return None

        paths["partial"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, paths["partial"])

        return source_path

    def fetch_full_history(
        self,
        symbol=None,
        interval=None,
        start_date=None,
        end_date=None,
        base_path=None
    ):
        """
        Download a historical Binance kline range with checkpointed progress.

        If a final CSV already exists, it is loaded directly. If a partial CSV
        or checkpoint exists, the next request starts after the last persisted
        candle. If the requested range extends an older completed CSV for the
        same symbol/interval/start date, that completed file is copied into the
        new partial path so the downloader can continue from its last candle
        instead of restarting from the first candle. On completion, the partial
        file is deduplicated, promoted to the final CSV, and the checkpoint is
        marked complete.
        """
        symbol = symbol or self.config.require("app", "default_symbol")
        interval = interval or self.config.require("binance", "default_interval")
        start_date = start_date or self.config.require("history", "start_date")
        end_date = end_date or self.config.require("history", "end_date")
        base_path = base_path or self.config.require("storage", "base_path")

        start_ts = self._to_utc_ms(start_date)
        end_ts = self._to_utc_ms(end_date)

        paths = self._history_paths(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            base_path=base_path
        )

        os.makedirs(paths["folder"], exist_ok=True)

        download_config = self.config.require("downloads", "history")
        resume_enabled = download_config["resume_enabled"]

        if resume_enabled and paths["final"].exists():
            print("\nCompleted historical file already exists.")
            print(f"Using cached file: {paths['final']}")
            return self.load_from_csv(paths["final"])

        bootstrap_source = None
        if resume_enabled:
            bootstrap_source = self._bootstrap_partial_from_completed_history(
                paths=paths,
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                base_path=base_path
            )

        checkpoint = self._read_checkpoint(paths["checkpoint"]) if resume_enabled else None
        partial_summary = (
            self._partial_summary(paths["partial"])
            if resume_enabled
            else {"rows": 0, "last_timestamp_ms": None}
        )
        partial_last_ts = partial_summary["last_timestamp_ms"]

        current_start = start_ts
        if partial_last_ts is not None:
            current_start = max(current_start, partial_last_ts + 1)
        elif checkpoint and checkpoint.get("next_start_ms"):
            current_start = max(current_start, checkpoint["next_start_ms"])

        total_batches = checkpoint.get("batches_downloaded", 0) if checkpoint else 0
        total_rows = max(
            checkpoint.get("rows_downloaded", 0) if checkpoint else 0,
            partial_summary["rows"]
        )

        start_clock = time.time()
        limit = self.config.require("binance", "historical_limit")
        throttle = self.config.require("binance", "throttle_seconds")
        status_every = download_config["status_every_batches"]
        save_every = download_config["save_every_batches"]
        total_range_ms = max(1, end_ts - start_ts)
        initial_progress_pct = min(
            100,
            max(0, ((current_start - start_ts) / total_range_ms) * 100)
        )
        verify_mode = self.client.describe_verify_mode()
        resume_detected = current_start > start_ts
        display = DownloadProgressDisplay(enabled=True)
        original_retry_callback = self.client.retry_callback
        self.client.retry_callback = display.update_retry if display.enabled else original_retry_callback

        if display.enabled:
            display.start(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                final_path=paths["final"],
                checkpoint_path=paths["checkpoint"],
                resumed=resume_detected,
                resume_point=_fmt(current_start) if resume_detected else None,
                total_rows=total_rows,
                initial_progress_pct=initial_progress_pct,
                verify_mode=verify_mode,
            )
            if bootstrap_source is not None:
                display.add_event(
                    "resume",
                    f"Bootstrapped from cached history {bootstrap_source.name}"
                )
        else:
            print(f"\nStarting download: {symbol} | {interval}")
            print(f"Range: {start_date} -> {end_date}\n")
            print(f"Final CSV: {paths['final']}")
            print(f"Checkpoint: {paths['checkpoint']}")
            print(f"TLS verify: {verify_mode}")

            if resume_detected:
                print("\nResume checkpoint detected")
                print(f"  Resuming from: {_fmt(current_start)}")
                print(f"  Existing rows: {total_rows}")
                if bootstrap_source is not None:
                    print(f"  Bootstrapped from: {bootstrap_source}")
                print("  Previous batches will not be downloaded again.\n")
            else:
                print("No usable checkpoint found. Starting from the beginning.\n")

        try:
            while current_start < end_ts:
                batch_start_time = time.time()
                request_batch_number = total_batches + 1

                if display.enabled:
                    display.update_request(
                        batch_number=request_batch_number,
                        request_from=_fmt(current_start),
                        limit=limit,
                    )
                else:
                    print(
                        f" Requesting batch {request_batch_number} | "
                        f"from {_fmt(current_start)} | limit={limit}"
                    )

                try:
                    raw = self.client.get_klines(
                        symbol=symbol,
                        interval=interval,
                        startTime=current_start,
                        endTime=end_ts,
                        limit=limit,
                        verbose=False
                    )
                except (Exception, KeyboardInterrupt) as exc:
                    self._write_checkpoint(paths["checkpoint"], {
                        "symbol": symbol,
                        "interval": interval,
                        "start_date": start_date,
                        "end_date": end_date,
                        "next_start_ms": current_start,
                        "next_start_time": _fmt(current_start),
                        "batches_downloaded": total_batches,
                        "rows_downloaded": total_rows,
                        "completed": False,
                        "last_error": str(exc),
                        "updated_at": datetime.utcnow().isoformat()
                    })

                    if display.enabled:
                        display.update_interrupted(
                            reason=exc,
                            checkpoint_path=paths["checkpoint"],
                        )
                    else:
                        reason = str(exc) or "Interrupted by user"
                        print("\nDownload interrupted.")
                        print(f"  Reason: {reason}")
                        print(f"  Checkpoint saved: {paths['checkpoint']}")
                        print("  Re-run the same command and it will continue from the saved point.")
                    raise

                if not raw:
                    if display.enabled:
                        display.add_event("stop", "No more data returned from Binance")
                    else:
                        print("WARNING: No more data returned. Stopping.")
                    break

                batch_df = self.klines_to_df(
                    raw,
                    closed_only=self.config.require("binance", "closed_klines_only")
                )
                self._append_batch(paths["partial"], batch_df)

                first_ts = self._to_utc_ms(batch_df.index[0])
                last_ts = self._to_utc_ms(batch_df.index[-1])
                current_start = last_ts + 1

                total_batches += 1
                total_rows += len(batch_df)

                batch_time = time.time() - batch_start_time
                total_time = time.time() - start_clock

                progress_pct = min(100, ((last_ts - start_ts) / total_range_ms) * 100)
                remaining_pct = max(0.01, 100 - progress_pct)
                session_progress_pct = max(0.0001, progress_pct - initial_progress_pct)
                eta_seconds = total_time * (remaining_pct / session_progress_pct)

                if total_batches % save_every == 0:
                    self._write_checkpoint(paths["checkpoint"], {
                        "symbol": symbol,
                        "interval": interval,
                        "start_date": start_date,
                        "end_date": end_date,
                        "next_start_ms": current_start,
                        "next_start_time": _fmt(current_start),
                        "last_timestamp_ms": last_ts,
                        "last_timestamp": _fmt(last_ts),
                        "batches_downloaded": total_batches,
                        "rows_downloaded": total_rows,
                        "partial_csv": str(paths["partial"]),
                        "final_csv": str(paths["final"]),
                        "completed": False,
                        "updated_at": datetime.utcnow().isoformat()
                    })

                if display.enabled:
                    display.update_batch_result(
                        batch_number=total_batches,
                        window_start=_fmt(first_ts),
                        window_end=_fmt(last_ts),
                        batch_rows=len(batch_df),
                        total_rows=total_rows,
                        progress_pct=progress_pct,
                        remaining_pct=remaining_pct,
                        elapsed_seconds=total_time,
                        eta_seconds=eta_seconds,
                        resume_point=_fmt(current_start),
                    )
                elif total_batches % status_every == 0:
                    print(f"Batch {total_batches} saved")
                    print(f"  Window: {_fmt(first_ts)} -> {_fmt(last_ts)}")
                    print(f"  Rows this batch: {len(batch_df)} | Total rows: {total_rows}")
                    print(f"  Progress: {progress_pct:.2f}% | Remaining: {remaining_pct:.2f}%")
                    print(
                        f"   Timing: batch {_fmt_duration(batch_time)} | "
                        f"elapsed {_fmt_duration(total_time)} | "
                        f"ETA {_fmt_duration(eta_seconds)}"
                    )
                    print(f"  Resume point: {_fmt(current_start)}")
                    print(f"  Checkpoint saved: {paths['checkpoint']}")

                if throttle > 0:
                    if display.enabled:
                        display.update_waiting(throttle)
                    else:
                        print(f"  Waiting {throttle:.2f}s before the next Binance request...\n")
                    time.sleep(throttle)

            if not paths["partial"].exists():
                raise FileNotFoundError(f"No partial download file found: {paths['partial']}")

            if display.enabled:
                display.update_finalizing()
            else:
                print("\nDownload loop complete. Finalizing CSV...\n")

            df = self._load_partial(paths["partial"])
            before_dedupe = len(df)
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df = df.loc[start_date:end_date]

            save_start = time.time()
            df.to_csv(paths["final"])
            save_time = time.time() - save_start
            duplicates_removed = before_dedupe - len(df)

            self._write_checkpoint(paths["checkpoint"], {
                "symbol": symbol,
                "interval": interval,
                "start_date": start_date,
                "end_date": end_date,
                "next_start_ms": end_ts,
                "next_start_time": _fmt(end_ts),
                "batches_downloaded": total_batches,
                "rows_downloaded": len(df),
                "partial_csv": str(paths["partial"]),
                "final_csv": str(paths["final"]),
                "completed": True,
                "updated_at": datetime.utcnow().isoformat()
            })

            if download_config["cleanup_partial_on_complete"] and paths["partial"].exists():
                paths["partial"].unlink()
                if display.enabled:
                    display.add_event("finalize", f"Removed partial file {paths['partial']}")
                else:
                    print(f"Removed completed partial file: {paths['partial']}")

            total_time = time.time() - start_clock

            if display.enabled:
                display.add_event("finalize", f"Duplicate rows removed: {duplicates_removed}")
                display.add_event("finalize", f"Final CSV write time: {save_time:.2f}s")
                display.update_completed(
                    total_rows=len(df),
                    total_time_seconds=total_time,
                    final_path=paths["final"],
                )
            else:
                print(f"Saved final CSV: {paths['final']}")
                print(f"Save time: {save_time:.2f}s")
                print(f"Duplicate rows removed: {duplicates_removed}")
                print(f"\nTOTAL TIME: {total_time/60:.2f} minutes")
                print(f"Total candles: {len(df)}")
                print(f"Final checkpoint: {paths['checkpoint']}")

            return df
        finally:
            self.client.retry_callback = original_retry_callback
            if display.enabled:
                display.stop()

    def fetch_recent(self, symbol=None, interval=None, limit=None):
        symbol = symbol or self.config.require("app", "default_symbol")
        interval = interval or self.config.require("binance", "default_interval")
        limit = limit or self.config.require("binance", "recent_limit")

        raw = self.client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            verbose=True
        )

        return self.klines_to_df(
            raw,
            closed_only=self.config.require("binance", "closed_klines_only")
        )

    def load_from_csv(self, filepath):
        filepath = Path(filepath)

        print(f"Loading: {filepath}")

        start = time.time()

        if not filepath.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        df = pd.read_csv(filepath, parse_dates=["timestamp"])
        df.set_index("timestamp", inplace=True)
        df = self._validate_ohlcv(df)

        print(f"Loaded in {time.time() - start:.2f} sec")

        return df


def _klines_to_df(raw):
    return MarketDataDownloader.klines_to_df(raw)


def fetch_recent(symbol=None, interval=None, limit=None, downloader=None):
    downloader = downloader or MarketDataDownloader()
    return downloader.fetch_recent(
        symbol=symbol,
        interval=interval,
        limit=limit
    )


def fetch_full_history(
    symbol=None,
    interval=None,
    start_date=None,
    end_date=None,
    base_path=None,
    downloader=None
):
    downloader = downloader or MarketDataDownloader()
    return downloader.fetch_full_history(
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        base_path=base_path
    )


def load_from_csv(filepath, downloader=None):
    downloader = downloader or MarketDataDownloader()
    return downloader.load_from_csv(filepath)
