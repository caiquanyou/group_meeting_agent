from __future__ import annotations

import asyncio
import json
import queue
import pathlib
import sys
import threading
import time
from dataclasses import dataclass, field

import numpy as np
import sounddevice as sd
import websockets
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

if __package__ is None or __package__ == "":
    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import settings

app = FastAPI(title="MiniMax TTS Server")
START_BUFFER_MS = settings.minimax_start_buffer_ms

audio_queue: queue.Queue[tuple[np.ndarray, int]] = queue.Queue()
tts_task_queue: asyncio.Queue["SpeakRequest"] | None = None
_worker_task: asyncio.Task | None = None
_player_thread: threading.Thread | None = None
_preload_tasks: dict[str, asyncio.Task] = {}
_preloaded_audio: dict[str, "PreloadedAudio"] = {}
_preload_lock: asyncio.Lock | None = None

_stop_event = threading.Event()
_is_playing_event = threading.Event()
_await_prebuffer_event = threading.Event()
_tts_generating_event = threading.Event()


@dataclass
class PreloadedAudio:
    session_id: str
    utterance_id: str
    text: str
    chunks: list[tuple[np.ndarray, int]] = field(default_factory=list)


class SpeakRequest(BaseModel):
    text: str = Field(..., description="Text to speak")
    voice_id: str = Field(default_factory=lambda: settings.minimax_voice_id, description="Voice ID")
    model: str = Field(default_factory=lambda: settings.minimax_model, description="Model name")
    speed: float = Field(default=1.0, description="Speech speed")
    vol: float = Field(default=1.0, description="Volume")
    sample_rate: int = Field(default=32000, description="Output sample rate")
    session_id: str = Field(default="", description="Playback session ID")
    utterance_id: str = Field(default="", description="Utterance ID")


def _ensure_player_started() -> None:
    global _player_thread
    if _player_thread is not None and _player_thread.is_alive():
        return

    def audio_player_thread() -> None:
        target_sr = 32000
        pending_samples = np.zeros((0, 2), dtype=np.float32)
        required_prebuffer_frames = max(1, int(target_sr * START_BUFFER_MS / 1000))

        def callback(outdata, frames, time_info, status):
            nonlocal pending_samples

            if _stop_event.is_set():
                outdata.fill(0)
                pending_samples = np.zeros((0, 2), dtype=np.float32)
                _is_playing_event.clear()
                _await_prebuffer_event.clear()
                return

            while len(pending_samples) < frames and not audio_queue.empty():
                try:
                    raw_samples, _ = audio_queue.get_nowait()
                except queue.Empty:
                    break

                if raw_samples.ndim == 1:
                    raw_samples = np.stack([raw_samples, raw_samples], axis=1)
                pending_samples = np.vstack([pending_samples, raw_samples])

            if _await_prebuffer_event.is_set():
                if len(pending_samples) < required_prebuffer_frames and _tts_generating_event.is_set():
                    outdata.fill(0)
                    _is_playing_event.clear()
                    return
                _await_prebuffer_event.clear()

            if len(pending_samples) >= frames:
                outdata[:] = pending_samples[:frames]
                pending_samples = pending_samples[frames:]
                _is_playing_event.set()
                return

            if len(pending_samples) > 0:
                outdata[: len(pending_samples)] = pending_samples
            outdata[len(pending_samples) :].fill(0)
            pending_samples = np.zeros((0, 2), dtype=np.float32)
            if audio_queue.empty():
                _is_playing_event.clear()
            else:
                _is_playing_event.set()

        try:
            with sd.OutputStream(samplerate=target_sr, channels=2, callback=callback):
                while True:
                    time.sleep(0.1)
        except Exception as exc:
            print(f"Audio Stream Error: {exc}")

    _player_thread = threading.Thread(target=audio_player_thread, daemon=True)
    _player_thread.start()


