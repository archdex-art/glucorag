import csv
import io

import pytest
from _runtime import STEP, T0, tiny_artifact
from fastapi.testclient import TestClient

from glucorag.api.app import create_app
from glucorag.api.settings import ApiSettings

KEY = "test-key"
AUTH = {"X-API-Key": KEY}
PROFILE = {"patient_id": "p1", "age": 40, "gender": "M", "bmi": 23.0, "diabetes_type": "T1D"}


def _settings(tmp_path, levels=None, **kw) -> ApiSettings:
    model = tiny_artifact(tmp_path / "models", levels)
    return ApiSettings(model_path=model, db_path=tmp_path / "db.sqlite", api_keys=[KEY],
                       clock="data", watchdog_interval_s=0, **kw)


@pytest.fixture
def client(tmp_path):
    # Constant forecast: q0.25 = 60 mg/dL at every horizon -> hypo (medium: level 1, 15 min).
    app = create_app(_settings(tmp_path, levels=[40, 50, 60, 90, 120, 130, 140]))
    with TestClient(app) as c:
        yield c


def _readings(n, start=0, pid="p1", value=110.0):
    return [{"patient_id": pid, "timestamp": (T0 + (start + i) * STEP).isoformat(),
             "glucose_mg_dl": value} for i in range(n)]


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/metrics"), ("get", "/cohort/risk"), ("get", "/alerts"), ("get", "/export"),
     ("get", "/patients/p1/forecast"), ("get", "/patients/p1/history"),
     ("post", "/patients"), ("post", "/readings")],
)
def test_endpoints_require_valid_api_key(client, method, path):
    assert getattr(client, method)(path).status_code == 401
    assert getattr(client, method)(path, headers={"X-API-Key": "wrong"}).status_code == 401


def test_healthz_is_public(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.json()["model_version"] == "tiny-1"


def test_without_api_keys_staff_routes_stay_closed(tmp_path):
    cfg = _settings(tmp_path).model_copy(update={"api_keys": []})
    with TestClient(create_app(cfg)) as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/cohort/risk").status_code == 401
        assert c.get("/cohort/risk", headers={"X-API-Key": ""}).status_code == 401


def test_end_to_end_cycle_alerts_and_review(client):
    assert client.post("/patients", json=PROFILE, headers=AUTH).status_code == 200
    batch = client.post("/readings", json=_readings(10), headers=AUTH).json()
    assert batch["counts"] == {"warming_up": 7, "predicted": 3}
    alerts = [a for r in batch["results"] for a in r["alerts"]]
    assert [(a["type"], a["horizon_min"], a["severity"]) for a in alerts] == [
        ("hypo", 15, "medium")
    ]

    single = client.post("/readings", json=_readings(1, start=10)[0], headers=AUTH)
    assert single.status_code == 200 and single.json()["alerts"] == []  # de-duplicated

    fc = client.get("/patients/p1/forecast", headers=AUTH).json()
    assert fc["prediction"]["t0"] == (T0 + 10 * STEP).isoformat()
    assert fc["prediction"]["model_version"] == "tiny-1"
    assert all(row == sorted(row) for row in fc["prediction"]["values"])
    assert [f["type"] for f in fc["risk"]] == ["hypo"] and fc["hypo_quantile"] == 0.25

    hist = client.get("/patients/p1/history", params={"limit": 5}, headers=AUTH).json()
    assert len(hist["readings"]) == 5 and hist["readings"][-1]["timestamp"] == fc[
        "prediction"]["t0"]
    assert [p["t0"] for p in hist["predictions"]] == sorted(p["t0"] for p in hist["predictions"])

    (row,) = client.get("/cohort/risk", headers=AUTH).json()["patients"]
    assert (row["status"], row["severity"], row["active_alerts"]) == ("at_risk", "medium",
                                                                      ["hypo"])
    assert [a["type"] for a in client.get("/alerts", headers=AUTH).json()] == ["hypo"]

    exported = client.get("/export", params={"format": "csv", "kind": "predictions"},
                          headers=AUTH)
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert len(rows) == 4 * 4 and rows[0]["q0.25"] == "60.00"
    assert client.get("/export", params={"format": "csv"}, headers=AUTH).status_code == 422
    as_json = client.get("/export", headers=AUTH).json()
    assert len(as_json["predictions"]) == 4 and len(as_json["alerts"]) == 1

    metrics = client.get("/metrics", headers=AUTH).text
    assert "glucorag_readings_ingested_total 11.0" in metrics
    assert 'glucorag_alerts_total{type="hypo"} 1.0' in metrics
    assert "glucorag_prediction_latency_seconds_count 4.0" in metrics


def test_reading_errors_map_to_http_statuses(client):
    client.post("/patients", json=PROFILE, headers=AUTH)
    client.post("/readings", json=_readings(1), headers=AUTH)
    dup = client.post("/readings", json=_readings(1)[0], headers=AUTH)
    assert dup.status_code == 422 and dup.json()["detail"]["reason"] == "duplicate"
    unknown = client.post("/readings", json=_readings(1, pid="nobody")[0], headers=AUTH)
    assert unknown.status_code == 404
    batch = client.post("/readings", json=_readings(1, pid="nobody") + _readings(1, start=1),
                        headers=AUTH).json()
    assert [(r["status"], r["reason"]) for r in batch["results"]] == [
        ("rejected", "unknown_patient"), ("warming_up", None)
    ]
    assert 'glucorag_readings_rejected_total{reason="duplicate"} 1.0' in client.get(
        "/metrics", headers=AUTH).text


def test_profile_validation(client):
    no_bmi = {k: v for k, v in PROFILE.items() if k != "bmi"}
    assert client.post("/patients", json=no_bmi, headers=AUTH).status_code == 422
    bad_q = PROFILE | {"alert_policy": {"hypo_quantile": 0.3}}
    assert client.post("/patients", json=bad_q, headers=AUTH).status_code == 422
    ok = client.post("/patients", json=PROFILE | {"alert_policy": {"hyper_quantile": 0.9}},
                     headers=AUTH).json()
    assert (ok["effective_hypo_quantile"], ok["effective_hyper_quantile"]) == (0.25, 0.9)
    assert client.get("/patients/p1/forecast", headers=AUTH).status_code == 404
