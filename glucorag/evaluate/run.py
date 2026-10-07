"""Evaluate a registered EPS-TFT artifact against baselines and ablations.

    python -m glucorag.evaluate.run --artifact models/shanghai-v1 \\
        --data-root data/raw/shanghai --baselines \\
        --ablation-artifacts models/shanghai-ablate-nostatic models/shanghai-ablate-nodecoder \\
        --out reports/shanghai-v1

    python -m glucorag.evaluate.run --artifact models/shanghai-v1 \\
        --data-root data/raw/shanghai --cv 5 --out reports/shanghai-v1

The first form writes ``report.md`` and ``metrics.json`` and stores the summary in the
artifact's ``meta.json``; ``--cv K`` instead retrains EPS-TFT in K cross-individual folds
and writes ``cv.md`` / ``cv.json``.
"""

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from glucorag.core.config import settings
from glucorag.core.registry import ModelMeta, load_artifact, update_meta
from glucorag.data.pipeline import PreparedData, load_dataset, make_windows, static_matrix
from glucorag.evaluate.baselines import build_baselines
from glucorag.evaluate.cv import run_cv
from glucorag.evaluate.metrics import horizon_index, metrics_at_horizons
from glucorag.evaluate.predict import predict_tft
from glucorag.evaluate.report import render_cv_report, render_report, summary_dict
from glucorag.evaluate.stats import align_patients, next_best, paired_test, patient_strata
from glucorag.explain.attention import attention_by_position
from glucorag.explain.vsn_importance import importance_by_step, variable_importance
from glucorag.train.cli import data_hash
from glucorag.train.trainer import resolve_device, seed_everything

log = logging.getLogger("glucorag.evaluate")

MAIN = "EPS-TFT"


def load_for_artifact(
    meta: ModelMeta, data_root: Path, ohio_profiles: Path | None
) -> tuple[PreparedData, bool]:
    """Load the dataset with the artifact's preprocessing and pinned normalization.

    Returns the data and whether its hash matches the one recorded at training time.
    """
    max_gap = int(meta.train_config.get("max_gap_min", settings.alert_thresholds.data_gap_min))
    data = load_dataset(meta.dataset, data_root, max_gap, ohio_profiles)
    matches = data_hash(data) == meta.data_hash
    if not matches:
        log.warning("data hash differs from the artifact's; using the artifact's normalizers")
    data.glucose_norm = meta.glucose_normalizer()
    data.static_encoder = meta.encoder()
    for part in (data.train, data.val, data.test):
        part["glucose_z"] = data.glucose_norm.transform(part["glucose_mg_dl"])
    return data, matches


def ablation_label(meta: ModelMeta) -> str:
    flags = ((meta.use_static, "covariate encoder"), (meta.use_decoder, "LSTM decoder"))
    parts = [label for flag, label in flags if not flag]
    return f"{MAIN} w/o " + " and ".join(parts) if parts else meta.version


def _check_compatible(main: ModelMeta, other: ModelMeta) -> None:
    same = (
        other.dataset == main.dataset
        and other.interval_min == main.interval_min
        and other.lookback_min == main.lookback_min
        and other.horizon_min == main.horizon_min
        and np.allclose(list(other.glucose_norm.values()), list(main.glucose_norm.values()))
    )
    if not same:
        raise ValueError(f"{other.version} differs in data/geometry from {main.version}")


def _by_type(per_patient: pd.DataFrame, types: pd.Series | None) -> dict[str, Any]:
    if types is None:
        return {}
    mapping = types.to_dict()
    labelled = per_patient.assign(dtype=per_patient["patient_id"].map(lambda p: mapping[p]))
    return {str(t): summary_dict(g.drop(columns="dtype")) for t, g in labelled.groupby("dtype")}


