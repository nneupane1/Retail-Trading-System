from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RegimeCapitalMultiplier:
    trend_regime: str
    volatility_regime: str
    correlation_regime: str
    risk_on_risk_off_regime: str
    regime_multiplier: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_regime_multiplier(
    *,
    trend_regime: str,
    volatility_regime: str,
    correlation_regime: str,
    risk_on_risk_off_regime: str,
) -> RegimeCapitalMultiplier:
    multiplier = 1.0
    if str(trend_regime).lower() == "aligned":
        multiplier += 0.05
    if str(volatility_regime).lower() == "compressed":
        multiplier -= 0.05
    if str(correlation_regime).lower() == "high":
        multiplier -= 0.05
    if str(risk_on_risk_off_regime).lower() == "risk_on":
        multiplier += 0.02
    return RegimeCapitalMultiplier(
        trend_regime=str(trend_regime),
        volatility_regime=str(volatility_regime),
        correlation_regime=str(correlation_regime),
        risk_on_risk_off_regime=str(risk_on_risk_off_regime),
        regime_multiplier=float(multiplier),
    )
