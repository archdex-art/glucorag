"""Live forecast accuracy (drift monitoring): the realised error of stored forecasts.

Each stored forecast is matched, at the 30- and 60-min horizons, to the reading nearest its
target time ``t0 + h`` when one lies within half the model's sampling interval (inclusive;
on a tie the earlier reading wins). Forecasts without such a reading (a sensor gap, or a
target still in the future) are left out, never counted as errors.

The point error is the median forecast (q0.50) minus the reading. Band coverage is the share
of readings inside the q0.25-q0.75 (50 %) and q0.10-q0.90 (80 %) forecast bands, inclusive.
Windows are rolling on the target time: the last 7 and 30 days up to ``now``. Daily series
group by the target's server-local date.
"""

import statistics
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pydantic import BaseModel

from glucorag.core.schemas import Alert, Prediction
from glucorag.evaluate.metrics import mae, rmse

HORIZONS = (30, 60)
DAILY_DAYS = 30
# Fewer matched forecasts than this make a summary too noisy to show a person or to warn on.
MIN_COUNT = 20
_BANDS = {"coverage_50": (0.25, 0.75), "coverage_80": (0.10, 0.90)}
_ALERT_TYPES = ("hypo", "hyper", "data_gap")


@dataclass(frozen=True)
class MatchedForecast:
    patient_id: str
    model_version: str
    t0: datetime
    horizon_min: int
    target: datetime  # t0 + horizon
    reading_at: datetime  # the matched reading's time
    actual_mg_dl: float
    median_mg_dl: float
    in_50: bool | None  # None when the forecast lacks the band's quantiles
    in_80: bool | None


def _index(quantiles: Sequence[float], q: float) -> int | None:
    for i, level in enumerate(quantiles):
        if abs(level - q) < 1e-9:
            return i
    return None


def _nearest(times: Sequence[datetime], target: datetime, tolerance: timedelta) -> int | None:
    """Index of the time nearest ``target`` within ``tolerance``; ties go to the earlier."""
    i = bisect_left(times, target)
    best: int | None = None
    for j in (i - 1, i):
        if 0 <= j < len(times) and abs(times[j] - target) <= tolerance and (
            best is None or abs(times[j] - target) < abs(times[best] - target)
        ):
            best = j
    return best


def match_forecasts(
    predictions: Iterable[Prediction],
    readings: Sequence[tuple[datetime, float]],
    tolerance: timedelta,
    horizons: Sequence[int] = HORIZONS,
) -> list[MatchedForecast]:
    """Pair one patient's forecasts with that patient's ``readings`` (ascending by time)."""
    times = [t for t, _ in readings]
    out: list[MatchedForecast] = []
    for p in predictions:
        mid = _index(p.quantiles, 0.5)
        if mid is None:
            continue
        bands = {
            name: (_index(p.quantiles, lo), _index(p.quantiles, hi))
            for name, (lo, hi) in _BANDS.items()
        }
        for h in horizons:
            if h not in p.horizons:
                continue
            target = p.t0 + timedelta(minutes=h)
            found = _nearest(times, target, tolerance)
            if found is None:
                continue
            at, actual = readings[found]
            row = p.values[p.horizons.index(h)]
            inside: dict[str, bool | None] = {
                name: None if lo is None or hi is None else row[lo] <= actual <= row[hi]
                for name, (lo, hi) in bands.items()
            }
            out.append(MatchedForecast(
                patient_id=p.patient_id, model_version=p.model_version, t0=p.t0,
                horizon_min=h, target=target, reading_at=at, actual_mg_dl=actual,
                median_mg_dl=row[mid], in_50=inside["coverage_50"], in_80=inside["coverage_80"],
            ))
    return out


class HorizonAccuracy(BaseModel):
    horizon_min: int
    count: int
    rmse_mg_dl: float | None = None
    mae_mg_dl: float | None = None
    median_abs_error_mg_dl: float | None = None
    coverage_50: float | None = None  # fraction 0..1
    coverage_80: float | None = None


