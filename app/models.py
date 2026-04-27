from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AppMode(str, Enum):
    IDLE = "IDLE"
    PRESENTING = "PRESENTING"
    INTERRUPTED_QA = "INTERRUPTED_QA"
    WAITING_RESUME = "WAITING_RESUME"
    DEFENSE_QA = "DEFENSE_QA"


class ChatRequest(BaseModel):
    text: str
    thread_id: str = "default_user"


class ASRStartRequest(BaseModel):
    device_index: Optional[int] = None


class PageEnterRequest(BaseModel):
    page: int = Field(ge=1)
    script: str = ""
    page_text: str = ""


class AppState(BaseModel):
    mode: AppMode = AppMode.IDLE
    current_page: Optional[int] = None
    current_script: str = ""
    current_page_text: str = ""
    resume_page: Optional[int] = None
    resume_segment_index: int = 0
    presentation_started: bool = False
    presentation_finished: bool = False
    qa_locked: bool = False
