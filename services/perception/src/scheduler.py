"""
Task Scheduler - 複数の監視タスクを並行実行
"""
import asyncio
import logging
from typing import Any, Dict
from monitors.base import MonitorBase

logger = logging.getLogger(__name__)

class TaskScheduler:
    def __init__(self):
        self.monitors: Dict[str, MonitorBase] = {}
        self._services: Dict[str, Any] = {}

    def register_monitor(self, name: str, monitor: MonitorBase):
        """監視タスクを登録"""
        self.monitors[name] = monitor
        logger.info(f"Registered monitor: {name}")

    def register_service(self, name: str, service):
        """長時間実行サービスを登録 (run() メソッドを持つオブジェクト)"""
        self._services[name] = service
        logger.info(f"Registered service: {name}")

    async def run(self):
        """全ての監視タスクとサービスを並行実行"""
        logger.info(
            f"Starting {len(self.monitors)} monitors, "
            f"{len(self._services)} services"
        )

        tasks = [
            asyncio.create_task(self._run_monitor(name, monitor))
            for name, monitor in self.monitors.items()
        ]
        tasks += [
            asyncio.create_task(self._run_service(name, service))
            for name, service in self._services.items()
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_monitor(self, name: str, monitor: MonitorBase):
        """個別の監視タスク実行（エラーハンドリング付き）"""
        try:
            await monitor.run()
        except Exception as e:
            logger.error(f"Monitor {name} crashed: {e}", exc_info=True)

    async def _run_service(self, name: str, service):
        """長時間実行サービスの実行（エラーハンドリング付き）"""
        try:
            await service.run()
        except Exception as e:
            logger.error(f"Service {name} crashed: {e}", exc_info=True)
