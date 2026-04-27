from __future__ import annotations

import asyncio
import pathlib
import sys
import time

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

if __package__ is None or __package__ == "":
    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.asr_service import LocalASRService
from app.agent_runtime import AgentRuntime
from app.config import logger, preview_text, settings
from app.models import ASRStartRequest, AppMode, AppState, ChatRequest, PageEnterRequest
from app.ppt_runtime import PPTBridge, Presenter
from app.session import SessionManager
from app.text_utils import parse_agent_json, sse_event
from app.tools import ToolRegistry
from app.tts_service import TTSService
from app.env_utils import set_project_env, get_project_env_values, read_project_env

app = FastAPI(title="Deep Agent Service (Defense Orchestrator)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

state = AppState()
tts = TTSService()
ppt = PPTBridge()
presenter = Presenter(state=state, tts=tts, ppt=ppt)
session_manager = SessionManager(presenter=presenter, tts=tts)
agent_runtime: AgentRuntime | None = None
asr_service = LocalASRService()
tool_map: dict[str, object] = {}


def build_runtime_context(raw_user_text: str) -> str:
    current_script = (state.current_script or "").strip()
    current_page_text = (state.current_page_text or "").strip()
    context_lines = [
        "Runtime context:",
        f"- mode: {state.mode}",
        f"- current_page: {state.current_page}",
        f"- resume_page: {state.resume_page}",
        f"- resume_segment_index: {state.resume_segment_index}",
        f"- presentation_started: {state.presentation_started}",
        f"- presentation_finished: {state.presentation_finished}",
        f"- qa_locked: {state.qa_locked}",
        f"- auto_play: {presenter.auto_play}",
        "",
    ]
    if current_page_text:
        context_lines.extend(["Current page text:", current_page_text, ""])
    if current_script:
        context_lines.extend(["Current speaker notes:", current_script, ""])
    context_lines.extend(["User instruction:", raw_user_text])
    return "\n".join(context_lines)


def summarize_state() -> dict:
    return {
        "mode": str(state.mode),
        "current_page": state.current_page,
        "resume_page": state.resume_page,
        "resume_segment_index": state.resume_segment_index,
        "presentation_started": state.presentation_started,
        "presentation_finished": state.presentation_finished,
        "qa_locked": state.qa_locked,
        "presenter_page": presenter.page,
        "presenter_index": presenter.index,
        "segment_total": len(presenter.segments),
        "auto_play": presenter.auto_play,
        "ws_clients": len(ppt.clients),
    }


async def get_runtime_status() -> dict:
    tts_status: dict = {
        "available": False,
        "is_playing": False,
        "is_generating": False,
        "task_queue_size": 0,
        "audio_queue_size": 0,
    }
    try:
        response = await tts.client.get(settings.tts_urls["status"])
        response.raise_for_status()
        data = response.json()
        tts_status = {
            "available": True,
            "is_playing": bool(data.get("is_playing")),
            "is_generating": bool(data.get("is_generating")),
            "task_queue_size": int(data.get("task_queue_size", 0)),
            "audio_queue_size": int(data.get("audio_queue_size", data.get("queue_size", 0))),
        }
    except Exception as exc:
        tts_status["error"] = str(exc)

    return {
        "presentation": summarize_state(),
        "asr": asr_service.status(),
        "tts": tts_status,
        "agent": {
            "active": bool(session_manager.active_task and not session_manager.active_task.done()),
            "presenter_task_active": bool(presenter.task and not presenter.task.done()),
        },
    }


if settings.web_root.is_dir():
    app.mount("/web", StaticFiles(directory=str(settings.web_root), html=True), name="web")
if settings.web_pages_root.is_dir():
    app.mount("/pages", StaticFiles(directory=str(settings.web_pages_root), html=True), name="pages")


@app.on_event("startup")
async def on_startup() -> None:
    global agent_runtime, tool_map
    await tts.startup()
    await ppt.startup()
    await asr_service.startup()
    tools = ToolRegistry(state=state, presenter=presenter, session=session_manager, ppt=ppt).build()
    tool_map = {tool.name: tool for tool in tools}
    agent_runtime = AgentRuntime(tools=tools)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await session_manager.stop_active_task()
    await asr_service.shutdown()
    await ppt.shutdown()
    await tts.shutdown()


@app.get("/")
async def root():
    if (settings.web_root / "index.html").is_file():
        return RedirectResponse(url="/web/")
    return {"status": "ok"}


@app.get("/ppt/pages")
async def ppt_pages():
    pages: list[int] = []
    try:
        for item in settings.web_pages_root.iterdir():
            if item.suffix == ".html" and item.stem.isdigit():
                pages.append(int(item.stem))
    except Exception:
        pages = []
    pages = sorted(set(pages))
    return {"pages": pages, "total": pages[-1] if pages else 0}


@app.get("/asr/devices")
async def asr_devices():
    return {"devices": asr_service.list_devices(), "status": asr_service.status()}


@app.get("/asr/status")
async def asr_status():
    return asr_service.status()


@app.get("/runtime/status")
async def runtime_status():
    return await get_runtime_status()


@app.get("/runtime/config")
async def runtime_config():
    return settings.public_runtime_config()


class EnvUpdateRequest(BaseModel):
    entries: dict[str, str] = Field(default_factory=dict)


@app.get("/runtime/env/status")
async def runtime_env_status():
    kv = read_project_env()
    return {
        "has_openai_key": bool(kv.get("OPENAI_API_KEY", "").strip()),
        "has_minimax_key": bool(kv.get("MINIMAX_API_KEY", "").strip()),
    }


@app.get("/runtime/env/values")
async def runtime_env_values():
    allowed = [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_TEMPERATURE",
        "MINIMAX_API_KEY",
        "MINIMAX_WS_URL",
        "MINIMAX_MODEL",
        "MINIMAX_VOICE_ID",
        "MINIMAX_START_BUFFER_MS",
    ]
    values = get_project_env_values(allowed, mask_secrets=True)
    fallbacks = {
        "OPENAI_BASE_URL": settings.openai_base_url,
        "OPENAI_MODEL": settings.openai_model,
        "OPENAI_TEMPERATURE": str(settings.openai_temperature),
        "MINIMAX_WS_URL": settings.minimax_ws_url,
        "MINIMAX_MODEL": settings.minimax_model,
        "MINIMAX_VOICE_ID": settings.minimax_voice_id,
        "MINIMAX_START_BUFFER_MS": str(settings.minimax_start_buffer_ms),
    }
    for k, fb in fallbacks.items():
        item = values.get(k)
        if item and not item.get("has_value"):
            item["value"] = fb
    return {"values": values}


@app.post("/runtime/env/update")
async def runtime_env_update(req: EnvUpdateRequest):
    allowed = {
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_TEMPERATURE",
        "MINIMAX_API_KEY",
        "MINIMAX_WS_URL",
        "MINIMAX_MODEL",
        "MINIMAX_VOICE_ID",
        "MINIMAX_START_BUFFER_MS",
    }
    payload = {k: v for k, v in (req.entries or {}).items() if k in allowed}
    if not payload:
        return {"status": "error", "detail": "no valid entries provided"}
    set_project_env(payload)
    return {"status": "success", "updated_keys": sorted(payload.keys()), "restart_required": True}


@app.post("/asr/start")
async def asr_start(req: ASRStartRequest):
    result = await asr_service.start(device_index=req.device_index)
    return {"status": "success", **result}


@app.post("/asr/stop")
async def asr_stop():
    result = await asr_service.stop()
    return {"status": "success", **result}


@app.post("/presentation/start")
async def presentation_start_direct():
    tool = tool_map.get("presentation_start")
    if tool is None:
        return {"status": "error", "detail": "presentation_start tool is not available"}
    result = await tool.ainvoke({"from_page": 1})
    return {"status": "success", "message": result, "state": summarize_state()}


@app.post("/presentation/resume")
async def presentation_resume_direct():
    tool = tool_map.get("presentation_resume")
    if tool is None:
        return {"status": "error", "detail": "presentation_resume tool is not available"}
    result = await tool.ainvoke({"from_saved_point": True})
    return {"status": "success", "message": result, "state": summarize_state()}


@app.post("/presentation/enter-defense-qa")
async def presentation_enter_defense_qa_direct():
    tool = tool_map.get("presentation_enter_defense_qa")
    if tool is None:
        return {"status": "error", "detail": "presentation_enter_defense_qa tool is not available"}
    result = await tool.ainvoke({})
    return {"status": "success", "message": result, "state": summarize_state()}


@app.get("/asr/events")
async def asr_events():
    async def event_generator():
        q = asr_service.subscribe()
        try:
            yield sse_event({"type": "asr_snapshot", **asr_service.status()})
            while True:
                payload = await q.get()
                yield sse_event(payload)
        except asyncio.CancelledError:
            raise
        finally:
            asr_service.unsubscribe(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/ppt/page_enter")
async def ppt_page_enter(req: PageEnterRequest):
    state.current_page = req.page
    state.current_script = req.script or ""
    state.current_page_text = req.page_text or ""

    try:
        total_pages = presenter.get_total_page_number()
    except Exception:
        total_pages = 0
    if total_pages > 0 and state.presentation_started and req.page >= total_pages and not state.qa_locked:
        state.qa_locked = True
        state.presentation_finished = True
        logger.info("ppt_page_enter: qa lock engaged at final page=%s total=%s", req.page, total_pages)

    changed = presenter.load(req.page, req.script, req.page_text)
    logger.info(
        "ppt_page_enter: page=%s changed=%s segments=%d mode=%s auto_play=%s",
        req.page,
        changed,
        len(presenter.segments),
        state.mode,
        presenter.auto_play,
    )
    logger.info(
        "ppt_page_enter detail: script_preview=%s page_text_preview=%s",
        preview_text(req.script),
        preview_text(req.page_text),
    )

    natural_auto_advance = (
        changed
        and state.mode == AppMode.PRESENTING
        and presenter.auto_play
        and presenter.awaiting_auto_page_advance
    )
    if changed and not natural_auto_advance:
        await session_manager.stop_audio()
    elif natural_auto_advance:
        logger.info("ppt_page_enter: natural auto advance detected, skipping stop_audio for page=%s", req.page)
    if natural_auto_advance and presenter.segments:
        await presenter.start(0)

    return {"status": "ok", "page": req.page, "segments": len(presenter.segments)}


@app.post("/chat")
async def chat(req: ChatRequest):
    assert agent_runtime is not None
    logger.info("chat request: text=%s state=%s", preview_text(req.text), summarize_state())

    if state.mode == AppMode.PRESENTING:
        state.resume_page = presenter.page
        state.resume_segment_index = presenter.index
        state.mode = AppMode.INTERRUPTED_QA
        presenter.auto_play = False

    await session_manager.stop_active_task()

    async def event_generator():
        current_task = asyncio.current_task()
        session_manager.active_task = current_task

        started_at = time.perf_counter()
        first_ai_at: float | None = None
        tool_count = 0
        ai_chunks = 0
        ai_chars = 0

        logger.info(
            "chat start: thread_id=%s raw_len=%d current_page=%s mode=%s ws_clients=%d",
            req.thread_id,
            len(req.text or ""),
            state.current_page,
            state.mode,
            len(ppt.clients),
        )

        config = {"configurable": {"thread_id": req.thread_id}}
        if state.current_page is None:
            await presenter.refresh_page_data(timeout=1.0)

        inputs = agent_runtime.build_inputs(build_runtime_context(req.text))
        assistant_buffer = ""
        streamed_text_buffer = ""
        streamed_text_last_log_len = 0
        stop_after_tool = False
        terminating_tools = {
            "ppt_navigate",
            "presentation_start",
            "presentation_resume",
            "presentation_replay_page",
            "presentation_enter_defense_qa",
            "presentation_finish",
        }
        qa_safe_redirect_tools = {
            "ppt_navigate",
            "presentation_start",
            "presentation_resume",
            "presentation_replay_page",
        }
        logger.info("chat runtime context preview: %s", preview_text(build_runtime_context(req.text), limit=320))

        try:
            async for chunk in agent_runtime.agent.astream(inputs, config=config, stream_mode="messages"):
                msg = chunk[0] if isinstance(chunk, tuple) and len(chunk) > 0 else chunk
                content = getattr(msg, "content", "") or ""
                msg_type = getattr(msg, "type", None) or ""
                msg_name = getattr(msg, "name", None)

                if msg_type == "tool" and msg_name in {
                    "get_presentation_state",
                    "ppt_navigate",
                    "presentation_start",
                    "presentation_pause",
                    "presentation_resume",
                    "presentation_replay_page",
                    "presentation_jump_and_hold",
                    "presentation_jump_for_qa",
                    "presentation_enter_defense_qa",
                    "presentation_finish",
                }:
                    ack = str(content).strip()
                    if ack:
                        tool_count += 1
                        logger.info("chat stream tool: name=%s content=%s", msg_name, preview_text(ack, limit=220))
                        if streamed_text_buffer.strip():
                            logger.info(
                                "chat stream ai partial before tool: len=%s text=%s",
                                len(streamed_text_buffer),
                                preview_text(streamed_text_buffer, limit=320),
                            )
                            streamed_text_last_log_len = len(streamed_text_buffer)
                        yield sse_event({"type": "tool", "name": msg_name, "text": ack, "tts": False})
                    if msg_name in terminating_tools and not (state.qa_locked and msg_name in qa_safe_redirect_tools):
                        stop_after_tool = True
                        logger.info("chat terminating after tool: name=%s", msg_name)
                        break
                    continue

                if msg_type not in {"ai", "AIMessageChunk"}:
                    continue

                if stop_after_tool:
                    logger.info("chat ai ignored after terminating tool: name=%s", msg_name)
                    continue

                text = str(content)
                if not text:
                    continue

                if first_ai_at is None:
                    first_ai_at = time.perf_counter()
                    logger.info("chat first_ai: latency_ms=%d", int((first_ai_at - started_at) * 1000))

                ai_chunks += 1
                ai_chars += len(text)
                assistant_buffer += text
                streamed_text_buffer += text
                if len(streamed_text_buffer) - streamed_text_last_log_len >= 120 or text.endswith((".", "!", "?", "。", "！", "？", "\n")):
                    logger.info(
                        "chat stream ai partial: len=%s text=%s",
                        len(streamed_text_buffer),
                        preview_text(streamed_text_buffer, limit=320),
                    )
                    streamed_text_last_log_len = len(streamed_text_buffer)
                yield sse_event({"type": "ai", "text": text, "tts": None})

            final_text = "" if stop_after_tool else assistant_buffer.strip()
            logger.info("chat final_text: %s", preview_text(final_text, limit=320))
            if final_text and state.mode != AppMode.PRESENTING:
                parsed = parse_agent_json(final_text)
                if parsed is None:
                    yield sse_event({"type": "final", "text": final_text, "tts": True, "tts_text": final_text})
                    await tts.speak_text(final_text)
                else:
                    display_text, tts_text, send_to_tts = parsed
                    yield sse_event({"type": "final", "text": display_text, "tts": send_to_tts, "tts_text": tts_text})
                    if send_to_tts and tts_text.strip():
                        await tts.speak_text(tts_text)

            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            logger.info("chat cancelled")
            raise
        except Exception as exc:
            logger.exception("chat error: %s", exc)
            yield sse_event({"error": str(exc)})
        finally:
            if session_manager.active_task == current_task:
                session_manager.active_task = None
            logger.info(
                "chat done: total_ms=%d tool_calls=%d ai_chunks=%d ai_chars=%d state=%s",
                int((time.perf_counter() - started_at) * 1000),
                tool_count,
                ai_chunks,
                ai_chars,
                summarize_state(),
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/stop")
async def stop():
    logger.info("stop endpoint called: state=%s", summarize_state())
    if state.mode == AppMode.PRESENTING:
        state.resume_page = presenter.page
        state.resume_segment_index = presenter.index
        state.mode = AppMode.WAITING_RESUME
        presenter.auto_play = False
    await session_manager.stop_active_task()
    return {"status": "success"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=False)
