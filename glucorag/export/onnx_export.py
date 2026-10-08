"""Export a model artifact to ONNX for the phone, with the metadata its preprocessing needs.

``glucorag-export-onnx --model models/shanghai-v1 --out android/phone/src/main/assets/model/``
writes:

* ``model.onnx`` – the whole EPS-TFT, static covariate encoder included. Inputs ``static``
  (1, S) encoded profile, ``x_enc`` (1, L, 2) ``[glucose_z, time_norm]`` and ``x_dec``
  (1, H, 1) ``[time_norm]``; output ``quantiles`` (1, H, Q) in normalized glucose units.
* ``meta.json`` – window geometry, quantiles, glucose z-normalization, the static encoding rule
  (categorical codes and continuous statistics, as ``StaticEncoder``) and the imputation limits
  ``ForecastEngine.build_inputs`` uses.

``--parity PATH`` also writes fixtures: raw readings, profile, the inputs ``build_inputs``
builds and the ``ForecastEngine.predict`` output, so an on-device port can prove it matches.
"""

import argparse
import json
import warnings
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import torch

from glucorag.core.registry import ModelMeta, load_artifact, resolve_artifact
from glucorag.inference.engine import _PAD_SLOTS, DataGapError, ForecastEngine, Reading
from glucorag.models.tft.tft import EPSTFT
from glucorag.preprocess.impute import SENSOR_MAX_MG_DL, SENSOR_MIN_MG_DL
from glucorag.preprocess.normalize import CATEGORICAL_CODES

MODEL_FILE = "model.onnx"
META_FILE = "meta.json"
INPUTS = ("static", "x_enc", "x_dec")
OUTPUT = "quantiles"
# Opset 17 runs on every ONNX Runtime release since 1.14, Android included.
OPSET = 17
DEFAULT_MAX_GAP_MIN = 60


class _Exported(torch.nn.Module):
    """``EPSTFT.forward`` without the interpretation tensors."""

    def __init__(self, model: EPSTFT) -> None:
        super().__init__()
        self.model = model

    def forward(
        self, static: torch.Tensor, x_enc: torch.Tensor, x_dec: torch.Tensor
    ) -> torch.Tensor:
        return self.model(static, x_enc, x_dec)[0]


def max_gap_min(meta: ModelMeta) -> int:
    """The imputation limit the model was trained (and is served) with."""
    return int(meta.train_config.get("max_gap_min", DEFAULT_MAX_GAP_MIN))


def device_meta(meta: ModelMeta) -> dict[str, Any]:
    """Everything the phone needs besides the graph to reproduce ``ForecastEngine.predict``."""
    features = list(meta.static_encoder["features"])
    stats = meta.static_encoder["stats"]
    return {
        "version": meta.version,
        "interval_min": meta.interval_min,
        "lookback_steps": meta.lookback_steps,
        "horizon_steps": meta.horizon_steps,
        "max_gap_min": max_gap_min(meta),
        "pad_slots": _PAD_SLOTS,
        "quantiles": list(meta.quantiles),
        "glucose_norm": {k: float(v) for k, v in meta.glucose_norm.items()},
        "sensor_range_mg_dl": [SENSOR_MIN_MG_DL, SENSOR_MAX_MG_DL],
        # Feature i of the static input: categorical features map through their codes,
        # continuous ones are z-normalized with the training statistics.
        "static_encoder": {
            "features": features,
            "categorical": {f: CATEGORICAL_CODES[f] for f in features if f in CATEGORICAL_CODES},
            "continuous": {
                f: {"mu": float(stats[f]["mu"]), "sigma": float(stats[f]["sigma"])}
                for f in features if f not in CATEGORICAL_CODES
            },
        },
        "inputs": list(INPUTS),
        "output": OUTPUT,
        "source_weights_sha256": meta.weights_sha256,
    }


