# 知识能力待办区

这里保存有价值但尚未形成当前 WILD 能力的声明。它不在 `wild-server/storage/knowledge_base/` 下，因此不会被分片、向量化或注入生成提示词。

进入活动知识库前，一项能力必须同时具备：合法字段或明确的现有几何映射、compiler/renderer 实现、必要的 validator、最小回归样例和准确的 capability/recipe 文档。只写 Markdown、标记 `status: proposed` 或让模型承诺遵守，都不算实现。

- [proposed-component-extensions.md](proposed-component-extensions.md)：尚未实现的组件类型与自动组合机制。
- [unimplemented-building-invariants.md](unimplemented-building-invariants.md)：用户期望但当前链路尚不能确定性保证的跨构件规则。
