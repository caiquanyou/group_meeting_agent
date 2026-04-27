# Important to Agent

这个文件是写给 Codex、Cursor、Claude Code 等代码代理看的，不是写给普通最终用户看的。

如果你是 Agent，请先读完这个文件，再决定怎么修改仓库。

---

## 一句话概括

这不是一个普通聊天机器人项目，而是一个 **“答辩 / 汇报流程编排器”**。

它的目标是让 Agent 像真实汇报者一样完成整套流程：

- 控制 PPT 页面
- 读取当前页讲稿
- 自动播报
- 在被提问时切入问答
- 在合适的时候继续汇报
- 在最后锁定进入答辩问答模式

所以你修改这个仓库时，优先级不是“生成更好看的代码”，而是 **不要破坏状态机和流程一致性**。

---

## 先看哪些文件

建议按这个顺序理解项目：

1. `app/models.py`
2. `app/config.py`
3. `app/main.py`
4. `app/ppt_runtime.py`
5. `app/tools.py`
6. `app/agent_runtime.py`
7. `app/asr_service.py`
8. `app/tts_service.py`
9. `app/tts_server.py`
10. `run.py`
11. `web/index.html`
12. `web/agent_control.html`
13. `web/pages/1.html`

如果资源/智能有限，至少先看：

1. `app/main.py`
2. `app/tools.py`
3. `app/ppt_runtime.py`
4. `app/agent_runtime.py`
5. `run.py`
6. `web/index.html`
7. `web/pages/1.html`

---

## 你需要理解的核心事实

### 1. 主入口

`app/main.py` 是主入口，负责：

- FastAPI API
- 静态页面托管
- Agent 生命周期
- ASR 生命周期
- PPT WebSocket 生命周期
- 与 TTS 服务交互

### 2. 核心状态机

`app/models.py` 里的 `AppMode` 非常关键。  
很多“看起来像 bug”的行为，实际上是在维持状态机一致性。

常见状态包括：

- `IDLE`
- `PRESENTING`
- `INTERRUPTED_QA`
- `WAITING_RESUME`
- `DEFENSE_QA`

### 3. Presenter 是汇报流程核心

`app/ppt_runtime.py` 里的 `Presenter` 负责：

- 加载当前页讲稿
- 切分讲稿段落
- 逐段播报
- 自动翻页
- 记录 resume point

如果这里改坏，最容易破坏：

- 中断后恢复
- 自动翻页一致性
- 当前页与当前讲稿的同步

### 4. ToolRegistry 决定 Agent 能做什么

`app/tools.py` 定义了 Agent 真正可调用的工具，例如：

- `presentation_start`
- `presentation_resume`
- `presentation_replay_page`
- `presentation_enter_defense_qa`
- `ppt_navigate`

Agent 的很多行为不是直接写死在 prompt 里，而是通过这些 tools 落地。

### 5. AgentRuntime 不是普通聊天接口

`app/agent_runtime.py` 里构建的不是纯文本问答模型，而是一个 **会调用工具的编排型 Agent**。

所以当用户说“继续汇报”“跳到第 5 页”时，重点不是模型怎么回复，而是它是否会正确调用工具、切换状态、恢复流程。

---

## 前后端耦合点

这个项目有几个强耦合点，不理解这些很容易误改：

- `web/index.html` 会通过 WebSocket 接收翻页和状态同步指令
- 页面切换后会把当前页内容回传给后端
- 后端依赖这些页面回传内容判断当前页和当前讲稿
- `web/agent_control.html` 会直接调用主服务 API

最重要的一条：

**演讲稿来自 `web/pages/*.html` 文件中的**

```html
<textarea id="speaker-notes" style="display:none">...</textarea>
```

这里面的文本就是当前页的讲稿来源。  
如果用户问“为什么讲稿不对”“怎么换成我自己的讲稿”，优先检查这里。

所以：

- 不要随便删掉 `speaker-notes`
- 不要轻易改 `speaker-notes` 的 `id`
- 不要随意改变页面向后端回传讲稿的约定
- 不要轻易改 `/ppt/page_enter` 的入参结构

---

## 如果用户想改成“自己的内容”，应该怎么改

