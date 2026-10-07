"""Out-of-process XGBoost fit/predict.

XGBoost (Homebrew libomp) and PyTorch (bundled libomp) load two different OpenMP runtimes;
in one process on macOS this segfaults or deadlocks as soon as both run parallel regions.
The XGBoost baseline therefore runs here, in a child interpreter that never imports torch:

    python -m glucorag.evaluate.xgb_worker fit <dir>      # x, y, xv, yv, params -> model.json
    python -m glucorag.evaluate.xgb_worker predict <dir>  # model.json, x -> pred.npy
"""

import json
import sys
from pathlib import Path

import numpy as np
from xgboost import XGBRegressor


def fit(work: Path) -> None:
    arrays = np.load(work / "train.npz")
    params = json.loads((work / "params.json").read_text())
    model = XGBRegressor(**params)
    model.fit(arrays["x"], arrays["y"], eval_set=[(arrays["xv"], arrays["yv"])], verbose=False)
    model.save_model(work / "model.json")


def predict(work: Path) -> None:
    model = XGBRegressor()
    model.load_model(work / "model.json")
    np.save(work / "pred.npy", model.predict(np.load(work / "x.npy")).astype(np.float32))


def main(argv: list[str]) -> None:
    mode, work = argv[0], Path(argv[1])
    {"fit": fit, "predict": predict}[mode](work)


if __name__ == "__main__":
    main(sys.argv[1:])
