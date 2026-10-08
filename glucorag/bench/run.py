"""Zero-shot TSFM benchmark against EPS-TFT on the artifact's test split (research only).

    glucorag-bench --artifact models/shanghai-v1 --data-root data/raw/shanghai \\
        --out reports/benchmark

Uses the evaluation protocol of ``glucorag.evaluate.run`` unchanged: the artifact's preprocessing
and split, test windows whose targets are real CGM observations, per-patient metrics on the
point forecast (0.5 quantile) reported as mean ± sample STD across patients, and the paired
per-patient RMSE test. EPS-TFT is re-run on CPU from the artifact so the comparison is paired on
identical windows. Each foundation model forecasts zero-shot from glucose alone, once with the
artifact's look-back and once per extra ``--context-min``. Needs ``pip install -e ".[bench]"``
for anything beyond the persistence reference. Writes ``report.md`` and ``results.json``.
"""

import argparse
import gc
import json
import logging
import platform
import time
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from glucorag.bench.models import SPECS, ModelSpec, load_forecaster
from glucorag.bench.protocol import (
    LOWER,
    UPPER,
    Forecast,
    coverage_summary,
    interval_coverage,
    series_histories,
    window_contexts,
)
from glucorag.bench.report import NOT_RUN, context_label, render_report
from glucorag.core.config import settings
from glucorag.core.registry import load_artifact
from glucorag.data.pipeline import make_windows, minutes_to_steps
from glucorag.evaluate.metrics import metrics_at_horizons
from glucorag.evaluate.predict import predict_tft
from glucorag.evaluate.report import summary_dict
from glucorag.evaluate.run import MAIN, load_for_artifact
from glucorag.evaluate.stats import align_patients, paired_test
from glucorag.preprocess.windows import Windows
from glucorag.train.trainer import seed_everything

log = logging.getLogger("glucorag.bench")

PACKAGES = ("torch", "chronos-forecasting", "timesfm", "transformers")


def _versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def _scored(
    forecast: Forecast, windows: Windows, interval: int, horizons: list[int]
) -> dict[str, Any]:
    if forecast.median.shape != windows.target_mg_dl.shape:
        raise ValueError(f"forecast {forecast.median.shape} != {windows.target_mg_dl.shape}")
    per_patient = metrics_at_horizons(
        windows.target_mg_dl, forecast.median, windows.patient_id, interval, horizons
    )
    out: dict[str, Any] = {
        "summary": summary_dict(per_patient),
        "per_patient": per_patient.to_dict("records"),
    }
    if forecast.lower is not None and forecast.upper is not None:
        cov = interval_coverage(
            windows.target_mg_dl, forecast.lower, forecast.upper, windows.patient_id,
            interval, horizons,
        )
        out["coverage"] = coverage_summary(cov)
    return out


def _context_stats(contexts: list[np.ndarray], steps: int) -> dict[str, Any]:
    lengths = np.array([len(c) for c in contexts])
    return {
        "steps": steps,
        "length_min": int(lengths.min()),
        "length_median": float(np.median(lengths)),
        "length_mean": float(lengths.mean()),
        "full_length_pct": float(100.0 * np.mean(lengths == steps)),
    }


def _significance(
    per_patient: dict[str, pd.DataFrame], names: list[str], horizons: list[int]
) -> dict[str, Any]:
    """EPS-TFT (``a``) vs each method (``b``) on per-patient RMSE; negative Δ favours EPS-TFT."""
    out: dict[str, Any] = {}
    for name in names:
        out[name] = {}
        for h in horizons:
            a, b = align_patients(per_patient, (MAIN, name), h, "RMSE")
            out[name][str(h)] = {"reference": MAIN, "metric": "RMSE"} | paired_test(a, b).to_dict()
    return out


