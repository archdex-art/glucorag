import torch
import torch.nn as nn


class InterpretableMHSA(nn.Module):
    """Multi-head attention with a shared value projection and head-averaged weights (TFT)."""

    def __init__(self, d_model: int, num_heads: int, dropout: float = 0.0) -> None:
        super().__init__()
        if d_model % num_heads:
            raise ValueError("d_model must be divisible by num_heads")
        self.num_heads = num_heads
        self.d_k = d_model // num_heads
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, mask: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Return ``(output (B, Lq, d), attention (B, Lq, Lk))``; ``mask`` 0 = blocked."""
        b, lq, _ = q.shape
        lk = k.shape[1]
        qh = self.q_proj(q).view(b, lq, self.num_heads, self.d_k).transpose(1, 2)
        kh = self.k_proj(k).view(b, lk, self.num_heads, self.d_k).transpose(1, 2)
        scores = qh @ kh.transpose(-2, -1) / self.d_k**0.5
        if mask is not None:
            scores = scores.masked_fill(mask == 0, float("-inf"))
        attn = torch.softmax(scores, dim=-1).mean(dim=1)
        out = self.dropout(attn) @ self.v_proj(v)
        return self.out_proj(out), attn
