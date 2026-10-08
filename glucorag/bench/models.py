"""Zero-shot forecasters for the benchmark: a persistence reference and pretrained TSFMs.

The foundation models need the optional ``bench`` extra (``chronos-forecasting``,
``timesfm[torch]``); their imports are deferred so the CLI loads without it. Weights are pinned
to the Hugging Face revisions benchmarked in ``reports/benchmark``. Every forecaster returns the
0.5 quantile as point forecast plus the 0.1/0.9 quantiles, all native to each model.
"""

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
import torch

from glucorag.bench.protocol import LOWER, MEDIAN, UPPER, FloatArray, Forecast

Family = Literal["persistence", "chronos", "timesfm-2.5", "timesfm-3"]
LEVELS = [LOWER, MEDIAN, UPPER]


@dataclass(frozen=True)
class ModelSpec:
    key: str  # CLI name
    label: str  # report name
    family: Family
    model_id: str | None = None
    revision: str | None = None
    licence: str = "n/a"


SPECS: dict[str, ModelSpec] = {
    s.key: s
    for s in (
        ModelSpec("persistence", "Persistence (last value)", "persistence"),
        ModelSpec(
            "chronos-bolt-small", "Chronos-Bolt small", "chronos", "amazon/chronos-bolt-small",
            "772f3d25d38aec6d914c8949dab4462e2d46f5d8", "Apache-2.0",
        ),
        ModelSpec(
            "chronos-bolt-base", "Chronos-Bolt base", "chronos", "amazon/chronos-bolt-base",
            "5d9f166d69f47aef3401367a7b842e78fe97b121", "Apache-2.0",
        ),
        ModelSpec(
            "chronos-2", "Chronos-2", "chronos", "amazon/chronos-2",
            "29ec3766d36d6f73f0696f85560a422f50e8498c", "Apache-2.0",
        ),
        ModelSpec(
            "timesfm-2.5", "TimesFM 2.5", "timesfm-2.5", "google/timesfm-2.5-200m-pytorch",
            "1d952420fba87f3c6dee4f240de0f1a0fbc790e3", "Apache-2.0",
        ),
        ModelSpec(
            "timesfm-3.0", "TimesFM 3.0", "timesfm-3", "google/timesfm-3.0-pytorch",
            "43046b85ec22d584a13f8098c2ed39c889e129c2",
            "TimesFM Non-Commercial License v1.0 (research/benchmarking only)",
        ),
    )
}


class Forecaster(Protocol):
    n_params: int

    def predict(self, contexts: Sequence[FloatArray], horizon_steps: int) -> Forecast: ...


def _batches(items: Sequence[FloatArray], size: int) -> Iterator[Sequence[FloatArray]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _n_params(module: torch.nn.Module) -> int:
    return sum(p.numel() for p in module.parameters())


def _from_levels(q: np.ndarray, levels: Sequence[float]) -> Forecast:
    """(N, H, Q) quantiles at ``levels`` -> Forecast with the 0.1/0.5/0.9 columns."""
    lo, mid, hi = (levels.index(x) for x in LEVELS)
    q = q.astype(np.float32)
    return Forecast(median=q[..., mid], lower=q[..., lo], upper=q[..., hi])


class Persistence:
    """Last observed value carried forward (no interval)."""

    n_params = 0

    def predict(self, contexts: Sequence[FloatArray], horizon_steps: int) -> Forecast:
        last = np.array([c[-1] for c in contexts], dtype=np.float32)
        return Forecast(median=np.repeat(last[:, None], horizon_steps, axis=1))


class Chronos:
    """Chronos-Bolt and Chronos-2 through ``BaseChronosPipeline`` (univariate, no covariates)."""

    def __init__(self, spec: ModelSpec, device: str, batch_size: int) -> None:
        from chronos import BaseChronosPipeline

        self.pipeline = BaseChronosPipeline.from_pretrained(
            spec.model_id, revision=spec.revision, device_map=device, dtype=torch.float32
        )
        self.batch_size = batch_size
        self.n_params = _n_params(self.pipeline.model)

    def predict(self, contexts: Sequence[FloatArray], horizon_steps: int) -> Forecast:
        parts: list[np.ndarray] = []
        for chunk in _batches(contexts, self.batch_size):
            q, _ = self.pipeline.predict_quantiles(
                [torch.from_numpy(c) for c in chunk],
                prediction_length=horizon_steps,
                quantile_levels=LEVELS,
            )
            # Chronos-Bolt returns one (B, H, Q) tensor, Chronos-2 a list of (1, H, Q).
            q = torch.cat(list(q)) if isinstance(q, list) else q
            parts.append(q.float().cpu().numpy())
        return _from_levels(np.concatenate(parts), LEVELS)


class TimesFM25:
    """TimesFM 2.5 (200M) with the decoding flags recommended in its README."""

    # Output index 0 is the mean; 1..9 are the 0.1..0.9 quantiles.
    LEVELS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

    def __init__(self, spec: ModelSpec, device: str, batch_size: int) -> None:
        import timesfm

        self.timesfm = timesfm
        self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
            spec.model_id, revision=spec.revision, torch_compile=False
        )
        # The torch module only auto-selects CUDA; move it explicitly for cpu/mps.
        self.model.model.to(device)
        self.model.model.device = torch.device(device)
        self.batch_size = batch_size
        self.n_params = _n_params(self.model.model)

    def predict(self, contexts: Sequence[FloatArray], horizon_steps: int) -> Forecast:
        patch = self.model.model.p
        max_context = math.ceil(max(len(c) for c in contexts) / patch) * patch
        self.model.compile(
            self.timesfm.ForecastConfig(
                max_context=max_context,
                max_horizon=self.model.model.o,
                per_core_batch_size=self.batch_size,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                force_flip_invariance=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
            )
        )
        # ``forecast`` pads its input list in place, so hand it a copy.
        _, q = self.model.forecast(horizon_steps, list(contexts))
        return _from_levels(np.asarray(q)[..., 1:], self.LEVELS)


class TimesFM3:
    """TimesFM 3.0, univariate, default forecaster settings."""

    def __init__(self, spec: ModelSpec, device: str, batch_size: int) -> None:
        from timesfm3 import TimesFM3Forecaster

        self.forecaster = TimesFM3Forecaster.from_pretrained(
            spec.model_id, device=device, revision=spec.revision, per_core_batch_size=batch_size
        )
        self.n_params = _n_params(self.forecaster.model)

    def predict(self, contexts: Sequence[FloatArray], horizon_steps: int) -> Forecast:
        outputs = self.forecaster.predict_batch(
            list(contexts), horizon=horizon_steps, return_quantiles=True
        )
        q = np.stack([np.asarray(o.quantiles) for o in outputs])
        return _from_levels(q, list(self.forecaster.config.quantiles))


def load_forecaster(spec: ModelSpec, device: str, batch_size: int) -> Forecaster:
    match spec.family:
        case "persistence":
            return Persistence()
        case "chronos":
            return Chronos(spec, device, batch_size)
        case "timesfm-2.5":
            return TimesFM25(spec, device, batch_size)
        case "timesfm-3":
            return TimesFM3(spec, device, batch_size)
