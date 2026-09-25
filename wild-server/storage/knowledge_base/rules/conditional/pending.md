---
doc_type: index
knowledge_role: navigation
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: conditional_rules_overview
topic: navigation
status: supported
authority: maintainer
primary_terms:
  - 条件约束
  - 跨构件触发规则
synonyms: []
---

# 条件约束

本目录收录**"选了 A 就必须落实 B"**的跨构件触发规则。

判定标准：规则形如「如果方案选择了 X，就必须落实 Y」；去掉 X 这个前提，规则不成立。

## 当前内容

- `component-selection.md` —— 按功能选择构件：列出「已选择的功能 → WILD 表达 → 必须保持的关系」，
  `entity_name: component_selection_conditions`，被生成期检索直接点名。

## 待判定是否迁入

- `rules/implementation/assembly-relations.md` 的「楼板与屋顶自动补全」一节 —— 由"多层交通"这个前提触发。
- 阳台组件的宿主与通行关系。
- ~~楼梯穿越楼板处的净空关系~~ → **已按"生成侧规则"迁入**
  `rules/implementation/validation-rules.md` §4.4：`floor` 无开洞字段，楼梯井用多块矩形 floor
  拼出（井口盖住跑步上半段，楼梯端点 3 个采样点须落在井外楼板上）。注意它**不是 validator
  执行的硬规则**——校验器只查端点落板、不查"楼板压住楼梯"（element 间碰撞只查同类型）；
  "floor 开洞字段"本身仍是引擎缺口，留在 backlog。

## 收录前提

条件约束必须同时在 Schema、compiler、resolver 或 validator 中执行；
文档只是它的可读投影，不是它的来源。未实现的关系不写进这里，留在 backlog。
