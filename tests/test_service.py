import math
from datetime import timedelta

import pytest
from _runtime import QUANTILES, STEP, T0, ManualClock, profile, tiny_artifact

from glucorag.core.storage import Storage
from glucorag.inference.engine import ForecastEngine
from glucorag.risk.detectors import AlertPolicy, RiskConfig
from glucorag.service import GlucoseService, ServiceConfig, UnknownPatientError

SAFE = [100, 110, 120, 130, 140, 150, 160]  # no hypo / hyper at any default quantile
# q0.10 = 65 (<= 70) but q0.25 = 75: hypo only if the alert quantile is 0.10.
LOW_TAIL = [55, 65, 75, 100, 120, 130, 140]


def _service(tmp_path, levels=SAFE, db=":memory:", config=None, clock=None, version="tiny-1"):
    path = tmp_path / "models" / version
    if not path.exists():
        path = tiny_artifact(tmp_path / "models", levels, version)
    cfg = config or ServiceConfig()
    engine = ForecastEngine.from_artifact(path, cfg.data_gap_min)
    clock = clock or ManualClock(T0 + timedelta(days=1))
    return GlucoseService(engine, Storage(db), cfg, clock)


def _feed(svc, n, start=T0, value=120.0, pid="p1"):
    return [svc.ingest(pid, start + i * STEP, value) for i in range(n)]


def test_warm_up_then_forecast_with_pinned_model_version(tmp_path):
    svc = _service(tmp_path)
    svc.register_profile(profile())
    results = _feed(svc, 9)
    assert [r.status for r in results[:7]] == ["warming_up"] * 7
    assert all(not r.alerts for r in results[:7])
    assert [r.status for r in results[7:]] == ["predicted", "predicted"]
    pred = svc.storage.latest_prediction("p1")
    assert pred is not None and pred.t0 == T0 + 8 * STEP and pred.model_version == "tiny-1"
    assert pred.horizons == [15, 30, 45, 60] and pred.quantiles == QUANTILES


def test_data_gap_60_min_imputes_but_75_min_suspends(tmp_path):
    svc = _service(tmp_path)
    for pid in ("a", "b"):
        svc.register_profile(profile(pid))
        _feed(svc, 8, pid=pid)
    last = T0 + 7 * STEP
    # Next reading 75 min later = 60 min (4 slots) missing: imputable.
    ok = svc.ingest("a", last + timedelta(minutes=75), 120.0)
    assert ok.status == "predicted" and not ok.alerts
    # Next reading 90 min later = 75 min (5 slots) missing: skip inference, raise data_gap.
    gap = svc.ingest("b", last + timedelta(minutes=90), 120.0)
    assert gap.status == "data_gap" and gap.prediction is None
    assert [a.type for a in gap.alerts] == ["data_gap"]
    latest = svc.storage.latest_prediction("b")
    assert latest is not None and latest.t0 == last  # nothing persisted for the gap
    # Still gappy on the following reading: same condition, no duplicate alert.
    again = svc.ingest("b", last + timedelta(minutes=105), 120.0)
    assert again.status == "data_gap" and not again.alerts
    assert [a.type for a in svc.storage.alerts("b")] == ["data_gap"]
    # Once the look-back refills, forecasting resumes and the condition clears.
    t = last + timedelta(minutes=105)
    statuses = [svc.ingest("b", t + i * STEP, 120.0).status for i in range(1, 8)]
    assert statuses[-1] == "predicted" and "data_gap" not in svc.dedup.active_types("b")
    assert svc.metrics.data_gaps.labels("cycle")._value.get() == statuses.count("data_gap") + 2


