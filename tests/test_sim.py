import pytest

pytest.importorskip("simglucose", reason="sim extra not installed")

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from glucorag.inference.engine import Reading
from glucorag.sim import cvga
from glucorag.sim.outcomes import glycemic_outcomes
from glucorag.sim.trial import (
    BasalBolusController,
    PatientSeeds,
    PLGMController,
    RescueRule,
    VirtualAdult,
    load_virtual_adult,
    make_patient,
    simulate,
)


@pytest.mark.parametrize(
    ("min_bg", "max_bg", "zone"),
    [
        (90.0, 180.0, "A"),
        (89.9, 180.0, "Lower B"),
        (90.0, 180.1, "Upper B"),
        (70.0, 180.0, "Lower B"),
        (69.9, 180.0, "Lower C"),
        (70.0, 300.0, "B"),
        (69.9, 300.0, "Lower D"),
        (70.0, 300.1, "Upper D"),
        (90.0, 300.1, "Upper C"),
        (69.9, 300.1, "E"),
        (120.0, 150.0, "A"),  # beyond the plotted axes: same rules
        (40.0, 450.0, "E"),
    ],
)
def test_cvga_zone_boundaries(min_bg: float, max_bg: float, zone: str) -> None:
    assert cvga.classify(min_bg, max_bg) == zone


def test_cvga_rejects_min_above_max() -> None:
    with pytest.raises(ValueError):
        cvga.classify(150.0, 100.0)


def test_daily_extremes_per_day_and_drops_partial_day() -> None:
    bg = np.array([100, 60, 200, 150, 95, 310, 80])  # 2 full days of 3 samples + 1 extra
    mins, maxs = cvga.daily_extremes(bg, samples_per_day=3)
    assert mins.tolist() == [60, 95]
    assert maxs.tolist() == [200, 310]


def test_cvga_summary_macro_zones() -> None:
    mins = [100, 80, 80, 100, 60, 60, 80, 100]
    maxs = [150, 150, 250, 250, 250, 350, 350, 350]
    # A, Lower B, B, Upper B, Lower D, E, Upper D, Upper C
    s = cvga.summarize(mins, maxs)
    assert s["A"] == 12.5
    assert s["A+B"] == 50.0
    assert s["C"] == 12.5
    assert s["D+E"] == 37.5
    assert sum(s[z] for z in cvga.ZONES) == pytest.approx(100.0)


def test_outcome_range_boundaries() -> None:
    o = glycemic_outcomes([69.9, 70.0, 180.0, 180.1])
    assert (o.tbr_pct, o.tir_pct, o.tar_pct) == (25.0, 50.0, 25.0)


def test_outcomes_reject_nan_and_empty() -> None:
    with pytest.raises(ValueError):
        glycemic_outcomes([100.0, float("nan")])
    with pytest.raises(ValueError):
        glycemic_outcomes([])


def _adult(**overrides: float) -> VirtualAdult:
    fields: dict[str, float] = {
        "age": 40.0,
        "body_weight_kg": 70.0,
        "basal_u_per_min": 0.02,
        "carb_ratio_g_per_u": 10.0,
        "correction_factor_mg_dl_per_u": 20.0,
    }
    fields.update(overrides)
    return VirtualAdult(name="stub", params=pd.Series(dtype=float), **fields)


def test_basal_bolus_corrects_only_above_threshold() -> None:
    bb = BasalBolusController(_adult(), target_mg_dl=140.0, correction_above_mg_dl=150.0)
    assert bb.meal_bolus_u(50.0, 150.0) == pytest.approx(5.0)
    assert bb.meal_bolus_u(50.0, 200.0) == pytest.approx(5.0 + 60.0 / 20.0)
    assert bb.meal_bolus_u(0.0, 60.0) == 0.0


class StubForecaster:
    def __init__(self, interval_min: int, history_steps: int, values: Sequence[float | None]):
        self.interval_min = interval_min
        self.history_steps = history_steps
        self._values = list(values)
        self.calls: list[list[Reading]] = []

    def predict_mg_dl(self, history: Sequence[Reading]) -> float | None:
        self.calls.append(list(history))
        return self._values.pop(0)


