"""Runtime orchestration of one prediction cycle per CGM sample (architecture section 5).

    reading -> validate -> persist + window buffer -> profile & cached StaticContext
            -> ForecastEngine.predict -> risk engine -> de-dup -> persist prediction/alerts

A look-back gap beyond the imputation limit skips inference and raises ``data_gap``; a
patient whose history does not yet span one look-back window is ``warming_up`` (no forecast,
no alert). The watchdog raises ``data_gap`` for patients without readings for longer than
``data_gap_min``. All state changes for one patient happen under a single lock, so the
service is safe to call from the API's worker threads.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Protocol

from prometheus_client import CollectorRegistry, Counter, Histogram
from pydantic import BaseModel

from glucorag.core.config import settings
from glucorag.core.logging import log_event
from glucorag.core.schemas import Alert, PatientProfile, Prediction
from glucorag.core.storage import Storage, StoredAlert, StoredPrediction, StoredProfile
from glucorag.features.window_buffer import WindowBuffer
from glucorag.inference.engine import DataGapError, ForecastEngine, Reading
from glucorag.ingest.validate import (
    RangeFlag,
    ReadingRejectedError,
    ValidatedReading,
    validate_reading,
)
from glucorag.models.tft.tft import StaticContext
from glucorag.notify.alerts import AlertDeduplicator
from glucorag.risk.detectors import (
    SEVERITY_RANK,
    AlertPolicy,
    RiskConfig,
    RiskFlag,
    assess,
    quantile_index,
)
from glucorag.risk.gap_guard import is_stale, is_warming_up, minutes_between

log = logging.getLogger("glucorag.service")

CycleStatus = Literal["predicted", "data_gap", "warming_up", "rejected"]
CohortStatus = Literal["at_risk", "data_gap", "warming_up", "ok", "no_data"]
_LATENCY_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)


class UnknownPatientError(KeyError):
    """Readings or queries for a patient without a registered profile."""


class Clock(Protocol):
    """Service time source. ``checks_future`` enables the future-timestamp rejection."""

    checks_future: bool

    def now(self) -> datetime: ...

    def observe(self, t: datetime) -> None: ...


class WallClock:
    """Server local wall-clock time (naive), for live CGM streams."""

    checks_future = True

    def now(self) -> datetime:
        return datetime.now()

    def observe(self, t: datetime) -> None:
        return None


class DataClock:
    """Time = latest accepted reading across the cohort, for replaying recorded datasets.

    Readings define time here, so there is no "future" to reject; staleness is measured
    against the most recent reading of any patient.
    """

    checks_future = False

    def __init__(self) -> None:
        self._now = datetime.min

    def now(self) -> datetime:
        return self._now

    def observe(self, t: datetime) -> None:
        self._now = max(self._now, t)


@dataclass(frozen=True)
class ServiceConfig:
    risk: RiskConfig = field(default_factory=RiskConfig)
    data_gap_min: int = settings.alert_thresholds.data_gap_min
    alert_cooldown: timedelta = timedelta(minutes=30)
    max_future_skew: timedelta = timedelta(minutes=2)


class ServiceMetrics:
    """Prometheus metrics on a private registry (one per service instance)."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.readings = Counter(
            "glucorag_readings_ingested", "Accepted CGM readings", registry=self.registry
        )
        self.clipped = Counter(
            "glucorag_readings_clipped", "Readings clipped to 40-400 mg/dL",
            registry=self.registry,
        )
        self.rejected = Counter(
            "glucorag_readings_rejected", "Rejected CGM readings", ["reason"],
            registry=self.registry,
        )
        self.predictions = Counter(
            "glucorag_predictions", "Forecasts produced", registry=self.registry
        )
        self.alerts = Counter(
            "glucorag_alerts", "Alerts raised (after de-duplication)", ["type"],
            registry=self.registry,
        )
        self.data_gaps = Counter(
            "glucorag_data_gaps",
            "Data-gap detections: skipped cycles (cycle) and newly stale patients (watchdog)",
            ["source"], registry=self.registry,
        )
        self.cycle_latency = Histogram(
            "glucorag_prediction_latency_seconds",
            "Full prediction cycle (validate -> persist) for readings that produced a forecast",
            buckets=_LATENCY_BUCKETS, registry=self.registry,
        )
        self.inference_latency = Histogram(
            "glucorag_inference_latency_seconds", "ForecastEngine.predict only",
            buckets=_LATENCY_BUCKETS, registry=self.registry,
        )


