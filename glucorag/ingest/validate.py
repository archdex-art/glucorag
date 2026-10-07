"""Validation and timestamp alignment of incoming CGM readings (architecture step 2).

Timestamps are handled as naive local wall-clock time, the frame the model was trained in
(time-of-day is a model input). Timezone-aware inputs are converted to the server's local
time and made naive.

Rules, in order:
  * empty patient id, non-finite or non-positive glucose -> rejected;
  * values outside the sensor range 40–400 mg/dL -> clipped to the range and flagged;
  * timestamps later than ``now + max_future_skew`` -> rejected (skipped when ``now`` is None,
    e.g. when replaying a dataset whose readings define the clock);
  * a timestamp equal to the patient's latest reading -> duplicate; earlier -> out of order.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from glucorag.preprocess.impute import SENSOR_MAX_MG_DL, SENSOR_MIN_MG_DL

RejectReason = Literal[
    "invalid_patient", "non_finite", "non_positive", "future", "duplicate", "out_of_order"
]
RangeFlag = Literal["ok", "clipped_low", "clipped_high"]


class ReadingRejectedError(ValueError):
    def __init__(self, reason: RejectReason, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason: RejectReason = reason
        self.detail = detail


@dataclass(frozen=True)
class ValidatedReading:
    patient_id: str
    timestamp: datetime
    glucose_mg_dl: float  # clipped to the sensor range
    raw_mg_dl: float
    flag: RangeFlag


def to_local_naive(t: datetime) -> datetime:
    return t.astimezone().replace(tzinfo=None) if t.tzinfo is not None else t


def validate_reading(
    patient_id: str,
    timestamp: datetime,
    glucose_mg_dl: float,
    *,
    last_timestamp: datetime | None,
    now: datetime | None,
    max_future_skew: timedelta,
) -> ValidatedReading:
    """Return the cleaned reading or raise :class:`ReadingRejectedError`."""
    if not patient_id.strip():
        raise ReadingRejectedError("invalid_patient", "empty patient_id")
    value = float(glucose_mg_dl)
    if not math.isfinite(value):
        raise ReadingRejectedError("non_finite", f"glucose={glucose_mg_dl!r}")
    if value <= 0:
        raise ReadingRejectedError("non_positive", f"glucose={value}")
    t = to_local_naive(timestamp)
    if now is not None and t > now + max_future_skew:
        raise ReadingRejectedError("future", f"{t.isoformat()} is after {now.isoformat()}")
    if last_timestamp is not None:
        if t == last_timestamp:
            raise ReadingRejectedError("duplicate", f"reading at {t.isoformat()} already ingested")
        if t < last_timestamp:
            raise ReadingRejectedError(
                "out_of_order", f"{t.isoformat()} precedes latest {last_timestamp.isoformat()}"
            )
    flag: RangeFlag = "ok"
    clipped = value
    if value < SENSOR_MIN_MG_DL:
        flag, clipped = "clipped_low", SENSOR_MIN_MG_DL
    elif value > SENSOR_MAX_MG_DL:
        flag, clipped = "clipped_high", SENSOR_MAX_MG_DL
    return ValidatedReading(patient_id, t, clipped, value, flag)
