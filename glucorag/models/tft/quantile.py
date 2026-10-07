import torch
import torch.nn as nn
import torch.nn.functional as F  # noqa: N812


class QuantileLoss(nn.Module):
    """
    Quantile loss for multi-horizon forecasting.
    L = 1/tau * sum_i sum_q [ (1-q)(pred_i - target_i)+ + q(target_i - pred_i)+ ]
    """

    def __init__(self, quantiles: list[float]) -> None:
        super().__init__()
        self.quantiles = quantiles

    def forward(self, preds: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """
        Args:
            preds: (batch_size, horizon_steps, num_quantiles)
            target: (batch_size, horizon_steps)
        Returns:
            Scalar loss
        """
        # Expand target to match preds shape
        target = target.unsqueeze(-1)  # (batch_size, horizon_steps, 1)
        
        losses = []
        for i, q in enumerate(self.quantiles):
            pred_q = preds[..., i : i + 1]
            # Ramp function (x)+ = ReLU(x)
            diff1 = F.relu(pred_q - target)
            diff2 = F.relu(target - pred_q)
            loss_q = (1 - q) * diff1 + q * diff2
            losses.append(loss_q)
            
        total_loss = torch.cat(losses, dim=-1)
        # Average over batch and horizon steps, sum over quantiles
        return total_loss.sum(dim=-1).mean()
