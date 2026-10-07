"""Hypo-/hyperglycaemia detectors over a quantile forecast (architecture L5).

The decision uses one quantile per direction ("uncertainty gate"): by default the lower
band q0.25 for hypo and the upper band q0.75 for hyper, so an alert fires when a
plausible part of the predictive distribution crosses a threshold, not only the median.

Inclusivity: hypo when the selected quantile is ``<= hypo_mg_dl`` (70) and hyper when it is
``>= hyper_mg_dl`` (180); a forecast of exactly 70 or 180 mg/dL raises.

Severity combines urgency (earliest crossing horizon) and depth (level-2 thresholds of the
International Consensus on Time in Range: < 54 and > 250 mg/dL, applied inclusively here):
  * ``high``   – a level-2 value within ``urgent_horizon_min``;
  * ``medium`` – first crossing within ``urgent_horizon_min``, or a level-2 value later;
  * ``low``    – only level-1 crossings beyond ``urgent_horizon_min``.
"""

from dataclasses import dataclass
from typing import Literal

from glucorag.core.config import settings
from glucorag.core.schemas import Prediction

RiskType = Literal["hypo", "hyper"]
Severity = Literal["low", "medium", "high"]
SEVERITY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class AlertPolicy:
    """Per-patient quantile choice; ``None`` fields fall back to the service defaults."""

    hypo_quantile: float | None = None
    hyper_quantile: float | None = None


@dataclass(frozen=True)
class RiskConfig:
    hypo_mg_dl: float = settings.alert_thresholds.hypo_mg_dl
    hyper_mg_dl: float = settings.alert_thresholds.hyper_mg_dl
    hypo_quantile: float = 0.25
    hyper_quantile: float = 0.75
    hypo_level2_mg_dl: float = 54.0
    hyper_level2_mg_dl: float = 250.0
    urgent_horizon_min: int = 30

    def quantiles_for(self, policy: AlertPolicy | None) -> tuple[float, float]:
        """Effective ``(hypo_q, hyper_q)``: patient policy first, then service defaults."""
        hypo_q = self.hypo_quantile
        hyper_q = self.hyper_quantile
        if policy is not None:
            if policy.hypo_quantile is not None:
                hypo_q = policy.hypo_quantile
            if policy.hyper_quantile is not None:
                hyper_q = policy.hyper_quantile
        return hypo_q, hyper_q


@dataclass(frozen=True)
class RiskFlag:
    type: RiskType
    horizon_min: int  # earliest horizon at which the selected quantile crosses
    quantile: float
    value_mg_dl: float  # selected quantile at the earliest crossing
    extreme_mg_dl: float  # most extreme selected-quantile value over all horizons
    margin_mg_dl: float  # how far the extreme lies beyond the threshold (>= 0)
    severity: Severity


def quantile_index(quantiles: list[float], q: float) -> int:
    """Index of ``q`` in the model's quantile set; unknown levels are a config error."""
    for i, level in enumerate(quantiles):
        if abs(level - q) < 1e-9:
            return i
    raise ValueError(f"Alert quantile {q} is not produced by the model (has {quantiles})")


def _severity(
    first_h: int, level2_horizons: list[int], urgent_horizon_min: int
) -> Severity:
    if any(h <= urgent_horizon_min for h in level2_horizons):
        return "high"
    if first_h <= urgent_horizon_min or level2_horizons:
        return "medium"
    return "low"


def assess(
    prediction: Prediction, config: RiskConfig, policy: AlertPolicy | None = None
) -> list[RiskFlag]:
    """Hypo and/or hyper flags for one forecast (both can fire on a wide band)."""
    hypo_q, hyper_q = config.quantiles_for(policy)
    flags: list[RiskFlag] = []

    hi = quantile_index(prediction.quantiles, hypo_q)
    lows = [row[hi] for row in prediction.values]
    crossing = [h for h, v in zip(prediction.horizons, lows, strict=True) if v <= config.hypo_mg_dl]
    if crossing:
        level2 = [
            h for h, v in zip(prediction.horizons, lows, strict=True)
            if v <= config.hypo_level2_mg_dl
        ]
        first = prediction.horizons.index(crossing[0])
        extreme = min(lows)
        flags.append(
            RiskFlag(
                "hypo", crossing[0], hypo_q, lows[first], extreme,
                config.hypo_mg_dl - extreme,
                _severity(crossing[0], level2, config.urgent_horizon_min),
            )
        )

    ki = quantile_index(prediction.quantiles, hyper_q)
    highs = [row[ki] for row in prediction.values]
    crossing = [
        h for h, v in zip(prediction.horizons, highs, strict=True) if v >= config.hyper_mg_dl
    ]
    if crossing:
        level2 = [
            h for h, v in zip(prediction.horizons, highs, strict=True)
            if v >= config.hyper_level2_mg_dl
        ]
        first = prediction.horizons.index(crossing[0])
        extreme = max(highs)
        flags.append(
            RiskFlag(
                "hyper", crossing[0], hyper_q, highs[first], extreme,
                extreme - config.hyper_mg_dl,
                _severity(crossing[0], level2, config.urgent_horizon_min),
            )
        )
    return flags
