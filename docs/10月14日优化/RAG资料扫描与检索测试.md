# 2026.10.13 资料扫描与 RAG 检索测试

扫描来源：`D:\Backup\桌面\2026.10.13`。该目录的说明和蓝图只作为候选资料，是否入库以当前 WILD Schema、编译消费路径和知识用途边界为准。

## 资料处置

| 资料 | 扫描结果 | 处置 |
| --- | --- | --- |
| 20 份 Markdown | 17 份不同内容；四合院、古典殿宇有跨目录副本 | 不整篇入库。形制、固定尺寸、配色和单栋校验脚本属于案例，不应成为其他建筑的限制。旧版通用书写协议以当前 Schema 和现有协议文档为准。 |
| 27 份 `.wild` | 24 份不同内容；均可解析为 JSON | 16 份通过当前 `wild-core/schema.json` 结构校验；另外 8 份含旧字段或非法值，只能逐片核对，不能直接当作有效示例。 |
| 1 份 `.bak` | 文件名标明损坏备份 | 不参与知识入库。 |

已有局部知识覆盖亭子、古典柱廊、球形塔、层叠塔檐、锥坡圆殿、幕墙、中式隔扇、双坡屋面和高层井道；对应建筑案例的整栋参数无需重复存储。本轮新增 [楼板围绕矩形洞口分片](../../wild-server/storage/knowledge_base/knowledge/components/massing-composition-rules.md)：从咖啡厅、别墅、院落的共同写法提取局部 `floor` 分片表达，不绑定任何建筑类型或固定尺寸。示例的四片楼板通过当前 Core Schema；面积为 44㎡，中央 4㎡ 保持无板。

当前 Schema 下未通过的 8 份不同 `.wild`：森林咖啡厅、独栋庭院咖啡厅、错位叠盒咖啡厅、高台观景咖啡厅的 `behaviors` 为数组且 `meta.type` 缺失；三层平顶挑檐现代别墅、三层退台现代别墅的部分 door 带当前 Schema 不接受的 `material`；高层住宅楼的 28 个梯段把 `width` 写成字符串 `fw`；天坛祈年殿的 24 个 primitive `rotation` 含 `null`。这些是当前结构契约检查结论，不否定它们在旧渲染环境中的观感。

## 检索测试集与结果

[LangSmith CSV 测试集](../../wild-server/evals/rag_retrieval_cases_langsmith.csv) 新增 17 题：architecture 基础设计 4 题、形制构件参考 3 题、建筑主体 4 题、plan 构件条目 6 题。测试题包含输入问题、实际节点使用的过滤形态、预期来源和必要术语。`building_body` 的四题只用 `doc_type=component`，与实际构件检索入口一致，不靠预设准确来源过滤制造命中。

读取当前正式路径 `wild-server/storage/chroma` 的只读索引后，534 个分片中有 16/17 题的预期来源及术语；新楼板洞口题的目标文件虽已入库，新增小节尚未同步到索引。按阶段分别为 architecture 7/7、主体 3/4、构件 6/6。此项只证明**过滤后索引中有内容**，不证明语义排序、Top-K、上下文截断或模型实现成功。`blueprint-skeleton.md` 和 `generation-redlines.md` 没出现在索引中是正常设计：它们作为基础规范直接注入。

| 阶段 | case_id | 当前索引中的来源及术语 |
| --- | --- | --- |
| architecture | `scan_arch_cafe`、`scan_arch_courtyard`、`scan_arch_tower`、`scan_arch_pavilion` | 4/4 有 |
| architecture 形制参考 | `scan_arch_shape_pavilion`、`scan_arch_shape_sphere`、`scan_arch_shape_temple` | 3/3 有 |
| building_body | `scan_body_open`、`scan_body_sphere`、`scan_body_highrise` | 3/3 有 |
| building_body | `scan_body_void` | 新小节待索引同步 |
| plan 构件 | `scan_item_stair`、`scan_item_roof`、`scan_item_chimney` | 3/3 有 |
| plan 构件 | `scan_item_lattice`、`scan_item_colonnade`、`scan_item_light` | 3/3 有 |

当前机器的 Python 在导入 `asyncio` 时抛出 `WinError 10106`。因此真实 `RAGSpecLoader.retrieve`、MarkdownChunker 预览、`check_kb.py`、目录检查和索引增量同步未能执行；本轮没有真实模型生成或节点级召回结论。文档 linter 通过（46 份活动文档、0 error；152 项 warning，本轮修改的知识文件无 warning），新 JSON 片段通过 Core Schema，`git diff --check` 通过。

提交或部署前需要在 Python 环境恢复后运行现有 `check_kb.py`、真实分片预览、目录 `--check`、`resync_knowledge_index.py`，再用这 17 题做真实 Loader/节点过滤的 Top-K 与注入上下文测试。索引签名若不兼容，应保留现有集合并诊断，不能直接重建覆盖。验证完成前，新小节仍属于**文件已更新、线上检索未生效**。