def export(artifact: str | Path, out_dir: str | Path) -> tuple[Path, Path]:
    """Write ``model.onnx`` and ``meta.json`` for ``artifact`` into ``out_dir``."""
    model, meta = load_artifact(resolve_artifact(artifact))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    example = (
        torch.zeros(1, len(meta.static_encoder["features"])),
        torch.zeros(1, meta.lookback_steps, 2),
        torch.zeros(1, meta.horizon_steps, 1),
    )
    onnx_path = out / MODEL_FILE
    with warnings.catch_warnings():
        # The TorchScript exporter writes one self-contained file (the dynamo exporter splits
        # weights into external data, which an app asset can't reference); batch is fixed at 1.
        warnings.simplefilter("ignore")
        torch.onnx.export(
            _Exported(model).eval(),
            example,
            str(onnx_path),
            input_names=list(INPUTS),
            output_names=[OUTPUT],
            opset_version=OPSET,
            dynamo=False,
        )
    meta_path = out / META_FILE
    meta_path.write_text(json.dumps(device_meta(meta), indent=2) + "\n")
    return onnx_path, meta_path


# Parity fixtures ---------------------------------------------------------------------------

_PROFILES = {
    "t1d_f": {"gender": "F", "age": 34, "bmi": 22.1, "diabetes_type": "T1D"},
    "t1d_m": {"gender": "M", "age": 19, "bmi": 20.4, "diabetes_type": "T1D"},
    "t2d_m": {"gender": "M", "age": 63, "bmi": 27.6, "diabetes_type": "T2D"},
    "t2d_f": {"gender": "F", "age": 71, "bmi": 31.2, "diabetes_type": "T2D"},
}


