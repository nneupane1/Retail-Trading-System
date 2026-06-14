from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CapitalRecyclingSignal:
    stale_position_candidate: bool
    dead_capital_score: float
    recycling_candidate: bool
    replacement_candidate: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_recycling_signal(*, hours_held: float, unrealized_r: float, replacement_score: float) -> CapitalRecyclingSignal:
    dead_capital_score = max(0.0, float(hours_held) / 24.0) + max(0.0, -float(unrealized_r))
    stale_position_candidate = float(hours_held) >= 24.0 and float(unrealized_r) <= 0.25
    recycling_candidate = stale_position_candidate and float(replacement_score) >= 0.8
    return CapitalRecyclingSignal(
        stale_position_candidate=stale_position_candidate,
        dead_capital_score=float(dead_capital_score),
        recycling_candidate=recycling_candidate,
        replacement_candidate="higher_priority_candidate" if recycling_candidate else None,
    )
