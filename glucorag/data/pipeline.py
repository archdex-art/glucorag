"""End-to-end data preparation shared by training, evaluation, and baselines."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch
from torch.utils.data import TensorDataset

from glucorag.data import ohio, shanghai
from glucorag.data.splits import create_shanghai_split, split_ohio_train
from glucorag.preprocess.impute import causal_linear_extrapolate
from glucorag.preprocess.normalize import StaticEncoder, ZNormalizer, normalize_timestamp
from glucorag.preprocess.resample import regularize
from glucorag.preprocess.windows import Windows, create_sliding_windows


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    interval_min: int
    static_features: tuple[str, ...]


SPECS: dict[str, DatasetSpec] = {
    "shanghai": DatasetSpec("shanghai", shanghai.INTERVAL_MIN, shanghai.STATIC_FEATURES),
    "ohio": DatasetSpec("ohio", ohio.INTERVAL_MIN, ohio.STATIC_FEATURES),
}


def minutes_to_steps(minutes: int, interval_min: int) -> int:
    if minutes % interval_min:
        raise ValueError(f"{minutes} min is not a multiple of the {interval_min}-min interval")
    return minutes // interval_min


def prepare_frame(cgm: pd.DataFrame, interval_min: int, max_gap_min: int) -> pd.DataFrame:
    """Regular grid -> causal imputation of gaps <= max_gap_min -> clip -> time-of-day."""
    df = regularize(cgm, interval_min)
    max_gap_steps = max_gap_min // interval_min
    df["glucose_mg_dl"] = df.groupby("series_id", sort=False)["glucose_mg_dl"].transform(
        lambda s: causal_linear_extrapolate(s, max_gap_steps=max_gap_steps)
    )
    df["time_norm"] = normalize_timestamp(df["timestamp"])
    return df


@dataclass
class PreparedData:
    spec: DatasetSpec
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    profiles: pd.DataFrame  # one row per series_id
    glucose_norm: ZNormalizer
    static_encoder: StaticEncoder


def load_dataset(
    name: str, data_root: str | Path, max_gap_min: int, ohio_profiles: str | Path | None = None
) -> PreparedData:
    """Load, prepare, split, and fit normalizers on the training split only."""
    spec = SPECS[name]
    if name == "shanghai":
        cgm, profiles = shanghai.load_shanghai(data_root)
        frame = prepare_frame(cgm, spec.interval_min, max_gap_min)
        train, val, test = create_shanghai_split(frame)
    elif name == "ohio":
        if ohio_profiles is None:
            raise ValueError("OhioT1DM needs a demographics CSV (patient_id,age,gender).")
        train_cgm, test_cgm, profiles = ohio.load_ohio(data_root, ohio_profiles)
        train_all = prepare_frame(train_cgm, spec.interval_min, max_gap_min)
        test = prepare_frame(test_cgm, spec.interval_min, max_gap_min)
        train, val = split_ohio_train(train_all)
    else:
        raise KeyError(name)

    glucose_norm = ZNormalizer().fit(train["glucose_mg_dl"])
    train_ids = set(train["series_id"])
    train_series = profiles[profiles["series_id"].map(lambda s: s in train_ids)]
    static_encoder = StaticEncoder(spec.static_features).fit(train_series)
    for part in (train, val, test):
        part["glucose_z"] = glucose_norm.transform(part["glucose_mg_dl"])
    return PreparedData(spec, train, val, test, profiles, glucose_norm, static_encoder)


def static_matrix(
    windows: Windows, profiles: pd.DataFrame, encoder: StaticEncoder
) -> npt.NDArray[np.float32]:
    """Static feature vector per window, looked up by series_id."""
    by_series = {
        row["series_id"]: encoder.encode_one(row) for row in profiles.to_dict("records")
    }
    if len(windows) == 0:
        return np.zeros((0, len(encoder.features)), np.float32)
    return np.stack([by_series[s] for s in windows.series_id]).astype(np.float32)


def make_windows(
    data: PreparedData,
    split: str,
    lookback_min: int,
    horizon_min: int,
    require_observed_target: bool | None = None,
) -> tuple[Windows, npt.NDArray[np.float32]]:
    """Windows + static matrix for ``split``; val/test score only on observed targets."""
    frame = {"train": data.train, "val": data.val, "test": data.test}[split]
    if require_observed_target is None:
        require_observed_target = split != "train"
    windows = create_sliding_windows(
        frame,
        minutes_to_steps(lookback_min, data.spec.interval_min),
        minutes_to_steps(horizon_min, data.spec.interval_min),
        require_observed_target=require_observed_target,
    )
    return windows, static_matrix(windows, data.profiles, data.static_encoder)


def to_tensor_dataset(windows: Windows, static: npt.NDArray[np.float32]) -> TensorDataset:
    """Tensors ordered as the trainer expects: (static, x_enc, x_dec, target_z)."""
    return TensorDataset(
        torch.from_numpy(static),
        torch.from_numpy(windows.x_enc),
        torch.from_numpy(windows.x_dec),
        torch.from_numpy(windows.target_z),
    )
