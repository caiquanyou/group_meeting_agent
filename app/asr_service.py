from __future__ import annotations

import asyncio
import contextlib
import math
import os
import queue
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

from .config import logger, settings

try:
    from faster_whisper import WhisperModel
except Exception as exc:  # pragma: no cover - import guard for local env
    WhisperModel = None
    _WHISPER_IMPORT_ERROR = exc
else:
    _WHISPER_IMPORT_ERROR = None


class LocalASRService:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.model: WhisperModel | None = None
        self.model_lock = threading.Lock()

        self._running = False
        self._device_index: Optional[int] = None
        self._device_name: str = ""
        self._sample_rate: int = 16000
        self._last_text: str = ""
        self._last_error: str = ""
        self._meter_level: float = 0.0

        self._subscriber_lock = threading.Lock()
        self._subscribers: set[asyncio.Queue[dict]] = set()

        self._stop_event = threading.Event()
        self._audio_queue: queue.Queue[tuple[np.ndarray, float]] = queue.Queue(maxsize=512)
        self._worker_thread: threading.Thread | None = None

    async def startup(self) -> None:
        self.loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._ensure_model_loaded)

    async def shutdown(self) -> None:
        await self.stop()

    def list_devices(self) -> list[dict]:
        hostapis = sd.query_hostapis()
        devices = sd.query_devices()
        result: list[dict] = []
        for idx, device in enumerate(devices):
            max_inputs = int(device.get("max_input_channels", 0) or 0)
            if max_inputs <= 0:
                continue
            hostapi_index = int(device.get("hostapi", -1))
            hostapi_name = ""
            if 0 <= hostapi_index < len(hostapis):
                hostapi_name = str(hostapis[hostapi_index].get("name", ""))
            result.append(
                {
                    "index": idx,
                    "name": str(device.get("name", f"Input {idx}")),
                    "hostapi": hostapi_name,
                    "max_input_channels": max_inputs,
                    "default_samplerate": int(float(device.get("default_samplerate", 16000) or 16000)),
                    "selected": idx == self._device_index,
                }
            )
        return result

    def status(self) -> dict:
        return {
            "running": self._running,
            "device_index": self._device_index,
            "device_name": self._device_name,
            "sample_rate": self._sample_rate,
            "meter_level": self._meter_level,
            "last_text": self._last_text,
            "last_error": self._last_error,
            "model_loaded": self.model is not None,
        }

    async def start(self, device_index: Optional[int] = None) -> dict:
        await self.stop()
        await asyncio.to_thread(self._ensure_model_loaded)

        devices = self.list_devices()
        if not devices:
            raise RuntimeError("No input audio devices are available for ASR.")

        target_index = device_index if device_index is not None else self._pick_default_device_index(devices)
        target_device = next((d for d in devices if d["index"] == target_index), None)
        if target_device is None:
            raise RuntimeError(f"Input device {target_index} is not available.")

        self._device_index = int(target_device["index"])
        self._device_name = str(target_device["name"])
        self._sample_rate = int(target_device["default_samplerate"] or 16000)
        self._last_error = ""
        self._last_text = ""
        self._meter_level = 0.0
        self._stop_event.clear()
        self._running = True
        self._worker_thread = threading.Thread(target=self._capture_worker, name="asr-capture", daemon=True)
        self._worker_thread.start()
        self._publish({"type": "asr_status", "status": "running", "device_name": self._device_name, "device_index": self._device_index})
        logger.info("asr.start: device_index=%s device_name=%s sample_rate=%s", self._device_index, self._device_name, self._sample_rate)
        return self.status()

    async def stop(self) -> dict:
        was_running = self._running
        self._running = False
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            await asyncio.to_thread(self._worker_thread.join, 2.0)
        self._worker_thread = None
        self._clear_audio_queue()
        self._meter_level = 0.0
        if was_running:
            self._publish({"type": "asr_status", "status": "stopped"})
            logger.info("asr.stop: device_index=%s device_name=%s", self._device_index, self._device_name)
        return self.status()

    def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
        with self._subscriber_lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        with self._subscriber_lock:
            self._subscribers.discard(q)

    def _pick_default_device_index(self, devices: list[dict]) -> int:
        try:
            default_input, _ = sd.default.device
        except Exception:
            default_input = None
        if isinstance(default_input, int) and any(d["index"] == default_input for d in devices):
            return default_input
        return int(devices[0]["index"])

    def _ensure_model_loaded(self) -> None:
        if self.model is not None:
            return
        if WhisperModel is None:
            raise RuntimeError(f"faster_whisper is not available: {_WHISPER_IMPORT_ERROR}")
        with self.model_lock:
            if self.model is not None:
                return
            logger.info(
                "asr.model.load: model_size=%s device=%s compute_type=%s",
                settings.asr_model_size,
                settings.asr_device,
                settings.asr_compute_type,
            )
            self.model = WhisperModel(
                settings.asr_model_size,
                device=settings.asr_device,
                compute_type=settings.asr_compute_type,
            )

    def _publish(self, payload: dict) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._publish_now, payload)

    def _publish_now(self, payload: dict) -> None:
        with self._subscriber_lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(payload)

    def _clear_audio_queue(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                return

    def _capture_worker(self) -> None:
        try:
            self._run_capture_loop()
        except Exception as exc:
            self._last_error = str(exc)
            self._publish({"type": "asr_error", "message": str(exc)})
            logger.exception("asr.capture error: %s", exc)
        finally:
            self._running = False
            self._meter_level = 0.0

    def _run_capture_loop(self) -> None:
        threshold = float(settings.asr_rms_threshold)
        silence_limit = float(settings.asr_silence_seconds)
        min_speech = float(settings.asr_min_speech_seconds)
        max_speech = float(settings.asr_max_speech_seconds)
        blocksize = max(256, int(self._sample_rate * 0.1))
        utterance_chunks: list[np.ndarray] = []
        voiced_seconds = 0.0
        silence_seconds = 0.0
        total_seconds = 0.0
        last_meter_emit = 0.0

        def callback(indata, frames, _time_info, status) -> None:
            nonlocal last_meter_emit
            if status:
                logger.warning("asr.input status: %s", status)
            samples = np.asarray(indata[:, 0], dtype=np.float32).copy()
            if samples.size == 0:
                return
            rms = float(math.sqrt(float(np.mean(np.square(samples)))))
            self._meter_level = min(1.0, rms * settings.asr_meter_scale)
            now = time.time()
            if now - last_meter_emit >= 0.12:
                last_meter_emit = now
                self._publish({"type": "asr_meter", "level": self._meter_level})
            try:
                self._audio_queue.put_nowait((samples, rms))
            except queue.Full:
                with contextlib.suppress(queue.Empty):
                    self._audio_queue.get_nowait()
                with contextlib.suppress(queue.Full):
                    self._audio_queue.put_nowait((samples, rms))

        logger.info(
            "asr.capture.start: device_index=%s device_name=%s sample_rate=%s blocksize=%s",
            self._device_index,
            self._device_name,
            self._sample_rate,
            blocksize,
        )
        with sd.InputStream(
            device=self._device_index,
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
            callback=callback,
        ):
            while not self._stop_event.is_set():
                try:
                    chunk, rms = self._audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                chunk_seconds = len(chunk) / float(self._sample_rate)
                if rms >= threshold:
                    utterance_chunks.append(chunk)
                    voiced_seconds += chunk_seconds
                    total_seconds += chunk_seconds
                    silence_seconds = 0.0
                    continue

                if utterance_chunks:
                    utterance_chunks.append(chunk)
                    total_seconds += chunk_seconds
                    silence_seconds += chunk_seconds
                    if (voiced_seconds >= min_speech and silence_seconds >= silence_limit) or total_seconds >= max_speech:
                        self._finalize_utterance(utterance_chunks, voiced_seconds)
                        utterance_chunks = []
                        voiced_seconds = 0.0
                        silence_seconds = 0.0
                        total_seconds = 0.0

            if utterance_chunks and voiced_seconds >= min_speech:
                self._finalize_utterance(utterance_chunks, voiced_seconds)
        logger.info("asr.capture.stop: device_index=%s device_name=%s", self._device_index, self._device_name)

    def _finalize_utterance(self, chunks: list[np.ndarray], voiced_seconds: float) -> None:
        if not chunks or voiced_seconds < float(settings.asr_min_speech_seconds):
            return
        audio = np.concatenate(chunks).astype(np.float32, copy=False)
        text = self._transcribe_audio(audio)
        if not text:
            return
        self._last_text = text
        self._publish({"type": "asr_final", "text": text})
        logger.info("asr.final: text=%s", text)

    def _transcribe_audio(self, audio: np.ndarray) -> str:
        self._ensure_model_loaded()
        assert self.model is not None

        fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="auto_ppt_asr_")
        os.close(fd)
        path = Path(tmp_path)
        try:
            pcm = np.clip(audio, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype(np.int16)
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self._sample_rate)
                wav_file.writeframes(pcm.tobytes())

            segments, info = self.model.transcribe(
                str(path),
                beam_size=1,
                language=settings.asr_language or None,
                vad_filter=settings.asr_vad_filter,
            )
            text = " ".join((segment.text or "").strip() for segment in segments).strip()
            logger.info(
                "asr.transcribe: language=%s probability=%.2f text=%s",
                getattr(info, "language", ""),
                float(getattr(info, "language_probability", 0.0) or 0.0),
                text,
            )
            return text
        finally:
            with contextlib.suppress(Exception):
                path.unlink(missing_ok=True)
