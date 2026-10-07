"""Causal gap filling for regularly sampled CGM series."""

import numpy as np
import numpy.typing as npt
import pandas as pd

SENSOR_MIN_MG_DL = 40.0
SENSOR_MAX_MG_DL = 400.0


def causal_linear_extrapolate(
    series: pd.Series,
    min_val: float = SENSOR_MIN_MG_DL,
    max_val: float = SENSOR_MAX_MG_DL,
    max_gap_steps: int | None = None,
) -> pd.Series:
    """Fill NaNs by extrapolating the line through the two most recent observed points.

    Only past observations are used (no future leakage). Slope is per step, so observed
    points separated by an earlier gap still give the correct per-step trend. With one prior
    point the fill is flat; with none the value stays NaN. Gaps longer than
    ``max_gap_steps`` are left entirely NaN. All values (observed and filled) are clipped
    to the sensor range.
    """
    values: npt.NDArray[np.float64] = series.to_numpy(dtype=float, copy=True)
    observed = ~np.isnan(values)
    filled = values.copy()

    last_i = -1
    prev_i = -1
    i = 0
    n = len(values)
    while i < n:
        if observed[i]:
            prev_i, last_i = last_i, i
            i += 1
            continue
        gap_end = i
        while gap_end < n and not observed[gap_end]:
            gap_end += 1
        gap_len = gap_end - i
        if last_i >= 0 and (max_gap_steps is None or gap_len <= max_gap_steps):
            steps = np.arange(i, gap_end) - last_i
            if prev_i >= 0:
                slope = (values[last_i] - values[prev_i]) / (last_i - prev_i)
            else:
                slope = 0.0
            filled[i:gap_end] = values[last_i] + slope * steps
        i = gap_end

    filled = np.where(np.isnan(filled), np.nan, np.clip(filled, min_val, max_val))
    return pd.Series(filled, index=series.index, name=series.name)
