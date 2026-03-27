"""Unit tests for ActivityModeManager."""
import time
from unittest.mock import MagicMock, patch

import pytest

from conftest import make_zone_state

# Patch env vars before import
import os
os.environ.setdefault("INACTIVE_CONFIRM_SECONDS", "300")
os.environ.setdefault("INACTIVE_LLM_COOLDOWN", "1800")

from activity_mode import ActivityModeManager, ActivityMode


def _make_world_model(zones_dict):
    """Create a mock WorldModel with .zones attribute."""
    wm = MagicMock()
    wm.zones = zones_dict
    return wm


class TestModeTransitions:
    """Test NORMAL <-> INACTIVE transitions."""

    def test_initial_mode_is_normal(self):
        mgr = ActivityModeManager()
        assert mgr.mode == ActivityMode.NORMAL
        assert not mgr.is_inactive

    def test_stays_normal_when_people_present(self):
        mgr = ActivityModeManager()
        wm = _make_world_model({
            "zone_a": make_zone_state(person_count=1),
        })
        changed = mgr.evaluate(wm)
        assert not changed
        assert mgr.mode == ActivityMode.NORMAL

    def test_stays_normal_when_empty_less_than_confirm(self):
        mgr = ActivityModeManager()
        zone = make_zone_state(person_count=0)
        zone.last_update = time.time()
        wm = _make_world_model({"zone_a": zone})

        changed = mgr.evaluate(wm)
        assert not changed
        assert mgr.mode == ActivityMode.NORMAL

    def test_transitions_to_inactive_after_confirm_period(self):
        mgr = ActivityModeManager()
        zone = make_zone_state(person_count=0)
        zone.last_update = time.time()
        wm = _make_world_model({"zone_a": zone})

        # First evaluation: starts empty timer
        mgr.evaluate(wm)
        assert mgr.mode == ActivityMode.NORMAL

        # Simulate time passage beyond INACTIVE_CONFIRM_SECONDS
        mgr._empty_since = time.time() - 301
        changed = mgr.evaluate(wm)
        assert changed
        assert mgr.mode == ActivityMode.INACTIVE
        assert mgr.is_inactive

    def test_transitions_back_to_normal_when_person_appears(self):
        mgr = ActivityModeManager()
        mgr._mode = ActivityMode.INACTIVE

        wm = _make_world_model({
            "zone_a": make_zone_state(person_count=1),
        })
        changed = mgr.evaluate(wm)
        assert changed
        assert mgr.mode == ActivityMode.NORMAL
        assert not mgr.is_inactive

    def test_empty_since_resets_when_person_appears_during_countdown(self):
        mgr = ActivityModeManager()
        zone = make_zone_state(person_count=0)
        zone.last_update = time.time()
        wm = _make_world_model({"zone_a": zone})

        # Start countdown
        mgr.evaluate(wm)
        assert mgr._empty_since is not None

        # Person appears
        zone2 = make_zone_state(person_count=1)
        zone2.last_update = time.time()
        wm2 = _make_world_model({"zone_a": zone2})
        mgr.evaluate(wm2)
        assert mgr._empty_since is None

    def test_no_transition_without_fresh_occupancy_data(self):
        mgr = ActivityModeManager()
        zone = make_zone_state(person_count=0)
        zone.last_update = 0  # No fresh data
        wm = _make_world_model({"zone_a": zone})

        mgr.evaluate(wm)
        assert mgr._empty_since is None  # Should not start countdown


class TestCycleInterval:
    """Test dynamic cycle interval properties."""

    def test_normal_mode_intervals(self):
        mgr = ActivityModeManager()
        assert mgr.cycle_interval == 30
        assert mgr.min_cycle_interval == 25

    def test_inactive_mode_intervals(self):
        mgr = ActivityModeManager()
        mgr._mode = ActivityMode.INACTIVE
        assert mgr.cycle_interval == 300
        assert mgr.min_cycle_interval == 60


class TestLLMThrottling:
    """Test LLM call throttling in inactive mode."""

    def test_always_allows_in_normal_mode(self):
        mgr = ActivityModeManager()
        assert mgr.allow_llm_call()

    def test_allows_first_call_in_inactive_mode(self):
        mgr = ActivityModeManager()
        mgr._mode = ActivityMode.INACTIVE
        mgr._last_llm_call = 0.0
        assert mgr.allow_llm_call()

    def test_blocks_during_cooldown(self):
        mgr = ActivityModeManager()
        mgr._mode = ActivityMode.INACTIVE
        mgr._last_llm_call = time.time()  # Just called
        assert not mgr.allow_llm_call()

    def test_allows_after_cooldown(self):
        mgr = ActivityModeManager()
        mgr._mode = ActivityMode.INACTIVE
        mgr._last_llm_call = time.time() - 1801  # Over 30 min ago
        assert mgr.allow_llm_call()

    def test_record_updates_timestamp(self):
        mgr = ActivityModeManager()
        before = time.time()
        mgr.record_llm_call()
        assert mgr._last_llm_call >= before

    def test_seconds_until_allowed(self):
        mgr = ActivityModeManager()
        mgr._mode = ActivityMode.INACTIVE
        mgr._last_llm_call = time.time() - 1700  # 100 seconds remaining
        remaining = mgr.seconds_until_llm_allowed()
        assert 95 <= remaining <= 105


class TestGetStatus:
    """Test status reporting."""

    def test_status_dict(self):
        mgr = ActivityModeManager()
        status = mgr.get_status()
        assert status["mode"] == "normal"
        assert "cycle_interval_sec" in status
        assert "llm_cooldown_remaining_sec" in status
