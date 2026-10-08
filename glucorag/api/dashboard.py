"""Monitoring endpoints for the web dashboard: model card data and service statistics."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from glucorag.api.deps import Service, require_staff
from glucorag.evaluate.live import HORIZONS, MIN_COUNT, AccuracyReport

router = APIRouter(dependencies=[Depends(require_staff)])


class ReleaseStatus(BaseModel):
    promoted: bool
    current_version: str | None
    last_promotion: dict[str, Any] | None


class ModelInfo(BaseModel):
    version: str
    dataset: str
    created_at: datetime
    interval_min: int
    lookback_min: int
    horizon_min: int
    quantiles: list[float]
    static_features: list[str]
    hyperparameters: dict[str, Any]
    weights_sha256: str
    data_hash: str
    evaluation: dict[str, Any] | None
    cross_individual_cv: dict[str, Any] | None
    in_silico: dict[str, Any] | None
    release: ReleaseStatus


class LatencyStats(BaseModel):
    samples: int
    p50_ms: float | None
    p95_ms: float | None
    max_ms: float | None
    cycle_mean_ms: float | None


class ServiceStats(BaseModel):
    started_at: datetime
    uptime_s: float
    model_version: str
    clock: str
    as_of: datetime
    counters: dict[str, float]
    rejected_by_reason: dict[str, float]
    alerts_by_type: dict[str, float]
    data_gaps_by_source: dict[str, float]
    latency: LatencyStats
    storage: dict[str, int]
    thresholds: dict[str, float]


def _release_status(artifact: Path, version: str) -> ReleaseStatus:
    root = artifact.parent
    pointer = root / "CURRENT"
    current = pointer.read_text().strip() if pointer.is_file() else None
    last = None
    log = root / "promotions.jsonl"
    if log.is_file():
        for line in log.read_text().splitlines():
            record = json.loads(line)
            if record.get("version") == version:
                last = record
    return ReleaseStatus(promoted=current == version, current_version=current, last_promotion=last)


def _in_silico(report: Path | None, version: str) -> dict[str, Any] | None:
    if report is None or not report.is_file():
        return None
    data = json.loads(report.read_text())
    if data.get("model", {}).get("version") != version:
        return None
    return {
        "config": data.get("config"),
        "runtime_s": data.get("runtime_s"),
        "aggregate": data.get("aggregate"),
        "paper": data.get("paper"),
    }


@router.get("/model")
def model_info(request: Request, service: Service) -> ModelInfo:
    meta = service.engine.meta
    artifact: Path = request.app.state.model_path
    test = meta.metrics.get("test")
    return ModelInfo(
        version=meta.version,
        dataset=meta.dataset,
        created_at=meta.created_at,
        interval_min=meta.interval_min,
        lookback_min=meta.lookback_min,
        horizon_min=meta.horizon_min,
        quantiles=meta.quantiles,
        static_features=list(meta.static_encoder.get("features", [])),
        hyperparameters={
            "d_model": meta.d_model,
            "num_heads": meta.num_heads,
            "dropout": meta.dropout,
            "use_static": meta.use_static,
            "use_decoder": meta.use_decoder,
            **{
                k: meta.train_config[k]
                for k in ("lr", "batch_size", "epochs", "patience", "seed", "epochs_run",
                          "best_val_loss")
                if k in meta.train_config
            },
        },
        weights_sha256=meta.weights_sha256,
        data_hash=meta.data_hash,
        evaluation=test,
        cross_individual_cv=meta.metrics.get("cross_individual_cv"),
        in_silico=_in_silico(request.app.state.sim_report, meta.version),
        release=_release_status(artifact, meta.version),
    )


# Live 7-day RMSE more than this many times the evaluation's test RMSE raises a warning.
DRIFT_RATIO = 1.25


class AccuracyReference(BaseModel):
    horizon_min: int
    rmse_mg_dl: float


class AccuracyWarning(BaseModel):
    horizon_min: int
    rmse_7d_mg_dl: float
    reference_rmse_mg_dl: float
    ratio: float


class ModelAccuracy(AccuracyReport):
    model_version: str
    reference: list[AccuracyReference]
    warning_ratio: float
    warnings: list[AccuracyWarning]


def _reference_rmse(test: dict[str, Any] | None) -> list[AccuracyReference]:
    """Mean test RMSE per horizon from the evaluation report stored with the model."""
    summary = (test or {}).get("summary", {})
    out = []
    for h in HORIZONS:
        value = summary.get(str(h), {}).get("RMSE", {}).get("mean")
        if isinstance(value, int | float):
            out.append(AccuracyReference(horizon_min=h, rmse_mg_dl=round(float(value), 2)))
    return out


@router.get("/model/accuracy")
def model_accuracy(service: Service) -> ModelAccuracy:
    """Realised forecast error (cohort, per model version, per patient, daily) and drift
    warnings: the served version's 7-day RMSE above ``DRIFT_RATIO`` x its test RMSE."""
    meta = service.engine.meta
    report = service.accuracy()
    reference = _reference_rmse(meta.metrics.get("test"))
    current = next((v for v in report.versions if v.model_version == meta.version), None)
    live_7d = {h.horizon_min: h for h in current.last_7_days} if current else {}
    warnings = []
    for ref in reference:
        live = live_7d.get(ref.horizon_min)
        if live is None or live.count < MIN_COUNT or live.rmse_mg_dl is None:
            continue
        ratio = live.rmse_mg_dl / ref.rmse_mg_dl
        if ratio > DRIFT_RATIO:
            warnings.append(AccuracyWarning(
                horizon_min=ref.horizon_min, rmse_7d_mg_dl=live.rmse_mg_dl,
                reference_rmse_mg_dl=ref.rmse_mg_dl, ratio=round(ratio, 3),
            ))
    return ModelAccuracy(
        **report.model_dump(), model_version=meta.version, reference=reference,
        warning_ratio=DRIFT_RATIO, warnings=warnings,
    )


