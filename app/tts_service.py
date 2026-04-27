from __future__ import annotations

import asyncio
import contextlib
import time
import uuid

import httpx

from .config import logger, preview_text, settings
from .text_utils import segment_script


class TTSService:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(trust_env=False, timeout=settings.tts_timeout)

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("TTSService not started")
        return self._client

    async def send(self, text: str, *, is_first: bool = False) -> bool:
        return await self.send_with_metadata(text, is_first=is_first)

    async def send_with_metadata(
        self,
        text: str,
        *,
        is_first: bool = False,
        session_id: str | None = None,
        utterance_id: str | None = None,
    ) -> bool:
        url = settings.tts_urls["speak" if is_first else "speak_stream"]
        payload = {"text": text}
        if session_id:
            payload["session_id"] = session_id
        if utterance_id:
            payload["utterance_id"] = utterance_id
        logger.info(
            "tts.send: first=%s url=%s session_id=%s utterance_id=%s text=%s",
            is_first,
            url,
            session_id,
            utterance_id,
            preview_text(text),
        )
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            resp = exc.response
            detail = ""
            try:
                detail = (resp.text or "").strip()
            except Exception:
                detail = ""
            logger.warning("TTS send failed: http=%s url=%s detail=%s", resp.status_code, str(resp.url), detail)
            return False
        except httpx.RequestError as exc:
            logger.warning("TTS send failed: url=%s error=%s", url, exc)
            return False
        except Exception as exc:
            logger.warning("TTS send failed: %s", exc)
            return False

    async def preload(self, text: str, *, session_id: str, utterance_id: str) -> bool:
        payload = {
            "text": text,
            "session_id": session_id,
            "utterance_id": utterance_id,
        }
        logger.info(
            "tts.preload: session_id=%s utterance_id=%s text=%s",
            session_id,
            utterance_id,
            preview_text(text),
        )
        try:
            response = await self.client.post(settings.tts_urls["preload"], json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            resp = exc.response
            detail = ""
            try:
                detail = (resp.text or "").strip()
            except Exception:
                detail = ""
            logger.warning("TTS preload failed: http=%s url=%s detail=%s", resp.status_code, str(resp.url), detail)
            return False
        except httpx.RequestError as exc:
            logger.warning("TTS preload failed: url=%s error=%s", settings.tts_urls["preload"], exc)
            return False
        except Exception as exc:
            logger.warning("TTS preload failed: %s", exc)
            return False

    def create_session_id(self) -> str:
        return uuid.uuid4().hex

    async def stop(self) -> bool:
        logger.info("tts.stop")
        try:
            response = await self.client.post(settings.tts_urls["stop"])
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            resp = exc.response
            detail = ""
            try:
                detail = (resp.text or "").strip()
            except Exception:
                detail = ""
            logger.warning("TTS stop failed: http=%s url=%s detail=%s", resp.status_code, str(resp.url), detail)
            return False
        except httpx.RequestError as exc:
            logger.warning("TTS stop failed: url=%s error=%s", settings.tts_urls["stop"], exc)
            return False
        except Exception as exc:
            logger.warning("TTS stop failed: %s", exc)
            return False

    async def is_active(self) -> bool:
        try:
            response = await self.client.get(settings.tts_urls["status"])
            response.raise_for_status()
            data = response.json()
            is_playing = bool(data.get("is_playing"))
            is_generating = bool(data.get("is_generating"))
            task_q = int(data.get("task_queue_size", 0))
            audio_q = int(data.get("audio_queue_size", data.get("queue_size", 0)))
            active = is_playing or is_generating or task_q > 0 or audio_q > 0
            logger.info(
                "tts.is_active: playing=%s generating=%s task_q=%s audio_q=%s active=%s",
                is_playing,
                is_generating,
                task_q,
                audio_q,
                active,
            )
            return active
        except Exception as exc:
            logger.warning("tts.is_active failed: %s", exc)
            return False

    async def wait_idle(
        self,
        *,
        timeout_seconds: float = 30.0,
        require_activity: bool = True,
        activity_timeout_seconds: float = 4.0,
    ) -> bool:
        stable = 0
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        activity_deadline = time.monotonic() + max(0.0, activity_timeout_seconds)
        polls = 0
        saw_activity = False
        poll_interval_seconds = 0.1
        while True:
            if timeout_seconds > 0 and time.monotonic() >= deadline:
                logger.warning("tts.wait_idle timeout: polls=%s stable=%s", polls, stable)
                return False

            idle = False
            is_playing = False
            is_generating = False
            task_q = 0
            audio_q = 0
            try:
                response = await self.client.get(settings.tts_urls["status"])
                response.raise_for_status()
                data = response.json()
                is_playing = bool(data.get("is_playing"))
                is_generating = bool(data.get("is_generating"))
                task_q = int(data.get("task_queue_size", 0))
                audio_q = int(data.get("audio_queue_size", data.get("queue_size", 0)))
                if is_playing or is_generating or task_q > 0 or audio_q > 0:
                    saw_activity = True
                idle = (not is_playing) and (not is_generating) and task_q == 0 and audio_q == 0
                polls += 1
                if polls == 1 or idle or polls % 25 == 0:
                    logger.info(
                        "tts.wait_idle poll=%s is_playing=%s is_generating=%s task_q=%s audio_q=%s idle=%s stable=%s saw_activity=%s",
                        polls,
                        is_playing,
                        is_generating,
                        task_q,
                        audio_q,
                        idle,
                        stable,
                        saw_activity,
                    )
            except Exception:
                idle = False

            if require_activity and not saw_activity:
                if activity_timeout_seconds > 0 and time.monotonic() >= activity_deadline:
                    logger.warning(
                        "tts.wait_idle activity timeout: polls=%s is_playing=%s is_generating=%s task_q=%s audio_q=%s",
                        polls,
                        is_playing,
                        is_generating,
                        task_q,
                        audio_q,
                    )
                    return False
                await asyncio.sleep(poll_interval_seconds)
                continue

            if idle:
                stable += 1
                if stable >= 2:
                    logger.info("tts.wait_idle success: polls=%s", polls)
                    return True
            else:
                stable = 0
            await asyncio.sleep(poll_interval_seconds)

    async def speak_text(self, text: str) -> None:
        segments = segment_script(text)
        if not segments:
            return

        session_id = self.create_session_id()
        first = True
        preload_task: asyncio.Task | None = None
        try:
            for index, seg in enumerate(segments):
                if preload_task and preload_task.done():
                    preload_task = None

                utterance_id = f"{session_id}:qa:{index}"
                next_text = segments[index + 1].strip() if index + 1 < len(segments) else ""
                next_utterance_id = f"{session_id}:qa:{index + 1}" if next_text else ""

                item = seg.strip()
                if not item:
                    continue

                ok = await self.send_with_metadata(
                    item,
                    is_first=first,
                    session_id=session_id,
                    utterance_id=utterance_id,
                )
                if not ok:
                    return

                if next_text and not preload_task:
                    preload_task = asyncio.create_task(
                        self.preload(
                            next_text,
                            session_id=session_id,
                            utterance_id=next_utterance_id,
                        ),
                        name=f"tts-qa-preload-{index + 1}",
                    )

                first = False
                idle = await self.wait_idle()
                if not idle:
                    return

                if preload_task and preload_task.done():
                    preload_task = None
        finally:
            if preload_task and not preload_task.done():
                preload_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await asyncio.wait_for(preload_task, timeout=0.5)
