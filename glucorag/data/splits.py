"""Chronological per-series splits (no shuffling, no overlap)."""

import pandas as pd


def _split_group(group: pd.DataFrame, tail_fraction: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    group = group.sort_values("timestamp")
    n_tail = int(len(group) * tail_fraction)
    cut = len(group) - n_tail
    return group.iloc[:cut], group.iloc[cut:]


def split_tail(
    df: pd.DataFrame, tail_fraction: float, group_col: str = "series_id"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split each group into (head, last ``tail_fraction`` of rows)."""
    if not 0.0 <= tail_fraction < 1.0:
        raise ValueError("tail_fraction must be in [0, 1)")
    heads: list[pd.DataFrame] = []
    tails: list[pd.DataFrame] = []
    for _, group in df.groupby(group_col, sort=False):
        head, tail = _split_group(group, tail_fraction)
        heads.append(head)
        tails.append(tail)
    return pd.concat(heads, ignore_index=True), pd.concat(tails, ignore_index=True)


def create_shanghai_split(
    df: pd.DataFrame, test_size: float = 0.20, val_size: float = 0.25, group_col: str = "series_id"
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Paper split: last 20% per series is test; last 25% of the remainder is validation."""
    train_val, test = split_tail(df, test_size, group_col)
    train, val = split_tail(train_val, val_size, group_col)
    return train, val, test


def split_ohio_train(
    df: pd.DataFrame, val_size: float = 0.25, group_col: str = "series_id"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """OhioT1DM ships its own test files; validation is the last 25% of each training series."""
    return split_tail(df, val_size, group_col)