def _history(n: int, step_min: int = 5) -> list[Reading]:
    t0 = datetime(2024, 1, 1)
    return [Reading(t0 + timedelta(minutes=step_min * i), 100.0 + i) for i in range(n)]


def test_plgm_suspends_at_threshold_and_resumes_above() -> None:
    base = BasalBolusController(_adult(basal_u_per_min=0.02))
    plgm = PLGMController(
        base, StubForecaster(5, 4, [120.0, 70.0, 50.0, 70.1, None]), 5, threshold_mg_dl=70.0
    )
    delivered = []
    for _ in range(5):
        plgm.on_cgm(_history(4))
        delivered.append(plgm.basal_u_per_min())
    assert delivered == [0.02, 0.0, 0.0, 0.02, 0.02]  # None (no forecast) -> basal delivered


def test_plgm_never_alters_bolus_while_suspended() -> None:
    base = BasalBolusController(_adult())
    plgm = PLGMController(base, StubForecaster(5, 4, [40.0]), 5)
    plgm.on_cgm(_history(4))
    assert plgm.suspended
    assert plgm.meal_bolus_u(60.0, 200.0) == base.meal_bolus_u(60.0, 200.0)


def test_plgm_strides_history_to_forecaster_interval_ending_at_newest() -> None:
    stub = StubForecaster(15, 3, [100.0])
    plgm = PLGMController(BasalBolusController(_adult()), stub, 5)
    history = _history(12)
    plgm.on_cgm(history)
    passed = stub.calls[0]
    assert passed == [history[5], history[8], history[11]]
    assert plgm.history_len == 9


def test_plgm_rejects_incompatible_intervals() -> None:
    with pytest.raises(ValueError):
        PLGMController(BasalBolusController(_adult()), StubForecaster(12, 3, []), 5)


def test_fast_patient_params_match_simglucose_series() -> None:
    from simglucose.patient.t1dpatient import Action, T1DPatient

    adult = load_virtual_adult("adult#001")
    fast, ref = make_patient(adult), T1DPatient(adult.params)
    for minute in range(240):
        action = Action(CHO=40.0 if minute == 30 else 0.0, insulin=adult.basal_u_per_min)
        fast.step(action)
        ref.step(action)
    np.testing.assert_allclose(fast.state, ref.state, rtol=1e-12)


def test_simulation_is_reproducible_and_suspension_withholds_basal() -> None:
    adult = load_virtual_adult("adult#001")
    seeds = PatientSeeds.derive(0, 0)
    rule = RescueRule()
    a = simulate(adult, BasalBolusController(adult), 1, seeds, 1.0, 0.3, rule)
    b = simulate(adult, BasalBolusController(adult), 1, seeds, 1.0, 0.3, rule)
    np.testing.assert_array_equal(a.bg_mg_dl, b.bg_mg_dl)

    always_low = StubForecaster(5, 1, [40.0] * a.bg_mg_dl.size)
    plgm = PLGMController(BasalBolusController(adult), always_low, 5)
    suspended = simulate(adult, plgm, 1, seeds, 1.0, 0.3, rule)
    assert suspended.suspended.all()
    assert suspended.basal_u == 0.0
    assert suspended.meals == a.meals and suspended.bolus_u > 0
    # Same scenario and sensor noise; only insulin differs, so withheld basal raises BG.
    assert suspended.bg_mg_dl.mean() > a.bg_mg_dl.mean()


def test_rescue_carbs_are_rate_limited_and_prevent_collapse() -> None:
    adult = load_virtual_adult("adult#001")
    overdosed = replace(adult, basal_u_per_min=4 * adult.basal_u_per_min)
    seeds = PatientSeeds.derive(0, 0)
    untreated = simulate(
        overdosed, BasalBolusController(overdosed), 1, seeds, 1.0, 0.0, RescueRule(carbs_g=0)
    )
    treated = simulate(
        overdosed, BasalBolusController(overdosed), 1, seeds, 1.0, 0.0, RescueRule(every_min=30)
    )
    assert untreated.rescues == 0
    assert untreated.bg_mg_dl.min() < 40
    assert 0 < treated.rescues <= 1440 // 30
    assert treated.bg_mg_dl.min() > untreated.bg_mg_dl.min()
