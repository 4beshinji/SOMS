"""
Report scheduler for SOMS Brain.

Manages the timing and execution of automated report generation.
Coordinates with ActivityModeManager (only generates when inactive)
and OllamaManager (swaps to larger model for generation).

Schedule:
  daily  — generated after REPORT_DAILY_HOUR (JST), when office is inactive
  weekly — generated on Monday, covering prior Mon-Sun
  monthly — generated on 1st of month, covering prior month
"""
import asyncio
import os
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncEngine

from activity_mode import ActivityModeManager
from ollama_manager import OllamaManager
from report_generator import ReportGenerator

logger = logging.getLogger(__name__)

SCHEDULER_CHECK_INTERVAL = 60  # seconds between schedule checks
REPORT_DAILY_HOUR = int(os.getenv("REPORT_DAILY_HOUR", "23"))
TZ = timezone(timedelta(hours=9))  # Asia/Tokyo


class ReportScheduler:
    """Manages automated report generation schedule."""

    def __init__(
        self,
        report_generator: ReportGenerator,
        activity_mode: ActivityModeManager,
        ollama_manager: OllamaManager,
        engine: AsyncEngine,
    ):
        self._generator = report_generator
        self._activity_mode = activity_mode
        self._ollama = ollama_manager
        self._engine = engine
        self._running = False
        self._current_task: asyncio.Task | None = None

    async def start(self):
        """Start the report scheduling loop."""
        self._running = True
        logger.info("[ReportScheduler] スケジューラ開始 (チェック間隔: %ds)", SCHEDULER_CHECK_INTERVAL)

        while self._running:
            await asyncio.sleep(SCHEDULER_CHECK_INTERVAL)
            try:
                await self._check_and_generate()
            except Exception as e:
                logger.error("[ReportScheduler] チェックエラー: %s", e)

    async def stop(self):
        """Stop the scheduler and cancel any ongoing generation."""
        self._running = False
        if self._current_task and not self._current_task.done():
            await self.on_activity_resumed()
        logger.info("[ReportScheduler] スケジューラ停止")

    async def on_activity_resumed(self):
        """Called when office transitions from INACTIVE to NORMAL.

        Cancels ongoing report generation and restores brain model.
        """
        if self._generator.is_generating:
            logger.info("[ReportScheduler] アクティビティ復帰 — レポート生成中止")
            await self._generator.cancel()

        if self._ollama.is_report_model_active:
            logger.info("[ReportScheduler] brainモデル復元中...")
            await self._ollama.restore_brain_model()

    # ------------------------------------------------------------------
    # Schedule checking
    # ------------------------------------------------------------------

    async def _check_and_generate(self):
        """Check if any report needs generation and conditions are met."""
        # Skip if already generating or model swapping
        if self._generator.is_generating or self._ollama.is_swapping:
            return

        # Must be in inactive mode
        if not self._activity_mode.is_inactive:
            return

        now = datetime.now(TZ)

        # Priority 1: Daily report
        daily_needed = await self._check_daily_needed(now)
        if daily_needed:
            await self._run_report_with_model_swap("daily", daily_needed)
            return

        # Priority 2: Weekly report (Monday)
        weekly_needed = await self._check_weekly_needed(now)
        if weekly_needed:
            await self._run_report_with_model_swap("weekly", weekly_needed)
            return

        # Priority 3: Monthly report (1st of month)
        monthly_needed = await self._check_monthly_needed(now)
        if monthly_needed:
            await self._run_report_with_model_swap("monthly", monthly_needed)
            return

    async def _check_daily_needed(self, now: datetime) -> datetime | None:
        """Check if a daily report needs to be generated.

        Returns the date to report on, or None.
        """
        # Only generate after REPORT_DAILY_HOUR
        if now.hour < REPORT_DAILY_HOUR:
            return None

        # Report on today (if after reporting hour)
        report_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Check if already generated
        if await self._generator.report_exists("daily", report_date):
            return None

        return report_date

    async def _check_weekly_needed(self, now: datetime) -> datetime | None:
        """Check if a weekly report needs to be generated.

        Generates on Monday (or later) for the previous week (Mon-Sun).
        """
        # Only generate on Monday or later for previous week
        if now.weekday() != 0:  # Monday = 0
            return None

        # Previous week's Monday
        week_start = (now - timedelta(days=7)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )

        if await self._generator.report_exists("weekly", week_start):
            return None

        return week_start

    async def _check_monthly_needed(self, now: datetime) -> datetime | None:
        """Check if a monthly report needs to be generated.

        Generates on the 1st of month for the previous month.
        """
        if now.day != 1:
            return None

        # Previous month
        if now.month == 1:
            prev_month_start = datetime(now.year - 1, 12, 1, tzinfo=TZ)
        else:
            prev_month_start = datetime(now.year, now.month - 1, 1, tzinfo=TZ)

        if await self._generator.report_exists("monthly", prev_month_start):
            return None

        return prev_month_start

    # ------------------------------------------------------------------
    # Report execution with model swap
    # ------------------------------------------------------------------

    async def _run_report_with_model_swap(
        self, report_type: str, period_start: datetime,
    ):
        """Execute report generation with VRAM model swap."""
        logger.info(
            "[ReportScheduler] %sレポート生成開始（モデルスワップ付き）: %s",
            report_type, period_start.isoformat(),
        )

        try:
            # Step 1: Swap to report model
            success = await self._ollama.prepare_for_report()
            if not success:
                logger.error("[ReportScheduler] モデルスワップ失敗 — 生成中止")
                return

            # Check if still inactive after model swap
            if not self._activity_mode.is_inactive:
                logger.info("[ReportScheduler] モデルスワップ後にアクティブ復帰 — 生成中止")
                return

            # Step 2: Generate report
            if report_type == "daily":
                await self._generator.generate_daily_report(period_start)
            elif report_type == "weekly":
                await self._generator.generate_weekly_report(period_start)
            elif report_type == "monthly":
                await self._generator.generate_monthly_report(
                    period_start.year, period_start.month,
                )

        except Exception as e:
            logger.error("[ReportScheduler] レポート生成エラー: %s", e)
        finally:
            # Step 3: Always restore brain model
            if self._ollama.is_report_model_active:
                await self._ollama.restore_brain_model()
