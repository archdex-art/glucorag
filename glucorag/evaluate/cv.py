"""Cross-individual K-fold validation of EPS-TFT (paper Discussion, ShanghaiDM).

Per fold: training patients keep their chronological train/val portions (validation drives
early stopping); held-out patients are scored on their full recordings. Normalizers and the
static encoder are refit on the fold's training data only.
"""

import logging
from collections.abc import Sequence
from typing import Any, cast

import numpy as np
import pandas as pd

from glucorag.core.config import settings
from glucorag.core.registry import ModelMeta
from glucorag.data.pipeline import PreparedData, make_windows
from glucorag.evaluate.metrics import metrics_at_horizons
from glucorag.evaluate.predict import predict_tft
from glucorag.evaluate.report import summary_dict
from glucorag.evaluate.stats import cross_individual_folds, patient_strata
from glucorag.preprocess.normalize import StaticEncoder, ZNormalizer
from glucorag.train.cli import loaders
from glucorag.train.trainer import resolve_device, seed_everything, train_model

log = logging.getLogger(__name__)


def _patients(frame: pd.DataFrame, ids: set[Any]) -> pd.DataFrame:
    return cast(pd.DataFrame, frame[frame["patient_id"].isin(list(ids))]).copy()


def fold_data(
    data: PreparedData, train_patients: Sequence[Any], test_patients: Sequence[Any]
) -> PreparedData:
    """Restrict ``data`` to a patient fold and refit normalization on its training split."""
    train_ids, test_ids = set(train_patients), set(test_patients)
    if train_ids & test_ids:
        raise ValueError("A patient cannot be in both the training and test folds")
    train = _patients(data.train, train_ids)
    val = _patients(data.val, train_ids)
    full = pd.concat([data.train, data.val, data.test], ignore_index=True)
    test = _patients(full, test_ids).sort_values(["series_id", "timestamp"], ignore_index=True)

    glucose_norm = ZNormalizer().fit(train["glucose_mg_dl"])
    train_series = data.profiles[data.profiles["series_id"].isin(list(set(train["series_id"])))]
    static_encoder = StaticEncoder(data.spec.static_features).fit(train_series)
    for part in (train, val, test):
        part["glucose_z"] = glucose_norm.transform(part["glucose_mg_dl"])
    return PreparedData(data.spec, train, val, test, data.profiles, glucose_norm, static_encoder)


def run_cv(
    data: PreparedData,
    meta: ModelMeta,
    n_folds: int,
    horizons_min: Sequence[int],
    epochs: int,
    patience: int,
    lr: float,
    batch_size: int,
    seed: int,
    device: str,
) -> dict[str, Any]:
    """Retrain EPS-TFT (``meta``'s architecture) per fold and score held-out patients."""
    cfg = settings.model
    if meta.lookback_min != cfg.lookback_min or meta.horizon_min != max(cfg.horizons_min):
        raise ValueError("CV reuses the training loaders, which follow settings.model geometry")
    dev = resolve_device(device)
    if "diabetes_type" in data.profiles.columns:
        strata = patient_strata(data.profiles)
    else:  # single-population datasets (OhioT1DM): plain K-fold over patients
        strata = pd.Series("all", index=sorted(data.profiles["patient_id"].unique()))
    folds = cross_individual_folds(strata, n_folds, seed)
    fold_results: list[dict[str, Any]] = []
    per_patient: list[pd.DataFrame] = []
    for k, (train_p, test_p) in enumerate(folds, start=1):
        log.info("CV fold %d/%d: %d train / %d test patients", k, n_folds, len(train_p),
                 len(test_p))
        seed_everything(seed)
        fd = fold_data(data, train_p, test_p)
        train_loader, val_loader = loaders(fd, batch_size, seed)
        model, history = train_model(
            meta.build_model(), train_loader, val_loader, dev, meta.quantiles, lr, epochs, patience
        )
        test_w, test_s = make_windows(fd, "test", meta.lookback_min, meta.horizon_min)
        out = predict_tft(model, test_w, test_s, fd.glucose_norm, meta.quantiles, device=dev)
        frame = metrics_at_horizons(
            test_w.target_mg_dl, out.median_mg_dl, test_w.patient_id, meta.interval_min,
            horizons_min,
        )
        frame.insert(0, "fold", k)
        per_patient.append(frame)
        fold_results.append(
            {
                "fold": k,
                "train_patients": train_p,
                "test_patients": test_p,
                "n_test_windows": len(test_w),
                "epochs_run": len(history["val_loss"]),
                "summary": summary_dict(frame.drop(columns="fold")),
            }
        )
        log.info("fold %d RMSE: %s", k, {h: fold_results[-1]["summary"][str(h)]["RMSE"]
                                         for h in horizons_min})
    pooled = pd.concat(per_patient, ignore_index=True)
    return {
        "artifact": meta.version,
        "dataset": meta.dataset,
        "n_folds": n_folds,
        "seed": seed,
        "horizons_min": list(horizons_min),
        "train_config": {"epochs": epochs, "patience": patience, "lr": lr,
                         "batch_size": batch_size},
        "folds": fold_results,
        "mean_of_fold_means": {
            str(h): float(np.mean([f["summary"][str(h)]["RMSE"]["mean"] for f in fold_results]))
            for h in horizons_min
        },
        "pooled": summary_dict(pooled.drop(columns="fold")),
        "per_patient": pooled.to_dict("records"),
    }
