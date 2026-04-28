---
page_number: 8a
layout: default
theme: default
---

# 什么是分析智能体：从 LLM 到可执行系统

**流程图（文字版）**

```text
User -> Planner -> Tool Router -> Executor -> Verifier -> Memory
```

- **Planner**：基于用户目标进行任务分解与步骤规划。
- **Tool Router**：根据当前步骤与数据状态，选择合适工具与调用参数。
- **Executor**：执行代码/工具调用，产出中间结果与日志。
- **Verifier**：对结果进行质量检查、一致性校验与错误恢复。
- **Memory**：维护会话上下文、数据对象状态与已验证结论。

**LangChain / LangGraph 在其中的位置**

- **LangChain**：负责工具封装、调用接口与链式编排。
- **LangGraph**：负责有状态工作流（状态机）编排、节点回路控制与多步反馈闭环。

**一句话总结**

> Agent = 推理 + 工具 + 状态 + 反馈闭环，不只是生成文本
