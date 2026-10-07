"""Staff HTTP routes (API key or clinician session). ``/healthz`` is public."""

import csv
import io
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from glucorag.api.deps import Service, require_staff
from glucorag.core.schemas import PatientProfile
from glucorag.core.storage import StoredAlert, StoredPrediction, StoredProfile, StoredReading
from glucorag.risk.detectors import AlertPolicy, RiskFlag
from glucorag.service import CycleResult, PatientRisk, UnknownPatientError

public = APIRouter()
router = APIRouter(dependencies=[Depends(require_staff)])


class AlertPolicyIn(BaseModel):
    hypo_quantile: float | None = Field(default=None, gt=0, lt=1)
    hyper_quantile: float | None = Field(default=None, gt=0, lt=1)


class ProfileIn(PatientProfile):
    alert_policy: AlertPolicyIn | None = None


class ProfileOut(StoredProfile):
    effective_hypo_quantile: float
    effective_hyper_quantile: float


class ReadingIn(BaseModel):
    patient_id: str
    timestamp: datetime
    glucose_mg_dl: float


class BatchOut(BaseModel):
    results: list[CycleResult]
    counts: dict[str, int]


class ForecastOut(BaseModel):
    prediction: StoredPrediction
    risk: list[RiskFlag]
    hypo_quantile: float
    hyper_quantile: float


class HistoryOut(BaseModel):
    patient_id: str
    readings: list[StoredReading]
    predictions: list[StoredPrediction]


class CohortOut(BaseModel):
    as_of: datetime
    patients: list[PatientRisk]


@public.get("/healthz")
def healthz(service: Service) -> dict[str, Any]:
    return {"status": "ok", "model_version": service.model_version}


@router.get("/metrics")
def metrics(service: Service) -> Response:
    return Response(generate_latest(service.metrics.registry), media_type=CONTENT_TYPE_LATEST)


@router.post("/patients")
def register_patient(body: ProfileIn, service: Service) -> ProfileOut:
    policy = body.alert_policy or AlertPolicyIn()
    profile = PatientProfile.model_validate(body.model_dump(exclude={"alert_policy"}))
    try:
        stored = service.register_profile(
            profile, AlertPolicy(policy.hypo_quantile, policy.hyper_quantile)
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    hypo_q, hyper_q = service.effective_quantiles(profile.patient_id)
    return ProfileOut(
        **stored.model_dump(), effective_hypo_quantile=hypo_q, effective_hyper_quantile=hyper_q
    )


@router.post("/readings", response_model=None)
def post_readings(
    body: ReadingIn | list[ReadingIn], request: Request, service: Service
) -> CycleResult | BatchOut:
    """One reading -> its cycle result (404 unknown patient, 422 rejected).

    A list is processed in submitted order; each item reports its own status.
    """
    if isinstance(body, ReadingIn):
        try:
            result = service.ingest(body.patient_id, body.timestamp, body.glucose_mg_dl)
        except UnknownPatientError as e:
            raise HTTPException(404, f"Unknown patient {body.patient_id!r}") from e
        if result.status == "rejected":
            raise HTTPException(422, {"reason": result.reason, "detail": result.detail})
        return result
    if len(body) > request.app.state.max_batch:
        raise HTTPException(413, f"Batch larger than {request.app.state.max_batch} readings")
    results: list[CycleResult] = []
    for r in body:
        try:
            results.append(service.ingest(r.patient_id, r.timestamp, r.glucose_mg_dl))
        except UnknownPatientError:
            results.append(CycleResult(
                patient_id=r.patient_id, timestamp=r.timestamp, status="rejected",
                reason="unknown_patient", cycle_ms=0.0,
            ))
    counts: dict[str, int] = {}
    for res in results:
        counts[res.status] = counts.get(res.status, 0) + 1
    return BatchOut(results=results, counts=counts)


@router.get("/patients/{patient_id}/forecast")
def forecast(patient_id: str, service: Service) -> ForecastOut:
    try:
        prediction, risk = service.latest_forecast(patient_id)
        hypo_q, hyper_q = service.effective_quantiles(patient_id)
    except UnknownPatientError as e:
        raise HTTPException(404, f"Unknown patient {patient_id!r}") from e
    if prediction is None:
        raise HTTPException(404, f"No forecast yet for {patient_id!r}")
    return ForecastOut(prediction=prediction, risk=risk, hypo_quantile=hypo_q,
                       hyper_quantile=hyper_q)


@router.get("/patients/{patient_id}/history")
def history(
    patient_id: str,
    service: Service,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(gt=0, le=10000)] = 500,
) -> HistoryOut:
    """Most recent ``limit`` readings and forecasts in ``[since, until]``, ascending."""
    if service.storage.profile(patient_id) is None:
        raise HTTPException(404, f"Unknown patient {patient_id!r}")
    readings = service.storage.readings(patient_id, since, until, limit)
    predictions = service.storage.predictions(patient_id, since, until, limit, latest_first=True)
    return HistoryOut(patient_id=patient_id, readings=readings, predictions=predictions[::-1])


