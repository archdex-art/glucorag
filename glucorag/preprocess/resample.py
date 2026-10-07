"""Snap irregular CGM readings onto a regular per-series time grid."""

import numpy as np
import pandas as pd


def regularize(df: pd.DataFrame, interval_min: int, series_col: str = "series_id") -> pd.DataFrame:
    """Reindex every series onto a regular grid anchored at its first reading.

    Readings are snapped to the nearest grid slot (duplicates keep the latest reading).
    Missing slots get NaN glucose and ``observed=False``. Input columns required:
    ``patient_id``, ``series_col``, ``timestamp``, ``glucose_mg_dl``.
    """
    step = pd.Timedelta(minutes=interval_min)
    out: list[pd.DataFrame] = []
    for series_id, group in df.groupby(series_col, sort=False):
        group = group.dropna(subset=["timestamp"]).sort_values("timestamp")
        if group.empty:
            continue
        origin = pd.Timestamp(group["timestamp"].iloc[0])
        slot = np.rint((group["timestamp"] - origin) / step).astype(np.int64)
        values = pd.Series(group["glucose_mg_dl"].to_numpy(dtype=float), index=slot.to_numpy())
        values = values[~values.index.duplicated(keep="last")]
        n_slots = int(slot.max()) + 1
        grid = values.reindex(np.arange(n_slots))
        out.append(
            pd.DataFrame(
                {
                    "patient_id": group["patient_id"].iloc[0],
                    series_col: series_id,
                    "timestamp": pd.DatetimeIndex([origin]).repeat(n_slots)
                    + pd.to_timedelta(np.arange(n_slots) * interval_min, unit="min"),
                    "glucose_mg_dl": grid.to_numpy(),
                    "observed": grid.notna().to_numpy(),
                }
            )
        )
    if not out:
        return pd.DataFrame(
            columns=["patient_id", series_col, "timestamp", "glucose_mg_dl", "observed"]
        )
    return pd.concat(out, ignore_index=True)
