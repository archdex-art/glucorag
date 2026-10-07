import torch
import torch.nn as nn


class GLU(nn.Module):
    """
    Gated Linear Unit as defined in the TFT paper.
    GLU(z) = sigma(W_g * z + b_g) * (W_l * z + b_l)
    """

    def __init__(self, d_model: int, output_size: int | None = None) -> None:
        super().__init__()
        self.d_model = d_model
        self.output_size = output_size if output_size is not None else d_model
        # We can implement this efficiently with a single linear layer
        # that outputs twice the size, then split.
        self.linear = nn.Linear(self.d_model, self.output_size * 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.linear(x)
        # Split along the last dimension
        z_l, z_g = torch.chunk(out, 2, dim=-1)
        return z_l * torch.sigmoid(z_g)
