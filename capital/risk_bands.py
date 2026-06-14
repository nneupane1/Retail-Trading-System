from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class RiskBand(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class RiskBandSnapshot:
    equity: float
    peak_equity: float
    drawdown_fraction: float
    band: RiskBand

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["band"] = self.band.value
        return payload


def classify_risk_band(*, equity: float, peak_equity: float, in_recovery: bool = False) -> RiskBandSnapshot:
    peak = max(float(peak_equity), 0.0)
    current = float(equity)
    drawdown_fraction = 0.0 if peak <= 0.0 else max(0.0, (peak - current) / peak)
    if in_recovery:
        band = RiskBand.RECOVERY
    elif drawdown_fraction >= 0.15:
        band = RiskBand.RED
    elif drawdown_fraction >= 0.05:
        band = RiskBand.YELLOW
    else:
        band = RiskBand.GREEN
    return RiskBandSnapshot(
        equity=current,
        peak_equity=peak,
        drawdown_fraction=float(drawdown_fraction),
        band=band,
    )
