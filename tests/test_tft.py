import pytest
import torch

from glucorag.models.tft.quantile import QuantileLoss
from glucorag.models.tft.tft import EPSTFT


def test_quantile_loss_matches_hand_computation():
    loss_fn = QuantileLoss([0.1, 0.9])
    preds = torch.tensor([[[1.0, 3.0]]])  # one sample, one step, two quantiles
    target = torch.tensor([[2.0]])
    # q=0.1: over-prediction? pred 1 < 2 -> q*(y-p) = 0.1; q=0.9: pred 3 > 2 -> (1-q)*(p-y) = 0.1
    assert loss_fn(preds, target).item() == pytest.approx(0.2)


def test_output_shape_and_vsn_weights_are_distributions():
    model = EPSTFT(static_size=4, d_model=16, num_heads=2, num_quantiles=7).eval()
    preds, interp = model(torch.randn(3, 4), torch.randn(3, 24, 2), torch.randn(3, 12, 1))
    assert preds.shape == (3, 12, 7)
    assert torch.allclose(interp["encoder_vsn_weights"].sum(-1), torch.ones(3, 24))
    assert interp["attention"].shape == (3, 12, 36)


def test_attention_is_causal():
    model = EPSTFT(static_size=2, d_model=16, num_heads=2, num_quantiles=3).eval()
    _, interp = model(torch.randn(1, 2), torch.randn(1, 8, 2), torch.randn(1, 4, 1))
    attn = interp["attention"][0]  # rows = decoder positions 8..11
    for row, pos in enumerate(range(8, 12)):
        assert torch.all(attn[row, pos + 1 :] == 0)


def test_precomputed_static_context_matches_full_forward():
    model = EPSTFT(static_size=4, d_model=16, num_heads=2, num_quantiles=3).eval()
    static = torch.randn(1, 4)
    x_enc, x_dec = torch.randn(5, 8, 2), torch.randn(5, 4, 1)
    with torch.no_grad():
        full, _ = model(static.expand(5, -1), x_enc, x_dec)
        ctx = model.encode_static(static).expand(5)
        cached, _ = model.forward_with_context(ctx, x_enc, x_dec)
    assert torch.allclose(full, cached, atol=1e-6)


def test_static_features_change_predictions_unless_ablated():
    torch.manual_seed(0)
    x_enc, x_dec = torch.randn(1, 8, 2), torch.randn(1, 4, 1)
    a, b = torch.zeros(1, 2), torch.ones(1, 2)
    for use_static, differs in ((True, True), (False, False)):
        model = EPSTFT(static_size=2, d_model=16, num_heads=2, num_quantiles=3,
                       use_static=use_static).eval()
        with torch.no_grad():
            pa, _ = model(a, x_enc, x_dec)
            pb, _ = model(b, x_enc, x_dec)
        assert (not torch.allclose(pa, pb)) == differs


def test_model_overfits_tiny_batch():
    torch.manual_seed(0)
    model = EPSTFT(static_size=2, d_model=16, num_heads=2, num_quantiles=3, dropout=0.0)
    static, x_enc, x_dec = torch.randn(8, 2), torch.randn(8, 8, 2), torch.randn(8, 4, 1)
    target = torch.randn(8, 4)
    loss_fn = QuantileLoss([0.1, 0.5, 0.9])
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    first: float | None = None
    for _ in range(300):
        opt.zero_grad()
        loss = loss_fn(model(static, x_enc, x_dec)[0], target)
        loss.backward()
        opt.step()
        if first is None:
            first = loss.item()
    assert first is not None and loss.item() < 0.1 * first
