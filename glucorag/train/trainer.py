"""Training loop: Adam on quantile loss with early stopping on validation loss."""

import copy
import logging
import random
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from glucorag.models.tft.quantile import QuantileLoss
from glucorag.models.tft.tft import EPSTFT

log = logging.getLogger(__name__)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def resolve_device(name: str = "auto") -> torch.device:
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _run_epoch(
    model: EPSTFT,
    loader: DataLoader[Any],
    loss_fn: QuantileLoss,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
) -> float:
    training = optimizer is not None
    model.train(training)
    total, count = 0.0, 0
    with torch.set_grad_enabled(training):
        for static, x_enc, x_dec, target in loader:
            static, x_enc, x_dec, target = (
                t.to(device) for t in (static, x_enc, x_dec, target)
            )
            preds, _ = model(static, x_enc, x_dec)
            loss = loss_fn(preds, target)
            if optimizer is not None:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total += loss.item() * static.size(0)
            count += static.size(0)
    if count == 0:
        raise ValueError("Empty data loader")
    return total / count


def train_epoch(
    model: EPSTFT,
    loader: DataLoader[Any],
    optimizer: torch.optim.Optimizer,
    loss_fn: QuantileLoss,
    device: torch.device,
) -> float:
    return _run_epoch(model, loader, loss_fn, device, optimizer)


def evaluate(
    model: EPSTFT, loader: DataLoader[Any], loss_fn: QuantileLoss, device: torch.device
) -> float:
    return _run_epoch(model, loader, loss_fn, device, None)


def train_model(
    model: EPSTFT,
    train_loader: DataLoader[Any],
    val_loader: DataLoader[Any],
    device: torch.device,
    quantiles: list[float],
    lr: float = 1e-3,
    epochs: int = 200,
    patience: int = 20,
    on_epoch: Any = None,
) -> tuple[EPSTFT, dict[str, list[float]]]:
    """Train and restore the best-validation weights. ``on_epoch(epoch, val_loss)`` may
    raise to abort (used by the tuner for pruning)."""
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = QuantileLoss(quantiles)
    best_val = float("inf")
    best_state: dict[str, Any] | None = None
    stale = 0
    history: dict[str, list[float]] = {"train_loss": [], "val_loss": []}

    for epoch in range(epochs):
        train_loss = train_epoch(model, train_loader, optimizer, loss_fn, device)
        val_loss = evaluate(model, val_loader, loss_fn, device)
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        log.info("epoch %d train=%.4f val=%.4f", epoch + 1, train_loss, val_loss)
        if on_epoch is not None:
            on_epoch(epoch, val_loss)
        if val_loss < best_val:
            best_val = val_loss
            best_state = copy.deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                log.info("early stop at epoch %d (best val=%.4f)", epoch + 1, best_val)
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, history
