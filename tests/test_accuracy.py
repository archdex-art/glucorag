from datetime import datetime, timedelta

import pytest
from _runtime import STEP, T0

from glucorag.core.schemas import Alert, Prediction
from glucorag.evaluate.live import MIN_COUNT, build_report, match_forecasts

T = datetime(2024, 3, 1, 12, 0)
QS = [0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98]
TOL = timedelta(minutes=7.5)
MIN = timedelta(minutes=1)
KEY_AUTH = {"X-API-Key": "k"}
PASSWORD = "correct horse battery"
PROFILE = {"age": 34, "gender": "F", "bmi": 22.5, "diabetes_type": "T1D"}


def _pred(t0: datetime, median: float = 100.0, version: str = "v1", pid: str = "p") -> Prediction:
    # 50 % band = median +- 10, 80 % band = median +- 20.
    row = [median - 30, median - 20, median - 10, median, median + 10, median + 20, median + 30]
    return Prediction(patient_id=pid, t0=t0, horizons=[15, 30, 45, 60], quantiles=QS,
                      values=[row] * 4, model_version=version)


def test_no_reading_near_target_leaves_forecast_out():
    # 30-min target T+30: nearest reading is 10 min away; nothing near T+60.
    readings = [(T, 100.0), (T + 20 * MIN, 100.0)]
    assert match_forecasts([_pred(T)], readings, TOL) == []


def test_tolerance_is_half_interval_inclusive():
    on_edge = [(T + 30 * MIN + TOL, 120.0)]
    beyond = [(T + 30 * MIN + TOL + timedelta(seconds=1), 120.0)]
    (m,) = match_forecasts([_pred(T)], on_edge, TOL)
    assert (m.horizon_min, m.actual_mg_dl, m.target) == (30, 120.0, T + 30 * MIN)
    assert match_forecasts([_pred(T)], beyond, TOL) == []


def test_dense_five_minute_feed_takes_nearest_reading_and_earlier_on_tie():
    # Readings every 5 min starting at T+2; value = minutes after T.
    offset = [(T + (2 + 5 * i) * MIN, float(2 + 5 * i)) for i in range(14)]
    by_h = {m.horizon_min: m.actual_mg_dl for m in match_forecasts([_pred(T)], offset, TOL)}
    assert by_h == {30: 32.0, 60: 62.0}  # 2 min away beats 3 min away
    tie = [(T + 25 * MIN, 25.0), (T + 35 * MIN, 35.0)]
    (m,) = match_forecasts([_pred(T)], tie, TOL)
    assert m.actual_mg_dl == 25.0 and m.reading_at == T + 25 * MIN


def test_band_coverage_and_errors():
    # Median 100 for all: actual 105 is inside 50 %, 115 only inside 80 %, 130 outside both.
    t0s = [T, T + 60 * MIN, T + 120 * MIN]
    readings = [(t + 30 * MIN, v) for t, v in zip(t0s, [105.0, 115.0, 130.0], strict=True)]
    matches = match_forecasts([_pred(t) for t in t0s], readings, TOL, horizons=[30])
    assert [(m.in_50, m.in_80) for m in matches] == [(True, True), (False, True), (False, False)]
    report = build_report(matches, [], T + 4 * 60 * MIN)
    (h30, h60) = report.cohort.last_7_days
    assert (h30.count, h60.count) == (3, 0) and h60.rmse_mg_dl is None
    assert h30.mae_mg_dl == pytest.approx(50 / 3, abs=0.01)
    assert h30.rmse_mg_dl == pytest.approx(((25 + 225 + 900) / 3) ** 0.5, abs=0.01)
    assert h30.median_abs_error_mg_dl == 15.0
    assert (h30.coverage_50, h30.coverage_80) == (pytest.approx(1 / 3, abs=1e-3),
                                                  pytest.approx(2 / 3, abs=1e-3))