class AccuracyWindows(BaseModel):
    last_7_days: list[HorizonAccuracy]
    last_30_days: list[HorizonAccuracy]


class VersionAccuracy(AccuracyWindows):
    model_version: str


class PatientAccuracy(AccuracyWindows):
    patient_id: str


class DailyAccuracy(BaseModel):
    date: date
    horizons: list[HorizonAccuracy]
    alerts: dict[str, int]


class AccuracyReport(BaseModel):
    as_of: datetime | None
    cohort: AccuracyWindows
    versions: list[VersionAccuracy]
    patients: list[PatientAccuracy]
    daily: list[DailyAccuracy]


def _share(flags: list[bool | None]) -> float | None:
    known = [f for f in flags if f is not None]
    return round(sum(known) / len(known), 4) if known else None


def summarise(matches: Sequence[MatchedForecast], horizon_min: int) -> HorizonAccuracy:
    sel = [m for m in matches if m.horizon_min == horizon_min]
    if not sel:
        return HorizonAccuracy(horizon_min=horizon_min, count=0)
    actual = [m.actual_mg_dl for m in sel]
    forecast = [m.median_mg_dl for m in sel]
    return HorizonAccuracy(
        horizon_min=horizon_min,
        count=len(sel),
        rmse_mg_dl=round(rmse(actual, forecast), 2),
        mae_mg_dl=round(mae(actual, forecast), 2),
        median_abs_error_mg_dl=round(
            statistics.median(abs(f - a) for a, f in zip(actual, forecast, strict=True)), 2
        ),
        coverage_50=_share([m.in_50 for m in sel]),
        coverage_80=_share([m.in_80 for m in sel]),
    )


def windows(matches: Sequence[MatchedForecast], now: datetime) -> AccuracyWindows:
    def last(days: int) -> list[HorizonAccuracy]:
        start = now - timedelta(days=days)
        inside = [m for m in matches if start < m.target <= now]
        return [summarise(inside, h) for h in HORIZONS]

    return AccuracyWindows(last_7_days=last(7), last_30_days=last(30))


def first_daily_date(now: datetime) -> date:
    return now.date() - timedelta(days=DAILY_DAYS - 1)


def build_report(
    matches: Sequence[MatchedForecast], alerts: Iterable[Alert], now: datetime | None
) -> AccuracyReport:
    """Windows for the cohort, each model version and each patient, plus a daily series of
    the last ``DAILY_DAYS`` dates (oldest first, every date present) with alert counts.
    ``now=None`` (no time yet: a replay clock before its first reading) gives an empty report.
    """
    if now is None:
        empty = windows([], datetime(2000, 1, 1))
        return AccuracyReport(as_of=None, cohort=empty, versions=[], patients=[], daily=[])
    versions = sorted({m.model_version for m in matches})
    patients = sorted({m.patient_id for m in matches})
    days = [first_daily_date(now) + timedelta(days=i) for i in range(DAILY_DAYS)]
    errors: dict[date, list[MatchedForecast]] = {d: [] for d in days}
    for m in matches:
        if m.target <= now and m.target.date() in errors:
            errors[m.target.date()].append(m)
    counts: dict[date, dict[str, int]] = {d: dict.fromkeys(_ALERT_TYPES, 0) for d in days}
    for a in alerts:
        day = counts.get(a.t_raised.date())
        if day is not None and a.t_raised <= now:
            day[a.type] = day.get(a.type, 0) + 1
    return AccuracyReport(
        as_of=now,
        cohort=windows(matches, now),
        versions=[
            VersionAccuracy(
                model_version=v,
                **windows([m for m in matches if m.model_version == v], now).model_dump(),
            )
            for v in versions
        ],
        patients=[
            PatientAccuracy(
                patient_id=p,
                **windows([m for m in matches if m.patient_id == p], now).model_dump(),
            )
            for p in patients
        ],
        daily=[
            DailyAccuracy(date=d, horizons=[summarise(errors[d], h) for h in HORIZONS],
                          alerts=counts[d])
            for d in days
        ],
    )
