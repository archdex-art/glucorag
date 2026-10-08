"""Benchmark windowing on synthetic data (no foundation model or download needed)."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from glucorag.bench.models import Persistence
from glucorag.bench.protocol import interval_coverage, series_histories, window_contexts
from glucorag.data.splits import create_shanghai_split
from glucorag.preprocess.windows import create_sliding_windows

LOOKBACK, HORIZON = 8, 4


def _frame(n: int = 200, gap_at: int | None = None) -> pd.DataFrame:
    frames = []
    for k, sid in enumerate(("a", "b")):
        mg = 100.0 + 10 * k + np.arange(n, dtype=np.float64)  # value encodes the position
        if gap_at is not None:
            mg[gap_at] = np.nan
        frames.append(pd.DataFrame({
            "series_id": sid,
            "patient_id": f"p{sid}",
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="15min"),
            "glucose_mg_dl": mg,
            "glucose_z": (mg - 100.0) / 50.0,
            "time_norm": 0.0,
            "observed": True,
        }))
    return pd.concat(frames, ignore_index=True)


def _split_windows(frame: pd.DataFrame):
    train, val, test = create_shanghai_split(frame)
    windows = create_sliding_windows(test, LOOKBACK, HORIZON, require_observed_target=True)
    return series_histories([train, val, test]), windows, test


def test_lookback_context_matches_encoder_window():
    histories, windows, _ = _split_windows(_frame())
    contexts = window_contexts(histories, windows, LOOKBACK)
    assert len(contexts) == len(windows) > 0
    encoder_mg = windows.x_enc[:, :, 0] * 50.0 + 100.0
    np.testing.assert_allclose(np.stack(contexts), encoder_mg, atol=1e-4)


def test_long_context_reaches_into_earlier_splits_but_not_past_origin():
    histories, windows, test = _split_windows(_frame())
    contexts = window_contexts(histories, windows, 64)
    first_test_mg = test.groupby("series_id")["glucose_mg_dl"].min().to_dict()
    reaches_back = False
    for ctx, sid, target in zip(contexts, windows.series_id, windows.target_mg_dl, strict=True):
        assert len(ctx) == 64  # the synthetic series has enough history everywhere
        np.testing.assert_allclose(np.diff(ctx), 1.0)  # contiguous, oldest first
        assert ctx[-1] + 1 == pytest.approx(target[0])  # ends at t0: next value is the target
        reaches_back |= bool(ctx[0] < first_test_mg[sid])
    assert reaches_back


def test_long_context_stops_at_unimputed_gap():
    histories, windows, test = _split_windows(_frame(gap_at=150))
    contexts = window_contexts(histories, windows, 64)
    for ctx in contexts:
        assert not np.isnan(ctx).any()
        # Values encode positions; nothing at or before the NaN at position 150 survives.
        assert (ctx - ctx[0] == np.arange(len(ctx))).all()
    starts_after_gap = [c for c, sid in zip(contexts, windows.series_id, strict=True)
                        if sid == "a" and c[0] > 100.0 + 150]
    assert starts_after_gap and all(len(c) < 64 for c in starts_after_gap)


def test_unknown_origin_and_empty_context_raise():
    histories, windows, _ = _split_windows(_frame())
    with pytest.raises(ValueError):
        window_contexts(histories, windows, 0)
    shifted = replace(windows, t0=windows.t0 + np.timedelta64(1, "m"))
    with pytest.raises(ValueError, match="not in the history"):
        window_contexts(histories, shifted, LOOKBACK)


def test_interval_coverage_and_persistence():
    target = np.array([[100.0, 100.0], [100.0, 140.0], [100.0, 60.0], [100.0, 100.0]])
    lower = np.full_like(target, 80.0)
    upper = np.full_like(target, 120.0)
    pid = np.array(["x", "x", "x", "y"], dtype=object)
    cov = interval_coverage(target, lower, upper, pid, 15, [30])
    x = cov.set_index("patient_id").loc["x"]
    assert x["coverage"] == pytest.approx(100 / 3)
    assert x["below"] == pytest.approx(100 / 3) and x["above"] == pytest.approx(100 / 3)
    assert x["width"] == 40.0

    fc = Persistence().predict([np.array([1.0, 2.0], np.float32), np.array([5.0], np.float32)], 3)
    np.testing.assert_array_equal(fc.median, [[2, 2, 2], [5, 5, 5]])
    assert fc.lower is None
