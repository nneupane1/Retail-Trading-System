from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class WinnerForensicsRecord:
    trade_id: str
    symbol: str
    strategy_type: str
    side: str
    entry_time: str
    exit_time: str
    score_bucket: str | None
    pnl: float
    r_multiple: float | None
    holding_time_hours: float | None
    max_favorable_excursion: float | None = None
    max_adverse_excursion: float | None = None
    exit_reason: str | None = None
    possible_add_on_points: int = 0
    early_exit_flag: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_top_winner_forensics(records: list[WinnerForensicsRecord] | None = None) -> dict[str, object]:
    rows = [record.to_dict() for record in list(records or [])]
    return {
        "schema_version": 1,
        "winner_count": len(rows),
        "records": rows,
        "warning": "scaffold_only_forensics_no_exit_behavior_change",
    }


def write_top_winner_forensics(path: Path, records: list[WinnerForensicsRecord] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_top_winner_forensics(records), indent=2), encoding="utf-8")
    return path
