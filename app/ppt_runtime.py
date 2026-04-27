from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from typing import Any

import websockets

from .config import logger, preview_text, settings
from .models import AppMode, AppState
from .text_utils import segment_script
from .tts_service import TTSService


class PPTBridge:
    def __init__(self) -> None:
        self.clients: set[Any] = set()
        self.server_task: asyncio.Task | None = None
        self._last_no_client_log_at = 0.0

    async def ws_handler(self, websocket):
        self.clients.add(websocket)
        logger.info("PPT WS client connected: remote=%s total=%d", getattr(websocket, "remote_address", None), len(self.clients))
        try:
            async for _ in websocket:
                pass
        finally:
            self.clients.discard(websocket)
            logger.info("PPT WS client disconnected: remote=%s total=%d", getattr(websocket, "remote_address", None), len(self.clients))

    async def startup(self) -> None:
        if self.server_task and not self.server_task.done():
            return

        async def _serve_forever():
            async with websockets.serve(self.ws_handler, settings.ws_host, settings.ws_port):
                await asyncio.Future()

        self.server_task = asyncio.create_task(_serve_forever(), name="ppt-ws-server")

    async def shutdown(self) -> None:
        if self.server_task and not self.server_task.done():
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass

    async def broadcast(self, message: dict) -> None:
        if not self.clients:
            now = time.time()
            if now - self._last_no_client_log_at >= 2.0:
                self._last_no_client_log_at = now
                logger.warning("PPT WS send skipped (no clients): %s", message)
            return

        data = json.dumps(message, ensure_ascii=False)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def request_page_data(self) -> None:
        await self.broadcast({"type": "request_page_data"})

    async def enable_reporting(self) -> None:
        await self.broadcast({"type": "enable_reporting"})

    async def navigate(self, action: str, page: int | None = None) -> None:
        payload = {"type": action}
        if page is not None:
            payload["page"] = page
        await self.broadcast(payload)


