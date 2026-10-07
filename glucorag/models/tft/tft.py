"""EPS-TFT: Temporal Fusion Transformer for population-specific glucose forecasting."""

from typing import NamedTuple

import torch
import torch.nn as nn

from glucorag.models.tft.glu import GLU
from glucorag.models.tft.grn import GRN
from glucorag.models.tft.mhsa import InterpretableMHSA
from glucorag.models.tft.vsn import VSN


class StaticContext(NamedTuple):
    """Covariate-encoder outputs; precomputable once per patient (architecture D4)."""

    c_s: torch.Tensor  # variable selection
    c_e: torch.Tensor  # static enrichment
    c_c: torch.Tensor  # LSTM initial cell state
    c_h: torch.Tensor  # LSTM initial hidden state

    def to(self, device: torch.device) -> "StaticContext":
        return StaticContext(*(t.to(device) for t in self))

    def expand(self, batch: int) -> "StaticContext":
        return StaticContext(*(t.expand(batch, -1) for t in self))


class EPSTFT(nn.Module):
    def __init__(
        self,
        static_size: int = 4,
        d_model: int = 64,
        num_heads: int = 4,
        num_quantiles: int = 7,
        dropout: float = 0.1,
        use_static: bool = True,
        use_decoder: bool = True,
    ) -> None:
        """``use_static``/``use_decoder`` = False reproduce the paper's ablations."""
        super().__init__()
        self.d_model = d_model
        self.use_static = use_static
        self.use_decoder = use_decoder

        self.static_proj = nn.Linear(static_size, d_model)
        self.static_cs = GRN(d_model, d_model, dropout=dropout)
        self.static_ce = GRN(d_model, d_model, dropout=dropout)
        self.static_cc = GRN(d_model, d_model, dropout=dropout)
        self.static_ch = GRN(d_model, d_model, dropout=dropout)

        self.past_cgm_proj = nn.Linear(1, d_model)
        self.past_time_proj = nn.Linear(1, d_model)
        self.future_time_proj = nn.Linear(1, d_model)

        self.encoder_vsn = VSN(num_vars=2, d_model=d_model, context_size=d_model, dropout=dropout)
        self.decoder_vsn = VSN(num_vars=1, d_model=d_model, context_size=d_model, dropout=dropout)

        self.lstm_encoder = nn.LSTM(d_model, d_model, batch_first=True)
        self.lstm_decoder = nn.LSTM(d_model, d_model, batch_first=True)
        self.lstm_skip_glu = GLU(d_model)
        self.lstm_ln = nn.LayerNorm(d_model)

        self.static_enrichment = GRN(d_model, d_model, context_size=d_model, dropout=dropout)

        self.mhsa = InterpretableMHSA(d_model, num_heads, dropout=dropout)
        self.mhsa_skip_glu = GLU(d_model)
        self.mhsa_ln = nn.LayerNorm(d_model)

        self.ffn = GRN(d_model, d_model, dropout=dropout)
        self.ffn_skip_glu = GLU(d_model)
        self.ffn_ln = nn.LayerNorm(d_model)

        self.quantile_head = nn.Linear(d_model, num_quantiles)

    def encode_static(self, static: torch.Tensor) -> StaticContext:
        """static: (B, static_size) -> four (B, d_model) context vectors."""
        if not self.use_static:
            z = torch.zeros(static.shape[0], self.d_model, device=static.device)
            return StaticContext(z, z, z, z)
        s = self.static_proj(static)
        return StaticContext(
            self.static_cs(s), self.static_ce(s), self.static_cc(s), self.static_ch(s)
        )

    def forward(
        self, static: torch.Tensor, x_enc: torch.Tensor, x_dec: torch.Tensor
    ) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        return self.forward_with_context(self.encode_static(static), x_enc, x_dec)

    def forward_with_context(
        self, ctx: StaticContext, x_enc: torch.Tensor, x_dec: torch.Tensor
    ) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        """
        x_enc: (B, L, 2) [glucose_z, time_norm]; x_dec: (B, H, 1) [time_norm].
        Returns quantile predictions (B, H, Q) in normalized glucose units and
        interpretation tensors (VSN weights, attention).
        """
        lookback = x_enc.shape[1]
        past = torch.stack(
            [self.past_cgm_proj(x_enc[:, :, 0:1]), self.past_time_proj(x_enc[:, :, 1:2])], dim=2
        )
        future = self.future_time_proj(x_dec[:, :, 0:1]).unsqueeze(2)

        enc_feat, enc_w = self.encoder_vsn(past, ctx.c_s)
        dec_feat, dec_w = self.decoder_vsn(future, ctx.c_s)

        state = (ctx.c_h.unsqueeze(0).contiguous(), ctx.c_c.unsqueeze(0).contiguous())
        enc_out, enc_state = self.lstm_encoder(enc_feat, state)
        if self.use_decoder:
            dec_out, _ = self.lstm_decoder(dec_feat, enc_state)
        else:
            dec_out = dec_feat
        lstm_out = torch.cat([enc_out, dec_out], dim=1)
        vsn_feat = torch.cat([enc_feat, dec_feat], dim=1)
        temporal = self.lstm_ln(vsn_feat + self.lstm_skip_glu(lstm_out))

        enriched = self.static_enrichment(temporal, ctx.c_e.unsqueeze(1))

        seq_len = enriched.shape[1]
        causal = torch.ones(seq_len, seq_len, device=enriched.device).tril()
        attn_out, attn = self.mhsa(enriched, enriched, enriched, mask=causal)
        attn_out = self.mhsa_ln(enriched + self.mhsa_skip_glu(attn_out))

        ffn_out = self.ffn(attn_out)
        out = self.ffn_ln(temporal + self.ffn_skip_glu(ffn_out))

        preds = self.quantile_head(out[:, lookback:, :])
        return preds, {
            "encoder_vsn_weights": enc_w,
            "decoder_vsn_weights": dec_w,
            "attention": attn[:, lookback:, :],
        }
