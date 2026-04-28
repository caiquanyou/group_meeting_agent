---
page_number: 13
layout: full-image
theme: linear
---

# 空间自定位测试结果

本页指标定义见上一页。

## 定位精度与生成质量

**定位性能（MERFISH 小鼠脑数据集）：**

| 方法 | 中位误差 (μm) | Top-1 区域准确率 |
|------|:---:|:---:|
| Tangram | 48.3 | 71.2% |
| novoSpaRc | 52.1 | 68.5% |
| PASTE | 44.7 | 73.8% |
| **Ours** | **31.6** | **84.3%** |

**生成质量（FID / SSIM）**

- 空间表达图生成 FID：**18.4**（vs. 基线 34.7）
- 结构相似度 SSIM：**0.82**

![空间定位结果](../assets/figs_12/spatial_results.png)

*图：空间自定位结果可视化（左：真实坐标，右：预测坐标）*

---

<!-- 
  这页展示空间模型测试结果
  - layout: full-image 全屏展示可视化结果
  - theme: linear 深色背景适合展示空间图
  - 图片路径：../assets/figs_12/
-->
