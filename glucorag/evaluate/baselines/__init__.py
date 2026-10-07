"""Baseline forecasters of the paper's Tables I/II, trained on the same windows as EPS-TFT.

Every baseline exposes ``fit(train, val)`` and ``predict(windows) -> (N, H)`` forecasts in
z-normalized glucose units (same scale as ``Windows.target_z``). Single-horizon models
(LR, SVR, XGBoost) fill only the columns of the horizons they were trained for and leave
the remaining columns NaN; multi-horizon networks (LSTM, N-BEATS, N-HiTS) fill all columns.
"""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt

from glucorag.evaluate.baselines.classical import LinearBaseline, SVRBaseline, XGBoostBaseline
from glucorag.evaluate.baselines.neural import LSTMForecaster, NBeats, NeuralForecaster, NHiTS
from glucorag.preprocess.windows import Windows


class Baseline(Protocol):
    name: str

    def fit(self, train: Windows, val: Windows) -> None: ...

    def predict(self, windows: Windows) -> npt.NDArray[np.float32]: ...


def build_baselines(
    lookback_steps: int,
    horizon_steps: int,
    single_horizon_columns: Sequence[int],
    seed: int = 0,
    device: str = "cpu",
    epochs: int = 100,
    patience: int = 10,
    svr_max_train: int = 10_000,
) -> list[Baseline]:
    """The six baselines of the paper in table order."""
    cols = list(single_horizon_columns)
    common = {"horizon_steps": horizon_steps, "seed": seed, "device": device,
              "epochs": epochs, "patience": patience}
    return [
        LinearBaseline(horizon_steps, cols),
        SVRBaseline(horizon_steps, cols, max_train=svr_max_train, seed=seed),
        XGBoostBaseline(horizon_steps, cols, seed=seed),
        NeuralForecaster("LSTM", lambda: LSTMForecaster(horizon_steps), **common),
        NeuralForecaster("N-BEATS", lambda: NBeats(lookback_steps, horizon_steps), **common),
        NeuralForecaster("N-HiTS", lambda: NHiTS(lookback_steps, horizon_steps), **common),
    ]


__all__ = ["Baseline", "build_baselines"]
