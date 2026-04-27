from __future__ import annotations

import asyncio

from .config import logger
from .ppt_runtime import Presenter
from .tts_service import TTSService


class SessionManager:
    def __init__(self, presenter: Presenter, tts: TTSService) -> None:
        self.presenter = presenter
        self.tts = tts
        self.active_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def stop_active_task(self) -> None:
        async with self._lock:
            logger.info(
                "session.stop_active_task: has_active=%s presenter_task=%s",
                bool(self.active_task and not self.active_task.done()),
                bool(self.presenter.task and not self.presenter.task.done()),
            )
            if self.active_task and not self.active_task.done():
                logger.info("Interrupting active agent task...")
                self.active_task.cancel()
                try:
                    await asyncio.wait_for(self.active_task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            await self.stop_audio()

    async def stop_audio(self) -> None:
        logger.info(
            "session.stop_audio: presenter_page=%s presenter_index=%s auto_play=%s",
            self.presenter.page,
            self.presenter.index,
            self.presenter.auto_play,
        )
        await self.presenter.cancel()
        await self.tts.stop()
