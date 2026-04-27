from __future__ import annotations

import json
import re
from typing import Optional


def segment_script(text: str) -> list[str]:
    content = (text or "").strip()
    if not content:
        return []

    parts: list[str] = []
    buf = ""
    split_pat = re.compile(r"([。！？!?；;]\s*|\n+)")
    for ch in content:
        buf += ch
        m = split_pat.search(buf)
        if m and m.end() == len(buf):
            s = buf.strip()
            if s:
                parts.append(s)
            buf = ""
    if buf.strip():
        parts.append(buf.strip())

    segments: list[str] = []
    current = ""
    for part in parts:
        if not current:
            current = part
        elif len(current) < 60:
            current = f"{current} {part}".strip()
        else:
            segments.append(current.strip())
            current = part

        if len(current) >= 160:
            segments.append(current.strip())
            current = ""

    if current.strip():
        segments.append(current.strip())
    return segments


def parse_agent_json(text: str) -> Optional[tuple[str, str, bool]]:
    raw = (text or "").strip()
    if not raw or not (raw.startswith("{") and raw.endswith("}")):
        return None

    try:
        obj = json.loads(raw)
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    display_text = str(obj.get("text") or obj.get("display") or "")
    tts_text = str(obj.get("tts_text") or obj.get("speak") or display_text or "")
    send_to_tts = obj.get("tts")
    if send_to_tts is None:
        send_to_tts = obj.get("send_to_tts")
    if send_to_tts is None:
        send_to_tts = True

    return display_text, tts_text, bool(send_to_tts)


def sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
