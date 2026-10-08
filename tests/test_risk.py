from datetime import datetime, timedelta

import pytest

from glucorag.core.schemas import Prediction
from glucorag.notify.alerts import AlertDeduplicator
from glucorag.risk.detectors import AlertPolicy, RiskConfig, alerting, assess
from glucorag.risk.gap_guard import is_warming_up, stale_patients

QS = [0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98]
HORIZONS = [15, 30, 45, 60]
T = datetime(2021, 1, 1, 12, 0)


def _pred(rows: list[list[float]]) -> Prediction:
    return Prediction(patient_id="p", t0=T, horizons=HORIZONS, quantiles=QS, values=rows,
                      model_version="v")


def _band(q25: float, q75: float) -> list[float]:
    return [q25 - 20, q25 - 10, q25, (q25 + q75) / 2, q75, q75 + 10, q75 + 20]


def _flat(q25: float, q75: float) -> Prediction:
    return _pred([_band(q25, q75) for _ in HORIZONS])


@pytest.mark.parametrize(
    ("q25", "q75", "expected"),
    [
        (70.0, 120.0, {"hypo"}),
        (70.01, 120.0, set()),
        (100.0, 180.0, {"hyper"}),
        (100.0, 179.99, set()),
        (70.0, 180.0, {"hypo", "hyper"}),
    ],
)
def test_thresholds_are_inclusive_at_70_and_180(q25, q75, expected):
    assert {f.type for f in assess(_flat(q25, q75), RiskConfig())} == expected


def test_default_quantiles_use_lower_band_for_hypo_and_upper_band_for_hyper():
    # Median well inside range; only q0.25 is low and only q0.75 is high.
    flags = assess(_flat(68.0, 185.0), RiskConfig())
    assert {(f.type, f.quantile) for f in flags} == {("hypo", 0.25), ("hyper", 0.75)}
    # q0.10 (=58) would be lower still, but is not the configured hypo quantile.
    assert next(f for f in flags if f.type == "hypo").value_mg_dl == 68.0


def test_quantile_precedence_patient_policy_over_service_default():
    pred = _flat(75.0, 170.0)  # q0.10 = 65 <= 70, q0.25 = 75 > 70; q0.90 = 180
    service_low = RiskConfig(hypo_quantile=0.10)
    assert assess(pred, RiskConfig()) == []
    assert [f.type for f in assess(pred, service_low)] == ["hypo"]
    # Patient policy wins over the service setting...
    assert assess(pred, service_low, AlertPolicy(hypo_quantile=0.25)) == []
    # ...and an unset policy field falls back to the service setting.
    flags = assess(pred, service_low, AlertPolicy(hyper_quantile=0.90))
    assert {(f.type, f.quantile) for f in flags} == {("hypo", 0.10), ("hyper", 0.90)}


def test_quantile_missing_from_model_is_rejected():
    with pytest.raises(ValueError, match="not produced"):
        assess(_flat(100, 150), RiskConfig(hypo_quantile=0.3))


@pytest.mark.parametrize(
    ("q25_by_horizon", "horizon", "severity"),
    [
        ([90, 90, 90, 65], 60, "low"),  # level 1, late
        ([90, 65, 65, 65], 30, "medium"),  # level 1, within 30 min
        ([90, 90, 66, 50], 45, "medium"),  # level 2 but only beyond 30 min
        ([60, 54, 54, 54], 15, "high"),  # level 2 (<= 54) within 30 min
    ],
)
def test_hypo_severity_from_earliest_horizon_and_depth(q25_by_horizon, horizon, severity):
    pred = _pred([_band(v, 150.0) for v in q25_by_horizon])
    (flag,) = assess(pred, RiskConfig())
    assert (flag.horizon_min, flag.severity) == (horizon, severity)
    assert flag.margin_mg_dl == pytest.approx(70.0 - min(q25_by_horizon))


def test_hyper_severity_uses_level2_250():
    pred = _pred([_band(120.0, v) for v in [200, 250, 260, 270]])
    (flag,) = assess(pred, RiskConfig())
    assert (flag.type, flag.horizon_min, flag.severity) == ("hyper", 15, "high")
    assert flag.extreme_mg_dl == 270


