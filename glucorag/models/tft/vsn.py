import torch
import torch.nn as nn

from glucorag.models.tft.grn import GRN


class VSN(nn.Module):
    """
    Variable Selection Network.
    Calculates variable selection weights and applies them to the inputs.
    """

    def __init__(
        self,
        num_vars: int,
        d_model: int,
        context_size: int | None = None,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.num_vars = num_vars
        self.d_model = d_model

        # Variable-specific GRNs to transform each variable individually
        self.single_var_grns = nn.ModuleList(
            [GRN(d_model, d_model, dropout=dropout) for _ in range(num_vars)]
        )

        # GRN to compute the selection weights based on flattened inputs and optional context
        self.flattened_grn = GRN(
            num_vars * d_model,
            d_model,
            output_size=num_vars,
            context_size=context_size,
            dropout=dropout,
        )
        self.softmax = nn.Softmax(dim=-1)
    def forward(
        self, x: torch.Tensor, context: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: Tensor of shape (batch, time, num_vars, d_model)
            context: Optional static context of shape (batch, context_size)
                     or (batch, 1, context_size).
        Returns:
            processed_x: Tensor of shape (batch, time, d_model)
            weights: Tensor of shape (batch, time, num_vars)
        """
        # x is (batch, time, num_vars, d_model)
        batch_size, time_steps, _, _ = x.shape
        
        # Compute variable weights
        flattened = x.view(batch_size, time_steps, -1)
        if context is not None and context.dim() == 2:
            # (batch, context_size) -> (batch, 1, context_size)
            context = context.unsqueeze(1)
            
        weight_logits = self.flattened_grn(flattened, context)
        weights = self.softmax(weight_logits) # (batch, time, num_vars)

        # Process each variable through its own GRN
        processed_vars = []
        for i in range(self.num_vars):
            var_x = x[:, :, i, :] # (batch, time, d_model)
            processed_vars.append(self.single_var_grns[i](var_x))
            
        # Stack back to (batch, time, num_vars, d_model)
        processed_vars_tensor = torch.stack(processed_vars, dim=2)
        
        # Apply weights: sum_j weights_j * processed_j
        weights_expanded = weights.unsqueeze(-1) # (batch, time, num_vars, 1)
        out = torch.sum(weights_expanded * processed_vars_tensor, dim=2)
        
        return out, weights
