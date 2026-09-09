---
entity_type: roof
entity_name: roof_and_eaves_family
topic: parameters
status: supported
authority: maintainer
source: components/roofs-and-eaves.md
primary_terms:
  - 屋顶
  - 屋檐
  - roof
  - roofType
synonyms: []
---

# 屋顶与屋面附属关系

## 屋顶类型与参数

roof 的 roofType 支持 gable、hip、dome、flat、chinese_curved、chinese_pagoda。类型由本次设计决定，不能由建筑名称固定映射。span/depth 分别对应 X/Z 覆盖，height 表达相应屋型高度，thickness 为屋面厚度；position 及具体曲面参数遵循完整规范。shed、arch、pitched 等不是合法 roofType。

## 支撑、覆盖与多体量

屋盖按所覆盖体量的支点和墙顶确定位置及范围，出檐按本次需求增加。多个体量及院落必须分别确定屋盖，不让一个整体包围盒屋顶盖住全部空地。自动补位置和扩大范围只是 resolver 兜底，不等于屋顶设计；复杂曲面和重檐需要实际渲染检查。

## 屋面附属能力

cornice、canopy、chimney 已是 geometry.components 支持的组件。cornice 用 path/profile，chimney 可用 parentRoof 定位但不自动穿孔；canopy 依附 parentWall。独立亭棚用显式支撑及屋盖。没有 window.parentRoof，采光顶用受支持透明 roof 或 primitive 近似，不能发明屋面开窗组件。
