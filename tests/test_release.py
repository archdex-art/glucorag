import json
from pathlib import Path

from glucorag.core.registry import ModelMeta, resolve_artifact
from glucorag.release import check_accuracy, check_in_silico, check_significance, main


def _meta(**metrics: object) -> ModelMeta:
    return ModelMeta(
        version="v1",
        dataset="shanghai",
        interval_min=15,
        lookback_min=120,
        horizon_min=60,
        quantiles=[0.5],
        d_model=8,
        num_heads=1,
        dropout=0.0,
        static_encoder={"features": [], "stats": {}},
        glucose_norm={"mu": 0.0, "sigma": 1.0},
        data_hash="x",
        metrics=dict(metrics),
    )


def _summary(r30: float, r60: float) -> dict[str, object]:
    return {"summary": {"30": {"RMSE": {"mean": r30}}, "60": {"RMSE": {"mean": r60}}}}


def test_accuracy_limit_is_inclusive_and_any_horizon_fails():
    limits = {"30": 13.0, "60": 22.0}
    assert check_accuracy(_meta(test=_summary(13.0, 22.0)), limits).passed
    assert not check_accuracy(_meta(test=_summary(12.0, 22.01)), limits).passed
    assert not check_accuracy(_meta(), limits).passed


def test_significance_requires_every_horizon():
    sig = {
        h: {"significant": s, "comparator": "LSTM", "mean_difference": -1.0, "t_p": 0.01,
            "differences_normal": True}
        for h, s in (("30", True), ("60", False))
    }
    assert not check_significance(_meta(test={"significance": sig})).passed


def test_in_silico_rejects_report_for_other_version(tmp_path: Path):
    report = tmp_path / "r.json"
    agg = {"open_loop": {"tbr_pct": 5.0}, "plgm": {"tbr_pct": 2.0}}
    cfg = {"days": 90, "patients": ["a"]}
    report.write_text(json.dumps({"model": {"version": "other"}, "aggregate": agg, "config": cfg}))
    assert not check_in_silico(_meta(), report).passed
    report.write_text(json.dumps({"model": {"version": "v1"}, "aggregate": agg, "config": cfg}))
    assert check_in_silico(_meta(), report).passed


def test_failing_integrity_blocks_promotion_and_waiver_needs_reason(tmp_path: Path, capsys):
    art = tmp_path / "v1"
    art.mkdir()
    assert main(["--artifact", str(art)]) == 1
    assert not (tmp_path / "CURRENT").exists()
    try:
        main(["--artifact", str(art), "--waive", "integrity"])
    except SystemExit as exc:
        assert exc.code == 2


def test_resolve_artifact_follows_current_pointer(tmp_path: Path):
    (tmp_path / "CURRENT").write_text("v7\n")
    assert resolve_artifact(tmp_path) == tmp_path / "v7"
    assert resolve_artifact(tmp_path / "v7") == tmp_path / "v7"
