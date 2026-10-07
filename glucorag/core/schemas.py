from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class CGMRecord(BaseModel):
    patient_id: str
    timestamp: datetime
    glucose_mg_dl: float = Field(..., ge=0.0)


class PatientProfile(BaseModel):
    patient_id: str
    age: float
    gender: str
    bmi: float | None = None
    diabetes_type: Literal["T1D", "T2D"] | None = None
    context_vectors: list[float] | None = Field(
        default=None, description="Precomputed context from static demographics"
    )


class Prediction(BaseModel):
    patient_id: str
    t0: datetime
    horizons: list[int] = Field(..., description="Prediction horizons in minutes")
    quantiles: list[float] = Field(..., description="Quantile levels (e.g. 0.02, 0.5, 0.98)")
    values: list[list[float]] = Field(
        ..., description="Predicted values. Outer list: horizons, inner list: quantiles"
    )
    model_version: str


def _now_utc() -> datetime:
    return datetime.now(UTC)

class Alert(BaseModel):
    patient_id: str
    type: Literal["hypo", "hyper", "data_gap"]
    horizon_min: int | None = Field(
        default=None, description="Horizon in minutes for predictive alerts"
    )
    severity: str | None = None
    t_raised: datetime = Field(default_factory=_now_utc)
