from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from .env_utils import load_project_env

try:
    from langchain.globals import set_debug as lc_set_debug
    from langchain.globals import set_verbose as lc_set_verbose
except Exception:
    lc_set_debug = None
    lc_set_verbose = None

load_project_env(override=True)


class Settings(BaseModel):
    log_level: str = Field(default_factory=lambda: os.getenv("AUTO_PPT_LOG_LEVEL", "INFO").upper())
    debug_logging: bool = Field(default_factory=lambda: os.getenv("AUTO_PPT_DEBUG", "1").lower() in {"1", "true", "yes", "on"})
    langchain_debug: bool = Field(default_factory=lambda: os.getenv("AUTO_PPT_LANGCHAIN_DEBUG", "1").lower() in {"1", "true", "yes", "on"})
    langchain_verbose: bool = Field(default_factory=lambda: os.getenv("AUTO_PPT_LANGCHAIN_VERBOSE", "1").lower() in {"1", "true", "yes", "on"})

    project_root: Path = Field(default_factory=lambda: Path(os.getenv("AUTO_PPT_PROJECT_ROOT", Path(__file__).resolve().parents[1])))
    web_dir_name: str = "web"
    pages_dir_name: str = "pages"
    skills_dir_name: str = "skills"

    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = Field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-5.4"))
    openai_temperature: float = Field(default_factory=lambda: float(os.getenv("OPENAI_TEMPERATURE", "0.7")))

    tts_base_url: str = Field(default_factory=lambda: os.getenv("TTS_BASE_URL", "http://127.0.0.1:15000"))
    tts_host: str = Field(default_factory=lambda: os.getenv("TTS_HOST", "127.0.0.1"))
    tts_port: int = Field(default_factory=lambda: int(os.getenv("TTS_PORT", "15000")))
    tts_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("TTS_TIMEOUT_SECONDS", "5.0")))
    tts_connect_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("TTS_CONNECT_TIMEOUT_SECONDS", "2.0")))
    tts_idle_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("TTS_IDLE_TIMEOUT_SECONDS", "120.0")))
    tts_start_grace_seconds: float = Field(default_factory=lambda: float(os.getenv("TTS_START_GRACE_SECONDS", "0.35")))
    minimax_api_key: str = Field(default_factory=lambda: os.getenv("MINIMAX_API_KEY", ""))
    minimax_ws_url: str = Field(default_factory=lambda: os.getenv("MINIMAX_WS_URL", "wss://api.minimax.io/ws/v1/t2a_v2"))
    minimax_voice_id: str = Field(default_factory=lambda: os.getenv("MINIMAX_VOICE_ID", "Chinese (Mandarin)_Gentleman"))
    minimax_model: str = Field(default_factory=lambda: os.getenv("MINIMAX_MODEL", "speech-2.8-turbo"))
    minimax_start_buffer_ms: int = Field(default_factory=lambda: int(os.getenv("MINIMAX_START_BUFFER_MS", "120")))

    ws_host: str = Field(default_factory=lambda: os.getenv("PPT_WS_HOST", "127.0.0.1"))
    ws_port: int = Field(default_factory=lambda: int(os.getenv("PPT_WS_PORT", "8765")))

    api_host: str = Field(default_factory=lambda: os.getenv("AUTO_PPT_API_HOST", "127.0.0.1"))
    api_port: int = Field(default_factory=lambda: int(os.getenv("AUTO_PPT_API_PORT", "15005")))

    asr_model_size: str = Field(default_factory=lambda: os.getenv("ASR_MODEL_SIZE", "small"))
    asr_device: str = Field(default_factory=lambda: os.getenv("ASR_DEVICE", "cuda"))
    asr_compute_type: str = Field(default_factory=lambda: os.getenv("ASR_COMPUTE_TYPE", "float16"))
    asr_language: str = Field(default_factory=lambda: os.getenv("ASR_LANGUAGE", "zh"))
    asr_rms_threshold: float = Field(default_factory=lambda: float(os.getenv("ASR_RMS_THRESHOLD", "0.012")))
    asr_silence_seconds: float = Field(default_factory=lambda: float(os.getenv("ASR_SILENCE_SECONDS", "0.5")))
    asr_min_speech_seconds: float = Field(default_factory=lambda: float(os.getenv("ASR_MIN_SPEECH_SECONDS", "0.35")))
    asr_max_speech_seconds: float = Field(default_factory=lambda: float(os.getenv("ASR_MAX_SPEECH_SECONDS", "20.0")))
    asr_meter_scale: float = Field(default_factory=lambda: float(os.getenv("ASR_METER_SCALE", "8.0")))
    asr_vad_filter: bool = Field(default_factory=lambda: os.getenv("ASR_VAD_FILTER", "1").lower() in {"1", "true", "yes", "on"})

    @property
    def web_root(self) -> Path:
        return self.project_root / self.web_dir_name

    @property
    def web_pages_root(self) -> Path:
        return self.web_root / self.pages_dir_name

    @property
    def skills_path(self) -> Path:
        return self.project_root / self.skills_dir_name

    @property
    def tts_urls(self) -> dict[str, str]:
        return {
            "speak": f"{self.tts_base_url}/speak",
            "speak_stream": f"{self.tts_base_url}/speak_stream",
            "preload": f"{self.tts_base_url}/preload",
            "stop": f"{self.tts_base_url}/stop",
            "status": f"{self.tts_base_url}/status",
        }

    @property
    def ws_url(self) -> str:
        return f"ws://{self.ws_host}:{self.ws_port}"

    @property
    def tts_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self.tts_timeout_seconds, connect=self.tts_connect_timeout_seconds)

    def public_runtime_config(self) -> dict[str, object]:
        return {
            "api_base_url": f"http://{self.api_host}:{self.api_port}",
            "tts_base_url": self.tts_base_url,
            "ws_host": self.ws_host,
            "ws_port": self.ws_port,
            "ws_url": self.ws_url,
            "openai_model": self.openai_model,
            "openai_base_url": self.openai_base_url,
            "asr_model_size": self.asr_model_size,
            "asr_device": self.asr_device,
            "minimax_model": self.minimax_model,
            "minimax_voice_id": self.minimax_voice_id,
        }


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("auto_ppt")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

if settings.langchain_debug:
    os.environ["LANGCHAIN_DEBUG"] = "true"
if settings.langchain_verbose:
    os.environ["LANGCHAIN_VERBOSE"] = "true"

if lc_set_debug is not None:
    lc_set_debug(settings.langchain_debug)
if lc_set_verbose is not None:
    lc_set_verbose(settings.langchain_verbose)


def preview_text(value: str, limit: int = 160) -> str:
    text = (value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
