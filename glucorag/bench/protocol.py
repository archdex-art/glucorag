"""Benchmark protocol shared by every forecaster: per-window contexts and interval metrics.

Foundation models see what EPS-TFT sees at the same forecast origin: the prepared
(regularised, causally imputed, clipped) glucose series in mg/dL, ending at the window's last
encoder step ``t0``. With a context longer than EPS-TFT's look-back the history may reach back
into the train/validation part of the same series (the split is a chronological tail per
series), but never past ``t0``. Gaps longer than the imputation limit stay NaN in the prepared
frame; a context stops at the most recent such gap so every model receives a contiguous,
NaN-free series. Targets are the test windows' targets, which are real CGM observations.

Only numpy/pandas here, so the windowing is unit-tested without the ``bench`` extra.
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from glucorag.evaluate.metrics import horizon_index
from glucorag.preprocess.windows import Windows

FloatArray = npt.NDArray[np.float32]

# Quantiles every probabilistic forecaster in the benchmark produces natively.
LOWER, MEDIAN, UPPER = 0.1, 0.5, 0.9


@dataclass(frozen=True)
class Forecast:
    """(N, H) arrays in mg/dL; ``lower``/``upper`` are the 0.1/0.9 quantiles when available."""

    median: FloatArray
    lower: FloatArray | None = None
    upper: FloatArray | None = None


@dataclass(frozen=True)
class SeriesHistory:
    timestamps: npt.NDArray[Any]
    glucose_mg_dl: FloatArray


def series_histories(frames: Sequence[pd.DataFrame]) -> dict[Hashable, SeriesHistory]:
    """Re-join the prepared split frames into one chronological glucose series per series_id."""
    frame = pd.concat(frames, ignore_index=True).sort_values(["series_id", "timestamp"])
    out: dict[Hashable, SeriesHistory] = {}
    for series_id, group in frame.groupby("series_id", sort=False):
        timestamps = group["timestamp"].to_numpy()
        if len(timestamps) > 1 and not (timestamps[1:] > timestamps[:-1]).all():
            raise ValueError(f"series {series_id} has duplicate timestamps across splits")
        out[series_id] = SeriesHistory(timestamps, group["glucose_mg_dl"].to_numpy(np.float32))
    return out


def window_contexts(
    histories: dict[Hashable, SeriesHistory], windows: Windows, steps: int
) -> list[FloatArray]:
    """Up to ``steps`` glucose values ending at each window's ``t0`` (oldest first).

    The context is cut after the most recent NaN, so it can be shorter than ``steps``.
    """
    if steps < 1:
        raise ValueError("context needs at least one step")
    out: list[FloatArray] = []
    for series_id, t0 in zip(windows.series_id, windows.t0, strict=True):
        history = histories[series_id]
        end = int(np.searchsorted(history.timestamps, t0))
        if end >= len(history.timestamps) or history.timestamps[end] != t0:
            raise ValueError(f"forecast origin {t0} not in the history of series {series_id}")
        context = history.glucose_mg_dl[max(0, end - steps + 1) : end + 1]
        gaps = np.flatnonzero(np.isnan(context))
        if gaps.size:
            context = context[gaps[-1] + 1 :]
        if context.size == 0:
            raise ValueError(f"no glucose at the forecast origin {t0} of series {series_id}")
        out.append(context)
    return out


def interval_coverage(
    target: npt.ArrayLike,
    lower: npt.ArrayLike,
    upper: npt.ArrayLike,
    patient_id: npt.ArrayLike,
    interval_min: int,
    horizons_min: Sequence[int],
) -> pd.DataFrame:
    """Per-patient coverage (%) and mean width (mg/dL) of ``[lower, upper]`` per horizon.

    Columns ``horizon_min, patient_id, n, coverage, width, below, above`` where ``below`` /
    ``above`` are the % of targets under the lower / over the upper bound.
    """
    t = np.asarray(target, dtype=np.float64)
    lo = np.asarray(lower, dtype=np.float64)
    hi = np.asarray(upper, dtype=np.float64)
    if t.ndim != 2 or t.shape != lo.shape or t.shape != hi.shape:
        raise ValueError(f"Expected matching (N, H) arrays, got {t.shape}, {lo.shape}, {hi.shape}")
    pid = np.asarray(patient_id, dtype=object)
    rows: list[dict[str, Any]] = []
    for h in horizons_min:
        col = horizon_index(h, interval_min)
        y, a, b = t[:, col], lo[:, col], hi[:, col]
        for patient in sorted(set(pid.tolist())):
            m = pid == patient
            rows.append({
                "horizon_min": h,
                "patient_id": patient,
                "n": int(m.sum()),
                "coverage": float(100.0 * np.mean((y[m] >= a[m]) & (y[m] <= b[m]))),
                "width": float(np.mean(b[m] - a[m])),
                "below": float(100.0 * np.mean(y[m] < a[m])),
                "above": float(100.0 * np.mean(y[m] > b[m])),
            })
    return pd.DataFrame(rows)


def coverage_summary(per_patient: pd.DataFrame) -> dict[str, dict[str, dict[str, float]]]:
    """``{horizon: {metric: {"mean", "std"}}}`` across patients (sample STD), like the report."""
    cols = ["coverage", "width", "below", "above"]
    table = per_patient.groupby("horizon_min")[cols].agg(["mean", "std"])
    return {
        str(h): {
            c: {"mean": float(table.loc[h, (c, "mean")]), "std": float(table.loc[h, (c, "std")])}
            for c in cols
        }
        for h in table.index
    }