def test_validation_rejections_leave_no_trace(tmp_path):
    clock = ManualClock(T0 + 10 * STEP)
    svc = _service(tmp_path, clock=clock)
    svc.register_profile(profile())
    _feed(svc, 3)
    last = T0 + 2 * STEP
    cases = [
        (last + STEP, math.nan, "non_finite"),
        (last + STEP, math.inf, "non_finite"),
        (last + STEP, 0.0, "non_positive"),
        (last, 130.0, "duplicate"),
        (last - STEP, 130.0, "out_of_order"),
        (clock.now() + timedelta(minutes=2, seconds=1), 130.0, "future"),
    ]
    for t, v, reason in cases:
        r = svc.ingest("p1", t, v)
        assert (r.status, r.reason) == ("rejected", reason)
    assert len(svc.storage.readings("p1")) == 3
    assert svc.buffer.last_timestamp("p1") == last
    # Within the allowed clock skew is accepted.
    assert svc.ingest("p1", clock.now() + timedelta(minutes=2), 130.0).status != "rejected"
    with pytest.raises(UnknownPatientError):
        svc.ingest("nobody", last + STEP, 120.0)


def test_out_of_range_values_are_clipped_and_flagged(tmp_path):
    svc = _service(tmp_path)
    svc.register_profile(profile())
    flags = [svc.ingest("p1", T0 + i * STEP, v).range_flag for i, v in
             enumerate([39.0, 40.0, 400.0, 401.0])]
    assert flags == ["clipped_low", "ok", "ok", "clipped_high"]
    stored = svc.storage.readings("p1")
    assert [(r.glucose_mg_dl, r.raw_mg_dl) for r in stored] == [
        (40.0, 39.0), (40.0, 40.0), (400.0, 400.0), (400.0, 401.0)
    ]
    assert svc.buffer.history("p1")[-1].glucose_mg_dl == 400.0


def test_backfilled_batch_dedups_on_reading_time_not_wall_time(tmp_path):
    # Wall clock frozen: the whole batch arrives "at once"; cooldown must use reading time.
    svc = _service(tmp_path, levels=LOW_TAIL, config=ServiceConfig(
        alert_cooldown=timedelta(minutes=30)))
    sensitive, default = AlertPolicy(hypo_quantile=0.10), AlertPolicy()
    svc.register_profile(profile(), sensitive)
    first = _feed(svc, 8)[-1]  # onset at T0+105
    svc.register_profile(profile(), default)
    assert svc.ingest("p1", T0 + 8 * STEP, 120.0).risk == []  # clears at T0+120
    svc.register_profile(profile(), sensitive)
    again = svc.ingest("p1", T0 + 9 * STEP, 120.0)  # re-onset 30 min after the first raise
    assert [a.t_raised for a in first.alerts + again.alerts] == [T0 + 7 * STEP, T0 + 9 * STEP]


def test_hypo_alert_raised_once_while_condition_persists(tmp_path):
    svc = _service(tmp_path, levels=[40, 45, 50, 60, 70, 80, 90])
    svc.register_profile(profile())
    results = _feed(svc, 12)
    raised = [a for r in results for a in r.alerts]
    assert [(a.type, a.horizon_min, a.severity) for a in raised] == [("hypo", 15, "high")]
    assert raised[0].t0 == T0 + 7 * STEP and raised[0].model_version == "tiny-1"
    assert all(r.risk and r.risk[0].type == "hypo" for r in results[7:])


def test_patient_policy_quantile_overrides_service_default(tmp_path):
    svc = _service(tmp_path, levels=LOW_TAIL)
    svc.register_profile(profile("default"))
    svc.register_profile(profile("sensitive"), AlertPolicy(hypo_quantile=0.10))
    assert svc.effective_quantiles("sensitive") == (0.10, 0.75)
    for pid in ("default", "sensitive"):
        _feed(svc, 8, pid=pid)
    assert svc.storage.alerts("default") == []
    assert [a.type for a in svc.storage.alerts("sensitive")] == ["hypo"]
    with pytest.raises(ValueError, match="not produced"):
        svc.register_profile(profile("bad"), AlertPolicy(hyper_quantile=0.8))
    with pytest.raises(ValueError, match="not produced"):
        _service(tmp_path, config=ServiceConfig(risk=RiskConfig(hypo_quantile=0.3)))


