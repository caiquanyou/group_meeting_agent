# PPT Pilot 重构设计文档

**日期：** 2026-04-21
**方案：** A — 最小化接口抽象
**目标：** 为"更强的中断恢复"功能做准备，不改变现有行为

---

## 1. 核心逻辑重构

### 负责人
核心逻辑 Teammate — 只改 `app/ppt_runtime.py` 和 `app/tools.py`

### app/ppt_runtime.py — Presenter 类

新增两个显式方法，把 `_run` 里隐式的断点读写变成有名字的接口：

```python
def save_checkpoint(self) -> dict:
    """返回 {page, segment_index}，供外部保存到 AppState"""
    return {
        "page": self.page,
        "segment_index": self.index,
    }

def restore_checkpoint(self, page: int, segment_index: int) -> None:
    """设置播放起点，不触发 TTS"""
    self.page = page
    self.index = segment_index
```

`_run()` 内部更新 `state.resume_page` / `state.resume_segment_index` 的两处内联赋值，改为调用 `save_checkpoint()` 后写入 state，保持断点续播行为不变。

**不改动：** `PPTBridge`、`cancel()`、`load()`、`get_total_page_number()`、自动翻页逻辑

### app/tools.py — ToolRegistry

新增内部辅助类 `_StateGuard`，集中处理状态转换判断：

```python
class _StateGuard:
    def can_resume(self, state: AppState) -> bool:
        return state.resume_page is not None and not state.qa_locked

    def can_start(self, state: AppState) -> bool:
        return not state.qa_locked

    def redirect_if_locked(self, state: AppState, tool_name: str) -> str | None:
        if state.qa_locked:
            return f"{tool_name} blocked: presentation locked to QA mode"
        return None
```

`_autoplay_blocked()` 和 `_force_jump_for_qa()` 内部改为委托给 `_StateGuard`，对外签名不变。

**不改动：** 10 个工具函数的签名和返回值、`_jump_to_page()`、`_save_resume_point()`

### 不动的文件
`app/main.py`、`app/agent_runtime.py`、`app/models.py`、`app/session.py`、`app/tts_server.py`、`app/tts_service.py`、`app/asr_service.py`

---

## 2. 测试

### 负责人
测试 Teammate — 只新建 `tests/test_ppt_runtime.py` 和 `tests/test_tools.py`，不改任何现有代码

### tests/test_ppt_runtime.py

- `save_checkpoint()` 返回正确的 `{page, segment_index}`
- `restore_checkpoint()` 正确设置 `self.index` 和 `self.page`
- `_run()` 在每个 segment 播放前更新 `state.resume_segment_index`
- 中断后 resume 从正确 segment 继续，不从页首

### tests/test_tools.py

- `_StateGuard.can_resume()` 在各 `AppMode` 下的返回值
- `_StateGuard.redirect_if_locked()` 在 `qa_locked=True` 时触发重定向
- `presentation_pause` → `presentation_resume` 完整流程的状态转换

**技术栈：** `pytest` + `unittest.mock`，不依赖真实 TTS/WebSocket

---

## 3. API 文档

### 负责人
文档 Teammate — 只新建 `docs/api.md`，不改任何代码

### 覆盖内容

1. **HTTP 端点**（来自 `app/main.py`）：方法、路径、请求体、响应格式、状态码
2. **Agent 工具接口**（来自 `app/tools.py`）：10 个工具的参数、返回值、触发条件、状态机副作用
3. **WebSocket 协议**（`ws://127.0.0.1:8765`）：消息格式
4. **状态机速查表**：`AppMode` 各状态的合法转换路径

不包含部署说明、代码示例、内部实现细节。

---

## 团队分工边界

| Teammate | 可改文件 | 禁止触碰 |
|---|---|---|
| 核心逻辑 | `app/ppt_runtime.py`, `app/tools.py` | 其他所有文件 |
| 测试 | `tests/test_ppt_runtime.py`, `tests/test_tools.py`（新建） | 所有现有文件 |
| 文档 | `docs/api.md`（新建） | 所有现有文件 |