def _reference_methods(path: Path, n_windows: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Trained baselines from a stored ``metrics.json`` of the same split (and its EPS-TFT)."""
    if not path.is_file():
        log.warning("no reference metrics at %s", path)
        return {}, {}
    stored = json.loads(path.read_text())
    if stored["n_test_windows"] != n_windows:
        log.warning("%s has %d test windows, not %d; skipping", path, stored["n_test_windows"],
                    n_windows)
        return {}, {}
    methods = {
        name: {"kind": "reference", "summary": m["summary"]}
        for name, m in stored["methods"].items()
        if name != MAIN
    }
    return methods, stored["methods"].get(MAIN, {}).get("summary", {})


def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    seed_everything(args.seed)
    # EPS-TFT is small: run it on CPU so it reproduces the stored evaluation exactly.
    model, meta = load_artifact(args.artifact, "cpu")
    data, hash_ok = load_for_artifact(meta, args.data_root, args.ohio_profiles)
    interval = meta.interval_min
    horizons = [h for h in settings.model.horizons_min if h <= meta.horizon_min]
    test_w, test_s = make_windows(data, "test", meta.lookback_min, meta.horizon_min)
    log.info("test windows: %d", len(test_w))

    methods: dict[str, dict[str, Any]] = {}
    per_patient: dict[str, pd.DataFrame] = {}

    start = time.perf_counter()
    tft = predict_tft(model, test_w, test_s, meta.glucose_normalizer(), meta.quantiles,
                      args.batch_size, "cpu")
    seconds = time.perf_counter() - start
    q = tft.quantiles_mg_dl
    has_interval = LOWER in meta.quantiles and UPPER in meta.quantiles
    tft_forecast = Forecast(
        median=tft.median_mg_dl,
        lower=q[..., meta.quantiles.index(LOWER)] if has_interval else None,
        upper=q[..., meta.quantiles.index(UPPER)] if has_interval else None,
    )
    methods[MAIN] = {
        "kind": "eps-tft",
        "model_id": str(args.artifact),
        "revision": meta.version,
        "licence": "this project",
        "params": int(sum(p.numel() for p in model.parameters())),
        "context_min": meta.lookback_min,
        "device": "cpu",
        "runtime": {"load_s": None, "predict_s": round(seconds, 2)},
    } | _scored(tft_forecast, test_w, interval, horizons)
    per_patient[MAIN] = pd.DataFrame(methods[MAIN]["per_patient"])

    histories = series_histories([data.train, data.val, data.test])
    horizon_steps = meta.horizon_steps
    context_mins = sorted({meta.lookback_min, *args.context_min})
    contexts = {
        m: window_contexts(histories, test_w, minutes_to_steps(m, interval)) for m in context_mins
    }
    context_stats = {
        str(m): _context_stats(c, minutes_to_steps(m, interval)) for m, c in contexts.items()
    }
    if context_stats[str(meta.lookback_min)]["full_length_pct"] != 100.0:
        raise RuntimeError("look-back contexts must match the EPS-TFT encoder windows")

    compared: list[str] = []
    for key in args.models:
        spec: ModelSpec = SPECS[key]
        start = time.perf_counter()
        forecaster = load_forecaster(spec, args.device, args.batch_size)
        load_s = round(time.perf_counter() - start, 2)
        # Persistence only looks at the last value, so one context length is enough.
        minutes = [meta.lookback_min] if spec.family == "persistence" else context_mins
        for m in minutes:
            name = spec.label if spec.family == "persistence" else (
                f"{spec.label}, {context_label(m)} context"
            )
            log.info("%s ...", name)
            start = time.perf_counter()
            forecast = forecaster.predict(contexts[m], horizon_steps)
            seconds = time.perf_counter() - start
            methods[name] = {
                "kind": "naive" if spec.family == "persistence" else "tsfm",
                "model_id": spec.model_id,
                "revision": spec.revision,
                "licence": spec.licence,
                "params": forecaster.n_params,
                "context_min": m,
                "device": "cpu" if spec.family == "persistence" else args.device,
                "runtime": {"load_s": load_s, "predict_s": round(seconds, 2)},
            } | _scored(forecast, test_w, interval, horizons)
            per_patient[name] = pd.DataFrame(methods[name]["per_patient"])
            compared.append(name)
            log.info("%s done in %.1fs: RMSE %s", name, seconds, {
                h: round(s["RMSE"]["mean"], 2) for h, s in methods[name]["summary"].items()
            })
        del forecaster
        gc.collect()

    reference, stored_main = (
        _reference_methods(args.reference, len(test_w)) if args.reference else ({}, {})
    )
    reproduced = {
        h: abs(stored_main[h]["RMSE"]["mean"] - methods[MAIN]["summary"][h]["RMSE"]["mean"])
        for h in methods[MAIN]["summary"]
        if h in stored_main
    }
    return {
        "artifact": meta.version,
        "dataset": meta.dataset,
        "interval_min": interval,
        "horizons_min": horizons,
        "lookback_min": meta.lookback_min,
        "n_test_windows": len(test_w),
        "n_test_patients": int(len(set(test_w.patient_id.tolist()))),
        "data_hash_matches": hash_ok,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "machine": {"platform": platform.platform(), "processor": platform.processor(),
                    "device": args.device, "batch_size": args.batch_size},
        "packages": _versions(),
        "contexts": context_stats,
        "eps_tft_vs_stored_rmse_abs_diff": reproduced,
        "reference_source": str(args.reference) if reference else None,
        "methods": methods | reference,
        "significance": _significance(per_patient, compared, horizons),
        "not_run": NOT_RUN,
    }


def write_benchmark(results: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=1, default=str) + "\n")
    (out_dir / "report.md").write_text(render_report(results))
    log.info("wrote %s", out_dir)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="glucorag-bench",
        description="Zero-shot time-series foundation models vs EPS-TFT (research only).",
    )
    p.add_argument("--artifact", type=Path, default=Path("models/shanghai-v1"))
    p.add_argument("--data-root", type=Path, default=Path("data/raw/shanghai"))
    p.add_argument("--ohio-profiles", type=Path, default=None)
    p.add_argument("--models", nargs="+", choices=list(SPECS), default=list(SPECS))
    p.add_argument(
        "--context-min", nargs="*", type=int, default=[1440, 7680],
        help="context lengths besides the artifact's look-back (default 24 h and 128 h,"
        " i.e. 96 and 512 steps at 15 min)",
    )
    p.add_argument("--device", default="cpu", help="torch device for the foundation models")
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument(
        "--reference", type=Path, default=Path("reports/shanghai-v1/metrics.json"),
        help="stored glucorag-evaluate metrics.json whose trained baselines are listed for context",
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=Path("reports/benchmark"))
    return p


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    write_benchmark(benchmark(args), args.out)


if __name__ == "__main__":
    main()
