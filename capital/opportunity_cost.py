from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class OpportunityCostInput:
    current_position_score: float
    candidate_score: float
    capital_locked_duration_hours: float
    unrealized_r: float
    competing_signal_priority: float


@dataclass(frozen=True)
class OpportunityCostEvaluation:
    current_position_score: float
    candidate_score: float
    capital_locked_duration_hours: float
    unrealized_r: float
    competing_signal_priority: float
    opportunity_cost_score: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def evaluate_opportunity_cost(payload: OpportunityCostInput) -> OpportunityCostEvaluation:
    score = (
        (float(payload.candidate_score) - float(payload.current_position_score))
        + (float(payload.capital_locked_duration_hours) / 24.0) * 0.10
        - float(payload.unrealized_r) * 0.15
        + float(payload.competing_signal_priority) * 0.20
    )
    return OpportunityCostEvaluation(
        current_position_score=float(payload.current_position_score),
        candidate_score=float(payload.candidate_score),
        capital_locked_duration_hours=float(payload.capital_locked_duration_hours),
        unrealized_r=float(payload.unrealized_r),
        competing_signal_priority=float(payload.competing_signal_priority),
        opportunity_cost_score=float(score),
    )
