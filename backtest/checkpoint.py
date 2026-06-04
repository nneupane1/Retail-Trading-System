"""Checkpoint helpers for resumable historical backtests."""

import json
import time
from pathlib import Path


class BacktestCheckpointStore:
    """
    Persists resumable backtest state to a JSON checkpoint file.
    """

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def exists(self):
        return self.path.exists()

    def load(self):
        if not self.exists():
            return None

        with self.path.open() as file_handle:
            return json.load(file_handle)

    def save(self, payload):
        normalized = self._normalize(payload)
        temp_path = self.path.parent / f"{self.path.name}.tmp"
        for attempt in range(8):
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                with temp_path.open("w") as file_handle:
                    json.dump(normalized, file_handle, indent=2)
                temp_path.replace(self.path)
                return
            except (PermissionError, FileNotFoundError):
                if attempt == 7:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def clear(self):
        if self.exists():
            self.path.unlink()

    def _normalize(self, value):
        if isinstance(value, dict):
            return {
                str(key): self._normalize(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple)):
            return [self._normalize(item) for item in value]

        if hasattr(value, "item") and callable(value.item):
            return value.item()

        if hasattr(value, "isoformat") and callable(value.isoformat):
            return value.isoformat()

        return value
