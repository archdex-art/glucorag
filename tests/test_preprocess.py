import numpy as np
import pandas as pd
import pytest

from glucorag.preprocess.impute import causal_linear_extrapolate
from glucorag.preprocess.normalize import StaticEncoder, ZNormalizer, normalize_timestamp
from glucorag.preprocess.resample import regularize
from glucorag.preprocess.windows import create_sliding_windows


def test_extrapolation_continues_trend_without_future_values():
    s = pd.Series([100.0, 110.0, np.nan, np.nan, 50.0])
    res = causal_linear_extrapolate(s)
    # The future observation (50) must not influence the fill.
    assert res.tolist()[:4] == [100.0, 110.0, 120.0, 130.0]


def test_extrapolation_slope_is_per_step_across_earlier_gap():
    s = pd.Series([100.0, np.nan, 120.0, np.nan])
    res = causal_linear_extrapolate(s, max_gap_steps=None)
    # prev obs at i=0, last at i=2 -> slope 10/step
    assert res.iloc[3] == 130.0


def test_extrapolation_flat_with_single_prior_and_nan_without_prior():
    res = causal_linear_extrapolate(pd.Series([np.nan, 100.0, np.nan]))
    assert np.isnan(res.iloc[0])
    assert res.iloc[2] == 100.0


def test_extrapolation_clips_to_sensor_range():
    res = causal_linear_extrapolate(pd.Series([380.0, 395.0, np.nan, 30.0]))
    assert res.iloc[2] == 400.0
    assert res.iloc[3] == 40.0


def test_gap_longer_than_limit_stays_nan_but_limit_gap_is_filled():
    s = pd.Series([100.0, 110.0, np.nan, np.nan, np.nan, 150.0, 160.0, np.nan, np.nan])
    res = causal_linear_extrapolate(s, max_gap_steps=2)
    assert res.iloc[2:5].isna().all()
    assert res.iloc[7:9].tolist() == [170.0, 180.0]


def test_regularize_snaps_to_grid_and_marks_missing():
    t0 = pd.Timestamp("2024-01-01 10:03")
    df = pd.DataFrame(
        {
            "patient_id": "P",
            "series_id": "S",
            "timestamp": [t0, t0 + pd.Timedelta("16min"), t0 + pd.Timedelta("44min")],
            "glucose_mg_dl": [100.0, 110.0, 130.0],
        }
    )
    out = regularize(df, 15)
    assert out["timestamp"].tolist() == [t0 + pd.Timedelta(minutes=15 * i) for i in range(4)]
    assert out["observed"].tolist() == [True, True, False, True]
    assert np.isnan(out["glucose_mg_dl"].iloc[2])


def test_normalize_timestamp():
    times = pd.Series(pd.to_datetime(["2024-01-01 00:00", "2024-01-01 12:00", "2024-01-01 23:59"]))
    assert np.allclose(normalize_timestamp(times), [0.0, 0.5, 1439 / 1440])


def test_znormalizer_roundtrip_and_ignores_nan():
    norm = ZNormalizer().fit(pd.Series([10.0, 20.0, 30.0, np.nan]))
    assert norm.mu == 20.0
    restored = ZNormalizer.from_dict(norm.to_dict())
    assert restored.inverse_transform(restored.transform(25.0)) == pytest.approx(25.0)


def test_static_encoder_codes_and_rejects_bad_values():
    profiles = pd.DataFrame({"gender": ["F", "M"], "age": [40.0, 60.0]})
    enc = StaticEncoder(["gender", "age"]).fit(profiles)
    assert enc.encode_one({"gender": "M", "age": 50.0}).tolist() == [1.0, 0.0]
    with pytest.raises(ValueError):
        enc.encode_one({"gender": "X", "age": 50.0})
    with pytest.raises(ValueError):
        enc.encode_one({"gender": "F"})


def _frame(n: int, series: str = "S1") -> pd.DataFrame:
    g = np.arange(n, dtype=float)
    return pd.DataFrame(
        {
            "patient_id": "P1",
            "series_id": series,
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="5min"),
            "glucose_mg_dl": g,
            "glucose_z": g,
            "time_norm": np.linspace(0, 1, n),
            "observed": True,
        }
    )


def test_windows_align_targets_with_horizon():
    w = create_sliding_windows(_frame(10), lookback_steps=4, horizon_steps=2)
    assert len(w) == 5
    assert w.x_enc[0, :, 0].tolist() == [0, 1, 2, 3]
    assert w.target_mg_dl[0].tolist() == [4.0, 5.0]
    assert w.t0[0] == np.datetime64("2024-01-01T00:15")


def test_windows_never_cross_series_and_skip_nan_or_imputed_targets():
    a = _frame(6, "A")
    b = _frame(6, "B")
    b.loc[5, "observed"] = False
    a.loc[2, "glucose_z"] = np.nan
    w = create_sliding_windows(
        pd.concat([a, b]), lookback_steps=4, horizon_steps=2, require_observed_target=True
    )
    # A: only window contains NaN; B: only window has an imputed target.
    assert len(w) == 0
    w2 = create_sliding_windows(pd.concat([a, b]), lookback_steps=4, horizon_steps=2)
    assert w2.series_id.tolist() == ["B"]
