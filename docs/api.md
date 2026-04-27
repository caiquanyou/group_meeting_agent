# PPT Pilot API Reference

## Overview

This document describes all external-facing interfaces for the PPT Pilot presentation orchestration system.

## Base URLs

- **Main API:** `http://127.0.0.1:15005`
- **TTS Service:** `http://127.0.0.1:15000`
- **WebSocket:** `ws://127.0.0.1:8765`

---

## HTTP Endpoints

### GET /
Redirects to `/web/` if index.html exists.

### GET /ppt/pages
Returns list of available slide pages.

**Response:**
```json
{"pages": [1, 2, ..., 15], "total": 15}
```

### GET /asr/devices
Returns available ASR devices.

### GET /asr/status
Returns local ASR service status.

### POST /asr/start
Start local speech recognition.

**Request:**
```json
{"device_index": 0}
```

**Response:**
```json
{"status": "success", ...}
```

### POST /asr/stop
Stop local speech recognition.

### GET /runtime/status
Aggregated runtime status (TTS, ASR, agent, presenter).

### GET /runtime/config
Public runtime configuration.

### GET /runtime/env/status
Check environment variable status.

### GET /runtime/env/values
Get environment variable values (secrets masked).

### POST /runtime/env/update
Update environment variables in `.env` file.

**Request:**
```json
{"entries": {"OPENAI_API_KEY": "...", "OPENAI_MODEL": "gpt-4"}}
```

### POST /presentation/start
Directly trigger presentation start via tool.

### POST /presentation/resume
Directly trigger presentation resume via tool.

### POST /presentation/enter-defense-qa
Directly enter defense QA mode via tool.

### GET /asr/events
SSE stream of ASR transcription events.

### POST /ppt/page_enter
Receive page data from PPT client when page changes.

**Request:**
```json
{"page": 1, "script": "...", "page_text": "..."}
```

**Response:**
```json
{"status": "ok", "page": 1, "segments": 5}
```

### POST /chat
Main streaming endpoint for agent interaction via SSE.

**Request:**
```json
{"text": "What is this slide about?", "thread_id": "user1"}
```

**Response:** Server-Sent Events stream with AI text and tool calls.

### POST /stop
Stop active agent task and audio playback.

---

## Agent Tools (LangChain)

The following tools are available to the LangGraph agent. Each tool modifies `AppState` and may trigger side effects (TTS, PPT navigation).

### get_presentation_state
Returns current defense state and resume point.

**Parameters:** None

**Returns:** JSON string with mode, page, segment info, qa_locked status.

---

### ppt_navigate
Control PPT pages with next, prev, or jump.

**Parameters:**
- `action` (str): "next" | "prev" | "jump"
- `page` (int, optional): Target page number for jump
- `replay` (bool): If true on jump, continues defense from start of that page

**Side Effects:**
- Saves resume point
- Stops audio playback
- Changes `state.mode` to PRESENTING (if replay) or WAITING_RESUME/DEFENSE_QA

**Returns:** Navigation result string.

---

### presentation_start
Start the formal presentation from page 1 or a specified page, auto-continue.

**Parameters:**
- `from_page` (int, default=1): Starting page number

**Side Effects:**
- Sets `state.mode = PRESENTING`
- Sets `presenter.auto_play = True`
- Starts TTS playback from page start

**Returns:** Confirmation string with starting page.

---

### presentation_pause
Pause the presentation, keep resume point, enter interrupted QA.

**Parameters:**
- `save_resume_point` (bool, default=True): Whether to save current position

**Side Effects:**
- Sets `state.mode = INTERRUPTED_QA`
- Sets `presenter.auto_play = False`
- Stops audio playback

**Returns:** "Presentation paused. Ready for questions."

---

### presentation_resume
Resume the formal presentation from saved resume point, auto-continue.

**Parameters:**
- `from_saved_point` (bool, default=True): Use saved resume point vs current position

