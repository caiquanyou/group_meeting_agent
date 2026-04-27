---
page_number: 11
layout: default
theme: default
---

# 空间转录组基础：从表达到空间坐标

## 三类核心任务定义

- **Deconvolution（解卷积）**：从空间 spot 的混合表达中，估计每种细胞类型的组成比例。
- **Spatial Mapping（空间映射）**：将单细胞表达或细胞类型映射到组织中的空间坐标/区域。
- **Spatial Generation（空间生成）**：在给定条件下生成空间表达图或组织级别的基因表达模式。

## 两类评估指标

### 1) 定位指标

- **Median distance**：预测位置与真实位置的中位空间距离。
- **Region accuracy**：细胞/spot 被正确分配到组织区域的准确率。

### 2) 生成指标

- **FID**：生成结果与真实分布之间的特征分布差异。
- **SSIM**：生成图像与真实图像在结构层面的相似性。
- **Gene-pattern correlation**：生成与真实基因空间模式的一致性相关系数。

**你的任务属于“mapping + generation”联合建模，难度高于单任务。**
