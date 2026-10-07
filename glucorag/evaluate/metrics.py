"""Point-forecast accuracy metrics in mg/dL, aggregated per patient as in the paper.

The paper (Zhu et al., TBioCAS 2024, Eqs. 8-11; Tables I/II) reports RMSE, MAE, MAPE and
gRMSE as mean +- STD across subjects, so every metric is computed per patient first and
then summarized across patients.
"""

from collections.abc import Sequence
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pandas as pd

METRICS = ("RMSE", "MAE", "MAPE", "gRMSE")

ArrayLike = npt.ArrayLike
FloatArray = npt.NDArray[np.float64]

# Del Favero et al. 2012, Table I.
_ALPHA_L, _ALPHA_H = 1.5, 1.0
_BETA_L, _BETA_H = 30.0, 100.0
_GAMMA_L, _GAMMA_H = 10.0, 20.0
_T_L, _T_H = 85.0, 155.0


def _pair(y_true: ArrayLike, y_pred: ArrayLike) -> tuple[FloatArray, FloatArray]:
    t = np.asarray(y_true, dtype=np.float64).ravel()
    p = np.asarray(y_pred, dtype=np.float64).ravel()
    if t.shape != p.shape:
        raise ValueError(f"Shape mismatch: y_true {t.shape} vs y_pred {p.shape}")
    if t.size == 0:
        raise ValueError("Metrics need at least one sample")
    return t, p


