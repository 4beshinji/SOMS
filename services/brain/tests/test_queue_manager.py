"""Unit tests for brain queue_manager — task priority scoring and queue management."""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import make_zone_state, make_mock_world_model, make_mock_dashboard_client
from task_scheduling.priority import TaskUrgency, QueuedTask
from task_scheduling.decision import TaskDispatchDecision
from task_scheduling.queue_manager import TaskQueueManager


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def now():
    return time.time()


@pytest.fixture
def make_task(now):
    """Factory to create QueuedTask instances."""
    def _make(
        task_id=1,
        title="Test task",
        urgency=2,
        zone="main",
        created_at=None,
        deadline=None,
    ):
        return QueuedTask(
            task_id=task_id,
            title=title,
            urgency=TaskUrgency(urgency),
            zone=zone,
            min_people_required=1,
            estimated_duration=10,
            created_at=created_at or now,
            deadline=deadline,
        )
    return _make


# ── QueuedTask priority computation ──────────────────────────────


class TestQueuedTaskPriority:
    """Priority scoring for individual tasks."""

    def test_higher_urgency_higher_priority(self, make_task, now):
        low = make_task(urgency=1, created_at=now)
        high = make_task(urgency=3, created_at=now)
        assert high.compute_priority() > low.compute_priority()

    def test_critical_highest_priority(self, make_task, now):
        critical = make_task(urgency=4, created_at=now)
        assert critical.compute_priority() >= 4000

    def test_deferred_lowest_base_priority(self, make_task, now):
        deferred = make_task(urgency=0, created_at=now)
        # Base priority is 0 * 1000 = 0, plus small age component
        assert deferred.compute_priority() < 100

    def test_age_increases_priority(self, make_task, now):
        fresh = make_task(urgency=2, created_at=now)
        old = make_task(urgency=2, created_at=now - 7200)  # 2 hours old
        assert old.compute_priority() > fresh.compute_priority()

    def test_deadline_within_2_hours_bonus(self, make_task, now):
        no_deadline = make_task(urgency=2, created_at=now)
        tight_deadline = make_task(urgency=2, created_at=now, deadline=now + 3600)
        assert tight_deadline.compute_priority() > no_deadline.compute_priority()

    def test_deadline_within_6_hours_smaller_bonus(self, make_task, now):
        no_deadline = make_task(urgency=2, created_at=now)
        medium_deadline = make_task(urgency=2, created_at=now, deadline=now + 4 * 3600)
        assert medium_deadline.compute_priority() > no_deadline.compute_priority()
        # But less bonus than <2h deadline
        tight_deadline = make_task(urgency=2, created_at=now, deadline=now + 3600)
        assert tight_deadline.compute_priority() > medium_deadline.compute_priority()

    def test_deadline_far_away_no_bonus(self, make_task, now):
        no_deadline = make_task(urgency=2, created_at=now)
        far_deadline = make_task(urgency=2, created_at=now, deadline=now + 24 * 3600)
        # Both have same base + age, far deadline adds no bonus
        assert abs(far_deadline.compute_priority() - no_deadline.compute_priority()) < 1.0


# ── QueuedTask staleness ─────────────────────────────────────────


class TestQueuedTaskStale:
    """Staleness check for aging tasks."""

    def test_fresh_task_not_stale(self, make_task, now):
        task = make_task(created_at=now)
        assert task.is_stale(max_age_hours=24) is False

    def test_old_task_is_stale(self, make_task, now):
        task = make_task(created_at=now - 25 * 3600)
        assert task.is_stale(max_age_hours=24) is True

    def test_custom_staleness_threshold(self, make_task, now):
        task = make_task(created_at=now - 3700)  # ~1 hour old
        assert task.is_stale(max_age_hours=1) is True
        assert task.is_stale(max_age_hours=2) is False


# ── QueuedTask comparison ────────────────────────────────────────


class TestQueuedTaskComparison:
    """__lt__ comparison for heap ordering."""

    def test_higher_priority_is_less_than(self, make_task, now):
        """Higher priority should be 'less than' for min-heap to pop it first."""
        high = make_task(urgency=4, created_at=now)
        low = make_task(urgency=1, created_at=now)
        assert high < low  # higher priority is "less" for heap


