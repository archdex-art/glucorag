"""Multi-horizon neural baselines (LSTM, N-BEATS, N-HiTS) trained with MSE.

All networks map the encoder input ``x_enc`` (B, L, 2) = [glucose_z, time_norm] to a direct
multi-horizon forecast (B, H) in z units. N-BEATS and N-HiTS are univariate (glucose only),
as in their original formulations; the LSTM also sees the time-of-day channel.
"""

import copy
import logging
from collections.abc import Callable, Sequence

import numpy as np
import numpy.typing as npt
import torch
import torch.nn.functional as F  # noqa: N812
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from glucorag.preprocess.windows import Windows

log = logging.getLogger(__name__)


class LSTMForecaster(nn.Module):
    """Stacked LSTM over the look-back; last hidden state -> linear multi-horizon head."""

    def __init__(
        self, horizon_steps: int, hidden: int = 64, layers: int = 2, dropout: float = 0.1
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(2, hidden, num_layers=layers, batch_first=True, dropout=dropout)
        self.head = nn.Linear(hidden, horizon_steps)

    def forward(self, x_enc: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x_enc)
        return self.head(out[:, -1])


def _mlp(in_size: int, hidden: int, layers: int) -> nn.Sequential:
    mods: list[nn.Module] = []
    for i in range(layers):
        mods += [nn.Linear(in_size if i == 0 else hidden, hidden), nn.ReLU()]
    return nn.Sequential(*mods)


class _Block(nn.Module):
    """Doubly-residual block: optional input max-pooling (N-HiTS multi-rate sampling), FC
    stack, linear backcast of length L and forecast coefficients linearly interpolated to H
    (identity when ``n_forecast_coeffs == H``, i.e. the N-BEATS generic block)."""

    def __init__(
        self,
        lookback: int,
        horizon: int,
        hidden: int,
        layers: int,
        pool_size: int = 1,
        n_forecast_coeffs: int | None = None,
    ) -> None:
        super().__init__()
        self.horizon = horizon
        self.pool = (
            nn.MaxPool1d(pool_size, stride=pool_size, ceil_mode=True) if pool_size > 1 else None
        )
        pooled = -(-lookback // pool_size)
        self.mlp = _mlp(pooled, hidden, layers)
        self.backcast = nn.Linear(hidden, lookback)
        self.forecast = nn.Linear(hidden, n_forecast_coeffs or horizon)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = x if self.pool is None else self.pool(x.unsqueeze(1)).squeeze(1)
        h = self.mlp(h)
        theta_f = self.forecast(h)
        if theta_f.shape[1] != self.horizon:
            theta_f = F.interpolate(
                theta_f.unsqueeze(1), size=self.horizon, mode="linear", align_corners=True
            ).squeeze(1)
        return self.backcast(h), theta_f


class _ResidualStack(nn.Module):
    def __init__(self, blocks: Sequence[_Block]) -> None:
        super().__init__()
        self.horizon = blocks[0].horizon
        self.blocks = nn.ModuleList(blocks)

    def forward(self, x_enc: torch.Tensor) -> torch.Tensor:
        residual = x_enc[:, :, 0]
        forecast = x_enc.new_zeros(x_enc.shape[0], self.horizon)
        for block in self.blocks:
            backcast, block_forecast = block(residual)
            residual = residual - backcast
            forecast = forecast + block_forecast
        return forecast


class NBeats(_ResidualStack):
    """N-BEATS generic architecture (Oreshkin et al., ICLR 2020).

    ``n_blocks`` generic blocks of ``layers`` FC+ReLU layers. The generic basis expansion
    (FC -> theta -> linear basis) is two consecutive linear maps, implemented as one linear
    layer per output. Sized down from the paper's 30x512 for 8-24-step look-backs.
    """

    def __init__(
        self, lookback: int, horizon: int, n_blocks: int = 6, hidden: int = 256, layers: int = 4
    ) -> None:
        super().__init__([_Block(lookback, horizon, hidden, layers) for _ in range(n_blocks)])


class NHiTS(_ResidualStack):
    """N-HiTS (Challu et al., AAAI 2023): one block per stack, stack ``s`` max-pools the
    input with kernel ``pool_sizes[s]`` and predicts ``ceil(H / downsample[s])`` forecast
    coefficients that are linearly interpolated to H (hierarchical interpolation)."""

    def __init__(
        self,
        lookback: int,
        horizon: int,
        pool_sizes: Sequence[int] = (4, 2, 1),
        downsample: Sequence[int] = (4, 2, 1),
        hidden: int = 256,
        layers: int = 2,
    ) -> None:
        if len(pool_sizes) != len(downsample):
            raise ValueError("pool_sizes and downsample need one entry per stack")
        super().__init__(
            [
                _Block(lookback, horizon, hidden, layers, k, max(1, -(-horizon // r)))
                for k, r in zip(pool_sizes, downsample, strict=True)
            ]
        )


class NeuralForecaster:
    """Adam + MSE on z-normalized targets, early stopping on validation MSE."""

    def __init__(
        self,
        name: str,
        factory: Callable[[], nn.Module],
        horizon_steps: int,
        seed: int = 0,
        device: str = "cpu",
        epochs: int = 100,
        patience: int = 10,
        lr: float = 1e-3,
        batch_size: int = 256,
    ) -> None:
        self.name = name
        self.factory = factory
        self.horizon_steps = horizon_steps
        self.seed = seed
        self.device = torch.device(device)
        self.epochs = epochs
        self.patience = patience
        self.lr = lr
        self.batch_size = batch_size
        self.model: nn.Module | None = None
        self.epochs_run = 0

    def _loader(self, windows: Windows, shuffle: bool) -> DataLoader[tuple[torch.Tensor, ...]]:
        ds = TensorDataset(torch.from_numpy(windows.x_enc), torch.from_numpy(windows.target_z))
        gen = torch.Generator().manual_seed(self.seed)
        return DataLoader(ds, self.batch_size, shuffle=shuffle, generator=gen)

    def _epoch(
        self, model: nn.Module, loader: DataLoader[tuple[torch.Tensor, ...]],
        optimizer: torch.optim.Optimizer | None,
    ) -> float:
        model.train(optimizer is not None)
        total, count = 0.0, 0
        with torch.set_grad_enabled(optimizer is not None):
            for x, y in loader:
                x, y = x.to(self.device), y.to(self.device)
                loss = F.mse_loss(model(x), y)
                if optimizer is not None:
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                total += loss.item() * x.shape[0]
                count += x.shape[0]
        return total / max(count, 1)

    def fit(self, train: Windows, val: Windows) -> None:
        torch.manual_seed(self.seed)
        model = self.factory().to(self.device)
        optimizer = torch.optim.Adam(model.parameters(), lr=self.lr)
        train_loader, val_loader = self._loader(train, True), self._loader(val, False)
        best, best_state, stale = float("inf"), copy.deepcopy(model.state_dict()), 0
        for epoch in range(self.epochs):
            train_loss = self._epoch(model, train_loader, optimizer)
            val_loss = self._epoch(model, val_loader, None)
            self.epochs_run = epoch + 1
            log.info("%s epoch %d train=%.4f val=%.4f", self.name, epoch + 1, train_loss, val_loss)
            if val_loss < best:
                best, best_state, stale = val_loss, copy.deepcopy(model.state_dict()), 0
            else:
                stale += 1
                if stale >= self.patience:
                    break
        model.load_state_dict(best_state)
        self.model = model.eval()

    @torch.no_grad()
    def predict(self, windows: Windows) -> npt.NDArray[np.float32]:
        if self.model is None:
            raise RuntimeError(f"{self.name} is not fitted")
        outs = [
            self.model(x.to(self.device)).cpu()
            for x, _ in self._loader(windows, shuffle=False)
        ]
        if not outs:
            return np.zeros((0, self.horizon_steps), np.float32)
        return torch.cat(outs).numpy().astype(np.float32)