def rmse(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    t, p = _pair(y_true, y_pred)
    return float(np.sqrt(np.mean((p - t) ** 2)))


def mae(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    t, p = _pair(y_true, y_pred)
    return float(np.mean(np.abs(p - t)))


def mape(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Mean absolute percentage error in percent (glucose is strictly positive)."""
    t, p = _pair(y_true, y_pred)
    if np.any(t <= 0):
        raise ValueError("MAPE requires strictly positive reference values")
    return float(100.0 * np.mean(np.abs(p - t) / t))


def _smooth_step(x: FloatArray, a: ArrayLike, eps: float) -> FloatArray:
    """Del Favero's C1 'sigmoid' sigma(x; a, eps): 0 for x <= a, 1 for x >= a + eps,
    quartic polynomial pieces in between (value 0.5 at a + eps/2)."""
    a = np.asarray(a, dtype=np.float64)
    xi = (2.0 / eps) * (x - a - eps / 2.0)
    rising = np.where(
        xi <= 0.0,
        -0.5 * xi**4 - xi**3 + xi + 0.5,
        0.5 * xi**4 - xi**3 + xi + 0.5,
    )
    return np.where(x <= a, 0.0, np.where(x >= a + eps, 1.0, rising))


def _smooth_step_down(x: FloatArray, a: ArrayLike, eps: float) -> FloatArray:
    """Mirror image sigma_hat(x; a, eps): 1 for x <= a - eps, 0 for x >= a."""
    a = np.asarray(a, dtype=np.float64)
    return _smooth_step(2.0 * a - x, a, eps)


def gmse_penalty(y_true: ArrayLike, y_pred: ArrayLike) -> FloatArray:
    """Clarke-grid-inspired penalty Pen(g, g_hat) of the glucose-specific MSE.

    Del Favero, Facchinetti & Cobelli, "A glucose-specific metric to assess predictors and
    identify models", IEEE Trans. Biomed. Eng. 59(5):1281-1290, 2012 (ref. [51] of the paper):

        Pen = 1 + alpha_L * sigma_hat(g; T_L, beta_L) * sigma(g_hat; g, gamma_L)
                + alpha_H * sigma(g; T_H, beta_H) * sigma_hat(g_hat; g, gamma_H)

    with alpha_L=1.5, alpha_H=1, T_L=85, T_H=155, beta_L=30, beta_H=100, gamma_L=10,
    gamma_H=20 mg/dL. Overestimation in hypoglycaemia (g <= 55, g_hat >= g + 10) is weighted
    up to 2.5x, underestimation in hyperglycaemia (g >= 255, g_hat <= g - 20) up to 2x;
    errors in euglycaemia (85 <= g <= 155) are not penalized. The smooth steps use the
    corrected xi = (2/eps)(x - a - eps/2) (the article's typesetting misplaces the 2/eps).
    """
    g, g_hat = _pair(y_true, y_pred)
    hypo = _smooth_step_down(g, _T_L, _BETA_L) * _smooth_step(g_hat, g, _GAMMA_L)
    hyper = _smooth_step(g, _T_H, _BETA_H) * _smooth_step_down(g_hat, g, _GAMMA_H)
    return 1.0 + _ALPHA_L * hypo + _ALPHA_H * hyper


def grmse(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Glucose-specific RMSE: sqrt(mean(Pen(g, g_hat) * (g_hat - g)^2)) (paper Eq. 11)."""
    t, p = _pair(y_true, y_pred)
    return float(np.sqrt(np.mean(gmse_penalty(t, p) * (p - t) ** 2)))


def point_metrics(y_true: ArrayLike, y_pred: ArrayLike) -> dict[str, float]:
    return {
        "RMSE": rmse(y_true, y_pred),
        "MAE": mae(y_true, y_pred),
        "MAPE": mape(y_true, y_pred),
        "gRMSE": grmse(y_true, y_pred),
    }


def horizon_index(horizon_min: int, interval_min: int) -> int:
    """Column of an (N, H) forecast holding the ``horizon_min``-ahead value."""
    if horizon_min <= 0 or horizon_min % interval_min:
        raise ValueError(f"{horizon_min} min is not a positive multiple of {interval_min} min")
    return horizon_min // interval_min - 1


def per_patient_metrics(
    y_true: ArrayLike, y_pred: ArrayLike, patient_id: ArrayLike
) -> pd.DataFrame:
    """One row per patient with every metric computed over that patient's samples."""
    t, p = _pair(y_true, y_pred)
    pid = np.asarray(patient_id, dtype=object).ravel()
    if pid.shape != t.shape:
        raise ValueError("patient_id must have one entry per sample")
    rows: list[dict[str, Any]] = []
    for patient in sorted(set(pid.tolist())):
        mask = pid == patient
        rows.append({"patient_id": patient, "n": int(mask.sum())} | point_metrics(t[mask], p[mask]))
    return pd.DataFrame(rows)


def metrics_at_horizons(
    y_true: ArrayLike,
    y_pred: ArrayLike,
    patient_id: ArrayLike,
    interval_min: int,
    horizons_min: Sequence[int],
) -> pd.DataFrame:
    """Per-patient metrics for each horizon from (N, H) forecasts/targets.

    Returns columns ``horizon_min, patient_id, n, RMSE, MAE, MAPE, gRMSE``.
    """
    t = np.asarray(y_true, dtype=np.float64)
    p = np.asarray(y_pred, dtype=np.float64)
    if t.ndim != 2 or t.shape != p.shape:
        raise ValueError(f"Expected matching (N, H) arrays, got {t.shape} and {p.shape}")
    frames = []
    for h in horizons_min:
        col = horizon_index(h, interval_min)
        if col >= t.shape[1]:
            raise ValueError(f"{h}-min horizon exceeds the forecast length {t.shape[1]}")
        frame = per_patient_metrics(t[:, col], p[:, col], patient_id)
        frame.insert(0, "horizon_min", h)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def summarize(per_patient: pd.DataFrame) -> pd.DataFrame:
    """Mean and sample STD (ddof=1) across patients for each horizon.

    Index: horizon_min; columns: MultiIndex (metric, {"mean", "std"}).
    """
    table = per_patient.groupby("horizon_min")[list(METRICS)].agg(["mean", "std"])
    return cast(pd.DataFrame, table)