# ── TaskDispatchDecision ──────────────────────────────────────────


class TestTaskDispatchDecision:
    """Dispatch decision rules."""

    def test_critical_always_dispatches(self):
        wm = make_mock_world_model()
        decision = TaskDispatchDecision(wm)
        should, reason = decision.should_dispatch_now(urgency=4, zone="main", min_people_required=1)
        assert should is True
        assert "Critical" in reason

    def test_no_zone_dispatches_immediately(self):
        wm = make_mock_world_model()
        decision = TaskDispatchDecision(wm)
        should, reason = decision.should_dispatch_now(urgency=2, zone=None, min_people_required=1)
        assert should is True
        assert "No zone" in reason

    def test_unknown_zone_queued(self):
        wm = make_mock_world_model()  # no zones registered
        decision = TaskDispatchDecision(wm)
        should, reason = decision.should_dispatch_now(urgency=2, zone="nonexistent", min_people_required=1)
        assert should is False
        assert "not active" in reason

    def test_not_enough_people_queued(self):
        zone = make_zone_state(zone_id="main", person_count=1)
        wm = make_mock_world_model(zones={"main": zone})
        decision = TaskDispatchDecision(wm)
        should, reason = decision.should_dispatch_now(
            urgency=2, zone="main", min_people_required=3,
        )
        assert should is False
        assert "Not enough people" in reason

    def test_enough_people_dispatches(self):
        zone = make_zone_state(zone_id="main", person_count=3)
        wm = make_mock_world_model(zones={"main": zone})
        decision = TaskDispatchDecision(wm)
        with patch("task_scheduling.decision.time") as mock_time:
            mock_time.localtime.return_value = time.struct_time((2026, 1, 1, 12, 0, 0, 0, 1, 0))
            should, reason = decision.should_dispatch_now(
                urgency=2, zone="main", min_people_required=1,
            )
        assert should is True

    def test_high_urgency_dispatches_regardless(self):
        zone = make_zone_state(zone_id="main", person_count=1, dominant_activity="focused")
        wm = make_mock_world_model(zones={"main": zone})
        decision = TaskDispatchDecision(wm)
        should, reason = decision.should_dispatch_now(
            urgency=3, zone="main", min_people_required=1,
        )
        assert should is True
        assert "High urgency" in reason

    def test_focused_users_non_interruptible_queued(self):
        zone = make_zone_state(zone_id="main", person_count=2, dominant_activity="focused")
        wm = make_mock_world_model(zones={"main": zone})
        decision = TaskDispatchDecision(wm)
        with patch("task_scheduling.decision.time") as mock_time:
            mock_time.localtime.return_value = time.struct_time((2026, 1, 1, 12, 0, 0, 0, 1, 0))
            should, reason = decision.should_dispatch_now(
                urgency=2, zone="main", min_people_required=1, interruptible=False,
            )
        assert should is False
        assert "focused" in reason.lower()

    def test_outside_hours_low_urgency_queued(self):
        zone = make_zone_state(zone_id="main", person_count=1)
        wm = make_mock_world_model(zones={"main": zone})
        decision = TaskDispatchDecision(wm)
        with patch("task_scheduling.decision.time") as mock_time:
            # 3 AM - outside preferred hours
            mock_time.localtime.return_value = time.struct_time((2026, 1, 1, 3, 0, 0, 0, 1, 0))
            should, reason = decision.should_dispatch_now(
                urgency=1, zone="main", min_people_required=1,
            )
        assert should is False
        assert "Outside preferred hours" in reason


# ── TaskDispatchDecision.get_optimal_dispatch_conditions ──────────