def test_cohort_row_carries_value_trend_and_band_of_the_patients_alert_quantiles(tmp_path):
    svc = _service(tmp_path, levels=LOW_TAIL, clock=ManualClock(T0 + 7 * STEP))
    svc.register_profile(profile("sensitive"), AlertPolicy(hypo_quantile=0.10))
    for i in range(8):
        svc.ingest("sensitive", T0 + i * STEP, 100.0 + 3 * i)  # +3 mg/dL per 15 min
    (row,) = svc.cohort_risk()
    assert row.last_glucose_mg_dl == 121.0
    assert row.trend_mg_dl_per_min == pytest.approx(3 / 15)
    band = row.forecast
    assert band is not None and band.t0 == T0 + 7 * STEP
    # Band edges are the patient's own alert quantiles (q0.10 / q0.75), median is q0.5.
    assert (band.low_quantile, band.high_quantile) == (0.10, 0.75)
    assert band.low == pytest.approx([65.0] * 4, abs=1e-3)
    assert band.median == pytest.approx([100.0] * 4, abs=1e-3)
    assert band.high == pytest.approx([120.0] * 4, abs=1e-3)


def test_cohort_row_drops_band_and_trend_across_a_gap(tmp_path):
    svc = _service(tmp_path)
    svc.register_profile(profile())
    _feed(svc, 8)
    svc.ingest("p1", T0 + 13 * STEP, 140.0)  # 75 min gap: forecast suspended
    (row,) = svc.cohort_risk()
    assert row.status == "data_gap" and row.last_glucose_mg_dl == 140.0
    assert row.trend_mg_dl_per_min is None and row.forecast is None


def test_watchdog_raises_data_gap_after_60_min_silence_once(tmp_path):
    clock = ManualClock(T0 + 7 * STEP)
    svc = _service(tmp_path, clock=clock)
    svc.register_profile(profile())
    svc.register_profile(profile("silent-never"))  # no readings: never stale
    _feed(svc, 8)
    last = T0 + 7 * STEP
    clock.set(last + timedelta(minutes=60))
    assert svc.watchdog() == []
    assert {r.patient_id: r.status for r in svc.cohort_risk()}["p1"] == "ok"
    clock.set(last + timedelta(minutes=75))
    (alert,) = svc.watchdog()
    assert (alert.patient_id, alert.type, alert.details["minutes_since_last"]) == (
        "p1", "data_gap", 75.0
    )
    clock.set(last + timedelta(minutes=90))
    assert svc.watchdog() == []
    risk = {r.patient_id: r for r in svc.cohort_risk()}
    assert risk["p1"].status == "data_gap" and risk["p1"].stale and risk["p1"].risk == []
    assert risk["silent-never"].status == "no_data"
    assert [r.patient_id for r in svc.cohort_risk()] == ["p1", "silent-never"]


def test_restart_rehydrates_buffers_profiles_and_policy(tmp_path):
    db = tmp_path / "state.sqlite"
    svc = _service(tmp_path, levels=LOW_TAIL, db=db)
    svc.register_profile(profile(), AlertPolicy(hypo_quantile=0.10))
    _feed(svc, 6)
    svc.storage.close()
    restarted = _service(tmp_path, db=db)
    assert restarted.ingest("p1", T0 + 5 * STEP, 120.0).reason == "duplicate"
    results = [restarted.ingest("p1", T0 + i * STEP, 120.0) for i in (6, 7)]
    assert [r.status for r in results] == ["warming_up", "predicted"]
    assert [a.type for a in results[1].alerts] == ["hypo"]  # persisted policy q0.10 applies


@pytest.mark.parametrize(
    ("upper", "latest", "alerted"),
    [(189.0, 150.0, False), (190.0, 150.0, True), (230.0, 185.0, False)],
)
def test_hyper_alert_gate_leaves_status_at_risk(tmp_path, upper, latest, alerted):
    # q0.75 = upper at every horizon: the status is at risk in all cases; the alert needs
    # the 10 mg/dL margin and a latest reading still under 180.
    levels = [100, 120, 140, 160, upper, upper + 10, upper + 20]
    svc = _service(tmp_path, levels=levels, clock=ManualClock(T0 + 7 * STEP))
    svc.register_profile(profile())
    results = _feed(svc, 8, value=latest)
    assert results[-1].status == "predicted"
    assert [a.type for a in results[-1].alerts] == (["hyper"] if alerted else [])
    row = svc.patient_status("p1")
    assert row.status == "at_risk" and [f.type for f in row.risk] == ["hyper"]
