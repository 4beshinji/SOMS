"""Unit tests for wallet auth-protected endpoints.

Tests the auth guard behavior on p2p-transfer, stakes/buy, and stakes/return.
Uses mocked DB and service dependencies to isolate the auth logic.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Ensure wallet/src is importable
_WALLET_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _WALLET_SRC not in sys.path:
    sys.path.insert(0, _WALLET_SRC)

os.environ.setdefault("JWT_SECRET", "test_jwt_secret_wallet_32bytes!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jwt_auth import JWT_SECRET
from routers.transactions import router as transactions_router
from routers.stakes import router as stakes_router
from database import get_db


# ── Helpers ─────────────────────────────────────────────────────


def _make_token(sub=1, username="testuser", display_name="Test User",
                iss="soms-auth", exp_delta_sec=900, secret=None):
    payload = {
        "sub": str(sub),
        "username": username,
        "display_name": display_name,
        "iss": iss,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_delta_sec),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret or JWT_SECRET, algorithm="HS256")


def _auth_header(sub=1, **kwargs):
    """Build Authorization header dict for a given user."""
    return {"Authorization": f"Bearer {_make_token(sub=sub, **kwargs)}"}


def _make_wallet(user_id=1, balance=10000):
    w = MagicMock()
    w.user_id = user_id
    w.balance = balance
    return w


def _make_ledger_entry(txn_id, wallet_id=1, amount=100):
    """Create a mock LedgerEntry with all fields required by LedgerEntryResponse."""
    e = MagicMock()
    e.id = 1
    e.transaction_id = txn_id
    e.wallet_id = wallet_id
    e.amount = amount
    e.balance_after = 9900
    e.entry_type = "DEBIT"
    e.transaction_type = "P2P_TRANSFER"
    e.description = "test transfer"
    e.reference_id = None
    e.counterparty_wallet_id = None
    e.region_id = "local"
    e.created_at = datetime.now(timezone.utc)
    return e


def _mock_db_with_entries(entries):
    """Create an AsyncMock DB that returns given entries from execute().scalars().all()."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = entries
    mock_result.scalars.return_value = mock_scalars
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _p2p_patches(wallet, txn_id):
    """Context manager stack for patching p2p-transfer dependencies."""
    return (
        patch("routers.transactions.get_circulating", return_value=100000),
        patch("routers.transactions.calc_min_transfer", return_value=1),
        patch("routers.transactions.calc_fee", return_value=10),
        patch("routers.transactions.get_or_create_wallet", return_value=wallet),
        patch("routers.transactions.transfer", return_value=txn_id),
        patch("routers.transactions.burn", return_value=None),
    )


# ── P2P Transfer Auth Tests ────────────────────────────────────


class TestP2PTransferAuth:
    """Auth guard on POST /transactions/p2p-transfer."""

    def _create_app(self, db_mock):
        app = FastAPI()
        app.include_router(transactions_router)
        app.dependency_overrides[get_db] = lambda: db_mock
        return app

    def _run_p2p(self, client, from_user_id=1, to_user_id=2, amount=100, headers=None):
        return client.post(
            "/transactions/p2p-transfer",
            json={"from_user_id": from_user_id, "to_user_id": to_user_id, "amount": amount},
            headers=headers,
        )

    def test_unauthenticated_request_returns_401(self):
        """No JWT → 401 (require_auth rejects unauthenticated requests)."""
        wallet = _make_wallet(user_id=1, balance=10000)
        txn_id = uuid4()
        db = _mock_db_with_entries([_make_ledger_entry(txn_id)])

        patches = _p2p_patches(wallet, txn_id)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            app = self._create_app(db)
            client = TestClient(app)
            resp = self._run_p2p(client)
            assert resp.status_code == 401

    def test_authenticated_matching_user_allowed(self):
        """JWT user_id == from_user_id → no 403."""
        wallet = _make_wallet(user_id=5, balance=10000)
        txn_id = uuid4()
        db = _mock_db_with_entries([_make_ledger_entry(txn_id, wallet_id=5)])

        patches = _p2p_patches(wallet, txn_id)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            app = self._create_app(db)
            client = TestClient(app)
            resp = self._run_p2p(client, from_user_id=5, headers=_auth_header(sub=5))
            assert resp.status_code != 403

    def test_authenticated_different_user_returns_403(self):
        """JWT user_id != from_user_id → 403 Forbidden."""
        db = AsyncMock()
        app = self._create_app(db)
        client = TestClient(app)

        resp = self._run_p2p(client, from_user_id=1, headers=_auth_header(sub=99))
        assert resp.status_code == 403
        assert "Cannot transfer from another user" in resp.json()["detail"]

    def test_expired_token_returns_401(self):
        """Expired JWT → 401 (require_auth rejects expired tokens)."""
        wallet = _make_wallet(user_id=1, balance=10000)
        txn_id = uuid4()
        db = _mock_db_with_entries([_make_ledger_entry(txn_id)])

        patches = _p2p_patches(wallet, txn_id)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            app = self._create_app(db)
            client = TestClient(app)
            headers = {"Authorization": f"Bearer {_make_token(sub=99, exp_delta_sec=-60)}"}
            resp = self._run_p2p(client, headers=headers)
            assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        """Malformed JWT → 401."""
        wallet = _make_wallet(user_id=1, balance=10000)
        txn_id = uuid4()
        db = _mock_db_with_entries([_make_ledger_entry(txn_id)])

        patches = _p2p_patches(wallet, txn_id)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            app = self._create_app(db)
            client = TestClient(app)
            resp = self._run_p2p(client, headers={"Authorization": "Bearer invalid.jwt.token"})
            assert resp.status_code == 401

    def test_403_detail_message(self):
        """Verify the exact error message for user mismatch."""
        db = AsyncMock()
        app = self._create_app(db)
        client = TestClient(app)

        resp = self._run_p2p(client, from_user_id=10, headers=_auth_header(sub=30))
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Cannot transfer from another user's wallet"

    def test_self_transfer_with_auth_allowed(self):
        """Authenticated user transferring from their own wallet is allowed."""
        wallet = _make_wallet(user_id=42, balance=10000)
        txn_id = uuid4()
        db = _mock_db_with_entries([_make_ledger_entry(txn_id, wallet_id=42)])

        patches = _p2p_patches(wallet, txn_id)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            app = self._create_app(db)
            client = TestClient(app)
            resp = self._run_p2p(client, from_user_id=42, to_user_id=99,
                                 amount=50, headers=_auth_header(sub=42))
            assert resp.status_code != 403


