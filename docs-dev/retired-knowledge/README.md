# 退出活动检索的历史知识

本目录保存已从 `wild-server/storage/knowledge_base/` 移出的历史资料，仅用于追溯旧设计，不会被 `RAGSpecLoader` 扫描或注入生成 Prompt。

## building_types-rules-v2

该目录是 rules-v2 的建筑用途、风格描述和整栋配方快照。它们在 2026-09-10 退出活动知识库，原因是内容与模型已有语义重复，并含固定构件组合、尺寸或完整 Blueprint，容易锚定生成结果。

如需从历史资料提取新知识，只能加工成以下内容后重新进入活动库：

- 当前引擎或 WILD Schema 的可验证能力；
- 有明确触发条件、字段映射和执行位置的组装关系；
- 能由 validator、resolver 或 compiler 确定性执行的约束。

建筑百科、用途类型卡、风格描述、完整案例和无代码执行点的强制参数不得原样迁回。
