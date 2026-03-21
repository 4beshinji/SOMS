"""Unit tests for ArUco marker endpoints in spatial router.

Tests GET /sensors/spatial/aruco and PUT /sensors/spatial/aruco.
"""
import os
import sys
import tempfile
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault("JWT_SECRET", "test_jwt_secret_dashboard_32b!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_service_token_for_unit_tests")

import pytest
import yaml
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_app():
    from routers.spatial import router
    app = FastAPI()
    app.include_router(router)
    return app


class TestGetArucoMarkers:
    """GET /sensors/spatial/aruco -- get markers from YAML."""

    def test_returns_empty_when_no_file(self):
        app = _create_app()
        client = TestClient(app)
        with patch("routers.spatial.os.path.exists", return_value=False):
            resp = client.get("/sensors/spatial/aruco")
        assert resp.status_code == 200
        assert resp.json() == {"aruco_markers": {}}

    def test_returns_empty_when_no_aruco_section(self):
        app = _create_app()
        client = TestClient(app)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"building": {"name": "test"}, "zones": {}}, f)
            tmp_path = f.name
        try:
            with patch("routers.spatial.SPATIAL_YAML_PATH", tmp_path):
                resp = client.get("/sensors/spatial/aruco")
            assert resp.status_code == 200
            assert resp.json() == {"aruco_markers": {}}
        finally:
            os.unlink(tmp_path)

    def test_returns_markers_from_yaml(self):
        app = _create_app()
        client = TestClient(app)
        yaml_content = {
            "aruco_markers": {
                "0": {"corners": [[1.0, 2.0], [1.1, 2.0], [1.1, 2.1], [1.0, 2.1]]},
                "1": {"corners": [[3.0, 4.0], [3.1, 4.0], [3.1, 4.1], [3.0, 4.1]]},
            }
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml_content, f)
            tmp_path = f.name
        try:
            with patch("routers.spatial.SPATIAL_YAML_PATH", tmp_path):
                resp = client.get("/sensors/spatial/aruco")
            assert resp.status_code == 200
            data = resp.json()
            assert "0" in data["aruco_markers"]
            assert "1" in data["aruco_markers"]
            assert len(data["aruco_markers"]["0"]["corners"]) == 4
        finally:
            os.unlink(tmp_path)


class TestSaveArucoMarkers:
    """PUT /sensors/spatial/aruco -- save markers to YAML."""

    def test_save_creates_aruco_section(self):
        app = _create_app()
        client = TestClient(app)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"building": {"name": "test"}, "zones": {}}, f)
            tmp_path = f.name
        try:
            import spatial_config as sc
            original = sc._cached_config
            with patch("routers.spatial.SPATIAL_YAML_PATH", tmp_path):
                resp = client.put("/sensors/spatial/aruco", json={
                    "aruco_markers": {
                        "0": {"corners": [[1.0, 2.0], [1.1, 2.0], [1.1, 2.1], [1.0, 2.1]]},
                    }
                })
            sc._cached_config = original
            assert resp.status_code == 200
            data = resp.json()
            assert data["saved"] == 1

            # Verify YAML was written
            with open(tmp_path, 'r') as f:
                written = yaml.safe_load(f)
            assert "aruco_markers" in written
            assert "0" in written["aruco_markers"]
            assert len(written["aruco_markers"]["0"]["corners"]) == 4
            # Verify zones preserved
            assert "zones" in written
        finally:
            os.unlink(tmp_path)

    def test_save_preserves_other_sections(self):
        app = _create_app()
        client = TestClient(app)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                "building": {"name": "test", "width_m": 10},
                "zones": {"zone_01": {"display_name": "Zone 1"}},
                "cameras": {"cam_01": {"zone": "main"}},
            }, f)
            tmp_path = f.name
        try:
            import spatial_config as sc
            original = sc._cached_config
            with patch("routers.spatial.SPATIAL_YAML_PATH", tmp_path):
                resp = client.put("/sensors/spatial/aruco", json={
                    "aruco_markers": {
                        "5": {"corners": [[5.0, 5.0], [5.1, 5.0], [5.1, 5.1], [5.0, 5.1]]},
                    }
                })
            sc._cached_config = original
            assert resp.status_code == 200

            with open(tmp_path, 'r') as f:
                written = yaml.safe_load(f)
            assert written["building"]["name"] == "test"
            assert "zone_01" in written["zones"]
            assert "cam_01" in written["cameras"]
        finally:
            os.unlink(tmp_path)

    def test_save_replaces_existing_markers(self):
        app = _create_app()
        client = TestClient(app)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                "building": {"name": "test"},
                "aruco_markers": {
                    "0": {"corners": [[0, 0], [0, 0], [0, 0], [0, 0]]},
                    "1": {"corners": [[1, 1], [1, 1], [1, 1], [1, 1]]},
                },
            }, f)
            tmp_path = f.name
        try:
            import spatial_config as sc
            original = sc._cached_config
            with patch("routers.spatial.SPATIAL_YAML_PATH", tmp_path):
                resp = client.put("/sensors/spatial/aruco", json={
                    "aruco_markers": {
                        "99": {"corners": [[9, 9], [9, 9], [9, 9], [9, 9]]},
                    }
                })
            sc._cached_config = original
            assert resp.status_code == 200

            with open(tmp_path, 'r') as f:
                written = yaml.safe_load(f)
            # Old markers should be gone, only new one
            assert "0" not in written["aruco_markers"]
            assert "1" not in written["aruco_markers"]
            assert "99" in written["aruco_markers"]
        finally:
            os.unlink(tmp_path)

    def test_save_empty_markers(self):
        app = _create_app()
        client = TestClient(app)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"building": {"name": "test"}}, f)
            tmp_path = f.name
        try:
            import spatial_config as sc
            original = sc._cached_config
            with patch("routers.spatial.SPATIAL_YAML_PATH", tmp_path):
                resp = client.put("/sensors/spatial/aruco", json={
                    "aruco_markers": {}
                })
            sc._cached_config = original
            assert resp.status_code == 200
            assert resp.json()["saved"] == 0
        finally:
            os.unlink(tmp_path)

    def test_save_validation_error(self):
        """Invalid corners format -> 422."""
        app = _create_app()
        client = TestClient(app)
        resp = client.put("/sensors/spatial/aruco", json={
            "aruco_markers": {
                "0": {"corners": "not-a-list"},
            }
        })
        assert resp.status_code == 422
