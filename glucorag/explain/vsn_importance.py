"""Variable importance from the encoder's variable-selection network (paper Fig. 4).

The VSN emits softmax weights over input variables at every encoder step; importance is the
mean weight per variable over all steps and windows, so the scores sum to 1.
"""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

ENCODER_VARIABLES = ("glucose", "time_of_day")


def variable_importance(
    weights: npt.ArrayLike, names: Sequence[str] = ENCODER_VARIABLES
) -> dict[str, float]:
    """``weights``: (N, L, V) selection weights -> {variable: mean weight}, sorted desc."""
    w = np.asarray(weights, dtype=np.float64)
    if w.ndim != 3 or w.shape[-1] != len(names):
        raise ValueError(f"Expected (N, L, {len(names)}) weights, got {w.shape}")
    if w.shape[0] == 0:
        raise ValueError("No windows to aggregate")
    means = w.reshape(-1, w.shape[-1]).mean(axis=0)
    order = np.argsort(-means)
    return {str(names[i]): float(means[i]) for i in order}


def importance_by_step(weights: npt.ArrayLike, interval_min: int) -> dict[int, list[float]]:
    """Mean weights per encoder step keyed by minutes relative to the forecast origin
    (0 = last observation, negative = older)."""
    w = np.asarray(weights, dtype=np.float64)
    lookback = w.shape[1]
    means = w.mean(axis=0)
    return {(i - lookback + 1) * interval_min: means[i].tolist() for i in range(lookback)}
