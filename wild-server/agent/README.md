# Agent 目录与职责

`agent` 负责意图判断、设计、任务规划与执行。应用入口在根目录 `main.py`，编辑器和任务服务通过 `integration` 层调用工作流。

| 目录 | 职责 |
| --- | --- |
| `workflows` | 意图、问答、图纸、修改、规划、执行、装配、校验和修订 |
| `prompts` | 各节点的提示词和字段协议 |
| `llm` | 模型供应商、客户端、调用和资源初始化 |
| `rag` | 文档切分、索引、检索和联网资料处理 |
| `tools` | 工作流的检索、空间和图纸检查工具 |
| `utils` | 设计契约、几何、构件配方、编译与校验 |
| `script` | 图纸 Schema 导出等离线入口 |

从 `graph.py` 进入节点。图直接导入各工作流包的公开入口。`state.py` 定义图状态，`runtime.py` 保存模型实例、加载器和本轮回调。

建筑和物件共用 `architecture → plan → execute / replanner → compile → final_validate`。Plan 按图纸展开任务，并把材质角色映射到初始蓝图。校验结果与蓝图一起由交付层处理。

知识文档存放在仓库的 `storage/knowledge_base/`。完整应用中的素材清单、任务恢复和结果保存由外层提供。
