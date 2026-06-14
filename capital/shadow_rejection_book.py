from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShadowRejectionRecord:
    timestamp: str
    symbol: str
    strategy_type: str
    side: str
    score: float | None
    score_bucket: str | None
    rejection_reason: str
    hypothetical_entry: float | None = None
    hypothetical_stop: float | None = None
    hypothetical_exit: float | None = None
    hypothetical_r: float | None = None
    hypothetical_pnl: float | None = None
    would_have_won: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_shadow_rejection_report(records: list[ShadowRejectionRecord] | None = None) -> dict[str, object]:
    rows = [record.to_dict() for record in list(records or [])]
    return {
        "schema_version": 1,
        "record_count": len(rows),
        "records": rows,
        "warning": "scaffold_only_schema_no_allocator_behavior_change",
    }


def write_shadow_rejection_report(path: Path, records: list[ShadowRejectionRecord] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_shadow_rejection_report(records), indent=2), encoding="utf-8")
    return path
