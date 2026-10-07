import pandas as pd

from glucorag.data.splits import create_shanghai_split, split_ohio_train


def _frame(series: list[str], n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": [s for s in series for _ in range(n)],
            "timestamp": list(pd.date_range("2024-01-01", periods=n, freq="15min")) * len(series),
        }
    )


def test_shanghai_split_sizes_and_chronology_per_series():
    train, val, test = create_shanghai_split(_frame(["A", "B"], 100))
    for sid in ("A", "B"):
        tr, va, te = (d[d["series_id"] == sid] for d in (train, val, test))
        assert (len(tr), len(va), len(te)) == (60, 20, 20)
        assert tr["timestamp"].max() < va["timestamp"].min()
        assert va["timestamp"].max() < te["timestamp"].min()


def test_ohio_train_val_split_is_chronological_and_disjoint():
    train, val = split_ohio_train(_frame(["A"], 100))
    assert (len(train), len(val)) == (75, 25)
    assert train["timestamp"].max() < val["timestamp"].min()
