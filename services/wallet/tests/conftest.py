"""Shared fixtures and helpers for wallet service unit tests."""
import os
import sys
from pathlib import Path

# Ensure wallet/src is importable
_WALLET_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _WALLET_SRC not in sys.path:
    sys.path.insert(0, _WALLET_SRC)

# Set test-safe environment before imports
os.environ.setdefault("JWT_SECRET", "test_jwt_secret_wallet_32bytes!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_service_token_for_unit_tests")
