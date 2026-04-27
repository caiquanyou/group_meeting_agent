---
page_number: 7
layout: default
theme: default
---

# SCOPE-X 进展

## 当前阶段成果

**模型架构**

- BERT 编码器 + 模态特异性解码器
- 基因/peak token 化：支持变长输入
- 预训练任务：掩码基因预测（MGP）+ 跨模态重建（CMR）

**预训练进展**

| 阶段 | 数据量 | 状态 |
|------|--------|------|
| Phase 1 - RNA + ATAC scMultiome | 2M+ 细胞 | ✅ 完成 |
| Phase 2 - RNA + ATAC scPaired | 4M+ 细胞 | ⏳ 计划中 |
| Phase 3 - 图先验 | - | ⏳ 计划中 |

**初步结果**

- Phase 1 细胞类型聚类 ARI：**0.87**
- 跨模态预测准确率：准确率 **84.6%**

**下一步**

- 完成 Phase 2/3 多组学联合预训练
- 开展下游任务评估

---

<!-- 
  这页展示 SCOPE 当前进展

  - layout: default 标准布局
  - 用表格展示阶段进度
-->
