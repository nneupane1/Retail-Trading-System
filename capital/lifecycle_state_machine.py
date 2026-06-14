from __future__ import annotations

from enum import Enum


class LifecycleState(str, Enum):
    CANDIDATE = "candidate"
    PROBE = "probe"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    ADD_ON_ELIGIBLE = "add_on_eligible"
    RUNNER = "runner"
    MOONSHOT = "moonshot"
    DE_RISK = "de_risk"
    EXIT = "exit"


ALLOWED_TRANSITIONS = {
    LifecycleState.CANDIDATE: {LifecycleState.PROBE, LifecycleState.EXIT},
    LifecycleState.PROBE: {LifecycleState.VALIDATED, LifecycleState.DE_RISK, LifecycleState.EXIT},
    LifecycleState.VALIDATED: {LifecycleState.PROMOTED, LifecycleState.DE_RISK, LifecycleState.EXIT},
    LifecycleState.PROMOTED: {LifecycleState.ADD_ON_ELIGIBLE, LifecycleState.RUNNER, LifecycleState.DE_RISK, LifecycleState.EXIT},
    LifecycleState.ADD_ON_ELIGIBLE: {LifecycleState.RUNNER, LifecycleState.DE_RISK, LifecycleState.EXIT},
    LifecycleState.RUNNER: {LifecycleState.MOONSHOT, LifecycleState.DE_RISK, LifecycleState.EXIT},
    LifecycleState.MOONSHOT: {LifecycleState.DE_RISK, LifecycleState.EXIT},
    LifecycleState.DE_RISK: {LifecycleState.EXIT},
    LifecycleState.EXIT: set(),
}


def can_transition(current: LifecycleState, target: LifecycleState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