class CycleResult(BaseModel):
    patient_id: str
    timestamp: datetime
    status: CycleStatus
    range_flag: RangeFlag | None = None
    reason: str | None = None
    detail: str | None = None
    prediction: Prediction | None = None
    risk: list[RiskFlag] = []
    alerts: list[StoredAlert] = []
    inference_ms: float | None = None
    cycle_ms: float


class BackfillResult(BaseModel):
    """Per-row outcomes of :meth:`GlucoseService.backfill` and how many rows were added."""

    outcomes: dict[str, int]
    added: int


class ForecastBand(BaseModel):
    """Latest fresh forecast reduced to what the risk engine reads: the alert band."""

    t0: datetime
    horizons: list[int]
    low_quantile: float  # the patient's hypo alert quantile
    high_quantile: float  # the patient's hyper alert quantile
    low: list[float]
    median: list[float]
    high: list[float]


class PatientRisk(BaseModel):
    patient_id: str
    diabetes_type: str | None
    status: CohortStatus
    severity: str | None
    last_reading: datetime | None
    minutes_since_last: float | None
    stale: bool
    latest_t0: datetime | None
    model_version: str | None
    risk: list[RiskFlag]
    active_alerts: list[str]
    last_glucose_mg_dl: float | None = None
    # mg/dL per minute across the latest sampling interval; None without such a pair.
    trend_mg_dl_per_min: float | None = None
    # Only while the latest forecast was made from the last reading (status at_risk / ok).
    forecast: ForecastBand | None = None


@dataclass
class _Patient:
    profile: PatientProfile
    policy: AlertPolicy
    ctx: StaticContext


