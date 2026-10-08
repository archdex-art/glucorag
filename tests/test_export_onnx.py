"""ONNX export for the phone: the graph and metadata reproduce ForecastEngine.predict."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch
from _runtime import T0, tiny_artifact

from glucorag.core.registry import load_artifact
from glucorag.export.onnx_export import device_meta, export, main, parity_fixtures
from glucorag.inference.engine import ForecastEngine, Reading

ort = pytest.importorskip("onnxruntime")

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = ROOT / "models" / "shanghai-v1"
PHONE = ROOT / "android" / "phone" / "src"
PARITY = PHONE / "test" / "resources" / "parity.json"
ASSETS = PHONE / "main" / "assets" / "model"
TOLERANCE_MG_DL = 1e-3


def _random_weights(path: Path) -> None:
    """Replace the tiny artifact's weights so every layer contributes (not just the bias)."""
    state = torch.load(path / "model.pt", weights_only=True)
    torch.manual_seed(1)
    for v in state.values():
        if v.is_floating_point():
            v.copy_(torch.randn_like(v) * 0.3)
    torch.save(state, path / "model.pt")
    meta = json.loads((path / "meta.json").read_text())
    meta["weights_sha256"] = hashlib.sha256((path / "model.pt").read_bytes()).hexdigest()
    (path / "meta.json").write_text(json.dumps(meta))


def _encode(meta: dict, profile: dict) -> np.ndarray:
    """The static encoding rule as meta.json states it (what the phone implements)."""
    enc = meta["static_encoder"]
    out = []
    for f in enc["features"]:
        if f in enc["categorical"]:
            out.append(enc["categorical"][f][profile[f]])
        else:
            s = enc["continuous"][f]
            out.append((float(profile[f]) - s["mu"]) / s["sigma"])
    return np.array([out], dtype=np.float32)


def _onnx_predict(session, meta: dict, profile: dict, x_enc, x_dec) -> np.ndarray:
    out = session.run(
        [meta["output"]],
        {"static": _encode(meta, profile), "x_enc": x_enc[None], "x_dec": x_dec[None]},
    )[0][0]
    norm = meta["glucose_norm"]
    mg = out.astype(np.float64) * norm["sigma"] + norm["mu"]
    lo, hi = meta["sensor_range_mg_dl"]
    return np.clip(np.sort(mg, axis=-1), lo, hi)


@pytest.fixture
def tiny(tmp_path):
    path = tiny_artifact(tmp_path / "models")
    _random_weights(path)
    return path


def test_onnx_output_equals_torch_within_a_thousandth_mg_dl(tiny, tmp_path):
    onnx_path, meta_path = export(tiny, tmp_path / "out")
    meta = json.loads(meta_path.read_text())
    session = ort.InferenceSession(str(onnx_path))
    assert [i.name for i in session.get_inputs()] == ["static", "x_enc", "x_dec"]
    model, _ = load_artifact(tiny)
    sigma = meta["glucose_norm"]["sigma"]
    rng = np.random.default_rng(0)
    for _ in range(25):
        static = rng.normal(size=(1, 4)).astype(np.float32)
        x_enc = np.concatenate(
            [rng.normal(size=(1, 8, 1)), rng.random((1, 8, 1))], axis=-1
        ).astype(np.float32)
        x_dec = rng.random((1, 4, 1)).astype(np.float32)
        got = session.run(None, {"static": static, "x_enc": x_enc, "x_dec": x_dec})[0]
        with torch.no_grad():
            want = model(*map(torch.from_numpy, (static, x_enc, x_dec)))[0].numpy()
        assert got.shape == (1, 4, 7)
        assert np.abs(got - want).max() * sigma < TOLERANCE_MG_DL


def test_meta_json_reproduces_engine_predict_end_to_end(tiny, tmp_path):
    onnx_path, meta_path = export(tiny, tmp_path / "out")
    meta = json.loads(meta_path.read_text())
    session = ort.InferenceSession(str(onnx_path))
    engine = ForecastEngine.from_artifact(tiny, meta["max_gap_min"])
    profile = {"gender": "M", "age": 44, "bmi": 29.3, "diabetes_type": "T2D"}
    history = [Reading(T0 + (i - 12) * engine.step, 120 + 4 * i) for i in range(13)]
    x_enc, x_dec, _ = engine.build_inputs(history)
    want = np.array(engine.predict("p", engine.context_for(profile), history).values)
    got = _onnx_predict(session, meta, profile, x_enc, x_dec)
    assert np.abs(got - want).max() < TOLERANCE_MG_DL


def test_device_meta_mirrors_the_artifact(tiny):
    _, meta = load_artifact(tiny)
    d = device_meta(meta)
    assert (d["lookback_steps"], d["horizon_steps"], d["interval_min"]) == (8, 4, 15)
    assert d["quantiles"] == meta.quantiles
    assert d["glucose_norm"] == {"mu": 150.0, "sigma": 50.0}
    assert d["static_encoder"]["categorical"]["diabetes_type"] == {"T1D": 0.0, "T2D": 1.0}
    assert d["static_encoder"]["continuous"]["age"] == {"mu": 50.0, "sigma": 15.0}
    assert (d["max_gap_min"], d["pad_slots"], d["sensor_range_mg_dl"]) == (60, 2, [40.0, 400.0])


def test_cli_writes_model_meta_and_parity(tiny, tmp_path):
    parity = tmp_path / "res" / "parity.json"
    main(["--model", str(tiny), "--out", str(tmp_path / "out"), "--parity", str(parity)])
    assert (tmp_path / "out" / "model.onnx").stat().st_size > 0
    cases = json.loads(parity.read_text())["cases"]
    assert len(cases) >= 10
    assert {c.get("error") for c in cases} == {None, "DataGap"}
    for c in cases:
        if "values" in c:
            assert np.array(c["values"]).shape == (4, 7)


@pytest.mark.skipif(not SHANGHAI.is_dir(), reason="shanghai-v1 artifact not present")
def test_committed_parity_fixtures_match_the_current_engine():
    """The phone's parity test reads these; they must come from the shipped model."""
    committed = json.loads(PARITY.read_text())
    fresh = parity_fixtures(SHANGHAI)
    assert committed["model_version"] == fresh["model_version"]
    for old, new in zip(committed["cases"], fresh["cases"], strict=True):
        assert old["readings"] == new["readings"] and old.get("error") == new.get("error")
        if "values" in new:
            assert np.abs(np.array(old["values"]) - np.array(new["values"])).max() < 1e-9


def test_shipped_phone_model_reproduces_the_parity_fixtures():
    """The committed assets give the committed engine outputs from the engine's own inputs."""
    meta = json.loads((ASSETS / "meta.json").read_text())
    session = ort.InferenceSession(str(ASSETS / "model.onnx"))
    parity = json.loads(PARITY.read_text())
    assert parity["model_version"] == meta["version"]
    checked = 0
    for c in parity["cases"]:
        if "values" not in c:
            continue
        assert np.allclose(_encode(meta, c["profile"]), np.array([c["static"]], dtype=np.float32))
        x_enc = np.array(c["x_enc"], dtype=np.float32)
        x_dec = np.array(c["x_dec"], dtype=np.float32)
        got = _onnx_predict(session, meta, c["profile"], x_enc, x_dec)
        assert np.abs(got - np.array(c["values"])).max() < TOLERANCE_MG_DL
        checked += 1
    assert checked >= 8
