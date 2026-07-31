---
doc_type: index
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: patterns_index
topic: navigation
wild_version: "1.1"
status: supported
authority: maintainer
source: patterns/README.md
keywords:
  - 设计模式
  - 项目案例
  - patterns
---

# 设计模式与项目案例

> 用途：存放用户确认后的可复用设计模式、项目偏好、场景案例和领域经验。
> RAG 关键词：设计模式、用户偏好、案例、项目经验、可复用配置、patterns。

## 适合存放

- 用户确认过的建筑组合方案。
- 某个项目反复使用的材料、比例、构件配置。
- 从生成结果中沉淀出的稳定案例。
- 不属于通用规范、但对当前项目有价值的经验。

## 条目模板

```md
---
doc_type: pattern
doc_scope: generation
knowledge_layer: project_pattern
entity_type: building
entity_name: confirmed_pattern_name
topic: assembly
wild_version: "1.1"
status: supported
authority: verified_example
source: patterns/confirmed-pattern-name.md
keywords:
  - 用户用词
  - project pattern
---

# 模式名称

> 来源：用户确认 / 项目沉淀。
> 适用场景：
> RAG 关键词：

## 设计意图

## 构件组合

## 参数偏好

## 使用限制
```
