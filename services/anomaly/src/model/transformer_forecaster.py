"""Transformer-based time series forecaster (~70K params). Pure PyTorch fallback."""
import math

import torch
import torch.nn as nn


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term[: d_model // 2])
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1)]


class TransformerForecaster(nn.Module):
    def __init__(
        self,
        n_features: int = 22,
        d_model: int = 64,
        nhead: int = 4,
        n_layers: int = 2,
        horizon: int = 6,
        n_targets: int = 6,
    ):
        super().__init__()
        self.horizon = horizon
        self.n_targets = n_targets

        self.input_proj = nn.Linear(n_features, d_model)
        self.pos_enc = PositionalEncoding(d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 4,
            batch_first=True,
            dropout=0.1,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)

        self.output_proj = nn.Linear(d_model, horizon * n_targets)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: (batch, seq_len, n_features)

        Returns:
            (batch, horizon, n_targets)
        """
        h = self.input_proj(x)
        h = self.pos_enc(h)
        h = self.transformer(h)

        # Use last timestep for prediction
        out = self.output_proj(h[:, -1, :])
        return out.view(-1, self.horizon, self.n_targets)
