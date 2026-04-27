# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Project

```bash
# Start both servers (TTS on :15000, main API on :15005)
python run.py
```

Then open in browser:
- PPT view: `http://127.0.0.1:15005/web/`
- Control panel: `http://127.0.0.1:15005/web/agent_control.html`

## Environment Setup

```bash
conda create -n pptpilot python=3.11 -y
conda activate pptpilot
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:
- `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_MODEL` — LLM for the agent
- `MINIMAX_API_KEY` — MiniMax TTS WebSocket API

All config is loaded from `.env` via `app/config.py` (`Settings` pydantic model). When adding new config, update `.env.example` and `README.md` too.

## Architecture

This is a **presentation orchestrator**, not a chatbot. The agent controls a live PPT slideshow, reads speaker notes, and manages a full defense flow with interruption/resume.

### Dual-service design

`run.py` starts two processes:
1. **TTS server** (`app/tts_server.py`) on `:15000` — handles MiniMax WebSocket TTS and local audio playback
2. **Main server** (`app/main.py`) on `:15005` — FastAPI app with all orchestration logic

### State machine (`app/models.py`)

`AppMode` is the central state enum. Many behaviors that look like bugs are intentional state-machine enforcement:

| State | Meaning |
|---|---|
| `IDLE` | Not started |
| `PRESENTING` | Auto-playing through slides |
| `INTERRUPTED_QA` | Mid-presentation question |
| `WAITING_RESUME` | Paused, waiting for resume command |
| `DEFENSE_QA` | Final QA mode, auto-play permanently locked |

`AppState` holds the full runtime state including `resume_page`, `resume_segment_index`, and `qa_locked`.

### Key components

- **`app/ppt_runtime.py`** — `PPTBridge` (WebSocket server for browser) + `Presenter` (loads speaker notes, segments them, drives TTS playback, auto-advances pages). `Presenter._run` is the highest-risk method.
- **`app/tools.py`** — `ToolRegistry` builds all LangChain tools the agent can call. Every tool that changes `AppMode` is high-risk.
- **`app/agent_runtime.py`** — Wraps `deepagents.create_deep_agent` with the system prompt. The `## Slide Anchors And Jump Rule` section maps question topics to page numbers — this must be updated when slides change.
- **`app/asr_service.py`** — Local microphone input via `faster-whisper`.
- **`app/session.py`** — `SessionManager` tracks the active async task and handles stop/cancel.

### Frontend–backend coupling

`web/index.html` connects to the WebSocket at `ws://127.0.0.1:8765` and:
1. Receives navigation commands (`next`, `prev`, `jump`, `request_page_data`)
2. On page change, POSTs to `/ppt/page_enter` with `{ page, script, page_text }`

The `script` field comes from the hidden `<textarea id="speaker-notes">` in each `web/pages/*.html` file. This is the actual spoken script — not the visible slide content.

`/chat` returns an SSE stream. The agent streams text and tool calls; certain tools (`presentation_start`, `presentation_resume`, etc.) terminate the stream early.

## Customizing for a Different Presentation

All four of these must be changed together:

1. **`web/pages/*.html`** — slide visual content
2. **`<textarea id="speaker-notes">` in each page** — the spoken script per slide
3. **`app/agent_runtime.py` system prompt** — especially the `## Slide Anchors And Jump Rule` table mapping topics to page numbers
4. **`skills/paper-knowledge/SKILL.md`** — domain knowledge for QA answers

## High-Risk Areas

Do not modify these without understanding the full state-machine flow:

- `Presenter._run` in `app/ppt_runtime.py`
- Any tool in `ToolRegistry` that sets `state.mode` or `state.qa_locked`
- `/ppt/page_enter` endpoint and its `PageEnterRequest` schema
- `/chat` SSE stream logic and `terminating_tools` set
- `app/tts_server.py` stop/preload/queue logic
- The `speaker-notes` textarea id in `web/pages/*.html`

## Behaviors to Preserve

When refactoring, verify these still work:

1. Presentation can be interrupted mid-sentence and enter QA
2. After QA, `presentation_resume` continues from the exact saved segment
3. Reaching the final page locks `qa_locked = True` permanently
4. Page navigation keeps speaker notes in sync with current page
5. TTS stop/resume does not produce audio overlap
6. ASR event stream continues working after interruptions
