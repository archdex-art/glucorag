import math

import numpy as np
import pytest

from glucorag.evaluate.metrics import (
    gmse_penalty,
    grmse,
    horizon_index,
    mae,
    mape,
    metrics_at_horizons,
    per_patient_metrics,
    rmse,
    summarize,
)


def test_point_metrics_match_hand_computation():
    y, p = [100.0, 200.0], [110.0, 180.0]  # errors +10, -20
    assert rmse(y, p) == pytest.approx(math.sqrt(250.0))
    assert mae(y, p) == pytest.approx(15.0)
    assert mape(y, p) == pytest.approx(10.0)  # (10/100 + 20/200) / 2 * 100


def test_mape_rejects_non_positive_reference():
    with pytest.raises(ValueError):
        mape([0.0, 100.0], [10.0, 100.0])


@pytest.mark.parametrize(
    ("g", "g_hat", "expected"),
    [
        (120.0, 60.0, 1.0),  # euglycaemia: no penalty whatever the error
        (120.0, 200.0, 1.0),
        (50.0, 70.0, 2.5),  # overestimating hypoglycaemia: full 1 + alpha_L
        (50.0, 30.0, 1.0),  # underestimating hypoglycaemia is not penalized
        (55.0, 65.0, 2.5),  # g = T_L - beta_L and g_hat = g + gamma_L: both steps saturated
        (85.0, 150.0, 1.0),  # g = T_L: hypo step is exactly 0
        (300.0, 270.0, 2.0),  # underestimating hyperglycaemia: full 1 + alpha_H
        (300.0, 330.0, 1.0),  # overestimating hyperglycaemia is not penalized
        (155.0, 100.0, 1.0),  # g = T_H: hyper step is exactly 0
        (70.0, 75.0, 1.0 + 1.5 * 0.5 * 0.5),  # both hypo steps at their midpoints
        (205.0, 195.0, 1.0 + 1.0 * 0.5 * 0.5),  # both hyper steps at their midpoints
    ],
)
def test_gmse_penalty_direction_and_boundaries(g, g_hat, expected):
    assert gmse_penalty([g], [g_hat])[0] == pytest.approx(expected)


def test_gmse_penalty_is_smooth_and_monotone_in_overestimation():
    g = np.full(201, 50.0)
    g_hat = np.linspace(40.0, 70.0, 201)
    pen = gmse_penalty(g, g_hat)
    assert np.all(np.diff(pen) >= -1e-12)
    assert np.max(np.abs(np.diff(pen))) < 0.05  # no jumps
    # the smooth step is point-symmetric about its midpoint
    quarter = gmse_penalty([50.0, 50.0], [52.5, 57.5])
    assert (quarter[0] - 1.0) + (quarter[1] - 1.0) == pytest.approx(1.5)


def test_grmse_weights_squared_error_by_penalty():
    assert grmse([50.0], [70.0]) == pytest.approx(math.sqrt(2.5 * 400.0))
    y = np.array([60.0, 120.0, 280.0])
    p = np.array([75.0, 100.0, 250.0])
    assert grmse(y, p) > rmse(y, p)
    assert grmse([120.0, 130.0], [100.0, 150.0]) == pytest.approx(rmse([120, 130], [100, 150]))


@pytest.mark.parametrize(
    ("horizon", "interval", "col"), [(30, 15, 1), (60, 15, 3), (30, 5, 5), (60, 5, 11)]
)
def test_horizon_index(horizon, interval, col):
    assert horizon_index(horizon, interval) == col


@pytest.mark.parametrize("horizon", [0, 20, -15])
def test_horizon_index_rejects_off_grid(horizon):
    with pytest.raises(ValueError):
        horizon_index(horizon, 15)


def test_metrics_are_averaged_per_patient_not_pooled():
    # Patient A: two errors of 10; patient B: four perfect predictions.
    y = np.full(6, 100.0)
    p = np.array([110.0, 110.0, 100.0, 100.0, 100.0, 100.0])
    pid = ["A", "A", "B", "B", "B", "B"]
    per = per_patient_metrics(y, p, pid)
    assert per.set_index("patient_id")["RMSE"].to_dict() == pytest.approx({"A": 10.0, "B": 0.0})
    per.insert(0, "horizon_min", 30)
    table = summarize(per)
    assert table.loc[30, ("RMSE", "mean")] == pytest.approx(5.0)  # pooled would be 5.77
    assert table.loc[30, ("RMSE", "std")] == pytest.approx(math.sqrt(50.0))  # sample STD


def test_metrics_at_horizons_reads_the_right_column():
    target = np.full((4, 4), 150.0)
    pred = target.copy()
    pred[:, 1] += 12.0  # error only in the 30-min column for 15-min data
    out = metrics_at_horizons(target, pred, ["A", "A", "B", "B"], 15, [30, 60])
    rmse_by_h = out.groupby("horizon_min")["RMSE"].mean()
    assert rmse_by_h.loc[30] == pytest.approx(12.0)
    assert rmse_by_h.loc[60] == pytest.approx(0.0)
    assert set(out.columns) >= {"horizon_min", "patient_id", "n", "MAPE", "gRMSE"}


def test_metrics_at_horizons_rejects_horizon_beyond_forecast():
    with pytest.raises(ValueError):
        metrics_at_horizons(np.ones((2, 2)), np.ones((2, 2)), ["A", "B"], 15, [60])

