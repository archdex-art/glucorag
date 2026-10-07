"""Feature normalization fitted on training data only."""

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd


class ZNormalizer:
    def __init__(self, mu: float = 0.0, sigma: float = 1.0, is_fitted: bool = False) -> None:
        self.mu = mu
        self.sigma = sigma
        self.is_fitted = is_fitted

    def fit(self, series: Any) -> "ZNormalizer":
        """Fit on any 1-D array-like (Series, ndarray); NaNs are ignored."""
        values = np.asarray(series, dtype=float)
        values = values[~np.isnan(values)]
        if values.size == 0:
            raise ValueError("Cannot fit ZNormalizer on an empty/all-NaN series.")
        self.mu = float(values.mean())
        sigma = float(values.std())
        self.sigma = sigma if sigma > 0 else 1.0
        self.is_fitted = True
        return self

    def _check(self) -> None:
        if not self.is_fitted:
            raise RuntimeError("ZNormalizer is not fitted yet.")

    def transform(self, x: Any) -> Any:
        self._check()
        return (x - self.mu) / self.sigma

    def inverse_transform(self, x: Any) -> Any:
        self._check()
        return x * self.sigma + self.mu

    def to_dict(self) -> dict[str, float]:
        self._check()
        return {"mu": self.mu, "sigma": self.sigma}

    @classmethod
    def from_dict(cls, d: Mapping[str, float]) -> "ZNormalizer":
        return cls(mu=float(d["mu"]), sigma=float(d["sigma"]), is_fitted=True)


def normalize_timestamp(times: Any) -> pd.Series:
    """Map time of day onto [0, 1) over a 24 h cycle."""
    minutes = times.dt.hour * 60 + times.dt.minute + times.dt.second / 60.0
    return minutes / (24.0 * 60.0)


CATEGORICAL_CODES: dict[str, dict[str, float]] = {
    "gender": {"F": 0.0, "M": 1.0},
    "diabetes_type": {"T1D": 0.0, "T2D": 1.0},
}
CONTINUOUS = ("age", "bmi")


class StaticEncoder:
    """Encode demographic profiles into the model's static input vector.

    Categorical features map to {0, 1}; continuous features are z-normalized with
    training statistics.
    """

    def __init__(
        self, features: Sequence[str], stats: Mapping[str, Mapping[str, float]] | None = None
    ) -> None:
        unknown = set(features) - set(CATEGORICAL_CODES) - set(CONTINUOUS)
        if unknown:
            raise ValueError(f"Unsupported static features: {sorted(unknown)}")
        self.features = list(features)
        self.stats: dict[str, ZNormalizer] = {
            k: ZNormalizer.from_dict(v) for k, v in (stats or {}).items()
        }

    def fit(self, profiles: Any) -> "StaticEncoder":
        for f in self.features:
            if f in CONTINUOUS:
                self.stats[f] = ZNormalizer().fit(profiles[f].astype(float))
        return self

    def encode_one(self, profile: Mapping[str, Any]) -> npt.NDArray[np.float32]:
        out = np.empty(len(self.features), dtype=np.float32)
        for i, f in enumerate(self.features):
            value = profile.get(f)
            if value is None or (isinstance(value, float) and np.isnan(value)):
                raise ValueError(f"Profile is missing static feature '{f}'")
            if f in CATEGORICAL_CODES:
                codes = CATEGORICAL_CODES[f]
                if value not in codes:
                    raise ValueError(f"Invalid {f}={value!r}; expected one of {list(codes)}")
                out[i] = codes[value]
            else:
                out[i] = float(self.stats[f].transform(float(value)))
        return out

    def encode_frame(self, profiles: pd.DataFrame) -> npt.NDArray[np.float32]:
        return np.stack([self.encode_one(row) for row in profiles.to_dict("records")])

    def to_dict(self) -> dict[str, Any]:
        return {"features": self.features, "stats": {k: v.to_dict() for k, v in self.stats.items()}}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "StaticEncoder":
        return cls(d["features"], d["stats"])
