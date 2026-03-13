"""Unit tests for dashboard shopping router endpoints."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from conftest import MockResult, make_mock_db


# ── Helpers ──────────────────────────────────────────────────────


def _make_shopping_item(
    id=1,
    name="コーヒー",
    category="飲料",
    quantity=1,
    unit=None,
    store=None,
    price=500,
    is_purchased=False,
    is_recurring=False,
    recurrence_days=None,
    last_purchased_at=None,
    next_purchase_at=None,
    notes=None,
    priority=1,
    created_by="user",
    share_token=None,
):
    now = datetime.now(timezone.utc)

    class FakeItem:
        pass

    item = FakeItem()
    item.id = id
    item.name = name
    item.category = category
    item.quantity = quantity
    item.unit = unit
    item.store = store
    item.price = price
    item.is_purchased = is_purchased
    item.is_recurring = is_recurring
    item.recurrence_days = recurrence_days
    item.last_purchased_at = last_purchased_at
    item.next_purchase_at = next_purchase_at
    item.notes = notes
    item.priority = priority
    item.created_at = now
    item.purchased_at = None
    item.created_by = created_by
    item.share_token = share_token
    return item


_SHOPPING_REFRESH_DEFAULTS = {
    "is_purchased": False,
    "is_recurring": False,
    "quantity": 1,
    "priority": 1,
    "purchased_at": None,
    "share_token": None,
    "last_purchased_at": None,
    "created_by": "user",
    "notes": None,
    "unit": None,
    "store": None,
    "price": None,
    "category": None,
    "recurrence_days": None,
}


def _create_app():
    from routers import shopping

    app = FastAPI()
    app.include_router(shopping.router)
    return app


# ── Tests ────────────────────────────────────────────────────────


class TestListItems:
    def test_list_empty(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_items(self):
        items = [_make_shopping_item(id=1, name="牛乳"), _make_shopping_item(id=2, name="卵")]
        db = make_mock_db([MockResult(items)], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "牛乳"


class TestAddItem:
    @patch("routers.shopping._publish_shopping_event")
    def test_add_new_item(self, mock_publish):
        # First execute: check for duplicates (none found)
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.post("/shopping/", json={"name": "トイレットペーパー", "category": "日用品"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "トイレットペーパー"
        assert len(db._added) == 1

    @patch("routers.shopping._publish_shopping_event")
    def test_add_duplicate_merges_quantity(self, mock_publish):
        existing = _make_shopping_item(id=5, name="牛乳", quantity=1)
        db = make_mock_db([MockResult([existing])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.post("/shopping/", json={"name": "牛乳", "quantity": 2})
        assert resp.status_code == 201
        assert existing.quantity == 3  # 1 + 2
        assert len(db._added) == 0  # No new item created

    @patch("routers.shopping._publish_shopping_event")
    def test_add_duplicate_upgrades_priority(self, mock_publish):
        existing = _make_shopping_item(id=5, name="牛乳", priority=0)
        db = make_mock_db([MockResult([existing])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.post("/shopping/", json={"name": "牛乳", "priority": 2})
        assert resp.status_code == 201
        assert existing.priority == 2

    @patch("routers.shopping._publish_shopping_event")
    def test_add_recurring_sets_next_purchase(self, mock_publish):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.post("/shopping/", json={
            "name": "牛乳",
            "is_recurring": True,
            "recurrence_days": 7,
        })
        assert resp.status_code == 201
        # Verify the added object has next_purchase_at set
        assert len(db._added) == 1
        assert db._added[0].next_purchase_at is not None


class TestUpdateItem:
    def test_update_existing(self):
        item = _make_shopping_item(id=3, name="パン")
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.put("/shopping/3", json={"name": "食パン", "priority": 2})
        assert resp.status_code == 200
        assert item.name == "食パン"
        assert item.priority == 2

    def test_update_not_found(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.put("/shopping/999", json={"name": "x"})
        assert resp.status_code == 404


class TestPurchaseItem:
    @patch("routers.shopping._publish_shopping_event")
    def test_purchase_marks_complete(self, mock_publish):
        item = _make_shopping_item(id=1, name="牛乳", price=200)
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.put("/shopping/1/purchase")
        assert resp.status_code == 200
        assert item.is_purchased is True
        assert item.purchased_at is not None
        # Should add PurchaseHistory
        assert len(db._added) >= 1

    @patch("routers.shopping._publish_shopping_event")
    def test_purchase_recurring_creates_next(self, mock_publish):
        item = _make_shopping_item(
            id=1, name="牛乳", is_recurring=True, recurrence_days=7,
        )
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.put("/shopping/1/purchase")
        assert resp.status_code == 200
        # Should add both PurchaseHistory and next recurring item
        assert len(db._added) == 2

    def test_purchase_not_found(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.put("/shopping/999/purchase")
        assert resp.status_code == 404


class TestDeleteItem:
    def test_delete_existing(self):
        item = _make_shopping_item(id=1)
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.delete("/shopping/1")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        db.delete.assert_called_once()

    def test_delete_not_found(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.delete("/shopping/999")
        assert resp.status_code == 404


class TestStats:
    def test_get_stats(self):
        db = make_mock_db([
            MockResult(scalar_val=10),    # total
            MockResult(scalar_val=3),     # purchased
            MockResult(scalar_val=2500),  # monthly spent
            MockResult([("食品", 4), ("日用品", 3)]),  # category breakdown
        ], track_added=True, refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_items"] == 10
        assert data["purchased_items"] == 3
        assert data["pending_items"] == 7
        assert data["total_spent_this_month"] == 2500
        assert data["category_breakdown"]["食品"] == 4


class TestCategories:
    def test_list_categories(self):
        db = make_mock_db([MockResult([("食品",), ("日用品",)])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/categories")
        assert resp.status_code == 200
        assert "食品" in resp.json()


class TestStores:
    def test_list_stores(self):
        db = make_mock_db([MockResult([("コンビニ",), ("スーパー",)])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/stores")
        assert resp.status_code == 200
        assert "コンビニ" in resp.json()


class TestHistory:
    def test_get_history(self):
        class FakeHistory:
            id = 1
            item_name = "牛乳"
            category = "食品"
            store = "スーパー"
            price = 200
            quantity = 1
            purchased_at = datetime.now(timezone.utc)

        db = make_mock_db([MockResult([FakeHistory()])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/history?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["item_name"] == "牛乳"


class TestShareLink:
    def test_share_all_pending(self):
        items = [_make_shopping_item(id=1), _make_shopping_item(id=2)]
        db = make_mock_db([MockResult(items)], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.post("/shopping/0/share")
        assert resp.status_code == 200
        data = resp.json()
        assert "share_url" in data
        assert "token" in data
        assert len(data["items"]) == 2

    def test_share_no_pending(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.post("/shopping/0/share")
        assert resp.status_code == 404


class TestSharedList:
    def test_shared_list_valid_token(self):
        token_item = _make_shopping_item(id=1, share_token="abc123")
        all_pending = [_make_shopping_item(id=1), _make_shopping_item(id=2)]
        db = make_mock_db([MockResult([token_item]), MockResult(all_pending)],
                          track_added=True, refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/shared/abc123")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_shared_list_invalid_token(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/shared/invalid")
        assert resp.status_code == 404


class TestRecurring:
    def test_list_recurring(self):
        item = _make_shopping_item(id=1, is_recurring=True, recurrence_days=7)
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/recurring")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestDueItems:
    def test_list_due(self):
        item = _make_shopping_item(
            id=1, is_recurring=True, recurrence_days=7,
            next_purchase_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_SHOPPING_REFRESH_DEFAULTS)
        app = _create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        resp = client.get("/shopping/due")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
