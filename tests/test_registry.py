import pytest
import torch

from glucorag.core.registry import ModelMeta, load_artifact, save_artifact, update_meta


def _meta(version: str = "t-1") -> ModelMeta:
    return ModelMeta(
        version=version,
        dataset="shanghai",
        interval_min=15,
        lookback_min=120,
        horizon_min=60,
        quantiles=[0.1, 0.5, 0.9],
        d_model=16,
        num_heads=2,
        dropout=0.0,
        static_encoder={"features": ["gender", "age"], "stats": {"age": {"mu": 50, "sigma": 10}}},
        glucose_norm={"mu": 150.0, "sigma": 50.0},
        data_hash="abc",
    )


def test_artifact_roundtrip_reproduces_predictions(tmp_path):
    meta = _meta()
    model = meta.build_model().eval()
    path = save_artifact(tmp_path, model, meta)
    loaded, loaded_meta = load_artifact(path)
    assert loaded_meta.lookback_steps == 8 and loaded_meta.horizon_steps == 4
    args = (torch.randn(2, 2), torch.randn(2, 8, 2), torch.randn(2, 4, 1))
    with torch.no_grad():
        assert torch.equal(model(*args)[0], loaded(*args)[0])
    assert update_meta(path, metrics={"rmse": 1.0}).metrics == {"rmse": 1.0}


def test_tampered_weights_are_rejected(tmp_path):
    meta = _meta()
    path = save_artifact(tmp_path, meta.build_model(), meta)
    (path / "model.pt").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        load_artifact(path)


def test_versions_are_immutable(tmp_path):
    meta = _meta()
    save_artifact(tmp_path, meta.build_model(), meta)
    with pytest.raises(FileExistsError):
        save_artifact(tmp_path, meta.build_model(), _meta())
