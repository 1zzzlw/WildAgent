# 文档模板

模板是写作辅助，不要求无信息的栏目占位。真实 Markdown 标题是实体边界，避免粗体 A/B/C 伪分块。

🔴 文件级 frontmatter 只写"整篇共享"的字段；**同一文件里并列讲多个构件时，每个构件必须用自己的
`rag-meta` 声明 `entity_type`**，否则按构件检索命中不到（机制与后果见
[chunk-contract.md](chunk-contract.md)）。

## 构件级分片（多构件文件必用）

```md
## 墙体构件

<!-- rag-meta
entity_type: wall
entity_name: wall_family
topic: parameters
primary_terms:
  - 墙体
  - wall
synonyms: []
-->

必需字段：…（本构件独有的字段表）
边界：…（本构件做不到的事）
```

## 专用系统条件映射

```md
## 类型名称

<!-- rag-meta
entity_type: component
entity_name: stable_system
topic: assembly
knowledge_role: relation
authority: engine
primary_terms:
  - 类型名称
synonyms: []
applies_to:
  - 类型名称
-->

- 适用条件：本次需求或已批准方案点名此系统。
- 字段与关系：选择相应系统后应维持的组件角色、宿主和连接。
- WILD 映射与边界：受支持表达、无法表达的部分及近似方式。
- 自由变量：由本次方案决定的轮廓、尺寸、数量、布局或材料。
```

注意 `entity_type` 只能取代码里真实使用的值（当前查询涉及
`structural_component` / `wall` / `window` / `door` / `railing` / `roof`，
以及协议类的 `schema`、组装类的 `assembly`）。写一个没人查询的值等于没写。

不要通过建筑用途或风格自动添加庭院、门廊、幕墙或阳台。复杂系统可拆成子标题，但每片保留实体上下文与触发条件。

## 能力与关系

```md
## 实体或组装关系

适用条件：已选系统或调用此字段时。
字段与关系：当前源码支持的字段、引用、坐标与约束。
边界：不能自动完成的能力；存在受支持近似时说明语义差异。
检查：对应确定性校验或需要渲染确认的结果。
```

局部 JSON 说明它属于 elements、components 或 materials，不能标为完整 .wild。示例中所用数值仅解释字段；引用必须在片段中给出或明确前置条件。错误示例单独隔离，不混入有效示例。

## 策略与案例

策略与案例保存在活动知识库之外，并写明适用意图、可替换选择、不可泛化的尺寸和来源。未经实际验证的案例不能标 verified_example。只有建立专用 reference 索引和显式策略路由后，才为它们设计可检索模板。
