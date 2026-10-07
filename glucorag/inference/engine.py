"""Single-patient forecasting from raw CGM history using a registered artifact.

Shared by the API service and the in-silico trial so both run exactly the training-time
preprocessing (regular grid, causal imputation of short gaps, z-normalization, time of day).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from glucorag.core.registry import ModelMeta, load_artifact
from glucorag.core.schemas import Prediction
from glucorag.models.tft.tft import EPSTFT, StaticContext
from glucorag.preprocess.impute import SENSOR_MAX_MG_DL, SENSOR_MIN_MG_DL, causal_linear_extrapolate

# Extra history slots before the look-back window so extrapolation has a trend to continue.
_PAD_SLOTS = 2


class DataGapError(Exception):
    """History has a gap longer than the imputation limit inside the look-back window."""


@dataclass(frozen=True)
class Reading:
    timestamp: datetime
    glucose_mg_dl: float


class ForecastEngine:
    def __init__(
        self, model: EPSTFT, meta: ModelMeta, max_gap_min: int, device: str = "cpu"
    ) -> None:
        self.model = model.to(device).eval()
        self.meta = meta
        self.device = torch.device(device)
        self.max_gap_steps = max_gap_min // meta.interval_min
        self.glucose_norm = meta.glucose_normalizer()
        self.static_encoder = meta.encoder()
        self.step = timedelta(minutes=meta.interval_min)
        self.horizons_min = [
            meta.interval_min * (i + 1) for i in range(meta.horizon_steps)
        ]

    @classmethod
    def from_artifact(
        cls, path: str | Path, max_gap_min: int, device: str = "cpu"
    ) -> "ForecastEngine":
        model, meta = load_artifact(path, device)
        return cls(model, meta, max_gap_min, device)

    @torch.no_grad()
    def context_for(self, profile: Mapping[str, Any]) -> StaticContext:
        """Precompute covariate-encoder context once per patient (architecture D4)."""
        static = torch.from_numpy(self.static_encoder.encode_one(profile)).unsqueeze(0)
        return self.model.encode_static(static.to(self.device))

    def build_inputs(self, history: Sequence[Reading]) -> tuple[np.ndarray, np.ndarray, datetime]:
        """Return ``(x_enc (L,2), x_dec (H,1), t0)``; raises DataGapError on long gaps."""
        if not history:
            raise DataGapError("No CGM readings")
        readings = sorted(history, key=lambda r: r.timestamp)
        t0 = readings[-1].timestamp
        n_slots = self.meta.lookback_steps + _PAD_SLOTS + self.max_gap_steps
        grid = np.full(n_slots, np.nan)
        best = np.full(n_slots, np.inf)  # |offset| (s) of each slot's current holder
        half_step = self.step.total_seconds() / 2
        step_s = self.step.total_seconds()
        # Each slot keeps the reading nearest its grid time within half a step; ascending
        # order with `<=` lets the later reading win an exact tie. On a native grid this
        # is the plain one-reading-per-slot assignment.
        for r in readings:
            age_s = (t0 - r.timestamp).total_seconds()
            lo = math.floor(age_s / step_s)
            for k in (lo, lo + 1):
                offset = abs(age_s - k * step_s)
                if 0 <= k < n_slots and offset <= half_step and offset <= best[n_slots - 1 - k]:
                    best[n_slots - 1 - k] = offset
                    grid[n_slots - 1 - k] = r.glucose_mg_dl
        filled = causal_linear_extrapolate(
            pd.Series(grid), max_gap_steps=self.max_gap_steps
        ).to_numpy()[-self.meta.lookback_steps :]
        if np.isnan(filled).any():
            raise DataGapError(
                f"Gap > {self.max_gap_steps * self.meta.interval_min} min in look-back window"
            )
        past_times = [t0 - self.step * k for k in range(self.meta.lookback_steps - 1, -1, -1)]
        future_times = [t0 + self.step * (k + 1) for k in range(self.meta.horizon_steps)]
        x_enc = np.stack(
            [self.glucose_norm.transform(filled), [_time_norm(t) for t in past_times]], axis=-1
        ).astype(np.float32)
        x_dec = np.array([[_time_norm(t)] for t in future_times], dtype=np.float32)
        return x_enc, x_dec, t0

    @torch.no_grad()
    def predict(
        self, patient_id: str, ctx: StaticContext, history: Sequence[Reading]
    ) -> Prediction:
        x_enc, x_dec, t0 = self.build_inputs(history)
        preds, _ = self.model.forward_with_context(
            ctx,
            torch.from_numpy(x_enc).unsqueeze(0).to(self.device),
            torch.from_numpy(x_dec).unsqueeze(0).to(self.device),
        )
        mg = self.glucose_norm.inverse_transform(preds[0].cpu().numpy().astype(np.float64))
        # Quantile heads are trained independently and can cross; enforce monotonicity.
        mg = np.clip(np.sort(mg, axis=-1), SENSOR_MIN_MG_DL, SENSOR_MAX_MG_DL)
        return Prediction(
            patient_id=patient_id,
            t0=t0,
            horizons=self.horizons_min,
            quantiles=self.meta.quantiles,
            values=mg.tolist(),
            model_version=self.meta.version,
        )


def _time_norm(t: datetime) -> float:
    return (t.hour * 60 + t.minute + t.second / 60.0) / 1440.0