@pytest.mark.parametrize(
    ("q75", "latest", "alerts"),
    [
        (189.0, 150.0, False),  # at risk (>= 180) but under the 10 mg/dL alert margin
        (189.99, 150.0, False),
        (190.0, 150.0, True),  # margin is inclusive
        (230.0, 179.9, True),
        (230.0, 180.0, False),  # already high: the status says so, no alert
        (230.0, 240.0, False),
    ],
)
def test_hyper_alert_needs_margin_and_not_already_high(q75, latest, alerts):
    flags = assess(_flat(100.0, q75), RiskConfig())
    assert [f.type for f in flags] == ["hyper"]  # the status still flags the risk
    assert bool(alerting(flags, latest, RiskConfig())) is alerts


def test_hyper_alert_margin_counts_at_any_horizon():
    # Only the 60-min upper value reaches 190; the first crossing (180) is earlier.
    pred = _pred([_band(100.0, v) for v in [175.0, 180.0, 185.0, 190.0]])
    flags = alerting(assess(pred, RiskConfig()), 120.0, RiskConfig())
    assert [(f.type, f.horizon_min) for f in flags] == [("hyper", 30)]


@pytest.mark.parametrize(
    ("q25", "latest", "alerts"),
    [
        (70.0, 100.0, True),  # hypo keeps no margin: exactly 70 alerts
        (69.0, 70.1, True),
        (60.0, 70.0, False),  # already low
        (50.0, 55.0, False),
    ],
)
def test_hypo_alert_has_no_margin_and_not_already_low(q25, latest, alerts):
    flags = assess(_flat(q25, 150.0), RiskConfig())
    assert [f.type for f in flags] == ["hypo"]
    assert bool(alerting(flags, latest, RiskConfig())) is alerts


def test_alert_gate_is_per_direction():
    # A wide band flags both; already high suppresses only the hyper alert.
    flags = assess(_flat(70.0, 200.0), RiskConfig())
    assert [f.type for f in alerting(flags, 185.0, RiskConfig())] == ["hypo"]


def test_dedup_suppresses_while_active_and_within_cooldown():
    d = AlertDeduplicator(cooldown=timedelta(minutes=30))
    m = timedelta(minutes=1)
    assert d.observe("p", "hypo", True, T) is True  # onset
    assert d.observe("p", "hypo", True, T + 15 * m) is False  # persists
    assert d.observe("p", "hypo", True, T + 120 * m) is False  # persists beyond cooldown
    assert d.active_types("p") == ["hypo"]
    assert d.observe("p", "hypo", False, T + 135 * m) is False  # clears
    assert d.active_types("p") == []
    assert d.observe("p", "hypo", True, T + 150 * m) is True  # re-onset, cooldown elapsed
    d.observe("p", "hypo", False, T + 165 * m)
    assert d.observe("p", "hypo", True, T + 170 * m) is False  # flap within 30-min cooldown
    assert d.active_types("p") == ["hypo"]  # suppressed onset still counts as active
    d.observe("p", "hypo", False, T + 175 * m)
    assert d.observe("p", "hypo", True, T + 180 * m) is True  # exactly 30 min after last raise


def test_dedup_state_is_per_patient_and_type():
    d = AlertDeduplicator(cooldown=timedelta(minutes=30))
    assert d.observe("p", "hypo", True, T)
    assert d.observe("p", "hyper", True, T)
    assert d.observe("q", "hypo", True, T)


def test_watchdog_staleness_is_strictly_greater_than_data_gap_min():
    last = {"at60": T - timedelta(minutes=60), "at75": T - timedelta(minutes=75),
            "at120": T - timedelta(minutes=120), "fresh": T}
    stale = stale_patients(last, T, data_gap_min=60)
    assert [s.patient_id for s in stale] == ["at120", "at75"]
    assert stale[1].minutes_since == 75


def test_warm_up_until_history_reaches_first_lookback_slot():
    # 120-min look-back at 15 min = slots t0-105 .. t0.
    t0 = T
    assert is_warming_up(None, t0, 120, 15)
    assert not is_warming_up(t0 - timedelta(minutes=105), t0, 120, 15)
    assert not is_warming_up(t0 - timedelta(minutes=98), t0, 120, 15)  # snaps to t0-105
    assert is_warming_up(t0 - timedelta(minutes=97.5), t0, 120, 15)  # rounds to t0-90
    assert is_warming_up(t0 - timedelta(minutes=90), t0, 120, 15)