class Presenter:
    def __init__(self, state: AppState, tts: TTSService, ppt: PPTBridge) -> None:
        self.state = state
        self.tts = tts
        self.ppt = ppt

        self.page: int | None = None
        self.script: str = ""
        self.page_text: str = ""
        self.segments: list[str] = []
        self.index: int = 0
        self.task: asyncio.Task | None = None
        self.auto_play: bool = False
        self.page_changed = asyncio.Event()
        self.awaiting_auto_page_advance: bool = False
        self.playback_session_id: str | None = None
        self.preload_task: asyncio.Task | None = None

    def load(self, page: int, script: str, page_text: str = "") -> bool:
        previous_page = self.page
        self.page = page
        self.script = script or ""
        self.page_text = page_text or ""
        self.segments = segment_script(self.script)
        self.index = 0
        self.state.current_page = page
        self.state.current_script = self.script
        self.state.current_page_text = self.page_text
        changed = previous_page != page
        logger.info(
            "presenter.load: previous_page=%s page=%s changed=%s segments=%d script_preview=%s",
            previous_page,
            page,
            changed,
            len(self.segments),
            preview_text(self.script),
        )
        if changed:
            self.page_changed.set()
        return changed

    def save_checkpoint(self) -> dict:
        """返回 {page, segment_index}，供外部保存到 AppState"""
        return {
            "page": self.page,
            "segment_index": self.index,
        }

    def restore_checkpoint(self, page: int, segment_index: int) -> None:
        """设置播放起点，不触发 TTS"""
        self.page = page
        self.index = segment_index

    async def start(self, from_index: int = 0) -> None:
        if self.page is None or not self.segments:
            logger.info(
                "presenter.start skipped: page=%s segments=%d from_index=%s",
                self.page,
                len(self.segments),
                from_index,
            )
            return
        self.index = max(0, min(from_index, len(self.segments)))
        self.state.resume_page = self.page
        self.state.resume_segment_index = self.index
        self.state.presentation_started = True
        logger.info(
            "presenter.start: page=%s from_index=%s segments=%d mode=%s auto_play=%s",
            self.page,
            self.index,
            len(self.segments),
            self.state.mode,
            self.auto_play,
        )
        await self.cancel()
        self.playback_session_id = self.tts.create_session_id()
        self.task = asyncio.create_task(self._run(), name="presenter-playback")

    async def cancel(self) -> None:
        if self.preload_task and not self.preload_task.done():
            self.preload_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(self.preload_task, timeout=0.5)
        self.preload_task = None
        self.playback_session_id = None
        if self.task and not self.task.done():
            logger.info("presenter.cancel: page=%s index=%s", self.page, self.index)
            self.task.cancel()
            try:
                await asyncio.wait_for(self.task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def refresh_page_data(self, timeout: float = 3.0) -> bool:
        self.page_changed.clear()
        await self.ppt.request_page_data()
        try:
            await asyncio.wait_for(self.page_changed.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _run(self) -> None:
        first = True
        session_id = self.playback_session_id or self.tts.create_session_id()
        self.playback_session_id = session_id
        logger.info(
            "presenter.run.start: page=%s index=%s segments=%d mode=%s auto_play=%s session_id=%s",
            self.page,
            self.index,
            len(self.segments),
            self.state.mode,
            self.auto_play,
            session_id,
        )
        while self.index < len(self.segments):
            text = self.segments[self.index].strip()
            checkpoint = self.save_checkpoint()
            self.state.resume_page = checkpoint["page"]
            self.state.resume_segment_index = checkpoint["segment_index"]
            if text:
                utterance_id = f"{session_id}:{self.page}:{self.index}"
                next_text = ""
                next_utterance_id = ""
                if self.index + 1 < len(self.segments):
                    next_text = self.segments[self.index + 1].strip()
                    if next_text:
                        next_utterance_id = f"{session_id}:{self.page}:{self.index + 1}"
                logger.info(
                    "presenter.run.segment: page=%s index=%s/%s first=%s session_id=%s utterance_id=%s text=%s",
                    self.page,
                    self.index,
                    len(self.segments),
                    first,
                    session_id,
                    utterance_id,
                    preview_text(text),
                )
                ok = await self.tts.send_with_metadata(
                    text,
                    is_first=first,
                    session_id=session_id,
                    utterance_id=utterance_id,
                )
                if not ok:
                    logger.warning("presenter.run.segment failed to send: page=%s index=%s", self.page, self.index)
                    return
                if next_text and next_utterance_id:
                    if self.preload_task and not self.preload_task.done():
                        self.preload_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await self.preload_task
                    self.preload_task = asyncio.create_task(
                        self.tts.preload(
                            next_text,
                            session_id=session_id,
                            utterance_id=next_utterance_id,
                        ),
                        name=f"tts-preload-{self.page}-{self.index + 1}",
                    )
                if first and settings.tts_start_grace_seconds > 0:
                    logger.info(
                        "presenter.run.segment grace_wait: page=%s index=%s seconds=%s",
                        self.page,
                        self.index,
                        settings.tts_start_grace_seconds,
                    )
                    await asyncio.sleep(settings.tts_start_grace_seconds)
                first = False
                idle = await self.tts.wait_idle(timeout_seconds=settings.tts_idle_timeout_seconds)
                if not idle:
                    logger.warning("presenter.run.segment wait_idle timeout: page=%s index=%s", self.page, self.index)
                    return
            self.index += 1
            checkpoint = self.save_checkpoint()
            self.state.resume_page = checkpoint["page"]
            self.state.resume_segment_index = checkpoint["segment_index"]

        if self.preload_task and not self.preload_task.done():
            self.preload_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(self.preload_task, timeout=0.5)
        self.preload_task = None

        if self.state.mode == AppMode.PRESENTING and self.auto_play:
            logger.info(
                "presenter.run.autonext: page=%s total=%s mode=%s auto_play=%s",
                self.page,
                self.get_total_page_number(),
                self.state.mode,
                self.auto_play,
            )
            total = self.get_total_page_number()
            if self.page is not None and total > 0 and self.page >= total:
                self.state.presentation_finished = True
                self.state.mode = AppMode.DEFENSE_QA
                self.auto_play = False
                logger.info("presenter.run.finished: page=%s total=%s", self.page, total)
                return

            self.awaiting_auto_page_advance = True
            self.page_changed.clear()
            await self.ppt.navigate("next")
            await self.ppt.request_page_data()
            try:
                await asyncio.wait_for(self.page_changed.wait(), timeout=5.0)
                logger.info("presenter.run.autonext page_changed received: page=%s", self.page)
            except asyncio.TimeoutError:
                self.state.mode = AppMode.WAITING_RESUME
                self.auto_play = False
                logger.warning("presenter.run.autonext timeout: page=%s", self.page)
            finally:
                self.awaiting_auto_page_advance = False
        else:
            logger.info(
                "presenter.run.stop-after-page: page=%s mode=%s auto_play=%s",
                self.page,
                self.state.mode,
                self.auto_play,
            )

    def get_total_page_number(self) -> int:
        try:
            pages: list[int] = []
            for name in settings.web_pages_root.iterdir():
                m = re.fullmatch(r"(\d+)\.html", name.name)
                if m:
                    pages.append(int(m.group(1)))
            return max(pages) if pages else 0
        except Exception:
            return 0