class GlucoseService:
    def __init__(
        self,
        engine: ForecastEngine,
        storage: Storage,
        config: ServiceConfig | None = None,
        clock: Clock | None = None,
        metrics: ServiceMetrics | None = None,
    ) -> None:
        self.engine = engine
        self.storage = storage
        self.config = config or ServiceConfig()
        self.clock: Clock = clock or WallClock()
        self.metrics = metrics or ServiceMetrics()
        self.dedup = AlertDeduplicator(self.config.alert_cooldown)
        meta = engine.meta
        self.buffer = WindowBuffer.for_engine(
            meta.lookback_min, meta.interval_min, self.config.data_gap_min
        )
        self._lock = threading.RLock()
        self._patients: dict[str, _Patient] = {}
        self._check_policy(AlertPolicy())
        self._rehydrate()

    @property
    def model_version(self) -> str:
        return self.engine.meta.version

    def _check_policy(self, policy: AlertPolicy) -> None:
        for q in self.config.risk.quantiles_for(policy):
            quantile_index(self.engine.meta.quantiles, q)

    def _rehydrate(self) -> None:
        """Restore profiles, contexts and window buffers from storage after a restart."""
        bounds = self.storage.reading_bounds()
        for stored in self.storage.profiles():
            pid = stored.profile.patient_id
            self._cache(stored)
            if pid in bounds:
                first, last = bounds[pid]
                recent = self.storage.readings(pid, since=last - self.buffer.span)
                self.buffer.load(
                    pid, (Reading(r.timestamp, r.glucose_mg_dl) for r in recent), first
                )
                self.clock.observe(last)

    def _cache(self, stored: StoredProfile) -> _Patient:
        policy = AlertPolicy(stored.hypo_quantile, stored.hyper_quantile)
        self._check_policy(policy)
        ctx = self.engine.context_for(stored.profile.model_dump())
        patient = _Patient(stored.profile, policy, ctx)
        self._patients[stored.profile.patient_id] = patient
        return patient

    def _patient(self, patient_id: str) -> _Patient:
        try:
            return self._patients[patient_id]
        except KeyError:
            raise UnknownPatientError(patient_id) from None

    # profiles ---------------------------------------------------------------------------
    def register_profile(
        self, profile: PatientProfile, policy: AlertPolicy | None = None
    ) -> StoredProfile:
        """Create/update a profile; the static context is (re)computed once here.

        Raises ValueError for profiles the model cannot encode or quantiles it lacks.
        """
        policy = policy or AlertPolicy()
        self._check_policy(policy)
        ctx = self.engine.context_for(profile.model_dump())
        with self._lock:
            self.storage.upsert_profile(profile, policy.hypo_quantile, policy.hyper_quantile)
            self._patients[profile.patient_id] = _Patient(profile, policy, ctx)
        log_event(log, "profile_registered", patient_id=profile.patient_id)
        stored = self.storage.profile(profile.patient_id)
        assert stored is not None
        return stored

    def effective_quantiles(self, patient_id: str) -> tuple[float, float]:
        return self.config.risk.quantiles_for(self._patient(patient_id).policy)

    # prediction cycle -------------------------------------------------------------------
    def ingest(self, patient_id: str, timestamp: datetime, glucose_mg_dl: float) -> CycleResult:
        """Run one full cycle for a new reading. Raises UnknownPatientError."""
        start = time.perf_counter()
        with self._lock:
            patient = self._patient(patient_id)
            try:
                reading = validate_reading(
                    patient_id,
                    timestamp,
                    glucose_mg_dl,
                    last_timestamp=self.buffer.last_timestamp(patient_id),
                    now=self.clock.now() if self.clock.checks_future else None,
                    max_future_skew=self.config.max_future_skew,
                )
            except ReadingRejectedError as e:
                self.metrics.rejected.labels(e.reason).inc()
                log_event(log, "reading_rejected", logging.WARNING, patient_id=patient_id,
                          reason=e.reason, detail=e.detail)
                return CycleResult(
                    patient_id=patient_id, timestamp=timestamp, status="rejected",
                    reason=e.reason, detail=e.detail, cycle_ms=_ms_since(start),
                )
            t = reading.timestamp
            self.storage.insert_reading(
                patient_id, t, reading.glucose_mg_dl, reading.raw_mg_dl, reading.flag
            )
            self.buffer.append(patient_id, Reading(t, reading.glucose_mg_dl))
            self.clock.observe(t)
            self.metrics.readings.inc()
            if reading.flag != "ok":
                self.metrics.clipped.inc()
            result = self._forecast(patient_id, patient, t, start)
            result.range_flag = reading.flag
        if result.status == "predicted":
            self.metrics.cycle_latency.observe(result.cycle_ms / 1000)
        log_event(
            log, "cycle", patient_id=patient_id, t=t.isoformat(), status=result.status,
            alerts=[a.type for a in result.alerts], inference_ms=result.inference_ms,
            cycle_ms=round(result.cycle_ms, 3),
        )
        return result

    def backfill(
        self, patient_id: str, readings: list[tuple[datetime, float]]
    ) -> "BackfillResult":
        """Merge a batch of readings in any order (file import, sample), then replay cycles.

        Rows whose exact timestamp is already stored are skipped; every other row is checked
        exactly as a live reading except for ordering. If the batch reaches back before the
        latest stored reading, forecasts and alerts from the earliest new reading on are
        deleted and replayed, so the stored timeline is what a live stream of the merged
        readings would have produced. Raises UnknownPatientError.
        """
        outcomes: dict[str, int] = {}

        def count(key: str) -> None:
            outcomes[key] = outcomes.get(key, 0) + 1

        with self._lock:
            patient = self._patient(patient_id)
            existing = {r.timestamp for r in self.storage.readings(patient_id)}
            now = self.clock.now() if self.clock.checks_future else None
            fresh: dict[datetime, ValidatedReading] = {}
            for ts, value in readings:
                try:
                    v = validate_reading(
                        patient_id, ts, value, last_timestamp=None, now=now,
                        max_future_skew=self.config.max_future_skew,
                    )
                except ReadingRejectedError as e:
                    self.metrics.rejected.labels(e.reason).inc()
                    count(f"rejected_{e.reason}")
                    continue
                if v.timestamp in existing or v.timestamp in fresh:
                    count("already_present")
                    continue
                fresh[v.timestamp] = v
            if not fresh:
                return BackfillResult(outcomes=outcomes, added=0)

            first_new = min(fresh)
            with self.storage.transaction():
                for t in sorted(fresh):
                    v = fresh[t]
                    self.storage.insert_reading(
                        patient_id, t, v.glucose_mg_dl, v.raw_mg_dl, v.flag
                    )
                    self.metrics.readings.inc()
                    if v.flag != "ok":
                        self.metrics.clipped.inc()
                self.storage.delete_derived_since(patient_id, first_new)

            timeline = [
                Reading(r.timestamp, r.glucose_mg_dl) for r in self.storage.readings(patient_id)
            ]
            first_seen = timeline[0].timestamp
            self.dedup.forget(patient_id)
            self._prime_dedup(patient_id, first_new)
            for i, reading in enumerate(timeline):
                if reading.timestamp < first_new:
                    continue
                window_start = reading.timestamp - self.buffer.span
                self.buffer.load(
                    patient_id,
                    (r for r in timeline[: i + 1] if r.timestamp >= window_start),
                    first_seen,
                )
                self.clock.observe(reading.timestamp)
                result = self._forecast(patient_id, patient, reading.timestamp, time.perf_counter())
                if reading.timestamp in fresh:
                    count(result.status)
            self.buffer.load(
                patient_id,
                (r for r in timeline if r.timestamp >= timeline[-1].timestamp - self.buffer.span),
                first_seen,
            )
        log_event(log, "backfill", patient_id=patient_id, added=len(fresh), outcomes=outcomes)
        return BackfillResult(outcomes=outcomes, added=len(fresh))

    def _prime_dedup(self, patient_id: str, before: datetime) -> None:
        """Seed de-dup state from the alerts kept before the replay starts, so a condition
        already alerting just before ``before`` is not raised twice and cooldowns hold."""
        for alert in self.storage.alerts(patient_id, until=before - timedelta(microseconds=1)):
            self.dedup.observe(patient_id, alert.type, True, alert.t_raised)

    def _forecast(
        self, patient_id: str, patient: _Patient, t: datetime, start: float
    ) -> CycleResult:
        meta = self.engine.meta
        if is_warming_up(self.buffer.first_seen(patient_id), t, meta.lookback_min,
                         meta.interval_min):
            return CycleResult(
                patient_id=patient_id, timestamp=t, status="warming_up",
                detail=f"history shorter than the {meta.lookback_min}-min look-back",
                cycle_ms=_ms_since(start),
            )
        # Cycle alerts live on the patient's reading timeline: t_raised = reading time and the
        # cooldown is measured in event time, so a backfilled batch de-duplicates exactly like
        # the live stream it replays (wall time would collapse the whole batch into seconds).
        t_inf = time.perf_counter()
        try:
            history = self.buffer.history(patient_id)
            prediction = self.engine.predict(patient_id, patient.ctx, history)
        except DataGapError as e:
            self.metrics.data_gaps.labels("cycle").inc()
            alerts: list[StoredAlert] = []
            if self.dedup.observe(patient_id, "data_gap", True, t):
                alerts.append(self._store_alert(
                    Alert(patient_id=patient_id, type="data_gap", severity="medium", t_raised=t),
                    t0=t, details={"reason": str(e)},
                ))
            return CycleResult(
                patient_id=patient_id, timestamp=t, status="data_gap", detail=str(e),
                alerts=alerts, cycle_ms=_ms_since(start),
            )
        inference_ms = _ms_since(t_inf)
        self.metrics.inference_latency.observe(inference_ms / 1000)
        flags = assess(prediction, self.config.risk, patient.policy)
        by_type = {f.type: f for f in flags}
        alerts = []
        with self.storage.transaction():
            self.storage.insert_prediction(prediction, inference_ms)
            self.dedup.observe(patient_id, "data_gap", False, t)
            for kind in ("hypo", "hyper"):
                flag = by_type.get(kind)
                if self.dedup.observe(patient_id, kind, flag is not None, t) and flag:
                    alerts.append(self._store_alert(
                        Alert(patient_id=patient_id, type=flag.type, horizon_min=flag.horizon_min,
                              severity=flag.severity, t_raised=t),
                        t0=t, model_version=prediction.model_version,
                        details={
                            "quantile": flag.quantile, "value_mg_dl": flag.value_mg_dl,
                            "extreme_mg_dl": flag.extreme_mg_dl, "margin_mg_dl": flag.margin_mg_dl,
                        },
                    ))
        self.metrics.predictions.inc()
        return CycleResult(
            patient_id=patient_id, timestamp=t, status="predicted", prediction=prediction,
            risk=flags, alerts=alerts, inference_ms=inference_ms, cycle_ms=_ms_since(start),
        )

    def _store_alert(
        self,
        alert: Alert,
        t0: datetime | None = None,
        model_version: str | None = None,
        details: dict[str, object] | None = None,
    ) -> StoredAlert:
        stored = self.storage.insert_alert(alert, t0, model_version, details)
        self.metrics.alerts.labels(alert.type).inc()
        log_event(log, "alert_raised", logging.WARNING, patient_id=alert.patient_id,
                  type=alert.type, severity=alert.severity, horizon_min=alert.horizon_min,
                  alert_id=stored.id)
        return stored

    # watchdog ---------------------------------------------------------------------------
    def watchdog(self) -> list[StoredAlert]:
        """Raise ``data_gap`` for patients silent for more than ``data_gap_min``."""
        raised: list[StoredAlert] = []
        with self._lock:
            now = self.clock.now()
            for pid in self._patients:
                last = self.buffer.last_timestamp(pid)
                if last is None or not is_stale(last, now, self.config.data_gap_min):
                    continue
                if "data_gap" not in self.dedup.active_types(pid):
                    self.metrics.data_gaps.labels("watchdog").inc()
                minutes = minutes_between(last, now)
                if self.dedup.observe(pid, "data_gap", True, now):
                    raised.append(self._store_alert(
                        Alert(patient_id=pid, type="data_gap", severity="medium", t_raised=now),
                        details={"reason": "no_reading", "minutes_since_last": round(minutes, 1),
                                 "last_reading": last.isoformat()},
                    ))
        return raised

    # queries ----------------------------------------------------------------------------
    def latest_forecast(self, patient_id: str) -> tuple[StoredPrediction | None, list[RiskFlag]]:
        with self._lock:
            patient = self._patient(patient_id)
        prediction = self.storage.latest_prediction(patient_id)
        if prediction is None:
            return None, []
        return prediction, assess(prediction, self.config.risk, patient.policy)

    def cohort_risk(self) -> list[PatientRisk]:
        """Every registered patient, most urgent first.

        Order: high-severity risk, data gap / stale, medium, low, warming up, ok, no data.
        A stale patient's last forecast is reported but its flags are not (outdated).
        """
        with self._lock:
            now = self.clock.now()
            rows = [self._patient_risk(pid, p, now) for pid, p in self._patients.items()]
        return sorted(rows, key=lambda r: (_cohort_rank(r), -(r.minutes_since_last or 0.0)))

    def patient_status(self, patient_id: str) -> PatientRisk:
        """One patient's row of :meth:`cohort_risk`. Raises UnknownPatientError."""
        with self._lock:
            return self._patient_risk(patient_id, self._patient(patient_id), self.clock.now())

    def is_registered(self, patient_id: str) -> bool:
        with self._lock:
            return patient_id in self._patients

    def forget_patient(self, patient_id: str, include_profile: bool) -> None:
        """Delete a patient's readings, forecasts and alerts (and optionally the profile)
        from storage and from every in-memory structure, atomically under the cycle lock."""
        with self._lock:
            self.storage.delete_patient_data(patient_id, include_profile)
            self.buffer.forget(patient_id)
            self.dedup.forget(patient_id)
            if include_profile:
                self._patients.pop(patient_id, None)
        log_event(log, "patient_forgotten", patient_id=patient_id, profile=include_profile)

    def _patient_risk(self, pid: str, patient: _Patient, now: datetime) -> PatientRisk:
        meta = self.engine.meta
        last = self.buffer.last_timestamp(pid)
        active = self.dedup.active_types(pid)
        latest = self.storage.latest_prediction(pid) if last is not None else None
        stale = last is not None and is_stale(last, now, self.config.data_gap_min)
        flags: list[RiskFlag] = []
        status: CohortStatus
        if last is None:
            status = "no_data"
        elif stale or "data_gap" in active:
            status = "data_gap"
        elif latest is not None and latest.t0 == last:
            flags = assess(latest, self.config.risk, patient.policy)
            status = "at_risk" if flags else "ok"
        elif is_warming_up(self.buffer.first_seen(pid), last, meta.lookback_min,
                           meta.interval_min):
            status = "warming_up"
        else:
            status = "data_gap"
        severity = max((f.severity for f in flags), key=SEVERITY_RANK.__getitem__, default=None)
        history = self.buffer.history(pid)
        fresh = latest is not None and status in ("at_risk", "ok")
        return PatientRisk(
            patient_id=pid,
            diabetes_type=patient.profile.diabetes_type,
            status=status,
            severity=severity,
            last_reading=last,
            minutes_since_last=minutes_between(last, now) if last is not None else None,
            stale=stale,
            latest_t0=latest.t0 if latest else None,
            model_version=latest.model_version if latest else None,
            risk=flags,
            active_alerts=active,
            last_glucose_mg_dl=history[-1].glucose_mg_dl if history else None,
            trend_mg_dl_per_min=_trend(history, meta.interval_min),
            forecast=self._band(latest, patient) if fresh and latest is not None else None,
        )

    def _band(self, prediction: Prediction, patient: _Patient) -> ForecastBand:
        lo_q, hi_q = self.config.risk.quantiles_for(patient.policy)
        qs = prediction.quantiles
        lo, mid, hi = (quantile_index(qs, q) for q in (lo_q, 0.5, hi_q))
        return ForecastBand(
            t0=prediction.t0,
            horizons=prediction.horizons,
            low_quantile=lo_q,
            high_quantile=hi_q,
            low=[row[lo] for row in prediction.values],
            median=[row[mid] for row in prediction.values],
            high=[row[hi] for row in prediction.values],
        )


def _trend(history: list[Reading], interval_min: int) -> float | None:
    """Rate over the latest interval: last reading vs one taken one interval earlier.

    Readings sit on the sampling grid; a missing predecessor (a gap) gives no trend
    rather than a rate smeared across the gap.
    """
    if len(history) < 2:
        return None
    last, prev = history[-1], history[-2]
    minutes = (last.timestamp - prev.timestamp).total_seconds() / 60.0
    if not 0.5 * interval_min <= minutes <= 1.5 * interval_min:
        return None
    return (last.glucose_mg_dl - prev.glucose_mg_dl) / minutes


def _cohort_rank(r: PatientRisk) -> int:
    if r.status == "at_risk":
        return {"high": 0, "medium": 2, "low": 3}[r.severity or "low"]
    return {"data_gap": 1, "warming_up": 4, "ok": 5, "no_data": 6}[r.status]


def _ms_since(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0
