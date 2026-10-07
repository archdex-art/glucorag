"""Batched EPS-TFT inference over prepared windows, keeping interpretation tensors."""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import torch

from glucorag.models.tft.tft import EPSTFT
from glucorag.preprocess.normalize import ZNormalizer
from glucorag.preprocess.windows import Windows

FloatArray = npt.NDArray[np.float32]


@dataclass(frozen=True)
class TFTOutputs:
    quantiles_mg_dl: FloatArray  # (N, H, Q), sorted along Q
    median_mg_dl: FloatArray  # (N, H): the 0.5 quantile, used as the point forecast
    encoder_vsn: FloatArray  # (N, L, V) encoder variable-selection weights
    attention: FloatArray  # (N, H, L + H) decoder-step attention over all positions


@torch.no_grad()
def predict_tft(
    model: EPSTFT,
    windows: Windows,
    static: FloatArray,
    glucose_norm: ZNormalizer,
    quantiles: list[float],
    batch_size: int = 1024,
    device: str | torch.device = "cpu",
) -> TFTOutputs:
    if 0.5 not in quantiles:
        raise ValueError("Point forecasts need the 0.5 quantile")
    model.to(device).eval()
    preds, vsn, attn = [], [], []
    for start in range(0, len(windows), batch_size):
        sl = slice(start, start + batch_size)
        p, interp = model(
            torch.from_numpy(static[sl]).to(device),
            torch.from_numpy(windows.x_enc[sl]).to(device),
            torch.from_numpy(windows.x_dec[sl]).to(device),
        )
        preds.append(p.cpu().numpy())
        vsn.append(interp["encoder_vsn_weights"].cpu().numpy())
        attn.append(interp["attention"].cpu().numpy())
    if not preds:
        raise ValueError("No windows to predict")
    q = np.sort(glucose_norm.inverse_transform(np.concatenate(preds)), axis=-1)
    return TFTOutputs(
        quantiles_mg_dl=q.astype(np.float32),
        median_mg_dl=q[:, :, quantiles.index(0.5)].astype(np.float32),
        encoder_vsn=np.concatenate(vsn).astype(np.float32),
        attention=np.concatenate(attn).astype(np.float32),
    )