# ── Stakes Buy Auth Tests ──────────────────────────────────────


def _make_stake_mock(device_id="dev1", user_id=5, shares=10):
    stake = MagicMock()
    stake.id = 1
    stake.device_id = device_id
    stake.user_id = user_id
    stake.shares = shares
    stake.acquired_at = datetime.now(timezone.utc)
    return stake


def _make_device_mock(total_shares=100):
    device = MagicMock()
    device.total_shares = total_shares
    return device


def _stakes_db(device):
    """Create AsyncMock DB for stakes endpoints (returns device from execute)."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = device
    mock_result.scalars.return_value = mock_scalars
    db.execute = AsyncMock(return_value=mock_result)
    return db


class TestStakesBuyAuth:
    """Auth guard on POST /devices/{device_id}/stakes/buy."""

    def _create_app(self, db_mock):
        app = FastAPI()
        app.include_router(stakes_router)
        app.dependency_overrides[get_db] = lambda: db_mock
        return app

    def test_unauthenticated_request_returns_401(self):
        """No JWT → 401 (require_auth rejects unauthenticated requests)."""
        db = _stakes_db(_make_device_mock())
        with patch("routers.stakes.buy_shares", return_value=_make_stake_mock()):
            app = self._create_app(db)
            client = TestClient(app)
            resp = client.post("/devices/dev1/stakes/buy", json={"user_id": 5, "shares": 10})
            assert resp.status_code == 401

    def test_authenticated_matching_user_allowed(self):
        """JWT user_id == body.user_id → no 403."""
        db = _stakes_db(_make_device_mock())
        with patch("routers.stakes.buy_shares", return_value=_make_stake_mock()):
            app = self._create_app(db)
            client = TestClient(app)
            resp = client.post("/devices/dev1/stakes/buy",
                               json={"user_id": 5, "shares": 10},
                               headers=_auth_header(sub=5))
            assert resp.status_code != 403

    def test_authenticated_different_user_returns_403(self):
        """JWT user_id != body.user_id → 403."""
        db = AsyncMock()
        app = self._create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/dev1/stakes/buy",
                           json={"user_id": 5, "shares": 10},
                           headers=_auth_header(sub=99))
        assert resp.status_code == 403
        assert "Cannot buy shares for another user" in resp.json()["detail"]

    def test_expired_token_returns_401(self):
        """Expired JWT → 401 (require_auth rejects expired tokens)."""
        db = _stakes_db(_make_device_mock())
        with patch("routers.stakes.buy_shares", return_value=_make_stake_mock()):
            app = self._create_app(db)
            client = TestClient(app)
            resp = client.post("/devices/dev1/stakes/buy",
                               json={"user_id": 5, "shares": 10},
                               headers={"Authorization": f"Bearer {_make_token(sub=99, exp_delta_sec=-60)}"})
            assert resp.status_code == 401

    def test_403_exact_message(self):
        db = AsyncMock()
        app = self._create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/dev1/stakes/buy",
                           json={"user_id": 1, "shares": 5},
                           headers=_auth_header(sub=2))
        assert resp.json()["detail"] == "Cannot buy shares for another user"


# ── Stakes Return Auth Tests ───────────────────────────────────


class TestStakesReturnAuth:
    """Auth guard on POST /devices/{device_id}/stakes/return."""

    def _create_app(self, db_mock):
        app = FastAPI()
        app.include_router(stakes_router)
        app.dependency_overrides[get_db] = lambda: db_mock
        return app

    def test_unauthenticated_request_returns_401(self):
        """No JWT → 401 (require_auth rejects unauthenticated requests)."""
        db = AsyncMock()
        with patch("routers.stakes.return_shares", return_value=None):
            app = self._create_app(db)
            client = TestClient(app)
            resp = client.post("/devices/dev1/stakes/return",
                               json={"user_id": 5, "shares": 10})
            assert resp.status_code == 401

    def test_authenticated_matching_user_allowed(self):
        """JWT user_id == body.user_id → no 403."""
        db = AsyncMock()
        with patch("routers.stakes.return_shares", return_value=None):
            app = self._create_app(db)
            client = TestClient(app)
            resp = client.post("/devices/dev1/stakes/return",
                               json={"user_id": 5, "shares": 10},
                               headers=_auth_header(sub=5))
            assert resp.status_code != 403

    def test_authenticated_different_user_returns_403(self):
        """JWT user_id != body.user_id → 403."""
        db = AsyncMock()
        app = self._create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/dev1/stakes/return",
                           json={"user_id": 5, "shares": 10},
                           headers=_auth_header(sub=99))
        assert resp.status_code == 403
        assert "Cannot return shares for another user" in resp.json()["detail"]

    def test_expired_token_returns_401(self):
        """Expired JWT → 401 (require_auth rejects expired tokens)."""
        db = AsyncMock()
        with patch("routers.stakes.return_shares", return_value=None):
            app = self._create_app(db)
            client = TestClient(app)
            resp = client.post("/devices/dev1/stakes/return",
                               json={"user_id": 5, "shares": 10},
                               headers={"Authorization": f"Bearer {_make_token(sub=99, exp_delta_sec=-60)}"})
            assert resp.status_code == 401

    def test_wrong_secret_returns_401(self):
        """Token signed with wrong secret → 401."""
        db = AsyncMock()
        with patch("routers.stakes.return_shares", return_value=None):
            app = self._create_app(db)
            client = TestClient(app)
            resp = client.post("/devices/dev1/stakes/return",
                               json={"user_id": 5, "shares": 10},
                               headers={"Authorization": f"Bearer {_make_token(sub=99, secret='wrong_secret_32bytes_longgggg!!')}"})
            assert resp.status_code == 401

    def test_403_exact_message(self):
        db = AsyncMock()
        app = self._create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/dev1/stakes/return",
                           json={"user_id": 1, "shares": 5},
                           headers=_auth_header(sub=2))
        assert resp.json()["detail"] == "Cannot return shares for another user"


# ── Cross-Endpoint Consistency ─────────────────────────────────


class TestAuthConsistency:
    """Verify all three wallet endpoints enforce auth the same way."""

    def test_all_endpoints_reject_mismatched_user(self):
        """All three auth-protected endpoints should return 403 for user mismatch."""
        db = AsyncMock()
        app = FastAPI()
        app.include_router(transactions_router)
        app.include_router(stakes_router)
        app.dependency_overrides[get_db] = lambda: db

        client = TestClient(app)
        headers = _auth_header(sub=999)

        resp1 = client.post("/transactions/p2p-transfer",
                            json={"from_user_id": 1, "to_user_id": 2, "amount": 100},
                            headers=headers)
        assert resp1.status_code == 403

        resp2 = client.post("/devices/dev1/stakes/buy",
                            json={"user_id": 1, "shares": 5},
                            headers=headers)
        assert resp2.status_code == 403

        resp3 = client.post("/devices/dev1/stakes/return",
                            json={"user_id": 1, "shares": 5},
                            headers=headers)
        assert resp3.status_code == 403

    def test_all_endpoints_allow_matching_user(self):
        """All three auth-protected endpoints should pass for matching user."""
        wallet = _make_wallet(user_id=7, balance=10000)
        txn_id = uuid4()
        device = _make_device_mock()
        stake = _make_stake_mock(user_id=7)
        entry = _make_ledger_entry(txn_id, wallet_id=7)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [entry]
        mock_scalars.first.return_value = device
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        app = FastAPI()
        app.include_router(transactions_router)
        app.include_router(stakes_router)
        app.dependency_overrides[get_db] = lambda: db

        client = TestClient(app)
        headers = _auth_header(sub=7)

        patches = _p2p_patches(wallet, txn_id)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("routers.stakes.buy_shares", return_value=stake), \
             patch("routers.stakes.return_shares", return_value=None):

            resp1 = client.post("/transactions/p2p-transfer",
                                json={"from_user_id": 7, "to_user_id": 2, "amount": 100},
                                headers=headers)
            assert resp1.status_code != 403

            resp2 = client.post("/devices/dev1/stakes/buy",
                                json={"user_id": 7, "shares": 5},
                                headers=headers)
            assert resp2.status_code != 403

            resp3 = client.post("/devices/dev1/stakes/return",
                                json={"user_id": 7, "shares": 5},
                                headers=headers)
            assert resp3.status_code != 403
