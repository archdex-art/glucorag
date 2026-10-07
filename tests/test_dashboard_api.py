import json

import pytest
from _runtime import STEP, T0, tiny_artifact
from fastapi.testclient import TestClient

from glucorag.api.app import create_app
from glucorag.api.settings import ApiSettings

KEY = "k"
AUTH = {"X-API-Key": KEY}
PROFILE = {"patient_id": "p1", "age": 40, "gender": "M", "bmi": 23.0, "diabetes_type": "T1D"}


@pytest.fixture
def web_dir(tmp_path):
    d = tmp_path / "web"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>dashboard</html>")
    (d / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    return d


@pytest.fixture
def app_env(tmp_path, web_dir):
    models = tmp_path / "models"
    artifact = tiny_artifact(models, [40, 50, 60, 90, 120, 130, 140])
    sim = tmp_path / "sim.json"
    sim.write_text(json.dumps({
        "model": {"version": "tiny-1"}, "config": {"days": 1}, "runtime_s": 1.0,
        "aggregate": {"open_loop": {"tbr_pct": 5.0}, "plgm": {"tbr_pct": 2.0}}, "paper": {},
    }))
    (models / "CURRENT").write_text("tiny-1\n")
    cfg = ApiSettings(model_path=models, db_path=tmp_path / "db.sqlite", api_keys=[KEY],
                      clock="data", watchdog_interval_s=0, web_dir=web_dir, sim_report=sim)
    with TestClient(create_app(cfg)) as c:
        yield c, artifact


@pytest.mark.parametrize("path", ["/model", "/stats"])
def test_monitoring_endpoints_require_key(app_env, path):
    client, _ = app_env
    assert client.get(path).status_code == 401


def test_model_reports_promotion_and_matching_sim_report(app_env):
    client, _ = app_env
    info = client.get("/model", headers=AUTH).json()
    assert info["version"] == "tiny-1"
    assert info["release"]["promoted"] is True
    assert info["in_silico"]["aggregate"]["plgm"]["tbr_pct"] == 2.0


def test_stats_counts_cycles_alerts_and_rejections(app_env):
    client, _ = app_env
    client.post("/patients", json=PROFILE, headers=AUTH)
    readings = [{"patient_id": "p1", "timestamp": (T0 + i * STEP).isoformat(),
                 "glucose_mg_dl": 110.0} for i in range(10)]
    client.post("/readings", json=readings + [readings[-1]], headers=AUTH)  # last = duplicate
    s = client.get("/stats", headers=AUTH).json()
    assert s["counters"]["readings_ingested"] == 10
    assert s["counters"]["predictions"] == 3
    assert s["rejected_by_reason"] == {"duplicate": 1}
    assert s["alerts_by_type"].get("hypo") == 1
    assert s["latency"]["samples"] == 3 and s["latency"]["p95_ms"] is not None
    assert s["storage"]["predictions"] == 3


def test_ui_serves_assets_spa_fallback_and_blocks_traversal(app_env):
    client, _ = app_env
    asset = client.get("/ui/assets/app-abc123.js")
    assert "immutable" in asset.headers["cache-control"]
    deep = client.get("/ui/patients/p1")
    assert deep.text == "<html>dashboard</html>" and deep.headers["cache-control"] == "no-cache"
    leak = client.get("/ui/..%2Fsecret.txt")
    assert "nope" not in leak.text
    assert client.get("/", follow_redirects=False).headers["location"] == "/ui/"


def test_security_headers_on_every_response(app_env):
    client, _ = app_env
    for path in ("/ui/", "/healthz"):
        h = client.get(path).headers
        assert "frame-ancestors 'none'" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff"