**Side Effects:**
- Sets `state.mode = PRESENTING` (if not qa_locked)
- Sets `presenter.auto_play = True`
- Starts TTS playback from saved segment

**Returns:** Confirmation with resume page and segment index.

---

### presentation_replay_page
Replay the current page or a specified page from the start.

**Parameters:**
- `page` (int, optional): Target page (defaults to current)
- `auto_advance` (bool, default=True): Whether to auto-advance after replay

**Side Effects:**
- Resets segment index to 0
- Starts TTS playback from beginning of page

**Returns:** Confirmation string.

---

### presentation_jump_and_hold
Jump to a target page but do not continue speaking automatically.

**Parameters:**
- `page` (int): Target page number

**Side Effects:**
- Sets `state.mode = WAITING_RESUME` (or DEFENSE_QA if qa_locked)
- Sets `presenter.auto_play = False`
- Stops audio playback

**Returns:** Confirmation or error string.

---

### presentation_jump_for_qa
Jump to a target page for audience question, stop automatic speaking.

**Parameters:**
- `page` (int): Target page number

**Side Effects:**
- Sets `state.mode = INTERRUPTED_QA` or `DEFENSE_QA`
- Sets `presenter.auto_play = False`
- Stops audio playback

**Returns:** Confirmation or error string.

---

### presentation_enter_defense_qa
End formal presentation and enter final defense QA mode.

**Parameters:** None

**Side Effects:**
- Sets `state.mode = DEFENSE_QA`
- Sets `state.qa_locked = True`
- Sets `state.presentation_finished = True`
- Sets `presenter.auto_play = False`
- Stops audio playback

**Returns:** "Entered final defense QA mode."

---

### presentation_finish
Mark the presentation as finished and stay in defense QA mode.

**Parameters:** None

**Side Effects:**
- Same as `presentation_enter_defense_qa`

**Returns:** "Presentation marked as finished. Now in defense QA mode."

---

## WebSocket Protocol (ws://127.0.0.1:8765)

Used by PPT client (browser) to receive navigation commands from server.

### Server → Browser Messages

| Type | Payload | Description |
|------|---------|-------------|
| `request_page_data` | `{}` | Request current page data from browser |
| `enable_reporting` | `{}` | Enable page reporting mode |
| `next` | `{}` | Navigate to next page |
| `prev` | `{}` | Navigate to previous page |
| `jump` | `{"page": N}` | Jump to specific page |

### Browser → Server

Currently no messages are sent from browser to server via WebSocket. Page data is sent via HTTP POST to `/ppt/page_enter`.

---

## State Machine

### AppMode Values

| Mode | Description |
|------|-------------|
| `IDLE` | Not started, initial state |
| `PRESENTING` | Auto-playing through slides |
| `INTERRUPTED_QA` | Mid-presentation question (pausable) |
| `WAITING_RESUME` | Paused, waiting for resume command |
| `DEFENSE_QA` | Final QA mode, permanently locked (qa_locked=true) |

### Valid Transitions

```
IDLE
  → PRESENTING (via presentation_start)

PRESENTING
  → INTERRUPTED_QA (via chat message or presentation_pause)
  → DEFENSE_QA (auto on final page or presentation_enter_defense_qa)

INTERRUPTED_QA
  → PRESENTING (via presentation_resume, if not qa_locked)
  → DEFENSE_QA (if qa_locked becomes true)

WAITING_RESUME
  → PRESENTING (via presentation_resume, if not qa_locked)

DEFENSE_QA
  → (locked, no exit - all resume attempts redirected to QA jump)
```

### State Fields

| Field | Type | Description |
|-------|------|-------------|
| `mode` | AppMode | Current state |
| `current_page` | int \| None | Currently displayed page |
| `resume_page` | int \| None | Saved resume page number |
| `resume_segment_index` | int | Saved segment index within page |
| `presentation_started` | bool | Whether presentation has ever started |
| `presentation_finished` | bool | Whether final slide reached |
| `qa_locked` | bool | Whether permanently in final QA mode |
