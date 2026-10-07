"""Single-horizon regressors (LR, SVR, XGBoost): one model per prediction horizon.

Features are the look-back glucose values (z-normalized) plus a cyclic encoding
(sin, cos) of the time of day at the forecast origin.
"""

import json
import logging
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from sklearn.linear_model import LinearRegression
from sklearn.svm import SVR

from glucorag.preprocess.windows import Windows

log = logging.getLogger(__name__)

FloatArray = npt.NDArray[np.float32]


def window_features(windows: Windows) -> FloatArray:
    """``(N, L + 2)``: look-back glucose_z and sin/cos of the origin's time of day."""
    angle = 2.0 * np.pi * windows.x_enc[:, -1, 1]
    return np.concatenate(
        [windows.x_enc[:, :, 0], np.sin(angle)[:, None], np.cos(angle)[:, None]], axis=1
    ).astype(np.float32)


class _SingleHorizon(ABC):
    """Fits an independent regressor for each requested forecast column."""

    name = ""

    def __init__(self, horizon_steps: int, columns: Sequence[int]) -> None:
        if not columns or min(columns) < 0 or max(columns) >= horizon_steps:
            raise ValueError(f"columns {list(columns)} outside 0..{horizon_steps - 1}")
        self.horizon_steps = horizon_steps
        self.columns = list(columns)
        self.models: dict[int, Any] = {}

    @abstractmethod
    def _make(self) -> Any: ...

    def _fit_one(
        self, model: Any, x: FloatArray, y: FloatArray, xv: FloatArray, yv: FloatArray
    ) -> None:
        model.fit(x, y)

    def _training_rows(self, n: int) -> npt.NDArray[np.int64]:
        return np.arange(n)

    def fit(self, train: Windows, val: Windows) -> None:
        x, xv = window_features(train), window_features(val)
        rows = self._training_rows(len(x))
        for col in self.columns:
            model = self._make()
            self._fit_one(model, x[rows], train.target_z[rows, col], xv, val.target_z[:, col])
            self.models[col] = model

    def predict(self, windows: Windows) -> FloatArray:
        out = np.full((len(windows), self.horizon_steps), np.nan, dtype=np.float32)
        x = window_features(windows)
        for col, model in self.models.items():
            out[:, col] = model.predict(x)
        return out


class LinearBaseline(_SingleHorizon):
    name = "LR"

    def _make(self) -> Any:
        return LinearRegression()


class SVRBaseline(_SingleHorizon):
    """RBF-kernel SVR. Kernel SVR training is O(n^2) in memory/time, so at most ``max_train``
    training windows are used, drawn uniformly without replacement with a fixed seed."""

    name = "SVR"

    def __init__(
        self, horizon_steps: int, columns: Sequence[int], max_train: int = 10_000, seed: int = 0
    ) -> None:
        super().__init__(horizon_steps, columns)
        self.max_train = max_train
        self.seed = seed

    def _make(self) -> Any:
        return SVR(kernel="rbf", C=1.0, epsilon=0.1, gamma="scale", cache_size=1000)

    def _training_rows(self, n: int) -> npt.NDArray[np.int64]:
        if n <= self.max_train:
            return np.arange(n)
        log.info("SVR: subsampling %d of %d training windows", self.max_train, n)
        rng = np.random.default_rng(self.seed)
        return np.sort(rng.choice(n, size=self.max_train, replace=False))


class _IsolatedXGBRegressor:
    """XGBRegressor fitted and applied in a torch-free child process (see ``xgb_worker``);
    the trained booster is kept in memory as XGBoost JSON."""

    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
        self.booster_json: str | None = None

    @staticmethod
    def _run(mode: str, work: Path) -> None:
        subprocess.run(
            [sys.executable, "-m", "glucorag.evaluate.xgb_worker", mode, str(work)], check=True
        )

    def fit(self, x: FloatArray, y: FloatArray, xv: FloatArray, yv: FloatArray) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            np.savez(work / "train.npz", x=x, y=y, xv=xv, yv=yv)
            (work / "params.json").write_text(json.dumps(self.params))
            self._run("fit", work)
            self.booster_json = (work / "model.json").read_text()

    def predict(self, x: FloatArray) -> FloatArray:
        if self.booster_json is None:
            raise RuntimeError("XGBoost model is not fitted")
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "model.json").write_text(self.booster_json)
            np.save(work / "x.npy", x)
            self._run("predict", work)
            return np.load(work / "pred.npy")


class XGBoostBaseline(_SingleHorizon):
    """Gradient-boosted trees with early stopping on the validation windows."""

    name = "XGBoost"

    def __init__(self, horizon_steps: int, columns: Sequence[int], seed: int = 0) -> None:
        super().__init__(horizon_steps, columns)
        self.seed = seed

    def _make(self) -> Any:
        return _IsolatedXGBRegressor(
            {
                "n_estimators": 1000,
                "learning_rate": 0.05,
                "max_depth": 6,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "early_stopping_rounds": 30,
                "random_state": self.seed,
                "n_jobs": -1,
            }
        )

    def _fit_one(
        self, model: Any, x: FloatArray, y: FloatArray, xv: FloatArray, yv: FloatArray
    ) -> None:
        model.fit(x, y, xv, yv)
