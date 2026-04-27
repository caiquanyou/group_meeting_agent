# 组会汇报-智能体

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-red.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()

> **组会汇报 AI 智能体。

PPT-Pilot 深度整合了幻灯片控制、讲稿状态机、本地 ASR/TTS 管线与 Agent 决策能力，使 AI 能够像真实答辩者一样完成完整链路

项目提供`LOADME.md`文件，方便AI理解项目结构与功能。建议用 Trae、 VS Code +插件等 AI IDE 修改本项目，理解、修改、调试更高效。


---

## 📢 News

- **[2026.03.26]** PPT-Pilot 首版发布！

---

## ✨ 亮点

- 🚀 **全自动汇报**  
  根据预设讲稿自动组织讲解内容，并联动页面状态完成汇报流程（汇报阶段不会胡言乱语，严格按照讲稿来）。

- 🔄 **无缝打断与恢复**  
  汇报过程中可随时被提问打断，系统自动切入问答模式；问答结束后，可从先前检查点继续汇报。

- 🎤 **语音交互**  
  `ASR` 基于本地音频输入与 `faster-whisper` 进行识别；`TTS` 接入 MiniMax 流式语音合成，实现低延迟、较强拟人感的语音反馈。

- 🎛️ **可视化控制终端**  
  内置 Agent Control 面板，用于管理 ASR、手动输入、汇报控制、运行状态监测与配置初始化。

- 🧠 **状态感知型汇报 Agent**  
  系统不是简单地“收到一句话就回答一句话”，而是围绕 `汇报中 / 被打断 / 继续汇报 / 进入答辩` 等状态进行统一编排。


---

## 🛠️ 部署

### 环境要求

- **OS**: Windows
- **Python**: >=3.11
- **Environment**: `conda`
- **Conda Env Name**: `pptpilot`
- **Hardware**: 可用的麦克风与扬声器，推荐有 GPU 以提升本地 ASR 速度（没有也能用）
- **Keys**: OpenAI 兼容模型 API Key 与 MiniMax TTS API Key


### 1. 下代码

```bash
git clone git@github.com:ssocean/PPT_Pilot.git
cd PPT_Pilot
```

### 2. 建环境

```powershell
conda create -n pptpilot python=3.11 -y
conda activate pptpilot
pip install -r requirements.txt
```

### 3. 付费API

系统至少依赖两个外部 API，请提前申请并在 .env 中完成配置。

1. LLM API
用于智能体推理、问答、指令理解与内容生成。
建议至少使用 GPT-5.1-mini 及以上级别的模型。我自己正式汇报时用的gpt-5.4，成本也就几块钱。

1. MiniMax 语音 API
用于语音合成能力，也就是汇报时的 TTS 播报。
可以考虑其海外版本（主要是有30元一个月的包，短期使用划算些）。按实际使用经验来看，30 元已经足够支撑几十次汇报演示。

##### ⚙️ 配置方法

【可以手动编辑】所有运行配置统一放在根目录 `.env` 中(git igored)。

【也可以在弹窗配置】如果缺配置的话，会在第一次进入`agent_control`界面时提示配置。

---

## ▶️ 运行

根目录直接运行。
```
python run.py
```

### 浏览器打开

- `http://127.0.0.1:15005/web/`
- `http://127.0.0.1:15005/web/agent_control.html`

---

## 🕹️ 使用Tips

### 按钮控制

1. 点击“开始汇报”，系统自动进入正式汇报流程。
2. 点击说话按钮可在汇报中可随时打断提问，例如：“解释一下这里的实验设置”。【支持“空格”快捷键，长按说话，松开发送】
3. 如果提问人在智能体回答后，没有继续追问，可以点击“继续汇报”。
4. 点击“停止输出”，立即停止播放。
5. 结束后点击“进入答辩”，锁定到答辩问答模式。

### 自然语言控制

支持但不限于以下自然语言控制：

- “你可以开始了”
- “继续吧”
- “跳到第 6 页”
- “你讲讲你的方法是怎么实现的”
- “你的数据集是怎么构建的”

---


## 🏗️ 系统结构

系统采用解耦的双服务架构，以保证响应速度与模块清晰性：

1. **`app.main` (Core Orchestrator)**  
   核心调度服务。负责 FastAPI 路由、Agent 状态机管理、ASR 生命周期、PPT 控制与 WebSocket 指令分发。

2. **`app.tts_server` (Audio Synthesis Service)**  
   TTS 专用服务。负责与 MiniMax WebSocket 接口通信，并在本地声卡完成音频流式播放。

浏览器端主要包含两个入口：

- `http://127.0.0.1:15005/web/`
- `http://127.0.0.1:15005/web/agent_control.html`

---

## 🧩 文件结构

```text
app/                   FastAPI 主服务、状态机、Agent、ASR/TTS 调度
app/tts_server.py      MiniMax TTS 本地服务
web/                   PPT 页面、控制面板、前端交互
skills/                给 Agent 的技能/知识目录
.env                   本地真实配置（默认不会被上传）
.env.example           开源模板配置
LOADME.md  给 AI Agent 的项目说明，便于AI快速理解
requirements.txt       Python 依赖
```


## 🔐 License

本项目采用 **CC BY-NC 4.0**（署名 - 非商业性使用）许可证。

这意味着：

- 你可以自由阅读、修改、研究和非商业使用本项目
- 你可以在保留署名的前提下进行二次开发
- **禁止将本项目直接或间接用于商业用途**

商业用途包括但不限于：

- 付费产品或 SaaS
- 企业内部盈利性工具
- 商业答辩 / 汇报服务
- 任何以本项目为核心能力进行收费的系统

如需商业授权，请联系原作者。

---

## 🤖 For Agents / Codex

如果你是 Codex、Cursor、Claude Code 或其他代码代理，请先阅读根目录 LOADME.md。

在修改本仓库前，建议先理解以下几点：

1. 这是一个**流程编排型项目**，不是聊天机器人。技术栈包括Agent、Langchain、Langraph、等。
2. 核心状态集中在后端的 `AppState`、`Presenter`、`SessionManager` 与 `ToolRegistry`。
3. 前端页面与后端状态机耦合较强，不建议在不了解流程的情况下随意改控制接口。
4. `.env` 是统一配置入口,提醒用户谨防泄露。
5. 与“开始汇报 / 继续汇报 / 进入答辩 / 中断恢复”相关的逻辑属于高风险修改区。

建议 Agent 修改前的阅读顺序：

1. `LOADME.md`
2. `app/main.py`
3. `app/tools.py`
4. `app/ppt_runtime.py`
5. `web/agent_control.html`

---

## License
本项目采用 Creative Commons Attribution-NonCommercial 4.0 International License（CC BY-NC 4.0）许可。

你可以在非商业前提下自由使用、修改和二次创作本项目；任何商业用途需另行获得授权。