def process_pcm_data(pcm_bytes: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    samples /= 32768.0
    return samples


def _get_minimax_api_key() -> str:
    return settings.minimax_api_key


def _require_task_queue() -> asyncio.Queue[SpeakRequest]:
    if tts_task_queue is None:
        raise HTTPException(status_code=503, detail="TTS worker not initialized")
    return tts_task_queue


def _get_preload_lock() -> asyncio.Lock:
    global _preload_lock
    if _preload_lock is None:
        _preload_lock = asyncio.Lock()
    return _preload_lock


def _clear_audio_queue() -> None:
    while True:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            return


def _clear_task_queue(q: asyncio.Queue[SpeakRequest]) -> None:
    while True:
        try:
            q.get_nowait()
            q.task_done()
        except asyncio.QueueEmpty:
            return


async def _cancel_preload_task(utterance_id: str) -> None:
    task = _preload_tasks.pop(utterance_id, None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except BaseException:
        pass


async def _clear_preloads() -> None:
    for utterance_id in list(_preload_tasks.keys()):
        await _cancel_preload_task(utterance_id)
    _preloaded_audio.clear()


async def _stream_minimax(req: SpeakRequest, *, sink: queue.Queue[tuple[np.ndarray, int]] | list[tuple[np.ndarray, int]]) -> None:
    api_key = _get_minimax_api_key()
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY is not set")

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        try:
            ws_cm = websockets.connect(settings.minimax_ws_url, additional_headers=headers)
        except TypeError:
            ws_cm = websockets.connect(settings.minimax_ws_url, extra_headers=headers)

        async with ws_cm as ws:
            try:
                await asyncio.wait_for(ws.recv(), timeout=5.0)
            except Exception:
                pass

            await ws.send(json.dumps({
                "event": "task_start",
                "model": req.model,
                "voice_setting": {"voice_id": req.voice_id, "speed": req.speed, "vol": req.vol},
                "audio_setting": {"format": "pcm", "sample_rate": req.sample_rate, "channel": 1},
            }))
            try:
                await asyncio.wait_for(ws.recv(), timeout=5.0)
            except Exception:
                pass

            await ws.send(json.dumps({"event": "task_continue", "text": req.text}))

            while True:
                if sink is audio_queue and _stop_event.is_set():
                    break

                try:
                    raw_resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    break

                if isinstance(raw_resp, (bytes, bytearray)):
                    raw_resp = raw_resp.decode("utf-8", errors="ignore")
                resp = json.loads(raw_resp)

                if "data" in resp and "audio" in resp["data"]:
                    hex_audio = resp["data"]["audio"]
                    if hex_audio:
                        pcm_bytes = bytes.fromhex(hex_audio)
                        samples = process_pcm_data(pcm_bytes)
                        chunk = (samples, req.sample_rate)
                        if sink is audio_queue:
                            audio_queue.put(chunk)
                        else:
                            sink.append(chunk)

                if resp.get("is_final"):
                    break
    finally:
        if sink is audio_queue:
            _tts_generating_event.clear()


async def stream_tts_logic(req: SpeakRequest) -> None:
    print(f"--- Processing TTS: {req.text[:30]}...")
    _await_prebuffer_event.set()
    _tts_generating_event.set()
    try:
        await _stream_minimax(req, sink=audio_queue)
    except Exception as exc:
        print(f"--- TTS API Error: {exc}")


async def _collect_tts_audio(req: SpeakRequest) -> list[tuple[np.ndarray, int]]:
    chunks: list[tuple[np.ndarray, int]] = []
    await _stream_minimax(req, sink=chunks)
    return chunks


async def tts_worker(task_queue: asyncio.Queue[SpeakRequest]) -> None:
    while True:
        req = await task_queue.get()
        try:
            await stream_tts_logic(req)
        except Exception as exc:
            print(f"Worker Error: {exc}")
        finally:
            task_queue.task_done()


async def _start_preload(req: SpeakRequest) -> str:
    if not req.session_id or not req.utterance_id:
        raise HTTPException(status_code=400, detail="session_id and utterance_id are required")

    lock = _get_preload_lock()
    async with lock:
        existing = _preloaded_audio.get(req.utterance_id)
        if existing and existing.session_id == req.session_id and existing.text == req.text:
            return "cached"
        if req.utterance_id in _preload_tasks:
            return "loading"

        async def _runner() -> None:
            chunks = await _collect_tts_audio(req)
            _preloaded_audio[req.utterance_id] = PreloadedAudio(
                session_id=req.session_id,
                utterance_id=req.utterance_id,
                text=req.text,
                chunks=chunks,
            )

        task = asyncio.create_task(_runner(), name=f"tts-preload-{req.utterance_id}")
        _preload_tasks[req.utterance_id] = task

        def _cleanup(done_task: asyncio.Task, *, utterance_id: str = req.utterance_id) -> None:
            _preload_tasks.pop(utterance_id, None)
            try:
                done_task.result()
            except BaseException:
                pass

        task.add_done_callback(_cleanup)
        return "started"


async def _consume_preloaded(req: SpeakRequest, *, wait_timeout: float = 1.5) -> bool:
    if not req.session_id or not req.utterance_id:
        return False

    preload_task = _preload_tasks.get(req.utterance_id)
    if preload_task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(preload_task), timeout=wait_timeout)
        except asyncio.TimeoutError:
            await _cancel_preload_task(req.utterance_id)
            _preloaded_audio.pop(req.utterance_id, None)
            return False
        except Exception:
            await _cancel_preload_task(req.utterance_id)
            _preloaded_audio.pop(req.utterance_id, None)
            return False

    preloaded = _preloaded_audio.pop(req.utterance_id, None)
    if preloaded is None:
        return False
    if preloaded.session_id != req.session_id or preloaded.text != req.text:
        return False

    _await_prebuffer_event.clear()
    _tts_generating_event.clear()
    for chunk in preloaded.chunks:
        audio_queue.put(chunk)
    return True


@app.on_event("startup")
async def startup_event() -> None:
    global tts_task_queue, _worker_task
    if tts_task_queue is None:
        tts_task_queue = asyncio.Queue()
    _ensure_player_started()
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(tts_worker(tts_task_queue))


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _worker_task
    _stop_event.set()
    try:
        sd.stop()
    except Exception:
        pass
    if _worker_task is not None and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except Exception:
            pass
    _worker_task = None
    await _clear_preloads()


@app.post("/speak")
async def speak(req: SpeakRequest):
    if not _get_minimax_api_key():
        raise HTTPException(status_code=500, detail="MINIMAX_API_KEY is not set")

    q = _require_task_queue()
    _stop_event.set()
    try:
        sd.stop()
    except Exception:
        pass

    _clear_task_queue(q)
    _clear_audio_queue()
    await _clear_preloads()

    await asyncio.sleep(0.1)
    _stop_event.clear()

    consumed = await _consume_preloaded(req)
    if consumed:
        return {"status": "success", "info": "played from preload"}

    await q.put(req)
    return {"status": "success", "info": "interrupted and restarted"}


@app.post("/speak_stream")
async def speak_stream(req: SpeakRequest):
    if not _get_minimax_api_key():
        raise HTTPException(status_code=500, detail="MINIMAX_API_KEY is not set")
    q = _require_task_queue()
    consumed = await _consume_preloaded(req)
    if consumed:
        return {"status": "success", "info": "played from preload"}
    await q.put(req)
    return {"status": "success", "info": "added to queue"}


@app.post("/preload")
async def preload(req: SpeakRequest):
    if not _get_minimax_api_key():
        raise HTTPException(status_code=500, detail="MINIMAX_API_KEY is not set")
    info = await _start_preload(req)
    return {"status": "success", "info": info}


@app.post("/stop")
async def stop():
    q = _require_task_queue()
    _stop_event.set()
    _tts_generating_event.clear()
    _await_prebuffer_event.clear()
    try:
        sd.stop()
    except Exception:
        pass
    _clear_task_queue(q)
    _clear_audio_queue()
    await _clear_preloads()
    return {"status": "success"}


@app.get("/status")
async def status():
    q = _require_task_queue()
    return {
        "is_playing": _is_playing_event.is_set(),
        "is_generating": _tts_generating_event.is_set(),
        "audio_queue_size": audio_queue.qsize(),
        "task_queue_size": q.qsize(),
        "preload_task_size": len(_preload_tasks),
        "preloaded_audio_size": len(_preloaded_audio),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.tts_host, port=settings.tts_port, access_log=False)
