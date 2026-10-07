"""Missing-data guard (architecture L5): suspend forecasting on stale or gappy history.

Two situations produce a ``data_gap``:
  * inside a cycle, the engine finds a gap longer than the imputation limit in the
    look-back window (``DataGapError``);
  * the watchdog sees no reading for more than ``data_gap_min`` (strictly greater: a
    patient whose last reading is exactly 60 min old is not yet stale).

A patient whose very first reading is too recent to fill one look-back window is
*warming up*: no forecast is possible yet, but that is not a data gap.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class StalePatient:
    patient_id: str
    last_reading: datetime
    minutes_since: float


def minutes_between(earlier: datetime, later: datetime) -> float:
    return (later - earlier) / timedelta(minutes=1)


def is_stale(last_reading: datetime, now: datetime, data_gap_min: int) -> bool:
    return minutes_between(last_reading, now) > data_gap_min


def stale_patients(
    last_readings: Mapping[str, datetime], now: datetime, data_gap_min: int
) -> list[StalePatient]:
    """Patients without a reading for more than ``data_gap_min``, most overdue first."""
    stale = [
        StalePatient(pid, t, minutes_between(t, now))
        for pid, t in last_readings.items()
        if is_stale(t, now, data_gap_min)
    ]
    return sorted(stale, key=lambda s: -s.minutes_since)


def is_warming_up(
    first_seen: datetime | None, t0: datetime, lookback_min: int, interval_min: int
) -> bool:
    """True until the patient's history reaches back to the first look-back slot."""
    if first_seen is None:
        return True
    window_start = t0 - timedelta(minutes=lookback_min - interval_min)
    # Half a step of tolerance: the engine snaps readings to the nearest grid slot (a reading
    # exactly half a step late rounds half-to-even, i.e. away from the first slot).
    return first_seen >= window_start + timedelta(minutes=interval_min / 2)
