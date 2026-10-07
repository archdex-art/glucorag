"""CGM source adapters: deliver readings to the service over HTTP or in-process.

The dataset replay adapter streams one recorded ShanghaiDM series (registering the
patient's demographics first) as if it were a live sensor::

    python -m glucorag.ingest.adapters data/raw/shanghai/Shanghai_T1DM/1001_0_20210730.xlsx \\
        --url http://127.0.0.1:8000            # API key from GLUCORAG_API_KEY
    python -m glucorag.ingest.adapters <series> --in-process --model-path models/shanghai-v1

Replayed timestamps lie in the past, so the receiving service should run with the data
clock (``GLUCORAG_CLOCK=data``) for staleness to be measured in dataset time.
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from glucorag.core.schemas import PatientProfile
from glucorag.core.storage import Storage
from glucorag.data import shanghai
from glucorag.inference.engine import ForecastEngine
from glucorag.risk.detectors import AlertPolicy
from glucorag.service import DataClock, GlucoseService, ServiceConfig


@dataclass(frozen=True)
class SourceReading:
    patient_id: str
    timestamp: datetime
    glucose_mg_dl: float

    def to_json(self) -> dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "timestamp": self.timestamp.isoformat(),
            "glucose_mg_dl": self.glucose_mg_dl,
        }


class ReadingSink(Protocol):
    def register(self, profile: PatientProfile) -> None: ...

    def send(self, readings: Sequence[SourceReading]) -> list[dict[str, Any]]:
        """Deliver readings in order; one cycle-result dict per reading."""
        ...


class HttpSink:
    def __init__(self, base_url: str, api_key: str, timeout_s: float = 30.0) -> None:
        self.client = httpx.Client(
            base_url=base_url, headers={"X-API-Key": api_key}, timeout=timeout_s
        )

    def register(self, profile: PatientProfile) -> None:
        self.client.post("/patients", json=profile.model_dump(mode="json")).raise_for_status()

    def send(self, readings: Sequence[SourceReading]) -> list[dict[str, Any]]:
        resp = self.client.post("/readings", json=[r.to_json() for r in readings])
        resp.raise_for_status()
        return resp.json()["results"]

    def get(self, path: str) -> Any:
        resp = self.client.get(path)
        resp.raise_for_status()
        return resp.json() if "json" in resp.headers.get("content-type", "") else resp.text


class InProcessSink:
    def __init__(self, service: GlucoseService) -> None:
        self.service = service

    def register(self, profile: PatientProfile) -> None:
        self.service.register_profile(profile, AlertPolicy())

    def send(self, readings: Sequence[SourceReading]) -> list[dict[str, Any]]:
        return [
            self.service.ingest(r.patient_id, r.timestamp, r.glucose_mg_dl).model_dump(mode="json")
            for r in readings
        ]


def load_shanghai_series(
    series_path: str | Path, summary_path: str | Path | None = None, patient_id: str | None = None
) -> tuple[PatientProfile, list[SourceReading]]:
    """Profile + time-ordered finite readings of one ShanghaiDM recording file."""
    series_path = Path(series_path)
    if summary_path is None:
        summary_path = series_path.parent.parent / f"{series_path.parent.name}_Summary.xlsx"
    frame = shanghai.read_series(series_path)
    summary = shanghai.read_summary(Path(summary_path))
    match = summary[summary["series_id"] == series_path.stem]
    if match.empty:
        raise ValueError(f"No demographics for {series_path.stem} in {summary_path}")
    row = match.iloc[0]
    pid = patient_id or str(row["patient_id"])
    profile = PatientProfile(
        patient_id=pid,
        age=float(row["age"]),
        gender=str(row["gender"]),
        bmi=float(row["bmi"]),
        diabetes_type=row["diabetes_type"],
    )
    frame = frame.dropna(subset=["timestamp", "glucose_mg_dl"])
    frame = frame.sort_values("timestamp", kind="stable")
    readings = [
        SourceReading(pid, t.to_pydatetime(), float(g))
        for t, g in zip(frame["timestamp"], frame["glucose_mg_dl"], strict=True)
    ]
    return profile, readings


@dataclass
class ReplayReport:
    statuses: Counter[str] = field(default_factory=Counter)
    rejections: Counter[str] = field(default_factory=Counter)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    cycle_ms: list[float] = field(default_factory=list)  # server-side, predicted cycles only
    request_ms: list[float] = field(default_factory=list)  # client round trip per send

    def summary(self) -> dict[str, Any]:
        return {
            "statuses": dict(self.statuses),
            "rejections": dict(self.rejections),
            "alerts_by_type": dict(Counter(a["type"] for a in self.alerts)),
            "cycle_ms": _stats(self.cycle_ms),
            "request_ms": _stats(self.request_ms),
        }


def _stats(xs: list[float]) -> dict[str, float]:
    if not xs:
        return {}
    s = sorted(xs)
    return {
        "n": len(s),
        "mean": round(statistics.fmean(s), 3),
        "p50": round(s[len(s) // 2], 3),
        "p95": round(s[min(len(s) - 1, math.ceil(0.95 * len(s)) - 1)], 3),
        "max": round(s[-1], 3),
    }


def _batches(readings: Sequence[SourceReading], size: int) -> Iterator[list[SourceReading]]:
    for i in range(0, len(readings), size):
        yield list(readings[i : i + size])


def replay(
    readings: Sequence[SourceReading],
    sink: ReadingSink,
    batch_size: int = 1,
    speed: float = 0.0,
) -> ReplayReport:
    """Send readings in order; ``speed`` > 0 paces by recorded time / speed (0 = no pacing)."""
    report = ReplayReport()
    prev: datetime | None = None
    for batch in _batches(readings, batch_size):
        if speed > 0 and prev is not None:
            time.sleep(max(0.0, (batch[0].timestamp - prev).total_seconds() / speed))
        prev = batch[-1].timestamp
        start = time.perf_counter()
        results = sink.send(batch)
        report.request_ms.append((time.perf_counter() - start) * 1000.0)
        for res in results:
            report.statuses[res["status"]] += 1
            if res["status"] == "rejected":
                report.rejections[res["reason"]] += 1
            if res["status"] == "predicted":
                report.cycle_ms.append(res["cycle_ms"])
            report.alerts.extend(res["alerts"])
    return report


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("series", type=Path, help="ShanghaiDM recording (.xls/.xlsx)")
    p.add_argument("--summary", type=Path, default=None, help="demographics sheet (auto)")
    p.add_argument("--patient-id", default=None, help="override (default: 4-digit prefix)")
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--api-key", default=os.environ.get("GLUCORAG_API_KEY"))
    p.add_argument("--in-process", action="store_true", help="run the service in-process")
    p.add_argument("--model-path", type=Path, help="artifact for --in-process")
    p.add_argument("--db-path", default=":memory:", help="SQLite for --in-process")
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--speed", type=float, default=0.0, help="time compression; 0 = unpaced")
    p.add_argument("--limit", type=int, default=None, help="replay only the first N readings")
    args = p.parse_args(argv)

    profile, readings = load_shanghai_series(args.series, args.summary, args.patient_id)
    readings = readings[: args.limit]
    sink: ReadingSink
    if args.in_process:
        if args.model_path is None:
            p.error("--in-process needs --model-path")
        config = ServiceConfig()
        engine = ForecastEngine.from_artifact(args.model_path, config.data_gap_min)
        sink = InProcessSink(GlucoseService(engine, Storage(args.db_path), config, DataClock()))
    else:
        if not args.api_key:
            p.error("--api-key or GLUCORAG_API_KEY is required for HTTP replay")
        sink = HttpSink(args.url, args.api_key)
    sink.register(profile)
    report = replay(readings, sink, args.batch_size, args.speed)
    out = {"patient_id": profile.patient_id, "series": args.series.stem,
           "readings": len(readings), **report.summary()}
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
