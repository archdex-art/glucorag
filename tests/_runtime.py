"""Shared helpers for runtime-service tests: tiny artifacts and a controllable clock."""

from datetime import datetime, timedelta
from pathlib import Path

import torch

from glucorag.core.registry import ModelMeta, save_artifact
from glucorag.core.schemas import PatientProfile

QUANTILES = [0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98]
MU, SIGMA = 150.0, 50.0
T0 = datetime(2021, 7, 30, 8, 0)
STEP = timedelta(minutes=15)


def tiny_artifact(
    root: Path, levels_mg: list[float] | None = None, version: str = "tiny-1"
) -> Path:
    """Save a 15-min ShanghaiDM-shaped artifact.

    With ``levels_mg`` the quantile head is constant, so every forecast equals ``levels_mg``
    at all horizons (lets tests force exact risk outcomes); otherwise weights are random.
    """
    torch.manual_seed(0)
    meta = ModelMeta(
        version=version,
        dataset="shanghai",
        interval_min=15,
        lookback_min=120,
        horizon_min=60,
        quantiles=QUANTILES,
        d_model=8,
        num_heads=2,
        dropout=0.0,
        static_encoder={
            "features": ["gender", "age", "bmi", "diabetes_type"],
            "stats": {"age": {"mu": 50.0, "sigma": 15.0}, "bmi": {"mu": 24.0, "sigma": 4.0}},
        },
        glucose_norm={"mu": MU, "sigma": SIGMA},
        data_hash="test",
    )
    model = meta.build_model().eval()
    if levels_mg is not None:
        with torch.no_grad():
            model.quantile_head.weight.zero_()
            model.quantile_head.bias.copy_(torch.tensor([(v - MU) / SIGMA for v in levels_mg]))
    return save_artifact(root, model, meta)


def profile(patient_id: str = "p1") -> PatientProfile:
    return PatientProfile(patient_id=patient_id, age=40, gender="F", bmi=22.5, diabetes_type="T1D")


class ManualClock:
    checks_future = True

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now

    def observe(self, t: datetime) -> None:
        return None