def _samples(service_metrics: Any, name: str) -> dict[str, float]:
    """Sum samples of a Prometheus counter by its single label (or '' if unlabelled)."""
    out: dict[str, float] = {}
    for metric in service_metrics.registry.collect():
        if metric.name != name:
            continue
        for s in metric.samples:
            if s.name.endswith("_total"):
                key = next(iter(s.labels.values()), "") if s.labels else ""
                out[key] = out.get(key, 0.0) + float(s.value)
    return out


def _hist_mean_ms(service_metrics: Any, name: str) -> float | None:
    total = count = 0.0
    for metric in service_metrics.registry.collect():
        if metric.name == name:
            for s in metric.samples:
                if s.name.endswith("_sum"):
                    total = float(s.value)
                elif s.name.endswith("_count"):
                    count = float(s.value)
    return total / count * 1000.0 if count else None


@router.get("/stats")
def stats(request: Request, service: Service) -> ServiceStats:
    m = service.metrics
    lat = np.array(service.storage.recent_latencies_ms(1000), dtype=float)
    started: datetime = request.app.state.started_at
    now = datetime.now(UTC)
    risk = service.config.risk
    return ServiceStats(
        started_at=started,
        uptime_s=(now - started).total_seconds(),
        model_version=service.model_version,
        clock=request.app.state.clock,
        as_of=service.clock.now(),
        counters={
            "readings_ingested": _samples(m, "glucorag_readings_ingested").get("", 0.0),
            "readings_clipped": _samples(m, "glucorag_readings_clipped").get("", 0.0),
            "predictions": _samples(m, "glucorag_predictions").get("", 0.0),
        },
        rejected_by_reason=_samples(m, "glucorag_readings_rejected"),
        alerts_by_type=_samples(m, "glucorag_alerts"),
        data_gaps_by_source=_samples(m, "glucorag_data_gaps"),
        latency=LatencyStats(
            samples=int(lat.size),
            p50_ms=float(np.percentile(lat, 50)) if lat.size else None,
            p95_ms=float(np.percentile(lat, 95)) if lat.size else None,
            max_ms=float(lat.max()) if lat.size else None,
            cycle_mean_ms=_hist_mean_ms(m, "glucorag_prediction_latency_seconds"),
        ),
        storage=service.storage.table_counts(),
        thresholds={
            "hypo_mg_dl": risk.hypo_mg_dl,
            "hyper_mg_dl": risk.hyper_mg_dl,
            "hypo_quantile": risk.hypo_quantile,
            "hyper_quantile": risk.hyper_quantile,
            "data_gap_min": float(service.config.data_gap_min),
        },
    )
