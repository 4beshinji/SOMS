"""
LLM model lifecycle manager for SOMS Brain.

When using llama.cpp (default), model swapping is not needed — the server
loads a single model at startup with continuous batching.  All swap methods
become no-ops and the brain model stays loaded permanently.

When OLLAMA_URL is set (indicating a running Ollama instance), the original
model-swap behaviour is retained: unload/preload models via /api/generate.
"""
import os
import logging
import aiohttp

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "")


class OllamaManager:
    """Manages LLM model lifecycle.

    If no OLLAMA_URL is configured, all swap operations are no-ops
    (llama.cpp server mode — single model, continuous batching).
    """

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
        self._report_model = report_model or os.getenv("REPORT_LLM_MODEL", self._brain_model)
        self._swapping = False
        self._report_model_active = False
        # llama.cpp mode: no Ollama API available
        self._ollama_available = bool(self._base_url)
        if not self._ollama_available:
            logger.info("[ModelManager] llama.cpp mode — model swap disabled, using single model")

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
        """Unload a model from VRAM.  No-op in llama.cpp mode."""
        if not self._ollama_available:
            return True
        try:
            async with self._session.post(
                f"{self._base_url}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    async for _ in resp.content:
                        pass
                    logger.info("[ModelManager] モデル %s をアンロード", model_name)
                    return True
                else:
                    body = await resp.text()
                    logger.warning(
                        "[ModelManager] モデル %s アンロード失敗: %d %s",
                        model_name, resp.status, body[:200],
                    )
                    return False
        except Exception as e:
            logger.error("[ModelManager] モデル %s アンロードエラー: %s", model_name, e)
            return False

    async def preload_model(self, model_name: str) -> bool:
        """Preload a model into VRAM.  No-op in llama.cpp mode."""
        if not self._ollama_available:
            return True
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
                    logger.info("[ModelManager] モデル %s をプリロード", model_name)
                    return True
                else:
                    body = await resp.text()
                    logger.warning(
                        "[ModelManager] モデル %s プリロード失敗: %d %s",
                        model_name, resp.status, body[:200],
                    )
                    return False
        except Exception as e:
            logger.error("[ModelManager] モデル %s プリロードエラー: %s", model_name, e)
            return False

    async def prepare_for_report(self) -> bool:
        """Swap to report model.  No-op in llama.cpp mode."""
        if not self._ollama_available:
            return True

        if self._swapping:
            logger.warning("[ModelManager] すでにスワップ中")
            return False

        self._swapping = True
        try:
            logger.info(
                "[ModelManager] レポート用モデルスワップ開始: %s → %s",
                self._brain_model, self._report_model,
            )
            await self.unload_model(self._brain_model)
            success = await self.preload_model(self._report_model)
            if success:
                self._report_model_active = True
                logger.info("[ModelManager] レポートモデル準備完了")
            else:
                logger.error("[ModelManager] レポートモデルのロードに失敗 — brainモデルを復元")
                await self.preload_model(self._brain_model)
                self._report_model_active = False
            return success
        finally:
            self._swapping = False

    async def restore_brain_model(self) -> bool:
        """Restore brain model.  No-op in llama.cpp mode."""
        if not self._ollama_available:
            self._report_model_active = False
            return True

        if self._swapping:
            logger.warning("[ModelManager] すでにスワップ中 — 復元をスキップ")
            return False

        self._swapping = True
        try:
            logger.info(
                "[ModelManager] brainモデル復元開始: %s → %s",
                self._report_model, self._brain_model,
            )
            await self.unload_model(self._report_model)
            self._report_model_active = False
            success = await self.preload_model(self._brain_model)
            if success:
                logger.info("[ModelManager] brainモデル復元完了")
            else:
                logger.error("[ModelManager] brainモデルの復元に失敗")
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
            "backend": "ollama" if self._ollama_available else "llama.cpp",
            "ollama_url": self._base_url if self._ollama_available else None,
        }
