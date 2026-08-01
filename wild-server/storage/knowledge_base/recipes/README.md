---
doc_type: index
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: recipes_index
topic: navigation
wild_version: "1.1"
status: supported
authority: maintainer
source: recipes/README.md
keywords:
  - 组装配方索引
  - recipes
  - assembly
---

# 组装配方索引

> 依据：当前引擎实现与分类后的领域资料。
> 用途：记录跨构件组装顺序、实际 resolver、构件矩阵和风格速配表。
> RAG 关键词：组装模板、构件矩阵、低层建筑、高层建筑、大跨建筑、温室、门窗风格、屋顶类型。

## 当前拆分

| 文件 | 内容 |
|---|---|
| `supported-assembly-relations.md` | 当前 resolver 与 expander 已实现的组合关系 |
| `assembly-templates.md` | 只使用当前类型的低层、多层和大跨降级模板 |
| `component-building-matrix.md` | 构件与建筑类型的常用程度矩阵 |
| `door-window-roof-style-reference.md` | 门窗风格与屋顶类型速查 |
| `residential-material-palette.md` | 居住建筑材质角色、建议颜色和当前 MaterialDef 约束 |

后两份领域矩阵仍含未来专用构件，按 `experimental` 使用；任何写入正式 WILD 的结果都必须先受 `engine-capability-boundaries.md` 约束。
