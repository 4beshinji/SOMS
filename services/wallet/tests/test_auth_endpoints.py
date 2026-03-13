"""Unit tests for wallet auth-protected endpoints.

Tests the auth guard behavior on p2p-transfer, stakes/buy, and stakes/return.
Uses mocked DB and service dependencies to isolate the auth logic.
Parametrized over endpoint configs to avoid copy-paste patterns.
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


# ── Endpoint config for parametrization ──────────────────────────


def _create_app(db_mock, routers):
    """Create a FastAPI app with given routers and DB override."""
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_mock
    return app


# Each tuple: (path, method, body_template, user_id_field, routers, 403_message,
#               setup_for_success_fn)
# body_template uses user_id=USER_ID as placeholder; setup_for_success_fn
# returns (db, patches_context_managers) needed for authenticated success.

def _p2p_success_setup(user_id):
    """Setup mocks for a successful p2p-transfer."""
    wallet = _make_wallet(user_id=user_id, balance=10000)
    txn_id = uuid4()
    db = _mock_db_with_entries([_make_ledger_entry(txn_id, wallet_id=user_id)])
    patches = _p2p_patches(wallet, txn_id)
    return db, list(patches)


def _stakes_buy_success_setup(user_id):
    """Setup mocks for a successful stakes/buy."""
    db = _stakes_db(_make_device_mock())
    patches = [patch("routers.stakes.buy_shares",
                     return_value=_make_stake_mock(user_id=user_id))]
    return db, patches


def _stakes_return_success_setup(user_id):
    """Setup mocks for a successful stakes/return."""
    db = AsyncMock()
    patches = [patch("routers.stakes.return_shares", return_value=None)]
    return db, patches


ENDPOINTS = [
    pytest.param(
        "/transactions/p2p-transfer",
        {"from_user_id": None, "to_user_id": 2, "amount": 100},
        "from_user_id",
        [transactions_router],
        "Cannot transfer from another user's wallet",
        _p2p_success_setup,
        id="p2p-transfer",
    ),
    pytest.param(
        "/devices/dev1/stakes/buy",
        {"user_id": None, "shares": 10},
        "user_id",
        [stakes_router],
        "Cannot buy shares for another user",
        _stakes_buy_success_setup,
        id="stakes-buy",
    ),
    pytest.param(
        "/devices/dev1/stakes/return",
        {"user_id": None, "shares": 10},
        "user_id",
        [stakes_router],
        "Cannot return shares for another user",
        _stakes_return_success_setup,
        id="stakes-return",
    ),
]


def _make_body(template, user_id_field, user_id):
    """Fill in the user_id placeholder in the body template."""
    body = dict(template)
    body[user_id_field] = user_id
    return body


# ── Parametrized Auth Tests ──────────────────────────────────────


class TestEndpointAuth:
    """Auth guard behavior across all protected wallet endpoints."""

    @pytest.mark.parametrize(
        "path, body_template, user_id_field, routers, forbidden_msg, setup_fn",
        ENDPOINTS,
    )
    def test_unauthenticated_request_returns_401(
        self, path, body_template, user_id_field, routers, forbidden_msg, setup_fn,
    ):
        """No JWT -> 401."""
        db, patches = setup_fn(user_id=5)
        body = _make_body(body_template, user_id_field, 5)

        with _enter_patches(patches):
            app = _create_app(db, routers)
            client = TestClient(app)
            resp = client.post(path, json=body)
            assert resp.status_code == 401

    @pytest.mark.parametrize(
        "path, body_template, user_id_field, routers, forbidden_msg, setup_fn",
        ENDPOINTS,
    )
    def test_authenticated_matching_user_allowed(
        self, path, body_template, user_id_field, routers, forbidden_msg, setup_fn,
    ):
        """JWT user_id == body user_id -> no 403."""
        db, patches = setup_fn(user_id=5)
        body = _make_body(body_template, user_id_field, 5)

        with _enter_patches(patches):
            app = _create_app(db, routers)
            client = TestClient(app)
            resp = client.post(path, json=body, headers=_auth_header(sub=5))
            assert resp.status_code != 403

    @pytest.mark.parametrize(
        "path, body_template, user_id_field, routers, forbidden_msg, setup_fn",
        ENDPOINTS,
    )
    def test_authenticated_different_user_returns_403(
        self, path, body_template, user_id_field, routers, forbidden_msg, setup_fn,
    ):
        """JWT user_id != body user_id -> 403 Forbidden."""
        db = AsyncMock()
        body = _make_body(body_template, user_id_field, 1)
        app = _create_app(db, routers)
        client = TestClient(app)

        resp = client.post(path, json=body, headers=_auth_header(sub=99))
        assert resp.status_code == 403
        assert resp.json()["detail"] == forbidden_msg

    @pytest.mark.parametrize(
        "path, body_template, user_id_field, routers, forbidden_msg, setup_fn",
        ENDPOINTS,
    )
    def test_expired_token_returns_401(
        self, path, body_template, user_id_field, routers, forbidden_msg, setup_fn,
    ):
        """Expired JWT -> 401."""
        db, patches = setup_fn(user_id=5)
        body = _make_body(body_template, user_id_field, 5)

        with _enter_patches(patches):
            app = _create_app(db, routers)
            client = TestClient(app)
            headers = {"Authorization": f"Bearer {_make_token(sub=99, exp_delta_sec=-60)}"}
            resp = client.post(path, json=body, headers=headers)
            assert resp.status_code == 401


# ── Endpoint-specific edge cases ─────────────────────────────────


class TestP2PTransferEdgeCases:
    """Edge cases specific to p2p-transfer auth."""

    def test_invalid_token_returns_401(self):
        """Malformed JWT -> 401."""
        wallet = _make_wallet(user_id=1, balance=10000)
        txn_id = uuid4()
        db = _mock_db_with_entries([_make_ledger_entry(txn_id)])

        patches = _p2p_patches(wallet, txn_id)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            app = _create_app(db, [transactions_router])
            client = TestClient(app)
            resp = client.post(
                "/transactions/p2p-transfer",
                json={"from_user_id": 1, "to_user_id": 2, "amount": 100},
                headers={"Authorization": "Bearer invalid.jwt.token"},
            )
            assert resp.status_code == 401


class TestStakesReturnEdgeCases:
    """Edge cases specific to stakes/return auth."""

    def test_wrong_secret_returns_401(self):
        """Token signed with wrong secret -> 401."""
        db = AsyncMock()
        with patch("routers.stakes.return_shares", return_value=None):
            app = _create_app(db, [stakes_router])
            client = TestClient(app)
            resp = client.post(
                "/devices/dev1/stakes/return",
                json={"user_id": 5, "shares": 10},
                headers={"Authorization": f"Bearer {_make_token(sub=99, secret='wrong_secret_32bytes_longgggg!!')}"},
            )
            assert resp.status_code == 401


# ── Patch helper ─────────────────────────────────────────────────


import contextlib


@contextlib.contextmanager
def _enter_patches(patches):
    """Enter a list of patch context managers."""
    if not patches:
        yield
        return
    with patches[0]:
        with _enter_patches(patches[1:]):
            yield
