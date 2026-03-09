"""Test configuration — mock ML dependencies before imports."""
import sys
from unittest.mock import MagicMock

import numpy as np


def _ensure_mock(module_name: str) -> MagicMock:
    """Install a MagicMock into sys.modules if the real module is absent."""
    if module_name not in sys.modules:
        mock = MagicMock()
        sys.modules[module_name] = mock
        return mock
    return sys.modules[module_name]


# Mock torch and submodules
_mock_torch = _ensure_mock("torch")
_mock_torch.FloatTensor = MagicMock(side_effect=lambda x: np.array(x, dtype=np.float32))
_mock_torch.no_grad = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
_ensure_mock("torch.nn")
_ensure_mock("torch.optim")

# Mock mamba_ssm
_ensure_mock("mamba_ssm")

# Mock paho.mqtt
_mock_mqtt = _ensure_mock("paho")
_ensure_mock("paho.mqtt")
_ensure_mock("paho.mqtt.client")

# Mock loguru
_mock_loguru = _ensure_mock("loguru")
_mock_logger = MagicMock()
_mock_loguru.logger = _mock_logger

# Mock sqlalchemy async
_ensure_mock("sqlalchemy")
_ensure_mock("sqlalchemy.ext")
_ensure_mock("sqlalchemy.ext.asyncio")
_ensure_mock("sqlalchemy.orm")
_ensure_mock("sqlalchemy.text")

# Ensure src is on path
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
