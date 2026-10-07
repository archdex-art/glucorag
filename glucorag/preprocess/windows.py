"""Sliding-window construction for encoder/decoder inputs."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

FloatArray = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Windows:
    """Window arrays; row ``i`` of every array describes the same sample."""

    x_enc: FloatArray  # (N, lookback, 2): [glucose_z, time_norm]
    x_dec: FloatArray  # (N, horizon, 1): [time_norm]
    target_z: FloatArray  # (N, horizon)
    target_mg_dl: FloatArray  # (N, horizon)
    series_id: npt.NDArray[Any]  # (N,) object
    patient_id: npt.NDArray[Any]  # (N,) object
    t0: npt.NDArray[Any]  # (N,) datetime64: timestamp of the last encoder step

    def __len__(self) -> int:
        return int(self.x_enc.shape[0])


def create_sliding_windows(
    df: pd.DataFrame,
    lookback_steps: int,
    horizon_steps: int,
    stride: int = 1,
    require_observed_target: bool = False,
    series_col: str = "series_id",
) -> Windows:
    """Build windows per series from a regular, imputed frame.

    Required columns: ``patient_id``, ``series_col``, ``timestamp``, ``glucose_mg_dl``,
    ``glucose_z``, ``time_norm``; ``observed`` when ``require_observed_target``.
    Windows containing any NaN are dropped; with ``require_observed_target`` windows whose
    targets include imputed values are dropped too (used for val/test scoring).
    """
    total = lookback_steps + horizon_steps
    parts: dict[str, list[npt.NDArray[Any]]] = {
        k: [] for k in ("enc", "dec", "tz", "tm", "sid", "pid", "t0")
    }
    for series_id, group in df.groupby(series_col, sort=False):
        group = group.sort_values("timestamp")
        if len(group) < total:
            continue
        z = group["glucose_z"].to_numpy(dtype=np.float32)
        mg = group["glucose_mg_dl"].to_numpy(dtype=np.float32)
        tn = group["time_norm"].to_numpy(dtype=np.float32)
        ts = group["timestamp"].to_numpy()

        zw = sliding_window_view(z, total)[::stride]
        mw = sliding_window_view(mg, total)[::stride]
        tw = sliding_window_view(tn, total)[::stride]
        keep = ~np.isnan(zw).any(axis=1)
        if require_observed_target:
            ow = sliding_window_view(group["observed"].to_numpy(dtype=bool), total)[::stride]
            keep &= ow[:, lookback_steps:].all(axis=1)
        if not keep.any():
            continue
        zw, mw, tw = zw[keep], mw[keep], tw[keep]
        starts = np.arange(0, len(z) - total + 1, stride)[keep]

        parts["enc"].append(np.stack([zw[:, :lookback_steps], tw[:, :lookback_steps]], axis=-1))
        parts["dec"].append(tw[:, lookback_steps:, None])
        parts["tz"].append(zw[:, lookback_steps:])
        parts["tm"].append(mw[:, lookback_steps:])
        parts["sid"].append(np.full(len(starts), series_id, dtype=object))
        parts["pid"].append(np.full(len(starts), group["patient_id"].iloc[0], dtype=object))
        parts["t0"].append(ts[starts + lookback_steps - 1])

    if not parts["enc"]:
        return Windows(
            x_enc=np.zeros((0, lookback_steps, 2), np.float32),
            x_dec=np.zeros((0, horizon_steps, 1), np.float32),
            target_z=np.zeros((0, horizon_steps), np.float32),
            target_mg_dl=np.zeros((0, horizon_steps), np.float32),
            series_id=np.zeros(0, dtype=object),
            patient_id=np.zeros(0, dtype=object),
            t0=np.zeros(0, dtype="datetime64[ns]"),
        )
    return Windows(
        x_enc=np.concatenate(parts["enc"]).astype(np.float32),
        x_dec=np.concatenate(parts["dec"]).astype(np.float32),
        target_z=np.concatenate(parts["tz"]).astype(np.float32),
        target_mg_dl=np.concatenate(parts["tm"]).astype(np.float32),
        series_id=np.concatenate(parts["sid"]),
        patient_id=np.concatenate(parts["pid"]),
        t0=np.concatenate(parts["t0"]),
    )
