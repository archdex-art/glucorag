"""Dense phone feeds (1-5 min readings) against the model's coarser sampling grid."""

from datetime import timedelta

import numpy as np
import pytest
from _runtime import T0, tiny_artifact

from glucorag.inference.engine import ForecastEngine, Reading
from glucorag.service import ServiceConfig, _trend


@pytest.fixture
def engine(tmp_path):
    path = tiny_artifact(tmp_path / "models", [40, 50, 60, 90, 120, 130, 140])
    return ForecastEngine.from_artifact(path, ServiceConfig().data_gap_min)


def decode_ages(engine: ForecastEngine, x_enc: np.ndarray) -> list[int]:
    mg = engine.glucose_norm.inverse_transform(x_enc[:, 0].astype(np.float64))
    return [round(float(v) - 100.0) for v in mg]


@pytest.mark.parametrize("step_min", [15, 5, 1])
def test_slots_hold_reading_nearest_grid_time(engine, step_min):
    hist = [Reading(T0 - timedelta(minutes=a), 100.0 + a) for a in range(0, 180, step_min)]
    x_enc, _, t0 = engine.build_inputs(hist)
    assert t0 == T0
    interval = engine.meta.interval_min
    ages = decode_ages(engine, x_enc)
    assert ages == [interval * k for k in range(engine.meta.lookback_steps - 1, -1, -1)]


def test_tie_between_readings_goes_to_the_later_one(engine):
    interval = engine.meta.interval_min
    d = interval / 3
    # Slot 1 has no exact reading; two readings sit d before and d after its grid time.
    ages = [0, interval - d, interval + d, *(interval * k for k in range(2, 12))]
    hist = [Reading(T0 - timedelta(minutes=a), 100.0 + a) for a in ages]
    x_enc, _, _ = engine.build_inputs(hist)
    assert decode_ages(engine, x_enc)[-2:] == [round(interval - d), 0]


def test_reading_beyond_half_step_leaves_slot_for_imputation(engine):
    interval = engine.meta.interval_min
    # Slot 3 has only a reading 0.6 step away -> NaN -> causally extrapolated (linear ages).
    ages = [interval * k for k in range(0, 12) if k != 3] + [interval * 3 + 0.6 * interval]
    hist = [Reading(T0 - timedelta(minutes=a), 100.0 + a) for a in ages]
    x_enc, _, _ = engine.build_inputs(hist)
    assert decode_ages(engine, x_enc)[-4] == interval * 3


@pytest.mark.parametrize("step_min", [15, 5, 1])
def test_trend_on_rising_feed(step_min):
    hist = [Reading(T0 - timedelta(minutes=a), 200.0 - a) for a in range(120, -1, -step_min)]
    assert _trend(hist, 15) == pytest.approx(1.0)


def test_trend_none_across_gap():
    hist = [Reading(T0 - timedelta(minutes=40), 100.0), Reading(T0, 120.0)]
    assert _trend(hist, 15) is None