def _feed(
    end: datetime, minutes: int, every_min: float, level: Any, rng: np.random.Generator,
    jitter_s: int = 0,
) -> list[tuple[datetime, float]]:
    """Readings every ``every_min`` over the ``minutes`` before ``end`` (inclusive)."""
    n = int(minutes // every_min)
    out = []
    for k in range(n, -1, -1):
        t = end - timedelta(minutes=k * every_min)
        if jitter_s and k:
            t += timedelta(seconds=int(rng.integers(-jitter_s, jitter_s + 1)))
        frac = 1 - k / n if n else 1.0
        out.append((t, round(float(level(frac) + rng.normal(0, 2.0)), 1)))
    return out


def _cases() -> list[tuple[str, str, list[tuple[datetime, float]]]]:
    rng = np.random.default_rng(7)
    day = datetime(2026, 10, 8)
    cases: list[tuple[str, str, list[tuple[datetime, float]]]] = []

    cases.append(("t1d_15min_steady", "t1d_f",
                  _feed(day.replace(hour=8), 180, 15, lambda f: 118, rng)))
    cases.append(("t2d_15min_rising", "t2d_m",
                  _feed(day.replace(hour=13, minute=30), 180, 15, lambda f: 150 + 70 * f, rng)))
    cases.append(("t1d_5min_dense_falling", "t1d_m",
                  _feed(day.replace(hour=16, minute=5), 210, 5, lambda f: 150 - 75 * f, rng)))
    cases.append(("t2d_5min_dense_high", "t2d_f",
                  _feed(day.replace(hour=19, minute=40), 210, 5,
                        lambda f: 235 + 25 * np.sin(6 * f), rng)))

    gap = _feed(day.replace(hour=10, minute=15), 180, 15, lambda f: 170 - 60 * f, rng)
    end = gap[-1][0]
    # Three missing readings (45 min) inside the look-back: filled by linear extrapolation.
    cases.append(("gap_45min_extrapolated", "t1d_f", [
        r for r in gap if not end - timedelta(minutes=75) <= r[0] <= end - timedelta(minutes=45)
    ]))
    edge = _feed(day.replace(hour=11), 180, 5, lambda f: 95 + 40 * f, rng)
    end = edge[-1][0]
    # 70 min without a reading: the grid misses 4 slots (60 min), the longest gap filled.
    cases.append(("gap_60min_edge_5min_feed", "t2d_m", [
        r for r in edge if not end - timedelta(minutes=95) <= r[0] <= end - timedelta(minutes=30)
    ]))
    long_gap = _feed(day.replace(hour=12), 180, 15, lambda f: 140, rng)
    end = long_gap[-1][0]
    cases.append(("gap_75min_data_gap", "t2d_f", [
        r for r in long_gap
        if not end - timedelta(minutes=90) <= r[0] <= end - timedelta(minutes=30)
    ]))

    jitter = _feed(day.replace(hour=6, minute=50, second=20), 180, 15, lambda f: 90 - 20 * f, rng,
                   jitter_s=40)
    t0 = jitter[-1][0]
    # Clear 25–65 min back, so only the tie readings below compete for those slots.
    jitter = [
        r for r in jitter
        if not t0 - timedelta(minutes=65) <= r[0] <= t0 - timedelta(minutes=25)
    ]
    jitter += [
        # Exactly half a step between two slots: fills only the newer one (the older stays
        # empty and is extrapolated).
        (t0 - timedelta(minutes=37, seconds=30), 77.7),
        # Two readings at the same distance from one slot: the later one wins.
        (t0 - timedelta(minutes=59), 81.1),
        (t0 - timedelta(minutes=61), 84.4),
    ]
    cases.append(("jitter_and_ties", "t1d_m", jitter))

    clipped = _feed(day.replace(hour=22, minute=15), 180, 15, lambda f: 300 + 120 * f, rng)
    clipped[-3] = (clipped[-3][0], 35.0)
    cases.append(("sensor_range_clipped", "t2d_m", clipped))

    cases.append(("one_min_feed_across_midnight", "t1d_f",
                  _feed(day.replace(hour=0, minute=20, second=45), 200, 1,
                        lambda f: 105 + 30 * np.cos(4 * f), rng)))
    cases.append(("warming_up_short_history", "t2d_f",
                  _feed(day.replace(hour=9), 75, 15, lambda f: 130, rng)))
    return cases


def parity_fixtures(artifact: str | Path) -> dict[str, Any]:
    """Raw readings (naive local wall time, as the server stores them) with the engine's
    inputs and quantile forecast (mg/dL, ``[horizon][quantile]``) or ``DataGap``."""
    model, meta = load_artifact(resolve_artifact(artifact))
    engine = ForecastEngine(model, meta, max_gap_min(meta))
    out: list[dict[str, Any]] = []
    for name, profile_key, readings in _cases():
        profile = _PROFILES[profile_key]
        history = [Reading(t, v) for t, v in readings]
        case: dict[str, Any] = {
            "name": name,
            "profile": profile,
            "readings": [[t.isoformat(), v] for t, v in sorted(readings)],
        }
        try:
            x_enc, x_dec, t0 = engine.build_inputs(history)
        except DataGapError:
            case["error"] = "DataGap"
        else:
            prediction = engine.predict("parity", engine.context_for(profile), history)
            case |= {
                "t0": t0.isoformat(),
                "static": engine.static_encoder.encode_one(profile).tolist(),
                "x_enc": x_enc.tolist(),
                "x_dec": x_dec.tolist(),
                "values": prediction.values,
            }
        out.append(case)
    return {
        "model_version": meta.version,
        "horizons": [meta.interval_min * (i + 1) for i in range(meta.horizon_steps)],
        "quantiles": list(meta.quantiles),
        "cases": out,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export a model artifact to ONNX for the phone.")
    parser.add_argument("--model", required=True, help="artifact dir or registry root")
    parser.add_argument("--out", required=True, help="directory for model.onnx and meta.json")
    parser.add_argument("--parity", help="also write parity fixtures (JSON) to this file")
    args = parser.parse_args(argv)
    onnx_path, meta_path = export(args.model, args.out)
    print(f"Wrote {onnx_path} ({onnx_path.stat().st_size} bytes) and {meta_path}")
    if args.parity:
        parity = Path(args.parity)
        parity.parent.mkdir(parents=True, exist_ok=True)
        parity.write_text(json.dumps(parity_fixtures(args.model), indent=1) + "\n")
        print(f"Wrote {parity}")


if __name__ == "__main__":
    main()