def _significance(
    per_patient: dict[str, pd.DataFrame], candidates: list[str], horizons: list[int]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not candidates:
        return out
    for h in horizons:
        means = {
            name: float(np.mean(per_patient[name].loc[lambda f: f["horizon_min"] == h, "RMSE"]))
            for name in [MAIN, *candidates]
        }
        comparator = next_best(means, MAIN)
        a, b = align_patients(per_patient, (MAIN, comparator), h, "RMSE")
        out[str(h)] = {"reference": MAIN, "comparator": comparator, "metric": "RMSE"} | (
            paired_test(a, b).to_dict()
        )
    return out


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    device = resolve_device(args.device)
    seed_everything(args.seed)
    model, meta = load_artifact(args.artifact, device)
    data, hash_ok = load_for_artifact(meta, args.data_root, args.ohio_profiles)
    interval = meta.interval_min
    horizons = [h for h in settings.model.horizons_min if h <= meta.horizon_min]
    test_w, test_s = make_windows(data, "test", meta.lookback_min, meta.horizon_min)
    log.info("test windows: %d", len(test_w))
    types = (
        patient_strata(data.profiles) if "diabetes_type" in data.profiles.columns else None
    )

    per_patient: dict[str, pd.DataFrame] = {}
    kinds: dict[str, str] = {}
    artifacts: dict[str, Path] = {MAIN: Path(args.artifact)}

    out = predict_tft(model, test_w, test_s, meta.glucose_normalizer(), meta.quantiles,
                      args.batch_size, device)
    per_patient[MAIN] = metrics_at_horizons(
        test_w.target_mg_dl, out.median_mg_dl, test_w.patient_id, interval, horizons
    )
    kinds[MAIN] = "eps-tft"

    for path in args.ablation_artifacts:
        abl_model, abl_meta = load_artifact(path, device)
        _check_compatible(meta, abl_meta)
        label = ablation_label(abl_meta)
        abl_static = static_matrix(test_w, data.profiles, abl_meta.encoder())
        abl_out = predict_tft(abl_model, test_w, abl_static, abl_meta.glucose_normalizer(),
                              abl_meta.quantiles, args.batch_size, device)
        per_patient[label] = metrics_at_horizons(
            test_w.target_mg_dl, abl_out.median_mg_dl, test_w.patient_id, interval, horizons
        )
        kinds[label] = "ablation"
        artifacts[label] = Path(path)

    notes: list[str] = []
    baseline_info: dict[str, Any] = {}
    if args.baselines:
        train_w, _ = make_windows(data, "train", meta.lookback_min, meta.horizon_min)
        val_w, _ = make_windows(data, "val", meta.lookback_min, meta.horizon_min)
        cols = [horizon_index(h, interval) for h in horizons]
        for baseline in build_baselines(
            meta.lookback_steps, meta.horizon_steps, cols, seed=args.seed, device=str(device),
            epochs=args.baseline_epochs, patience=args.baseline_patience,
            svr_max_train=args.svr_max_train,
        ):
            start = time.perf_counter()
            baseline.fit(train_w, val_w)
            pred_mg = data.glucose_norm.inverse_transform(baseline.predict(test_w))
            per_patient[baseline.name] = metrics_at_horizons(
                test_w.target_mg_dl, pred_mg, test_w.patient_id, interval, horizons
            )
            kinds[baseline.name] = "baseline"
            info: dict[str, Any] = {"fit_seconds": round(time.perf_counter() - start, 1)}
            if hasattr(baseline, "epochs_run"):
                info["epochs_run"] = baseline.epochs_run
            baseline_info[baseline.name] = info
            log.info("%s done in %.1fs", baseline.name, info["fit_seconds"])
        notes += [
            f"Baselines trained on the same {len(train_w)} train / {len(val_w)} val windows;"
            " LR/SVR/XGBoost are single-horizon (one model per horizon) on look-back glucose"
            " + sin/cos time of day; LSTM/N-BEATS/N-HiTS are multi-horizon, trained with MSE"
            f" and early stopping on validation (patience {args.baseline_patience}).",
            f"SVR is fit on a seeded uniform subsample of at most {args.svr_max_train}"
            " training windows (kernel SVR scales quadratically).",
        ]

    candidates = [n for n, k in kinds.items() if k == "baseline"] or [
        n for n, k in kinds.items() if k == "ablation"
    ]
    lookback_steps = meta.lookback_steps
    results: dict[str, Any] = {
        "artifact": meta.version,
        "dataset": meta.dataset,
        "interval_min": interval,
        "horizons_min": horizons,
        "n_test_windows": len(test_w),
        "n_test_patients": int(len(set(test_w.patient_id.tolist()))),
        "data_hash_matches": hash_ok,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "methods": {
            name: {
                "kind": kinds[name],
                "summary": summary_dict(frame),
                "by_type": _by_type(frame, types),
                "per_patient": frame.to_dict("records"),
            }
            | ({"artifact": str(artifacts[name])} if name in artifacts else {})
            | ({"training": baseline_info[name]} if name in baseline_info else {})
            for name, frame in per_patient.items()
        },
        "significance": _significance(per_patient, candidates, horizons),
        "explain": {
            "encoder_vsn_importance": variable_importance(out.encoder_vsn),
            "encoder_vsn_by_step": {
                str(k): v for k, v in importance_by_step(out.encoder_vsn, interval).items()
            },
            "attention_by_position": {
                str(k): v
                for k, v in attention_by_position(out.attention, lookback_steps, interval).items()
            },
        },
        "notes": notes,
    }
    return results


def _store_in_meta(path: Path, key: str, value: Any) -> None:
    meta = ModelMeta.model_validate_json((path / "meta.json").read_text())
    update_meta(path, metrics={**meta.metrics, key: value})


def write_evaluation(results: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(results, indent=2, default=str))
    (out_dir / "report.md").write_text(render_report(results))
    for name, m in results["methods"].items():
        if "artifact" not in m:
            continue
        compact = {
            "evaluated_at": results["evaluated_at"],
            "report": str(out_dir / "report.md"),
            "summary": m["summary"],
        }
        if name == MAIN:
            compact["significance"] = results["significance"]
        _store_in_meta(Path(m["artifact"]), "test", compact)
    log.info("wrote %s", out_dir)


def cross_validate(args: argparse.Namespace) -> dict[str, Any]:
    _, meta = load_artifact(args.artifact)
    data, _ = load_for_artifact(meta, args.data_root, args.ohio_profiles)
    tc = meta.train_config
    horizons = [h for h in settings.model.horizons_min if h <= meta.horizon_min]
    cv = run_cv(
        data,
        meta,
        args.cv,
        horizons,
        epochs=args.cv_epochs or int(tc.get("epochs", 200)),
        patience=args.cv_patience or int(tc.get("patience", 20)),
        lr=float(tc.get("lr", 1e-3)),
        batch_size=int(tc.get("batch_size", 256)),
        seed=args.seed,
        device=args.device,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cv.json").write_text(json.dumps(cv, indent=2, default=str))
    (args.out / "cv.md").write_text(render_cv_report(cv))
    _store_in_meta(
        Path(args.artifact),
        "cross_individual_cv",
        {k: cv[k] for k in ("n_folds", "seed", "mean_of_fold_means", "pooled", "train_config")},
    )
    return cv


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--artifact", type=Path, required=True)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--ohio-profiles", type=Path, default=None)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--baselines", action="store_true", help="train and evaluate the baselines")
    p.add_argument("--ablation-artifacts", type=Path, nargs="*", default=[])
    p.add_argument("--baseline-epochs", type=int, default=100)
    p.add_argument("--baseline-patience", type=int, default=10)
    p.add_argument("--svr-max-train", type=int, default=10_000)
    p.add_argument("--cv", type=int, default=0, help="run K-fold cross-individual CV instead")
    p.add_argument("--cv-epochs", type=int, default=0, help="default: artifact's training epochs")
    p.add_argument("--cv-patience", type=int, default=0, help="default: artifact's patience")
    p.add_argument("--batch-size", type=int, default=1024)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="auto")
    return p


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    if args.cv:
        cross_validate(args)
    else:
        write_evaluation(evaluate(args), args.out)


if __name__ == "__main__":
    main()
