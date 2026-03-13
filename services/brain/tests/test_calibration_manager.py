"""Unit tests for CalibrationManager — session lifecycle and step validation."""
import time
import pytest

from calibration_manager import CalibrationManager, CalibrationSession, CALIBRATION_TIMEOUT_SEC


class TestSessionLifecycle:
    """Session creation, retrieval, and cleanup."""

    def test_start_creates_new_session(self):
        mgr = CalibrationManager()
        session = mgr.start_or_get("shelf_01")
        assert session.device_id == "shelf_01"
        assert session.step == "awaiting_tare"

    def test_start_returns_existing_session(self):
        mgr = CalibrationManager()
        s1 = mgr.start_or_get("shelf_01")
        s2 = mgr.start_or_get("shelf_01")
        assert s1 is s2

    def test_get_session_returns_none_when_no_session(self):
        mgr = CalibrationManager()
        assert mgr.get_session("nonexistent") is None

    def test_finish_removes_session(self):
        mgr = CalibrationManager()
        mgr.start_or_get("shelf_01")
        mgr.finish("shelf_01")
        assert mgr.get_session("shelf_01") is None

    def test_finish_nonexistent_is_noop(self):
        mgr = CalibrationManager()
        mgr.finish("nonexistent")  # Should not raise

    def test_expired_sessions_are_cleaned_up(self):
        mgr = CalibrationManager()
        session = mgr.start_or_get("shelf_01")
        # Force expiration
        session.started_at = time.time() - CALIBRATION_TIMEOUT_SEC - 1
        assert mgr.get_session("shelf_01") is None


class TestStepValidation:
    """Step ordering enforcement."""

    def test_tare_is_always_valid(self):
        mgr = CalibrationManager()
        is_valid, reason = mgr.validate_step("shelf_01", "tare")
        assert is_valid

    def test_set_known_weight_requires_session(self):
        mgr = CalibrationManager()
        is_valid, reason = mgr.validate_step("shelf_01", "set_known_weight")
        assert not is_valid
        assert "未開始" in reason

    def test_set_known_weight_requires_tare_done(self):
        mgr = CalibrationManager()
        mgr.start_or_get("shelf_01")
        # Session started but tare not yet done — step is awaiting_tare
        is_valid, reason = mgr.validate_step("shelf_01", "set_known_weight")
        assert not is_valid
        assert "awaiting_tare" in reason

    def test_set_known_weight_valid_after_tare(self):
        mgr = CalibrationManager()
        mgr.start_or_get("shelf_01")
        mgr.record_tare_done("shelf_01", {"status": "ok", "offset": 100.0})
        is_valid, reason = mgr.validate_step("shelf_01", "set_known_weight")
        assert is_valid

    def test_unknown_step_rejected(self):
        mgr = CalibrationManager()
        is_valid, reason = mgr.validate_step("shelf_01", "invalid_step")
        assert not is_valid
        assert "不明" in reason


class TestRecordResults:
    """Recording tare and calibration results."""

    def test_record_tare_advances_step(self):
        mgr = CalibrationManager()
        mgr.start_or_get("shelf_01")
        mgr.record_tare_done("shelf_01", {"status": "ok", "offset": 50.0})
        session = mgr.get_session("shelf_01")
        assert session.step == "awaiting_known_weight"
        assert session.tare_result == {"status": "ok", "offset": 50.0}

    def test_record_calibrate_marks_complete(self):
        mgr = CalibrationManager()
        mgr.start_or_get("shelf_01")
        mgr.record_tare_done("shelf_01", {"status": "ok"})
        mgr.record_calibrate_done("shelf_01", {"status": "ok", "scale": 420.5})
        session = mgr.get_session("shelf_01")
        assert session.step == "complete"
        assert session.calibrate_result["scale"] == 420.5

    def test_record_on_nonexistent_session_is_noop(self):
        mgr = CalibrationManager()
        mgr.record_tare_done("nonexistent", {"status": "ok"})  # Should not raise
        mgr.record_calibrate_done("nonexistent", {"status": "ok"})  # Should not raise


class TestMultipleDevices:
    """Independent sessions for different devices."""

    def test_independent_sessions(self):
        mgr = CalibrationManager()
        s1 = mgr.start_or_get("shelf_01")
        s2 = mgr.start_or_get("shelf_02")
        assert s1.device_id == "shelf_01"
        assert s2.device_id == "shelf_02"
        mgr.record_tare_done("shelf_01", {"status": "ok"})
        assert mgr.get_session("shelf_01").step == "awaiting_known_weight"
        assert mgr.get_session("shelf_02").step == "awaiting_tare"