class TestOptimalDispatchConditions:
    """Human-readable conditions for logging."""

    def test_critical_immediate(self):
        wm = make_mock_world_model()
        decision = TaskDispatchDecision(wm)
        result = decision.get_optimal_dispatch_conditions(urgency=4, zone="main", min_people_required=1)
        assert "CRITICAL" in result

    def test_zone_with_people_requirement(self):
        wm = make_mock_world_model()
        decision = TaskDispatchDecision(wm)
        result = decision.get_optimal_dispatch_conditions(urgency=2, zone="main", min_people_required=3)
        assert "main" in result
        assert "3" in result

    def test_no_zone_no_urgency(self):
        wm = make_mock_world_model()
        decision = TaskDispatchDecision(wm)
        result = decision.get_optimal_dispatch_conditions(urgency=2, zone=None, min_people_required=1)
        # Low urgency, no zone -> conditions about focus + hours
        assert "focused" in result.lower() or "active hours" in result.lower()

    def test_high_urgency_no_focus_condition(self):
        wm = make_mock_world_model()
        decision = TaskDispatchDecision(wm)
        result = decision.get_optimal_dispatch_conditions(urgency=3, zone="main", min_people_required=1)
        # High urgency skips focus/hours conditions
        assert "focused" not in result.lower()


# ── TaskQueueManager ──────────────────────────────────────────────


class TestTaskQueueManager:
    """Queue management operations."""

    def _make_manager(self, zones=None):
        wm = make_mock_world_model(zones or {})
        dc = make_mock_dashboard_client()
        return TaskQueueManager(wm, dc)

    @pytest.mark.asyncio
    async def test_add_task_dispatched_immediately_critical(self):
        mgr = self._make_manager()
        await mgr.add_task(task_id=1, title="Fire alarm", urgency=4, zone="main")
        # Critical task dispatches immediately -> queue stays empty
        assert len(mgr.queue) == 0

    @pytest.mark.asyncio
    async def test_add_task_queued_when_zone_inactive(self):
        mgr = self._make_manager()  # no zones
        await mgr.add_task(task_id=1, title="Clean desk", urgency=2, zone="lab")
        assert len(mgr.queue) == 1
        assert mgr.queue[0].title == "Clean desk"

    @pytest.mark.asyncio
    async def test_process_queue_empty_is_noop(self):
        mgr = self._make_manager()
        await mgr.process_queue()  # should not raise

    def test_get_queue_stats_empty(self):
        mgr = self._make_manager()
        stats = mgr.get_queue_stats()
        assert stats["total"] == 0
        assert stats["by_urgency"] == {}
        assert stats["by_zone"] == {}

    @pytest.mark.asyncio
    async def test_get_queue_stats_with_tasks(self):
        mgr = self._make_manager()
        await mgr.add_task(task_id=1, title="Task A", urgency=2, zone="main")
        await mgr.add_task(task_id=2, title="Task B", urgency=3, zone="main")
        # urgency=3 dispatches immediately (high urgency, no zone state -> wait, but
        # urgency >= 3 actually dispatches due to no zone). Let's use zone that exists.
        # Actually urgency=3 + zone -> checks zone state. If zone missing -> queued.
        # So both get queued since zone "main" is not in world model.
        stats = mgr.get_queue_stats()
        assert stats["total"] == 2
        assert stats["by_zone"].get("main") == 2

    @pytest.mark.asyncio
    async def test_process_queue_dispatches_ready_tasks(self):
        """Tasks become dispatchable when zone conditions change."""
        zone = make_zone_state(zone_id="lab", person_count=2)
        mgr = self._make_manager()
        # Add task when zone is not yet active
        await mgr.add_task(task_id=1, title="Setup lab", urgency=2, zone="lab")
        assert len(mgr.queue) == 1

        # Now add zone to world model and process queue
        mgr.world_model.get_zone = MagicMock(return_value=zone)
        with patch("task_scheduling.decision.time") as mock_time:
            mock_time.localtime.return_value = time.struct_time((2026, 1, 1, 12, 0, 0, 0, 1, 0))
            mock_time.time.return_value = time.time()
            await mgr.process_queue()

        # Task should be dispatched (removed from queue)
        assert len(mgr.queue) == 0

    @pytest.mark.asyncio
    async def test_process_queue_force_dispatches_stale(self):
        """Tasks queued for >24h get force-dispatched."""
        mgr = self._make_manager()
        await mgr.add_task(task_id=1, title="Old task", urgency=1, zone="lab")
        assert len(mgr.queue) == 1

        # Make the task appear stale
        mgr.queue[0].created_at = time.time() - 25 * 3600

        await mgr.process_queue()
        assert len(mgr.queue) == 0
