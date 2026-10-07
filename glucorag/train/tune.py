"""HyperBand hyperparameter search (Optuna HyperbandPruner), selecting on validation loss.

    python -m glucorag.train.tune --dataset shanghai --data-root data/raw/shanghai --trials 30

Prints the best parameters as CLI flags for ``glucorag.train.cli``.
"""

import argparse
import logging
from pathlib import Path

import optuna
from torch.utils.data import DataLoader

from glucorag.core.config import settings
from glucorag.data.pipeline import load_dataset, make_windows, to_tensor_dataset
from glucorag.models.tft.tft import EPSTFT
from glucorag.train.trainer import resolve_device, seed_everything, train_model

log = logging.getLogger("glucorag.tune")


def run(args: argparse.Namespace) -> optuna.Study:
    cfg = settings.model
    device = resolve_device(args.device)
    data = load_dataset(args.dataset, args.data_root, args.max_gap_min, args.ohio_profiles)
    horizon = max(cfg.horizons_min)
    train_ds = to_tensor_dataset(*make_windows(data, "train", cfg.lookback_min, horizon))
    val_ds = to_tensor_dataset(*make_windows(data, "val", cfg.lookback_min, horizon))

    def objective(trial: optuna.Trial) -> float:
        seed_everything(args.seed)
        d_model = trial.suggest_categorical("d_model", [16, 32, 64, 128])
        heads = trial.suggest_categorical("heads", [1, 2, 4])
        dropout = trial.suggest_float("dropout", 0.0, 0.3)
        lr = trial.suggest_float("lr", 1e-4, 3e-3, log=True)
        batch = trial.suggest_categorical("batch_size", [128, 256, 512])
        model = EPSTFT(
            static_size=len(data.spec.static_features),
            d_model=d_model,
            num_heads=heads,
            num_quantiles=len(cfg.quantiles),
            dropout=dropout,
        )

        def report(epoch: int, val_loss: float) -> None:
            trial.report(val_loss, epoch)
            if trial.should_prune():
                raise optuna.TrialPruned()

        _, history = train_model(
            model,
            DataLoader(train_ds, batch, shuffle=True),
            DataLoader(val_ds, batch),
            device,
            cfg.quantiles,
            lr=lr,
            epochs=args.max_epochs,
            patience=args.patience,
            on_epoch=report,
        )
        return min(history["val_loss"])

    study = optuna.create_study(
        direction="minimize",
        pruner=optuna.pruners.HyperbandPruner(
            min_resource=1, max_resource=args.max_epochs, reduction_factor=3
        ),
        sampler=optuna.samplers.TPESampler(seed=args.seed),
    )
    study.optimize(objective, n_trials=args.trials)
    return study


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", choices=["shanghai", "ohio"], required=True)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--ohio-profiles", type=Path, default=None)
    p.add_argument("--trials", type=int, default=30)
    p.add_argument("--max-epochs", type=int, default=200)
    p.add_argument("--patience", type=int, default=20)
    p.add_argument("--max-gap-min", type=int, default=settings.alert_thresholds.data_gap_min)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="auto")
    study = run(p.parse_args(argv))
    b = study.best_params
    print(f"best val loss {study.best_value:.4f}")
    print(
        f"--d-model {b['d_model']} --heads {b['heads']} --dropout {b['dropout']:.3f} "
        f"--lr {b['lr']:.2e} --batch-size {b['batch_size']}"
    )


if __name__ == "__main__":
    main()
