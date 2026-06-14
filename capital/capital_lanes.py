from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class CapitalLaneName(str, Enum):
    CORE_FLOW = "core_flow"
    H1_TACTICAL = "h1_tactical"
    HTF_12H_STRUCTURAL = "htf_12h_structural"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True)
class CapitalLane:
    name: CapitalLaneName
    priority: int
    budget_fraction: float
    max_exposure_fraction: float
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["name"] = self.name.value
        return payload


DEFAULT_CAPITAL_LANES = [
    CapitalLane(
        name=CapitalLaneName.CORE_FLOW,
        priority=2,
        budget_fraction=0.25,
        max_exposure_fraction=0.25,
        notes="Future tactical flow lane scaffold only.",
    ),
    CapitalLane(
        name=CapitalLaneName.H1_TACTICAL,
        priority=3,
        budget_fraction=0.15,
        max_exposure_fraction=0.20,
        notes="Future H1 tactical lane scaffold only.",
    ),
    CapitalLane(
        name=CapitalLaneName.HTF_12H_STRUCTURAL,
        priority=4,
        budget_fraction=0.50,
        max_exposure_fraction=0.60,
        notes="Future structural lane scaffold only.",
    ),
    CapitalLane(
        name=CapitalLaneName.EXPERIMENTAL,
        priority=1,
        budget_fraction=0.10,
        max_exposure_fraction=0.10,
        notes="Future observation-only lane scaffold.",
    ),
]


def default_lane_payload() -> list[dict[str, object]]:
    return [lane.to_dict() for lane in DEFAULT_CAPITAL_LANES]
