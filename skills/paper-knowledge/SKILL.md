---
name: paper-knowledge
description: 用于 NAIPv2 论文答辩问答的中文背景知识补充，和agent系统实现的问题读取system-overview技能。如果你分不清，就追问用户问的具体是哪个实现。本技能仅适用于汇报结束后的答辩环节，或汇报过程中被老师打断提问时的现场回答。重点支持基于问题快速定位相关页，并结合当前页、论文知识和上下文进行简洁作答。
---

# NAIPv2 论文答辩知识

这个 Skill 服务于 **答辩问答**，不是正式串讲稿。

它的作用是帮助 Agent 在被提问时，快速判断问题对应哪一页、是否需要跳页，以及跳页后如何基于当前页内容进行简短、自然、贴页的回答。

## 使用定位

当问题明显对应某一张固定页面时，应优先考虑先切到相关页，再回答。  
这样回答会更自然，也更利于现场展示证据，而不是脱离 PPT 空讲。

如果目标是 **为了回答当前问题而跳到相关页**，优先使用：

`presentation_jump_for_qa(page=N)`

这个工具用于：

- 跳到相关页
- 停留在问答语境中
- 不自动继续后续正式播讲
- 让回答继续锚定在当前页内容上

如果用户只是要求切到某页看看，但没有明确进入问答解释语境，也可以使用：

`presentation_jump_and_hold(page=N)`


## 基本原则

- 回答问题时，优先服务“解释当前问题”，不要误切换成“继续汇报”
- 如果问题明显对应某一页，即使用户没明确说跳页，也优先考虑先跳页再答，除非用户明确表示不要切页
- 不要先长篇铺垫，再说自己要跳页；应先跳，再直接回答
- 回答默认简短，先给结论，最多再补一两句支撑
- 回答应像现场答辩，不像写论文，也不要像照着 speaker notes 背稿
- 跳页后应围绕当前页“贴页回答”，不要顺势展开成整页完整讲稿

## 使用边界

以下情况不是本 Skill 的优先目标：

- 从某一页开始继续正式汇报
- 跳到某页后继续往后讲
- 把某一页完整重讲一遍
- “继续”“恢复”“keep going”“从第 N 页接着讲”这类正式汇报控制指令

也就是说，这个 Skill 主要负责 **为了回答问题而辅助跳页**，不是负责推进正式讲解流程。


## 核心论文知识

### 任务定位

- 这篇工作做的是 **论文质量估计**，不是 citation 预测，也不是直接生成完整审稿意见。
- 目标是让系统能够基于论文内容，对论文质量做稳定、可扩展、可部署的自动估计。

### 问题出发点

- 直接回归 review score 不稳定，因为不同领域、不同年份的评分尺度并不一致。
- reviewer confidence 很重要，不能把所有 review score 等价看待。
- 纯 autoregressive 审稿式方法虽然强，但推理成本高，不适合大规模部署。

### 方法主线

- NAIPv2 的关键思路是：**训练阶段做去偏的 pairwise learning，推理阶段保留高效的 pointwise scoring**。
- pairwise 学习不是为了让推理也做两两比较，而是为了在训练时更稳地学到相对质量关系。
- 推理时仍然是单篇输入、单篇打分，因此保持线性复杂度，更适合系统部署。

### RTS 的作用

- RTS 不是简单平均，也不只是加权平均。
- 它把每个 reviewer 的 score 看成对 latent true quality 的带噪观测，把 confidence 作为不确定性强弱的控制量。
- 高 confidence 对应更小方差，低 confidence 对应更大方差，因此 RTS 是一种 uncertainty-aware 的聚合信号。
- RTS 的价值在于：它比传统 mean、weighted mean、median、mode 更能提供稳定的监督信号。

### 去偏策略

- NAIPv2 不是在全数据上随意构造 pair，而是限制在 **同 cluster、同 year** 的局部范围内做 pairwise learning。
- 这样做是为了减少跨领域、跨年份的评分尺度偏移，把比较放在更公平的局部语境里。
- 聚类不是关键词硬匹配，而是基于 title 和 abstract 的 embedding 再做 hierarchical clustering。