def test_report_splits_versions_patients_windows_and_days():
    now = T + timedelta(days=10)
    old, recent = now - timedelta(days=8), now - timedelta(hours=2)
    preds = [_pred(old, 100.0, "v1"), _pred(recent, 100.0, "v2"), _pred(recent, 90.0, "v1")]
    readings = [(old + 30 * MIN, 110.0), (recent + 30 * MIN, 110.0)]
    matches = match_forecasts(preds, readings, TOL, horizons=[30])
    alerts = [Alert(patient_id="p", type="hypo", severity="low", t_raised=recent),
              Alert(patient_id="p", type="hyper", severity="low", t_raised=recent),
              Alert(patient_id="p", type="hypo", severity="low", t_raised=now - timedelta(days=40))]
    report = build_report(matches, alerts, now)
    assert report.cohort.last_7_days[0].count == 2 and report.cohort.last_30_days[0].count == 3
    by_version = {v.model_version: v for v in report.versions}
    assert by_version["v1"].last_7_days[0].mae_mg_dl == 20.0  # 90 vs 110
    assert by_version["v1"].last_30_days[0].count == 2
    assert by_version["v2"].last_7_days[0].mae_mg_dl == 10.0
    assert [p.patient_id for p in report.patients] == ["p"]
    assert len(report.daily) == 30 and report.daily[-1].date == now.date()
    today = report.daily[-1]
    assert today.alerts == {"hypo": 1, "hyper": 1, "data_gap": 0}
    assert today.horizons[0].count == 2
    assert sum(d.alerts["hypo"] for d in report.daily) == 1  # the 40-day-old one is out


def test_report_without_time_is_empty():
    report = build_report([], [], None)
    assert report.as_of is None and report.daily == [] and report.versions == []
    assert report.cohort.last_7_days[0].count == 0


# API -----------------------------------------------------------------------------------


def _person(c) -> None:
    c.post("/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    c.put("/me/profile", json=PROFILE)


def _upload(c, n: int, value: float = 100.0) -> None:
    rows = [{"timestamp": (T0 + i * STEP).astimezone().isoformat(), "glucose_mg_dl": value}
            for i in range(n)]
    assert c.post("/me/readings/batch", json={"readings": rows}).status_code == 200


def test_me_accuracy_hidden_until_enough_matched_forecasts(make_client):
    # Constant tiny model: median 90 at every horizon; readings 100 -> error 10.
    with make_client() as c:
        assert c.get("/me/accuracy").status_code == 401
        _person(c)
        _upload(c, 20)  # forecasts from reading 8 on; 30-min matches: 11 < MIN_COUNT
        few = c.get("/me/accuracy").json()
        assert few["count"] == 11 and few["min_count"] == MIN_COUNT
        assert few["median_abs_error_mg_dl"] is None
        _upload(c, 40)
        enough = c.get("/me/accuracy").json()
        assert enough == {"days": 7, "horizon_min": 30, "count": 31, "min_count": MIN_COUNT,
                          "median_abs_error_mg_dl": 10.0}


def test_model_accuracy_is_staff_only_and_warns_on_drift(make_client):
    with make_client() as c:
        empty = c.get("/model/accuracy", headers=KEY_AUTH).json()
        assert empty["as_of"] is None and empty["daily"] == [] and empty["warnings"] == []
        _person(c)
        assert c.get("/model/accuracy").status_code == 403
        _upload(c, 40)
        meta = c.app.state.service.engine.meta
        meta.metrics["test"] = {"summary": {"30": {"RMSE": {"mean": 7.9}},
                                            "60": {"RMSE": {"mean": 8.1}}}}
        r = c.get("/model/accuracy", headers=KEY_AUTH).json()
        assert r["model_version"] == "tiny-1" and r["warning_ratio"] == 1.25
        assert r["reference"] == [{"horizon_min": 30, "rmse_mg_dl": 7.9},
                                  {"horizon_min": 60, "rmse_mg_dl": 8.1}]
        # Live RMSE 10: 10 / 7.9 = 1.27 warns; 10 / 8.1 = 1.23 does not.
        assert [(w["horizon_min"], w["rmse_7d_mg_dl"]) for w in r["warnings"]] == [(30, 10.0)]
        assert [v["model_version"] for v in r["versions"]] == ["tiny-1"]
        assert r["cohort"]["last_30_days"][1]["count"] == 29
        assert len(r["daily"]) == 30 and sum(d["alerts"]["hypo"] for d in r["daily"]) == 1


def test_downloads_offer_configured_apks_only(make_client, tmp_path):
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"PK\x03\x04apk")
    with make_client(phone_apk_path=apk, watch_apk_path=tmp_path / "missing.apk") as c:
        info = c.get("/downloads").json()
        assert info["phone_apk"] == "/download/phone.apk" and info["watch_apk"] is None
        assert info["releases_url"].startswith("https://github.com/")
        r = c.get("/download/phone.apk")
        assert r.status_code == 200 and r.content == b"PK\x03\x04apk"
        assert r.headers["content-type"] == "application/vnd.android.package-archive"
        assert "glucorag-phone.apk" in r.headers["content-disposition"]
        assert c.get("/download/watch.apk").status_code == 404
