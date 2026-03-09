"""Mamba SSM-based time series forecaster (~50K params)."""
import torch
import torch.nn as nn
from mamba_ssm import Mamba


class MambaForecaster(nn.Module):
    def __init__(
        self,
        n_features: int = 22,
        d_model: int = 64,
        d_state: int = 16,
        n_layers: int = 2,
        horizon: int = 6,
        n_targets: int = 6,
    ):
        super().__init__()
        self.horizon = horizon
        self.n_targets = n_targets

        self.input_proj = nn.Linear(n_features, d_model)

        self.mamba_layers = nn.ModuleList(
            [
                Mamba(d_model=d_model, d_state=d_state, d_conv=4, expand=2)
                for _ in range(n_layers)
            ]
        )
        self.layer_norms = nn.ModuleList(
            [nn.LayerNorm(d_model) for _ in range(n_layers)]
        )

        self.output_proj = nn.Linear(d_model, horizon * n_targets)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: (batch, seq_len, n_features)

        Returns:
            (batch, horizon, n_targets)
        """
        h = self.input_proj(x)

        for mamba, norm in zip(self.mamba_layers, self.layer_norms):
            h = h + mamba(norm(h))

        # Use last timestep for prediction
        out = self.output_proj(h[:, -1, :])
        return out.view(-1, self.horizon, self.n_targets)
