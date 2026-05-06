from __future__ import annotations

import asyncio
import json
from typing import Optional

from langchain_core.tools import tool

from .config import logger, settings
from .models import AppMode, AppState
from .ppt_runtime import PPTBridge, Presenter
from .session import SessionManager


class _StateGuard:
    def can_resume(self, state: AppState) -> bool:
        return state.resume_page is not None and not state.qa_locked

    def can_start(self, state: AppState) -> bool:
        return not state.qa_locked

    def redirect_if_locked(self, state: AppState, tool_name: str) -> str | None:
        if state.qa_locked:
            return f"{tool_name} blocked: presentation locked to QA mode"
        return None


class ToolRegistry:
    def __init__(self, state: AppState, presenter: Presenter, session: SessionManager, ppt: PPTBridge) -> None:
        self.state = state
        self.presenter = presenter
        self.session = session
        self.ppt = ppt
        self._guard = _StateGuard()

    def _save_resume_point(self) -> None:
        if self.presenter.page is None:
            return
        self.state.resume_page = self.presenter.page
        self.state.resume_segment_index = max(0, self.presenter.index)

    async def _jump_to_page(self, page: int, *, timeout: float = 5.0) -> bool:
        if self.presenter.page == int(page):
            self._log_state("jump.skip_same_page", page=page)
            return True
        self.presenter.page_changed.clear()
        await self.ppt.navigate("jump", page=int(page))
        await self.ppt.request_page_data()
        try:
            await asyncio.wait_for(self.presenter.page_changed.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def _state_payload(self) -> dict:
        return {
            "mode": self.state.mode,
            "current_page": self.presenter.page,
            "current_segment_index": self.presenter.index,
            "segment_total": len(self.presenter.segments),
            "resume_page": self.state.resume_page,
            "resume_segment_index": self.state.resume_segment_index,
            "presentation_started": self.state.presentation_started,
            "presentation_finished": self.state.presentation_finished,
            "qa_locked": self.state.qa_locked,
            "auto_play": self.presenter.auto_play,
            "ws_clients": len(self.ppt.clients),
        }

    def _log_state(self, label: str, **extra) -> None:
        payload = self._state_payload()
        payload.update(extra)
        logger.info("tool.%s: %s", label, json.dumps(payload, ensure_ascii=False))

    def _autoplay_blocked(self) -> bool:
        return bool(self.state.qa_locked)

    async def _force_jump_for_qa(self, page: Optional[int], source_tool: str) -> str:
        target_page = page if page and page > 0 else (self.presenter.page or self.state.current_page)
        self._log_state("qa_lock.redirect.before", source_tool=source_tool, target_page=target_page)
        if target_page is None:
            self.state.mode = AppMode.DEFENSE_QA
            self.presenter.auto_play = False
            self._log_state("qa_lock.redirect.after", source_tool=source_tool, target_page=target_page, redirected=False)
            return "Presentation is permanently locked to QA after the final slide. Staying in defense QA mode."

        self._save_resume_point()
        await self.session.stop_audio()
        await self._jump_to_page(int(target_page), timeout=3.0)
        self.presenter.auto_play = False
        self.state.mode = AppMode.DEFENSE_QA
        self.state.presentation_finished = True
        self.state.qa_locked = True
        self.state.resume_page = int(target_page)
        self.state.resume_segment_index = 0
        self._log_state("qa_lock.redirect.after", source_tool=source_tool, target_page=target_page, redirected=True)
        return f"Presentation is permanently locked to QA after the final slide. Redirected {source_tool} to QA jump on page {target_page}."

    def build(self) -> list:
        @tool("get_presentation_state", description="Get the current defense state and resume point.")
        async def get_presentation_state() -> str:
            self._log_state("get_presentation_state")
            return json.dumps(self._state_payload(), ensure_ascii=False)

        @tool("ppt_navigate", description="Control PPT pages with next, prev, or jump. Provide page for jump. If replay=true on jump, it jumps to that page and immediately continues the defense from the start of that page.")
        async def ppt_navigate(action: str, page: Optional[int] = None, replay: bool = False) -> str:
            self._log_state("ppt_navigate.before", action=action, page=page, replay=replay)
            if action not in {"next", "prev", "jump"}:
                return "Unsupported navigation action."
            if replay and self._autoplay_blocked():
                return await self._force_jump_for_qa(page, "ppt_navigate")

            logger.info(
                "ppt_navigate called: action=%s page=%s replay=%s ws_clients=%d",
                action,
                page,
                replay,
                len(self.ppt.clients),
            )

            self._save_resume_point()
            await self.session.stop_audio()

            if action == "jump":
                if page is None or page <= 0:
                    return "Invalid target page."
                changed = await self._jump_to_page(int(page))
                if replay:
                    self.state.mode = AppMode.PRESENTING
                    self.presenter.auto_play = True
                    self.state.presentation_started = True
                    self.state.presentation_finished = False
                    if changed or self.presenter.page is not None:
                        await self.presenter.start(0)
                else:
                    self.state.mode = AppMode.DEFENSE_QA if self.state.qa_locked else AppMode.WAITING_RESUME
                    self.presenter.auto_play = False
                    self._save_resume_point()
                base = f"Jumped to page {page}."
                if replay:
                    base = f"Replaying from page {page}."
            else:
                self.presenter.page_changed.clear()
                await self.ppt.navigate(action)
                await self.ppt.request_page_data()
                try:
                    await asyncio.wait_for(self.presenter.page_changed.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                self.state.mode = AppMode.DEFENSE_QA if self.state.qa_locked else AppMode.WAITING_RESUME
                self.presenter.auto_play = False
                self._save_resume_point()
                base = "Moved to next page." if action == "next" else "Moved to previous page."

            connected = len(self.ppt.clients)
            if connected <= 0:
                self._log_state("ppt_navigate.after", action=action, page=page, replay=replay, connected=connected)
                return f"{base} No page is connected to ws://{settings.ws_host}:{settings.ws_port}."
            self._log_state("ppt_navigate.after", action=action, page=page, replay=replay, connected=connected)
            return f"{base} Connected pages: {connected}."

        @tool("presentation_start", description="Start the formal presentation from page 1 or from a specified page, and continue automatically.")
        async def presentation_start(from_page: Optional[int] = 1) -> str:
            self._log_state("presentation_start.before", from_page=from_page)
            if self._autoplay_blocked():
                return await self._force_jump_for_qa(from_page, "presentation_start")
            await self.session.stop_audio()
            await self.ppt.enable_reporting()
            await self.presenter.refresh_page_data(timeout=3.0)

            target_page = from_page if from_page and from_page > 0 else self.presenter.page
            if target_page is None:
                self.state.mode = AppMode.IDLE
                self.presenter.auto_play = False
                return "PPT page data is not available yet."

            if self.presenter.page != target_page:
                changed = await self._jump_to_page(target_page, timeout=3.0)
                if not changed and self.presenter.page != target_page:
                    self.state.mode = AppMode.IDLE
                    self.presenter.auto_play = False
                    return f"Failed to navigate to page {target_page}. Please ensure the PPT client is connected and reporting page data."

            if self.presenter.page is None:
                self.state.mode = AppMode.IDLE
                self.presenter.auto_play = False
                return "PPT page data is not available yet."

            self.state.mode = AppMode.PRESENTING
            self.state.presentation_started = True
            self.state.presentation_finished = False
            self.presenter.auto_play = True
            await self.presenter.start(0)
            self._log_state("presentation_start.after", from_page=from_page, started_page=self.presenter.page)
            return f"Presentation started from page {target_page}."

        @tool("presentation_pause", description="Pause the presentation, keep the resume point, and enter interrupted QA.")
        async def presentation_pause(save_resume_point: bool = True) -> str:
            self._log_state("presentation_pause.before", save_resume_point=save_resume_point)
            if save_resume_point:
                self._save_resume_point()
            self.state.mode = AppMode.INTERRUPTED_QA
            self.presenter.auto_play = False
            await self.session.stop_audio()
            self._log_state("presentation_pause.after", save_resume_point=save_resume_point)
            return "Presentation paused. Ready for questions."

        @tool("presentation_resume", description="Resume the formal presentation from the saved resume point and continue automatically.")
        async def presentation_resume(from_saved_point: bool = True) -> str:
            self._log_state(
                "presentation_resume.before",
                from_saved_point=from_saved_point,
            )
            if self._autoplay_blocked():
                target_page = self.state.resume_page if from_saved_point else self.presenter.page
                return await self._force_jump_for_qa(target_page, "presentation_resume")
            resume_page = self.state.resume_page if from_saved_point else self.presenter.page
            if resume_page is None:
                self.state.mode = AppMode.IDLE
                self.presenter.auto_play = False
                return "No saved resume point is available."

            await self.session.stop_audio()
            await self.ppt.enable_reporting()

            if self.presenter.page != resume_page:
                await self._jump_to_page(resume_page, timeout=3.0)

            start_index = self.state.resume_segment_index if from_saved_point else self.presenter.index
            if not self.presenter.segments:
                self.state.mode = AppMode.WAITING_RESUME
                self.presenter.auto_play = False
                return "Current page does not have speaker notes."

            if start_index >= len(self.presenter.segments):
                start_index = max(0, len(self.presenter.segments) - 1)

            self.state.mode = AppMode.PRESENTING
            self.state.presentation_started = True
            self.state.presentation_finished = False
            self.presenter.auto_play = True
            await self.presenter.start(start_index)
            self._log_state(
                "presentation_resume.after",
                from_saved_point=from_saved_point,
                start_index=start_index,
            )
            return f"Resuming from page {self.presenter.page}, segment {start_index}."

        @tool("presentation_replay_page", description="Replay the current page or a specified page from the start.")
        async def presentation_replay_page(page: Optional[int] = None, auto_advance: bool = True) -> str:
            self._log_state("presentation_replay_page.before", page=page, auto_advance=auto_advance)
            target_page = page if page and page > 0 else self.presenter.page
            if target_page is None:
                return "No page is available to replay."
            if auto_advance and self._autoplay_blocked():
                return await self._force_jump_for_qa(target_page, "presentation_replay_page")

            await self.session.stop_audio()
            await self.ppt.enable_reporting()
            if self.presenter.page != target_page:
                await self._jump_to_page(target_page, timeout=3.0)

            self.state.mode = AppMode.PRESENTING
            self.state.presentation_started = True
            self.state.presentation_finished = False
            self.presenter.auto_play = bool(auto_advance)
            self.state.resume_page = target_page
            self.state.resume_segment_index = 0
            await self.presenter.start(0)
            self._log_state("presentation_replay_page.after", page=target_page, auto_advance=auto_advance)
            return f"Replaying page {target_page} from the beginning."

        @tool("presentation_jump_and_hold", description="Jump to a target page but do not continue speaking automatically.")
        async def presentation_jump_and_hold(page: int) -> str:
            self._log_state("presentation_jump_and_hold.before", page=page)
            if page <= 0:
                return "Invalid target page."
            self._save_resume_point()
            await self.session.stop_audio()
            changed = await self._jump_to_page(page, timeout=3.0)
            if not changed:
                self._log_state("presentation_jump_and_hold.timeout", page=page)
                return f"Failed to confirm jump to page {page}."
            self.presenter.auto_play = False
            self.state.mode = AppMode.DEFENSE_QA if self.state.qa_locked else AppMode.WAITING_RESUME
            self.state.resume_page = page
            self.state.resume_segment_index = 0
            self._log_state("presentation_jump_and_hold.after", page=page)
            return f"Jumped to page {page} and waiting."

        @tool("presentation_jump_for_qa", description="Jump to a target page for the current audience question, stop automatic speaking, and let the agent answer based on that page.")
        async def presentation_jump_for_qa(page: int) -> str:
            self._log_state("presentation_jump_for_qa.before", page=page)
            if page <= 0:
                return "Invalid target page."
            self._save_resume_point()
            await self.session.stop_audio()
            changed = await self._jump_to_page(page, timeout=3.0)
            if not changed:
                self._log_state("presentation_jump_for_qa.timeout", page=page)
                return f"Failed to confirm jump to page {page} for QA."
            self.presenter.auto_play = False
            self.state.mode = AppMode.INTERRUPTED_QA if self.state.presentation_started and not self.state.presentation_finished else AppMode.DEFENSE_QA
            self._log_state("presentation_jump_for_qa.after", page=page)
            return f"Jumped to page {page} for QA."

        @tool("presentation_enter_defense_qa", description="End formal presentation and enter final defense QA mode.")
        async def presentation_enter_defense_qa() -> str:
            self._log_state("presentation_enter_defense_qa.before")
            self._save_resume_point()
            self.state.mode = AppMode.DEFENSE_QA
            self.state.presentation_started = True
            self.state.presentation_finished = True
            self.state.qa_locked = True
            self.presenter.auto_play = False
            await self.session.stop_audio()
            self._log_state("presentation_enter_defense_qa.after")
            return "Entered final defense QA mode."

        @tool("presentation_finish", description="Mark the presentation as finished and stay in defense QA mode.")
        async def presentation_finish() -> str:
            self._log_state("presentation_finish.before")
            self._save_resume_point()
            self.state.mode = AppMode.DEFENSE_QA
            self.state.presentation_finished = True
            self.state.qa_locked = True
            self.presenter.auto_play = False
            await self.session.stop_audio()
            self._log_state("presentation_finish.after")
            return "Presentation marked as finished. Now in defense QA mode."

        return [
            get_presentation_state,
            ppt_navigate,
            presentation_start,
            presentation_pause,
            presentation_resume,
            presentation_replay_page,
            presentation_jump_and_hold,
            presentation_jump_for_qa,
            presentation_enter_defense_qa,
            presentation_finish,
        ]
