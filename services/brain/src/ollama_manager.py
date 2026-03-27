"""
Ollama model lifecycle manager for SOMS Brain.

Manages VRAM by loading/unloading models via Ollama's native API.
Used to swap between the brain's small model (for real-time decisions)
and a larger model (for report generation) on a single GPU.

Key operations:
  unload_model()        — free VRAM via keep_alive=0
  preload_model()       — load model into VRAM
  prepare_for_report()  — unload brain model, load report model
  restore_brain_model() — reverse: unload report model, reload brain model
"""
import os
import logging
import aiohttp

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")


class OllamaManager:
    """Manages Ollama model lifecycle for VRAM coordination."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        brain_model: str | None = None,
        report_model: str | None = None,
        ollama_base_url: str | None = None,
    ):
        self._session = session
        self._base_url = (ollama_base_url or DEFAULT_OLLAMA_URL).rstrip("/")
        self._brain_model = brain_model or os.getenv("LLM_MODEL", "qwen3.5:14b")
        self._report_model = report_model or os.getenv("REPORT_LLM_MODEL", "qwen3.5:32b")
        self._swapping = False
        self._report_model_active = False

    @property
    def is_swapping(self) -> bool:
        """True while a model swap is in progress."""
        return self._swapping

    @property
    def is_report_model_active(self) -> bool:
        """True when the report model is loaded (brain model unloaded)."""
        return self._report_model_active

    @property
    def brain_model(self) -> str:
        return self._brain_model

    @property
    def report_model(self) -> str:
        return self._report_model

    @property
    def base_url(self) -> str:
        return self._base_url

    async def unload_model(self, model_name: str) -> bool:
        """Unload a model from VRAM via Ollama API (keep_alive=0).

        Returns True on success, False on failure.
        """
        try:
            async with self._session.post(
                f"{self._base_url}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    # Consume response body (streaming NDJSON)
                    async for _ in resp.content:
                        pass
                    logger.info("[OllamaManager] モデル %s をアンロード", model_name)
                    return True
                else:
                    body = await resp.text()
                    logger.warning(
                        "[OllamaManager] モデル %s アンロード失敗: %d %s",
                        model_name, resp.status, body[:200],
                    )
                    return False
        except Exception as e:
            logger.error("[OllamaManager] モデル %s アンロードエラー: %s", model_name, e)
            return False

    async def preload_model(self, model_name: str) -> bool:
        """Preload a model into VRAM via Ollama API.

        Sends an empty prompt with keep_alive=10m to trigger model loading.
        Returns True on success, False on failure.
        """
        try:
            async with self._session.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "",
                    "keep_alive": "10m",
                },
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status == 200:
                    async for _ in resp.content:
                        pass
                    logger.info("[OllamaManager] モデル %s をプリロード", model_name)
                    return True
                else:
                    body = await resp.text()
                    logger.warning(
                        "[OllamaManager] モデル %s プリロード失敗: %d %s",
                        model_name, resp.status, body[:200],
                    )
                    return False
        except Exception as e:
            logger.error("[OllamaManager] モデル %s プリロードエラー: %s", model_name, e)
            return False

    async def prepare_for_report(self) -> bool:
        """Swap to report model: unload brain model, load report model.

        Returns True if the swap succeeded.
        """
        if self._swapping:
            logger.warning("[OllamaManager] すでにスワップ中")
            return False

        self._swapping = True
        try:
            logger.info(
                "[OllamaManager] レポート用モデルスワップ開始: %s → %s",
                self._brain_model, self._report_model,
            )

            # Unload brain model to free VRAM
            await self.unload_model(self._brain_model)

            # Load report model
            success = await self.preload_model(self._report_model)
            if success:
                self._report_model_active = True
                logger.info("[OllamaManager] レポートモデル準備完了")
            else:
                logger.error("[OllamaManager] レポートモデルのロードに失敗 — brainモデルを復元")
                await self.preload_model(self._brain_model)
                self._report_model_active = False

            return success
        finally:
            self._swapping = False

    async def restore_brain_model(self) -> bool:
        """Restore brain model: unload report model, reload brain model.

        Should always be called in a finally block after report generation.
        Returns True if restoration succeeded.
        """
        if self._swapping:
            logger.warning("[OllamaManager] すでにスワップ中 — 復元をスキップ")
            return False

        self._swapping = True
        try:
            logger.info(
                "[OllamaManager] brainモデル復元開始: %s → %s",
                self._report_model, self._brain_model,
            )

            # Unload report model
            await self.unload_model(self._report_model)
            self._report_model_active = False

            # Reload brain model
            success = await self.preload_model(self._brain_model)
            if success:
                logger.info("[OllamaManager] brainモデル復元完了")
            else:
                logger.error("[OllamaManager] brainモデルの復元に失敗")

            return success
        finally:
            self._swapping = False

    def get_status(self) -> dict:
        """Return current model manager status."""
        return {
            "brain_model": self._brain_model,
            "report_model": self._report_model,
            "is_swapping": self._swapping,
            "report_model_active": self._report_model_active,
            "ollama_url": self._base_url,
        }
