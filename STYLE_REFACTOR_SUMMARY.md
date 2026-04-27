# HTML 样式重构总结

基于 `design.md` 中的 Claude 设计系统，对项目的HTML/CSS样式进行了全面重构。

## 核心设计理念

采用 **温暖羊皮纸主题** (Warm Parchment Theme)，营造文学沙龙般的温馨、知性氛围，区别于传统科技产品的冷色调设计。

## 主要变更

### 1. 颜色系统 (`web/pages/shared.css`)

#### 主色调
- **背景色**: `#f5f4ed` (Parchment) - 温暖的羊皮纸色调，替代原来的深蓝/深色背景
- **卡片表面**: `#faf9f5` (Ivory) - 象牙白，用于卡片和容器
- **纯白**: `#ffffff` - 用于按钮和高对比度元素
- **暖沙色**: `#e8e6dc` - 用于次要按钮背景

#### 文字颜色
- **主文本**: `#141413` (Anthropic Near Black) - 温暖的近黑色
- **次要文本**: `#5e5d59` (Olive Gray) - 橄榄灰
- **三级文本**: `#87867f` (Stone Gray) - 石灰色
- **强调文本**: `#3d3d3a` (Dark Warm) - 深暖色

#### 品牌强调色
- **赤陶色**: `#c96442` (Terracotta Brand) - 主要CTA和品牌元素
- **珊瑚色**: `#d97757` (Coral Accent) - 次要强调

#### 边框和阴影
- **奶油边框**: `#f0eee6` (Border Cream) - 浅色边框
- **暖色边框**: `#e8e6dc` (Border Warm) - 强调边框
- **环形阴影**: 使用 `0px 0px 0px 1px` 模式创造深度感

### 2. 字体系统

#### 字体族
- **标题**: Georgia (作为 Anthropic Serif 的替代品)
- **正文/UI**: system-ui, -apple-system, sans-serif
- **代码**: SF Mono, Monaco, Consolas (等宽字体)

#### 字号层级
- **Display/Hero**: 64px (4rem), weight 500, line-height 1.10
- **Section Heading**: 52px (3.25rem), weight 500, line-height 1.20
- **Sub-heading**: 32px (2rem), weight 500, line-height 1.10
- **Body**: 17px (1.06rem), line-height 1.60 (宽松的閱讀体验)
- **Lead Paragraph**: 20px (1.25rem), line-height 1.60

**关键原则**:
- 所有标题使用 medium weight (500)，不用 bold
- 正文行高设为 1.60，营造书籍般的阅读体验
- 标题行高紧凑 (1.10-1.30)

### 3. 组件样式

#### 卡片 (`.card`)
- 背景: Ivory (`#faf9f5`)
- 边框: 1px solid Border Cream (`#f0eee6`)
- 圆角: 16px (舒适圆润)
- 阴影: `rgba(0,0,0,0.05) 0px 4px 24px` (柔和悬浮)

#### 项目卡片 (`.item`)
- 背景: Pure White (`#ffffff`)
- 悬停效果: 环形阴影 `0 0 0 1px var(--ring-warm)`

#### 按钮
- **主要按钮**: Terracotta 背景 + Ivory 文字
- **次要按钮**: Warm Sand 背景 + Charcoal 文字
- **成功按钮**: 绿色半透明背景 + Success Green 文字
- **危险按钮**: 红色半透明背景 + Error Crimson 文字
- **停止按钮**: 红色背景 + Ivory 文字

#### 标签 (`.tag`)
- 透明背景 + 边框
- 圆角: 999px (胶囊形)
- 字号: 14px

### 4. 布局改进

#### 间距系统
- 基础单位: 8px
- 小间距: 8px
- 中间距: 12-16px
- 大间距: 24px
- 超大间距: 32px+

#### 网格布局
- 保持现有的 grid 系统
- 优化 gap 值以符合新的视觉节奏

### 5. 特殊组件

#### 状态指示器 (agent_control.html)
- 使用温暖的颜色方案
- 状态点 (`.dot`): ok (绿色), live (琥珀色), off (灰色)

#### 终端输出
- 深色背景 (`#141413`)
- 文字: Warm Silver (`#b0aea5`)
- 保留macOS风格的三色圆点

#### PTT (Push-to-Talk) 按钮
- 圆形设计
- 按下时显示红色脉冲动画
- 使用品牌色作为默认状态

## 文件修改清单

1. ✅ `web/pages/shared.css` - 完全重写，采用Claude设计系统
2. ✅ `web/index.html` - 更新样式引用和内联样式
3. ✅ `web/agent_control.html` - 重写内部style标签

## 设计原则遵循

### ✅ 已实现的原则
1. **温暖中性色调**: 所有颜色都有黄/棕底色，没有冷蓝灰
2. **Serif标题权威感**: 使用Georgia作为标题字体，weight 500
3. **宽松正文行高**: 1.60 line-height营造阅读节奏
4. **圆角友好**: 最小8px，最大32px，避免尖锐角落
5. **环形阴影**: 使用 `0px 0px 0px 1px` 代替传统边框
6. **柔和深度**: 极轻的阴影 (0.05 opacity, 24px blur)

### 🎨 视觉特点
- 杂志般的排版节奏
- 章节式的明暗交替
- 有机的手绘感（通过emoji图标）
- 温暖的信任感

## 测试建议

1. 在浏览器中打开 `http://127.0.0.1:15005/web/` 查看标题页
2. 检查幻灯片页面的新样式渲染
3. 访问 `http://127.0.0.1:15005/web/agent_control.html` 查看控制面板
4. 验证不同主题（亮色/暗色）下的显示效果

## 注意事项

- 保留了原有的HTML结构和ID，确保JavaScript功能正常
- 所有CSS变量都定义在 `:root` 中，便于维护
- 响应式设计保持不变
- 暗色主题 (`.theme-linear`) 也已更新为温暖的深色调

## 后续优化建议

1. 可以考虑为每个slide页面添加独特的装饰性插图（有机手绘风格）
2. 可以添加更多微交互效果（hover状态的细微变化）
3. 考虑增加印刷品质感的纹理背景

---

*重构完成日期: 2026-04-14*
*基于 design.md v1.0*
