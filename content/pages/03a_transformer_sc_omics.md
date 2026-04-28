---
page_number: 4
layout: two-column
theme: default
---

# Transformer 如何建模单细胞多组学

## 3 个核心点

1. **token 设计**
   - gene token：表示基因表达信息
   - peak token：表示染色质可及性位点
   - modality token：显式标记 RNA / ATAC / 蛋白等模态来源
   - position token：编码基因组位置或序列上下文

2. **预训练目标**
   - masked gene prediction：学习基因表达分布与共表达关系
   - cross-modal reconstruction：从一种模态重建另一模态，增强互补信息利用
   - contrastive alignment：对齐同一细胞的跨模态表示，拉开不同细胞表征

3. **为什么优于传统方法**
   - 可扩展：统一 token 后可自然扩展到更大数据与更多模态
   - 可迁移：预训练表征可复用于注释、聚类、预测等下游任务
   - 支持零样本：依赖跨模态对齐能力实现跨数据集/跨平台泛化

---

**Take-home message：统一 token + 统一目标函数 = 多组学基础模型可复用能力**
