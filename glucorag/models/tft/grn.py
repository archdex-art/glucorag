import torch
import torch.nn as nn

from glucorag.models.tft.glu import GLU


class GRN(nn.Module):
    """
    Gated Residual Network.
    GRN(p, e) = LayerNorm(p + GLU(W_a * a + b_a))
    where a = ELU(W_p * p + W_e * e + b)
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        output_size: int | None = None,
        context_size: int | None = None,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.output_size = output_size if output_size is not None else input_size
        self.context_size = context_size

        self.linear_p = nn.Linear(input_size, hidden_size)
        if self.context_size is not None:
            self.linear_e = nn.Linear(self.context_size, hidden_size, bias=False)

        self.elu = nn.ELU()
        self.linear_a = nn.Linear(hidden_size, self.output_size)
        self.dropout = nn.Dropout(dropout)
        self.glu = GLU(self.output_size)
        
        # Skip connection projection if dimensions don't match
        if input_size != self.output_size:
            self.skip_proj = nn.Linear(input_size, self.output_size)
        else:
            self.skip_proj = nn.Identity()
            
        self.layer_norm = nn.LayerNorm(self.output_size)

    def forward(self, p: torch.Tensor, e: torch.Tensor | None = None) -> torch.Tensor:
        a = self.linear_p(p)
        if self.context_size is not None and e is not None:
            a = a + self.linear_e(e)
            
        a = self.elu(a)
        a = self.linear_a(a)
        a = self.dropout(a)
        
        out = self.glu(a)
        skip = self.skip_proj(p)
        return self.layer_norm(skip + out)