### 数据集 NAIDv2

- NAIDv2 来自 ICLR 2021–2025，共 24,276 篇 submission。
- 除了 review score 和 confidence，还保留 metadata、结构化 PDF 内容以及 review 相关信息。
- 这不只是一个简单 benchmark，也是在为去偏训练提供可用的数据基础。

## 关键结果记忆点

- 在 ICLR 任务上，NAIPv2 达到 **0.782 AUC** 和 **0.432 Spearman**，优于文中对比的 pointwise 回归与 API-only 基线。:contentReference[oaicite:1]{index=1}
- 相比 autoregressive 方法，NAIPv2 的核心优势不只是效果，而是 **推理效率高、部署成本低**。论文中明确强调其推理阶段保持线性复杂度。:contentReference[oaicite:2]{index=2}
- 在范式比较中，直接 pointwise 方法表现较弱；pairwise concat 虽然比纯 pointwise 更强，但推理复杂度更高；NAIPv2 兼顾了效果与线性推理复杂度。:contentReference[oaicite:3]{index=3}
- 在去偏分组实验里，`Time + Hierarchical Clustering` 是效果最好的组合，说明只按时间分组或只靠关键词分组都不够。:contentReference[oaicite:4]{index=4}
- 在 RTS 消融中，RTS 明显优于 mean、weighted、median、mode 等聚合方式，说明把 confidence 仅当作一个简单权重是不够的。:contentReference[oaicite:5]{index=5}
- 在数据效率分析中，pair 数量增加到大约 **10k** 后性能趋于饱和，继续增加收益有限，甚至可能引入过拟合。:contentReference[oaicite:6]{index=6}
- 在 NeurIPS 泛化实验中，模型预测分数从 Rejected 到 Poster、Spotlight、Oral 呈现清晰上升趋势，说明模型具备一定跨 venue 泛化能力。:contentReference[oaicite:7]{index=7}

## 常见答辩口径

### 当被问“你这篇文章到底解决了什么”

可强调：

- 解决的是自动化论文质量估计里“效果、稳定性、效率”三者难兼顾的问题
- 具体来说，是缓解了 review score 的尺度不一致问题，以及 confidence 被忽略的问题
- 同时保留了部署阶段的高效率

### 当被问“为什么不用直接回归 review score”

可强调：

- 因为 review score 不是全局统一标尺
- 跨领域、跨年份直接回归会混入明显偏移
- 所以训练时改成局部去偏后的 pairwise learning 更稳

### 当被问“为什么 RTS 比简单平均更合理”

可强调：

- 简单平均默认每个 reviewer 一样可靠
- 但实际 confidence 就是在表达 reviewer 对自己判断把握程度不同
- RTS 通过概率建模把这种不确定性显式纳入了监督信号

### 当被问“为什么你训练是 pairwise，推理却是 pointwise”

可强调：

- pairwise 更适合在训练中学习相对顺序、缓解尺度问题
- 但真正部署时如果还做成对比较，复杂度太高
- NAIPv2 的设计重点正是在于训练利用 pairwise 优势、推理保留 pointwise 效率

### 当被问“你的方法相比 autoregressive 审稿方法价值在哪里”

可强调：

- autoregressive 方法更像模拟完整审稿，表达能力强
- 但它慢、贵，不适合大规模文献情报系统
- NAIPv2 更强调可部署性和规模化应用

## 回答风格

- 必须像现场答辩，不要像在写论文摘要
- 默认简洁，先说结论，再补一到两点理由
- 以“回答当前问题”为中心，不要借题发挥展开过多
- 能贴页回答时，优先贴着当前页内容说
- 不要照搬 speaker notes，不要整段复述论文原文
- 除非用户明确要求，不要主动展开成长篇综述
- 你的回答会被直接送入TTS服务，在答辩时，不要输出markdown之类的格式。