---
page_number: 13a
layout: default
theme: default
---

# 单细胞时序建模：轨迹、伪时间与命运概率

## 三个概念最小定义

1. **Trajectory inference**：从静态单细胞快照中重建细胞状态随发育进程变化的连续路径与分叉结构。
2. **Pseudotime**：为每个细胞分配相对进程坐标，表示其在生物过程中的“先后位置”，而非真实物理时间。
3. **Fate probability / Branch assignment**：估计细胞流向各终末命运分支的概率，或直接给出最可能分支标签。

## 常见方法谱系（一句话）

在实践中，时序分析常沿三条主线展开：**OT** 负责跨时间点对齐与质量迁移，**RNA velocity** 提供局部动态方向信息，**Markov propagation** 用于在状态图上进行长期命运传播与吸收概率估计。

## 结论

**你的模型把“轨迹重建 + 命运预测”统一到同一时序框架。**
