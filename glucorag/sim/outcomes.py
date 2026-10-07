"""Glycemic outcome metrics (international consensus ranges, Battelino et al. 2019).

Time below range is BG < 70 mg/dL, time in range is 70-180 mg/dL inclusive and time above
range is BG > 180 mg/dL, matching the paper's Appendix B definitions ("BG<70 mg/dL",
"70-180 mg/dL"). The three percentages partition the trace and sum to 100.
"""

from dataclasses import asdict, dataclass

import numpy as np
import numpy.typing as npt

RANGE_LOW_MG_DL = 70.0
RANGE_HIGH_MG_DL = 180.0


@dataclass(frozen=True)
class GlycemicOutcomes:
    tbr_pct: float
    tir_pct: float
    tar_pct: float
    mean_mg_dl: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def glycemic_outcomes(bg_mg_dl: npt.ArrayLike) -> GlycemicOutcomes:
    """Outcomes of a regularly sampled BG trace (every sample carries equal time weight)."""
    bg = np.asarray(bg_mg_dl, dtype=float)
    if bg.size == 0:
        raise ValueError("Empty BG trace")
    if np.isnan(bg).any():
        raise ValueError("BG trace contains NaN")
    below = bg < RANGE_LOW_MG_DL
    above = bg > RANGE_HIGH_MG_DL
    n = bg.size
    return GlycemicOutcomes(
        tbr_pct=100.0 * below.sum() / n,
        tir_pct=100.0 * (~below & ~above).sum() / n,
        tar_pct=100.0 * above.sum() / n,
        mean_mg_dl=float(bg.mean()),
    )
