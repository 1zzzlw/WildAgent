# Document Templates

Use these templates when creating new knowledge-base Markdown files.

## Lightweight Building Catalog Template

Use for `building_types/catalog/` entries.

```md
# 轻量建筑分类：名称

> 来源：<source path or user-confirmed note>.
> 用途：当用户模糊请求“生成一个名称”时，提供默认语义入口、常见变体和最少可行版本。
> RAG 关键词：中文名、别名、英文名、默认版本、常见风格。

---

## 标准功能分区

## 常见变体

## 构件清单

## 典型尺寸

## 最少可行版本
```

## Building Type Template

```md
# 建筑类型：名称

> 来源：<source path or user-confirmed note>.
> 用途：说明这个文档回答哪类建筑生成问题。
> RAG 关键词：中文名、别名、英文名、构件关键词、风格关键词。

---

## 适用范围

## 标准功能分区

| 区域 | 位置 | 核心构件 |
|---|---|---|

## 构件清单

## 参数建议

## 风格与材料

## 最少可行版本

## 待确认
```

## Component Template

```md
# 构件：名称

> 来源：<source path or user-confirmed note>.
> 用途：说明该构件族如何分类、表达和组装。
> RAG 关键词：中文名、别名、WILD type、参数名、风格名。

---

## 适用范围

## WILD 映射

| 概念 | WILD type | 核心参数 | 说明 |
|---|---|---|---|

## 分类

## 参数建议

## 组装规则

## 与建筑类型速配

## 候选能力
```

## Recipe Template

```md
# 组装配方：名称

> 来源：<source path or user-confirmed note>.
> 用途：说明该配方适用的生成策略。
> RAG 关键词：模板名、建筑类型、构件顺序、WILD type。

---

## 适用范围

## 组装顺序

示例：`column -> floor -> wall -> opening -> door/window -> roof`

## 必需构件

## 可选构件

## 约束与校验

## 示例请求
```

## Pattern Template

```md
# 模式：名称

> 来源：用户确认 / 项目沉淀。
> 适用场景：
> RAG 关键词：

## 设计意图

## 构件组合

## 参数偏好

## 使用限制
```
