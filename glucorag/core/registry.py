"""Versioned model artifacts: weights + everything needed to reproduce inference.

Layout: ``<root>/<version>/{model.pt, meta.json}``. ``meta.json`` pins normalization
statistics, static encoding, window geometry, quantiles, hyperparameters, data hash and
the SHA-256 of the weights file (verified on load).
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from pydantic import BaseModel, Field

from glucorag.models.tft.tft import EPSTFT
from glucorag.preprocess.normalize import StaticEncoder, ZNormalizer

WEIGHTS = "model.pt"
META = "meta.json"


class ModelMeta(BaseModel):
    version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    dataset: str
    interval_min: int
    lookback_min: int
    horizon_min: int
    quantiles: list[float]
    d_model: int
    num_heads: int
    dropout: float
    use_static: bool = True
    use_decoder: bool = True
    static_encoder: dict[str, Any]
    glucose_norm: dict[str, float]
    data_hash: str
    train_config: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    weights_sha256: str = ""

    @property
    def lookback_steps(self) -> int:
        return self.lookback_min // self.interval_min

    @property
    def horizon_steps(self) -> int:
        return self.horizon_min // self.interval_min

    def build_model(self) -> EPSTFT:
        return EPSTFT(
            static_size=len(self.static_encoder["features"]),
            d_model=self.d_model,
            num_heads=self.num_heads,
            num_quantiles=len(self.quantiles),
            dropout=self.dropout,
            use_static=self.use_static,
            use_decoder=self.use_decoder,
        )

    def glucose_normalizer(self) -> ZNormalizer:
        return ZNormalizer.from_dict(self.glucose_norm)

    def encoder(self) -> StaticEncoder:
        return StaticEncoder.from_dict(self.static_encoder)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_version(dataset: str) -> str:
    return f"{dataset}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"


def save_artifact(root: str | Path, model: EPSTFT, meta: ModelMeta) -> Path:
    out = Path(root) / meta.version
    out.mkdir(parents=True, exist_ok=False)
    weights = out / WEIGHTS
    torch.save(model.state_dict(), weights)
    meta.weights_sha256 = _sha256(weights)
    (out / META).write_text(meta.model_dump_json(indent=2))
    return out


def update_meta(path: str | Path, **fields: Any) -> ModelMeta:
    """Merge fields (e.g. evaluation ``metrics``) into a saved artifact's metadata."""
    meta_path = Path(path) / META
    meta = ModelMeta.model_validate_json(meta_path.read_text())
    meta = meta.model_copy(update=fields)
    meta_path.write_text(meta.model_dump_json(indent=2))
    return meta


def load_artifact(path: str | Path, device: str | torch.device = "cpu") -> tuple[EPSTFT, ModelMeta]:
    path = Path(path)
    meta = ModelMeta.model_validate_json((path / META).read_text())
    weights = path / WEIGHTS
    if _sha256(weights) != meta.weights_sha256:
        raise ValueError(f"Weights checksum mismatch for {path}")
    model = meta.build_model()
    model.load_state_dict(torch.load(weights, map_location=device, weights_only=True))
    model.to(device).eval()
    return model, meta


def resolve_artifact(path: str | Path) -> Path:
    """Accept an artifact dir, or a registry root whose ``CURRENT`` names the promoted one."""
    path = Path(path)
    pointer = path / "CURRENT"
    if pointer.is_file():
        return path / pointer.read_text().strip()
    return path


def latest_artifact(root: str | Path, dataset: str | None = None) -> Path:
    candidates = [
        p for p in Path(root).iterdir() if (p / META).is_file()
        and (dataset is None or p.name.startswith(f"{dataset}-"))
    ]
    if not candidates:
        raise FileNotFoundError(f"No model artifacts under {root}")
    return max(candidates, key=lambda p: json.loads((p / META).read_text())["created_at"])


def hash_frame_bytes(*chunks: bytes) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
    return h.hexdigest()[:16]
