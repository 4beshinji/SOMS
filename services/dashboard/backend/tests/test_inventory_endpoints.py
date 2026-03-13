"""Unit tests for dashboard inventory router endpoints."""
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from conftest import MockResult, make_mock_db


# ── Helpers ──────────────────────────────────────────────────────


def _make_inventory_item(
    id=1,
    device_id="shelf_01",
    channel="weight",
    zone="kitchen",
    item_name="コーヒー豆",
    category="飲料",
    unit_weight_g=200.0,
    tare_weight_g=50.0,
    min_threshold=2,
    reorder_quantity=1,
    store=None,
    price=None,
    barcode=None,
    is_active=True,
):
    now = datetime.now(timezone.utc)

    class FakeItem:
        pass

    item = FakeItem()
    item.id = id
    item.device_id = device_id
    item.channel = channel
    item.zone = zone
    item.item_name = item_name
    item.category = category
    item.unit_weight_g = unit_weight_g
    item.tare_weight_g = tare_weight_g
    item.min_threshold = min_threshold
    item.reorder_quantity = reorder_quantity
    item.store = store
    item.price = price
    item.barcode = barcode
    item.is_active = is_active
    item.created_at = now
    item.updated_at = None
    return item


_INVENTORY_REFRESH_DEFAULTS = {
    "is_active": True,
    "channel": "weight",
    "tare_weight_g": 0.0,
    "min_threshold": 2,
    "reorder_quantity": 1,
    "store": None,
    "price": None,
    "barcode": None,
    "category": None,
    "updated_at": None,
}


def _create_app(db_override):
    from routers.inventory import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_override
    return app


# ── Tests ────────────────────────────────────────────────────────


class TestListInventoryItems:
    def test_list_empty(self):
        db = make_mock_db(track_added=True, refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/inventory/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_items(self):
        items = [_make_inventory_item(id=1), _make_inventory_item(id=2, item_name="コピー用紙")]
        db = make_mock_db([MockResult(items)], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/inventory/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["item_name"] == "コーヒー豆"

    def test_list_filter_by_zone(self):
        items = [_make_inventory_item(zone="kitchen")]
        db = make_mock_db([MockResult(items)], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/inventory/?zone=kitchen")
        assert resp.status_code == 200
        # Verify query was executed (mock returns items)
        assert len(resp.json()) == 1


class TestGetInventoryItem:
    def test_get_existing(self):
        item = _make_inventory_item()
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/inventory/1")
        assert resp.status_code == 200
        assert resp.json()["device_id"] == "shelf_01"

    def test_get_not_found(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/inventory/999")
        assert resp.status_code == 404


class TestCreateInventoryItem:
    def test_create_success(self):
        db = make_mock_db(track_added=True, refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        payload = {
            "device_id": "shelf_02",
            "zone": "main",
            "item_name": "コピー用紙",
            "unit_weight_g": 500.0,
            "tare_weight_g": 30.0,
            "min_threshold": 3,
        }
        resp = client.post("/inventory/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["device_id"] == "shelf_02"
        assert data["item_name"] == "コピー用紙"
        assert len(db._added) == 1

    def test_create_missing_required_field(self):
        db = make_mock_db(track_added=True, refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        payload = {"device_id": "shelf_02"}  # missing zone, item_name, unit_weight_g
        resp = client.post("/inventory/", json=payload)
        assert resp.status_code == 422

    def test_create_with_barcode(self):
        db = make_mock_db(track_added=True, refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        payload = {
            "device_id": "shelf_03",
            "zone": "kitchen",
            "item_name": "牛乳",
            "unit_weight_g": 1000.0,
            "barcode": "4901234567890",
        }
        resp = client.post("/inventory/", json=payload)
        assert resp.status_code == 201
        assert len(db._added) == 1


class TestUpdateInventoryItem:
    def test_update_success(self):
        item = _make_inventory_item()
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/inventory/1", json={"item_name": "ブレンド豆"})
        assert resp.status_code == 200
        assert item.item_name == "ブレンド豆"

    def test_update_not_found(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/inventory/999", json={"item_name": "test"})
        assert resp.status_code == 404

    def test_update_partial(self):
        item = _make_inventory_item(min_threshold=2, store="Amazon")
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/inventory/1", json={"min_threshold": 5})
        assert resp.status_code == 200
        assert item.min_threshold == 5
        assert item.store == "Amazon"  # unchanged


class TestDeleteInventoryItem:
    def test_delete_success(self):
        item = _make_inventory_item()
        db = make_mock_db([MockResult([item])], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.delete("/inventory/1")
        assert resp.status_code == 204

    def test_delete_not_found(self):
        db = make_mock_db([MockResult([])], track_added=True,
                          refresh_defaults=_INVENTORY_REFRESH_DEFAULTS)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.delete("/inventory/999")
        assert resp.status_code == 404
