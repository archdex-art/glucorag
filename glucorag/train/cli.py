"""Train EPS-TFT and register a versioned artifact.

    python -m glucorag.train.cli --dataset shanghai --data-root data/raw/shanghai
"""

import argparse
import logging
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from glucorag.core.config import settings
from glucorag.core.registry import ModelMeta, hash_frame_bytes, new_version, save_artifact
from glucorag.data.pipeline import PreparedData, load_dataset, make_windows, to_tensor_dataset
from glucorag.models.tft.tft import EPSTFT
from glucorag.train.trainer import resolve_device, seed_everything, train_model

log = logging.getLogger("glucorag.train")


def data_hash(data: PreparedData) -> str:
    chunks: list[bytes] = []
    for part in (data.train, data.val, data.test):
        chunks.append(part["timestamp"].astype("int64").to_numpy().tobytes())
        chunks.append(part["glucose_mg_dl"].to_numpy().tobytes())
    return hash_frame_bytes(*chunks)


def loaders(
    data: PreparedData, batch_size: int, seed: int
) -> tuple[DataLoader[Any], DataLoader[Any]]:
    cfg = settings.model
    horizon = max(cfg.horizons_min)
    train_w, train_s = make_windows(data, "train", cfg.lookback_min, horizon)
    val_w, val_s = make_windows(data, "val", cfg.lookback_min, horizon)
    log.info("windows: train=%d val=%d", len(train_w), len(val_w))
    gen = torch.Generator().manual_seed(seed)
    return (
        DataLoader(to_tensor_dataset(train_w, train_s), batch_size, shuffle=True, generator=gen),
        DataLoader(to_tensor_dataset(val_w, val_s), batch_size),
    )


def train(args: argparse.Namespace) -> Path:
    seed_everything(args.seed)
    device = resolve_device(args.device)
    cfg = settings.model
    data = load_dataset(args.dataset, args.data_root, args.max_gap_min, args.ohio_profiles)
    train_loader, val_loader = loaders(data, args.batch_size, args.seed)

    model = EPSTFT(
        static_size=len(data.spec.static_features),
        d_model=args.d_model,
        num_heads=args.heads,
        num_quantiles=len(cfg.quantiles),
        dropout=args.dropout,
        use_static=not args.no_static,
        use_decoder=not args.no_decoder,
    )
    model, history = train_model(
        model, train_loader, val_loader, device, cfg.quantiles, args.lr, args.epochs, args.patience
    )
    meta = ModelMeta(
        version=args.version or new_version(args.dataset),
        dataset=args.dataset,
        interval_min=data.spec.interval_min,
        lookback_min=cfg.lookback_min,
        horizon_min=max(cfg.horizons_min),
        quantiles=cfg.quantiles,
        d_model=args.d_model,
        num_heads=args.heads,
        dropout=args.dropout,
        use_static=not args.no_static,
        use_decoder=not args.no_decoder,
        static_encoder=data.static_encoder.to_dict(),
        glucose_norm=data.glucose_norm.to_dict(),
        data_hash=data_hash(data),
        train_config={
            k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()
        }
        | {"epochs_run": len(history["val_loss"]), "best_val_loss": min(history["val_loss"])},
    )
    out = save_artifact(args.models_dir, model.cpu(), meta)
    log.info("saved artifact %s", out)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", choices=["shanghai", "ohio"], required=True)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--ohio-profiles", type=Path, default=None)
    p.add_argument("--models-dir", type=Path, default=Path("models"))
    p.add_argument("--version", default=None)
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--patience", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--d-model", type=int, default=64)
    p.add_argument("--heads", type=int, default=4)
    p.add_argument("--dropout", type=float, default=0.1)
    p.add_argument("--max-gap-min", type=int, default=settings.alert_thresholds.data_gap_min)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="auto")
    p.add_argument("--no-static", action="store_true", help="ablation: drop covariate encoder")
    p.add_argument("--no-decoder", action="store_true", help="ablation: drop LSTM decoder")
    return p


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    train(build_parser().parse_args(argv))


if __name__ == "__main__":
    main()
