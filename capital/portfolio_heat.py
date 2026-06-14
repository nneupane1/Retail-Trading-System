from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PortfolioHeatSnapshot:
    total_open_risk: float
    risk_by_symbol: dict[str, float]
    risk_by_side: dict[str, float]
    risk_by_strategy: dict[str, float]
    risk_by_lane: dict[str, float]
    correlated_long_exposure: float
    correlated_short_exposure: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def aggregate_portfolio_heat(positions: list[dict[str, object]] | None = None) -> PortfolioHeatSnapshot:
    risk_by_symbol: dict[str, float] = defaultdict(float)
    risk_by_side: dict[str, float] = defaultdict(float)
    risk_by_strategy: dict[str, float] = defaultdict(float)
    risk_by_lane: dict[str, float] = defaultdict(float)
    total_open_risk = 0.0
    correlated_long = 0.0
    correlated_short = 0.0
    for position in list(positions or []):
        risk = float(position.get("risk_fraction", 0.0) or 0.0)
        symbol = str(position.get("symbol", "unknown"))
        side = str(position.get("side", "unknown"))
        strategy = str(position.get("strategy_type", "unknown"))
        lane = str(position.get("capital_lane", "unassigned"))
        total_open_risk += risk
        risk_by_symbol[symbol] += risk
        risk_by_side[side] += risk
        risk_by_strategy[strategy] += risk
        risk_by_lane[lane] += risk
        if side == "long":
            correlated_long += risk
        elif side == "short":
            correlated_short += risk
    return PortfolioHeatSnapshot(
        total_open_risk=float(total_open_risk),
        risk_by_symbol=dict(risk_by_symbol),
        risk_by_side=dict(risk_by_side),
        risk_by_strategy=dict(risk_by_strategy),
        risk_by_lane=dict(risk_by_lane),
        correlated_long_exposure=float(correlated_long),
        correlated_short_exposure=float(correlated_short),
    )
