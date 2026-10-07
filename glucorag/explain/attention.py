"""Temporal attention patterns of the interpretable multi-head self-attention layer.

The TFT's interpretable MHSA shares values across heads, so the head-averaged attention of
each decoder step over the encoder/decoder positions is directly interpretable as which past
(or already-forecast) time steps the forecast draws on.
"""

import numpy as np
import numpy.typing as npt


def position_offsets_min(lookback_steps: int, horizon_steps: int, interval_min: int) -> list[int]:
    """Minutes relative to the forecast origin for each of the L + H attention positions."""
    return [(i - lookback_steps + 1) * interval_min for i in range(lookback_steps + horizon_steps)]


def mean_attention(attention: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """(N, H, L + H) attention -> (H, L + H) mean over windows; rows still sum to 1."""
    a = np.asarray(attention, dtype=np.float64)
    if a.ndim != 3 or a.shape[0] == 0:
        raise ValueError(f"Expected non-empty (N, H, L + H) attention, got {a.shape}")
    return a.mean(axis=0)


def attention_by_position(
    attention: npt.ArrayLike, lookback_steps: int, interval_min: int
) -> dict[int, float]:
    """Mean attention per position (averaged over windows and decoder steps), keyed by
    minutes relative to the forecast origin."""
    per_step = mean_attention(attention)
    horizon_steps = per_step.shape[0]
    if per_step.shape[1] != lookback_steps + horizon_steps:
        raise ValueError("Attention width does not match lookback + horizon")
    offsets = position_offsets_min(lookback_steps, horizon_steps, interval_min)
    return dict(zip(offsets, per_step.mean(axis=0).tolist(), strict=True))