@router.get("/cohort/risk")
def cohort_risk(service: Service) -> CohortOut:
    return CohortOut(as_of=service.clock.now(), patients=service.cohort_risk())


@router.get("/alerts")
def alerts(
    service: Service,
    patient_id: str | None = None,
    type: Literal["hypo", "hyper", "data_gap"] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(gt=0, le=10000)] = 200,
) -> list[StoredAlert]:
    return service.storage.alerts(patient_id, type, since, until, limit)


@router.get("/export", response_model=None)
def export(
    service: Service,
    format: Literal["json", "csv"] = "json",
    kind: Literal["all", "predictions", "alerts"] = "all",
    patient_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Response | dict[str, Any]:
    """Predictions and/or alerts for offline review; CSV needs a single ``kind``."""
    storage = service.storage
    preds = storage.predictions(patient_id, since, until) if kind != "alerts" else []
    alerts_ = storage.alerts(patient_id, None, since, until) if kind != "predictions" else []
    if format == "json":
        out: dict[str, Any] = {}
        if kind != "alerts":
            out["predictions"] = [p.model_dump(mode="json") for p in preds]
        if kind != "predictions":
            out["alerts"] = [a.model_dump(mode="json") for a in alerts_]
        return out
    if kind == "all":
        raise HTTPException(422, "CSV export needs kind=predictions or kind=alerts")
    text = _predictions_csv(preds) if kind == "predictions" else _alerts_csv(alerts_)
    return Response(
        text, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="glucorag_{kind}.csv"'},
    )


def _predictions_csv(preds: list[StoredPrediction]) -> str:
    """One row per (forecast, horizon); a column per quantile level seen in the export."""
    levels = sorted({q for p in preds for q in p.quantiles})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["patient_id", "t0", "model_version", "horizon_min", *[f"q{q:g}" for q in levels]])
    for p in preds:
        for h, row in zip(p.horizons, p.values, strict=True):
            by_q = dict(zip(p.quantiles, row, strict=True))
            w.writerow([p.patient_id, p.t0.isoformat(), p.model_version, h,
                        *[f"{by_q[q]:.2f}" if q in by_q else "" for q in levels]])
    return buf.getvalue()


def _alerts_csv(alerts_: list[StoredAlert]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "patient_id", "type", "horizon_min", "severity", "t_raised", "t0",
                "model_version", "details"])
    for a in alerts_:
        w.writerow([a.id, a.patient_id, a.type, a.horizon_min, a.severity,
                    a.t_raised.isoformat(), a.t0.isoformat() if a.t0 else "",
                    a.model_version or "", _details(a.details)])
    return buf.getvalue()


def _details(d: dict[str, Any]) -> str:
    return ";".join(f"{k}={v}" for k, v in d.items())