这是最重要的一节。  
可能你面对的用户不会写代码，他们只会对你说“帮我换成我自己的答辩内容”。你必须知道应该改哪里。

如果用户想把这个项目改成自己的汇报 / 答辩内容，必须要同时修改四个地方：

### 1. 改 Agent system prompt 里的“汇报章节目录 / 讲解逻辑”

位置优先看：

- `app/agent_runtime.py`
- 以及它引用到的相关 prompt / skill 内容,尤其是## Slide Anchors And Jump Rule 下的内容。

这里通常需要替换成用户自己的：

- 章节结构
- 汇报顺序
- 页面组织方式
- 讲解风格
- 问答策略

如果用户说：

- “把目录换成我的论文结构”
- “让 Agent 按我的章节汇报”
- “把这里的章节提示词改成我的”


### 2. 改 `skills/paper-knowledge`

这是项目知识底座的一部分。  
如果用户换成自己的论文或项目，请提示他上传论文或提示用户上传符合标准的SKILL.md文件，你可以负责修改该文件夹下的SKILL.md文件。

如果用户说：

- “把论文内容换成我的”
- “让它讲我自己的研究”
- “更新项目背景知识”

优先检查：

- `skills/paper-knowledge/`


### 3. 改 `web/pages/*.html`

PPT 页面本身在这里。  
如果用户想换成自己的汇报内容，页面级 HTML 通常都要改。

用户可能会说：

- “换成我的 PPT”
- “把每一页换成我的内容”
- “重做这一页页面”

优先看：

- `web/pages/`

这里每一页对应一个 HTML 页面。

### 4. 改每页里的 `speaker-notes`

这一点非常关键，单独再强调一次：

**真正给系统播报用的讲稿，不是页面上的可见文字，而是页面 HTML 里的这个隐藏区域：**

```html
<textarea id="speaker-notes" style="display:none">
这里是当前页讲稿
</textarea>
```

如果用户只改了页面视觉内容，但没改这里，就会出现：

- 画面看起来是新的
- 但 Agent 讲的还是旧稿子

所以当用户想“换成自己的版本”时，最正确的理解是：

1. 改页面视觉内容(html文件)
2. 改 `speaker-notes` 里的讲稿
3. 改 Agent 的 System Prompt
4. 改 `paper-knowledge`

不要只改其中一个。必须四个同时改。或者至少提示用户，有四个地方需要修改。


---

## 配置规则

所有运行配置统一来自根目录 `.env`，该文件已被写入.gitignore。

原则：

- 不要把真实 key 写回源码
- 不要新加只有你自己知道的隐藏配置来源
- 如果新增配置项，请同步更新：
  - `.env.example`
  - `README.md`
  - 必要时更新本文件

---

## 外部依赖

当前项目依赖：

- OpenAI 兼容的 LLM API
- MiniMax TTS WebSocket API
- 本地音频输入设备
- 本地音频输出设备
- `faster-whisper`

所以很多问题不一定是代码 bug，也可能是环境问题。

---

## 修改时优先保护的行为

如果你要重构或优化，优先保证这些行为不要回归：

1. 汇报时可被打断进入 QA
2. QA 后可以从断点继续
3. 最后一页后能锁定到 `DEFENSE_QA`
4. 页面切换后讲稿与当前页一致
5. TTS 停止 / 恢复不会串音
6. ASR 事件流还能持续工作

---

## 高风险区域

这些地方改动时要格外小心：

- `Presenter._run`
- `ToolRegistry` 里所有会切换 mode 的工具
- `ppt_page_enter`
- `/chat` 的 SSE 流逻辑
- `app/tts_server.py` 的 stop / preload / queue 逻辑
- `web/index.html` 里回传页面讲稿的逻辑

---

## 如果用户说“顺手帮我优化一下”

先不要急着大改。  
这个仓库现在比“架构美化”更需要：

- 稳定
- 明确
- 可部署
- 可被非程序员通过 Agent 使用

通常这些目标比“写得更优雅”更重要。

---

## 推荐的改动习惯

- 先检查是否影响 `AppMode`
- 先检查是否会破坏 resume point
- 涉及配置时同步更新 `.env.example`
- 涉及用户使用方式时同步更新 `README.md`
- 涉及项目理解时同步更新本文件


