# architecture 设计意图与全链路优化记录

## 问题与依据

本次以用户提供的三次 trace 和《WILD 蓝图设计语言 v2.0》为依据，重建 architecture 的设计任务与知识检索，并调整下游交接。没有把“提示词是否完整送达”作为评测项目；用户已明确这一点成立。源码修改前已有多处工作区改动，本次保留它们，没有提交或推送。

三次记录属于同一条生成、确认和恢复链，不能作为三个独立设计样本。

| 记录 | 实际发现 | 对本次修改的影响 |
|---|---|---|
| `trace-01a11e45-34a2-7fb0-9530-d79d6a90f0cb` | 初始五个设计块之后又发生五次设计完善调用，没有采用完善结果；一个约束把 volumes 数组与数量 1 用 equals 比较，另一个归一化缺口尝试恢复入口索引 0 | 把协议错误与建筑设计缺口区分；不能靠改建筑关闭非法目标 |
| 同上 | 公共提示词约 1.6 万字符，包含低层书写约束；块级加载再次带入基础协议。部分块有真实召回，不能概括成“RAG 全部没有命中” | 公共提示词说明设计任务，字段协议留给块；块检索不重复注入基础协议 |
| `trace-01a11e4f-0ce3-7c51-8ee3-1176219e3079` | 用户确认后没有落实檐口，材料绑定也有未落实警告；执行文本仍宣称完整验收通过 | 审核前把实例未编译和材料未绑定转为设计完善任务；执行结束分别报告几何校验与设计履约 |
| 同上 | 履约 20 项：兑现 8，未兑现 1，待核对 2，不支持 9；0.889 是可判定 9 项中的满足率 | 不把几何零错误、图执行完成或局部满足率当作设计整体完成 |
| `trace-01a11e50-db10-7bb3-9e30-5d6d8a85f5de` | 恢复后的图纸、蓝图和履约结果与上一记录相同 | 恢复完成不构成新的设计改善证据 |

## 节点职责与设计数据

architecture 先形成整体设计主张，再将它表达为当前协议可消费的体量、交通、立面、屋面、实例和材料绑定。这里保留设计自由：简单体量、对称、重复、少装饰都可以采用，关系和理由应服务于本次需求。字段类型、宿主引用和编译能力属于表达契约，不据此指定建筑必须长成什么样。

新增 `decisions.design_intent`：设计目标 goals、假设 assumptions、空间组织 spatial_strategy、整体构图 composition、材料方向 material_strategy、已选系统 selected_systems。`design_rationale` 则在参数表达结束时说明实际选择与限制；归一化和审核最多保留十一条依据及一条程序生成的决策事实，不再截成五条。

```mermaid
flowchart LR
    A[architecture 整体设计意图] --> B[体量与分块表达]
    B --> C[材料落实]
    C --> D[审核前编译与设计完善]
    D --> E[design 图纸与设计依据展示]
    E --> F[批准设计编译]
    F --> G[plan 构件执行与核对]
    G --> H[几何校验与设计履约报告]
```

当前标准起草从五个块变为六个块：intent → massing → structure/facade/roof → components。通常新增一次设计意图调用；不保证模型调用总数或延迟降低。局部几何修订保持既有五块依赖组，不因新增意图块扩大所有修订。

材质节点读取建筑方案的材料方向，不再把分类器候选风格当作另一套建筑配色指令。用户修订导致材料方向变化时重新评估材质；纯几何修订可复用已有材料。编译清单携带设计意图与依据，plan 和构件生成据此落实形态，但不能覆盖已批准尺寸、宿主或槽位。

新文档默认 `design/1.3`，继续读取旧版本；没有 design_intent 的历史文档不伪造意图。审核 hash 包含设计意图，几何重复检测的 fingerprint 排除这类说明文字。

当前还没有房间坐标与逐层室内平面协议。空间组织是设计意图，界面展示它不等于已经画出完整室内图纸，也不能从门窗数量证明采光或动线完成。

## RAG 查询与知识答案

原来 architecture 入口的三条全局查询已移除。块执行前由 `block_knowledge_query_specs` 根据用户需求和当前设计选择生成 SpecQuery，实际 Loader 每条最多取两片，并按完整片段控制上下文；不截断半个知识片段。

| 阶段 | 要回答的问题 | 检索过滤 |
|---|---|---|
| intent | 当前设计链可表达哪些关系，哪些只能保留为意图 | component + architecture_design_expression |
| massing | 体量起点、总体包络、逐层轮廓与屋面表达边界 | component + massing_composition_rules |
| structure/facade/roof | 当前块如何表达交通、开口、屋面及其限制 | component + architecture_design_expression，查询文本按阶段区分 |
| components | 已选实例怎么挂接，材料角色如何绑定 | 上述表达文档 + recipe/supported_assembly_relations |
| components 的补充查询 | 已选系统的字段、宿主和形态 | component + capability，按已选系统或已有实例类型补充，去重并限制三条 |

每个查询文本保留当前方案的屋型、结构、交通与已选系统，不从“别墅”“塔”等用途名称追加斗拱、楼阁或默认构件套餐。`load_many(include_base=False)` 用于 architecture 块；其他调用默认仍为 True。FileSpecLoader 在该模式下返回空参考，字段协议仍由块提供；这不是假装检索命中。块诊断保存查询及过滤、来源标题、字符数、耗时和错误。

通过 [wild-knowledge-ingest skill](../../.codex/skills/wild-knowledge-ingest/SKILL.md) 新增设计表达知识，重写体量组织、分层体量两篇知识。资料的具体处置见 [source-ledger.md](source-ledger.md)。当前知识库目录的 36 篇 Markdown（含导航）与 required_documents 清单一致；没有复制整栋案例或新增 WILD 引擎能力。

## 缺口与执行证据

数组与数量的 equals 比较、入口索引 0 等非法目标标为待核对，保留证据而不继续自动恢复非法值。不支持的枚举仍报告 unsupported。合法但未满足的目标继续为 open，仍可驱动设计修订。

编译器对声明了但未产出的实例新增 `design_instance_uncompiled` 诊断，定位到具体 components 下标；它与已有 `material_region_unapplied` 一起进入审核前完善。完善结果仍须保留要求及已兑现决定、关闭实际缺口，不能删除约束、编造宿主或以换对象隐藏未落实项。有些选择无法在当前能力内修复，会保留缺口供审核，有限预算不会强行宣称成功。

执行修复文本使用“几何校验通过”“设计履约以报告为准”等准确口径。当前检查通过只代表对应检查范围，不以此宣称建筑审美或全部设计目标已经达成。

## 已执行检查与限制

- 34 项真实 pytest 通过：设计意图保存与审核交接、历史兼容、审核 hash、类型/范围错误判定、材料方向提示、计划上下文，以及知识库用途/语义/清单门禁。
- 38 项收集中的 4 项涉及构件生成、实际编译与完善调度，因本机异步模块异常暂未执行；没有把它们计入通过数量。
- 活动知识语义与清单检查零 error；现有 warning 共 123 条，不作为本次全面清理范围。
- 322 个 Python 文件 AST 检查通过；直接加载生产设计块文件的独立冒烟检查通过了字段归属、依赖顺序与查询组成，未替换函数实现。它不等于正常服务导入或完整检索验证。标准异步链路测试、真实 Markdown 分片预览及临时索引检索冒烟受 Windows `WinError 10106` 阻断。
- 前端 `vue-tsc -b` 在 Node 初始化阶段因 `ncrypto::CSPRNG` 断言退出，未获得类型检查通过或浏览器视觉验证结果。
- 没有同步或重建正式 Chroma 索引，没有完成新的真实模型生成对比。代码与文档更新不能据此宣称生产召回或建筑设计质量已经提升。

可在正常运行环境执行以下检查；pytest 正常插件可用时无需关闭自动加载。故障环境下用于已完成的同步测试：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.venv/Scripts/python.exe -X utf8 -m pytest tests/design/test_architecture_intent_chain.py tests/design/test_design_completeness.py tests/rag/test_knowledge_rules_v3.py -q -k 'not compile_reports and not implementation_warnings and not component_prompt'
```

完整针对性回归：

```powershell
cd E:\AgentProject\WildAgent\wild-server
.venv/Scripts/python.exe -X utf8 -m pytest tests/design/test_architecture_intent_chain.py tests/design/test_design_document.py tests/design/test_normalization_evidence.py tests/design/test_material_regions.py tests/design/test_roof_per_volume.py tests/agent/test_design_blocks.py tests/agent/test_design_completion.py tests/rag/test_architecture_design_queries.py tests/rag/test_rag_semantic_chunking.py tests/rag/test_knowledge_rules_v3.py -q
```

知识预览及隔离索引冒烟：

```powershell
cd E:\AgentProject\WildAgent
wild-server/.venv/Scripts/python.exe -X utf8 .codex/skills/wild-knowledge-ingest/scripts/preview_wild_rag_chunks.py wild-server/storage/knowledge_base --json
wild-server/.venv/Scripts/python.exe -X utf8 wild-server/scripts/rag/smoke_test.py
```

后续真实生成对比应使用同一模型配置与相同需求，观察设计意图怎样影响实际入口、体量、开口、屋面与材料关系，及未表达项是否如实展示；同时看 SVG、编译蓝图和渲染结果。提示词送达、召回条数、零几何错误只能作为过程数据，不能作为本次设计优化效果的结论。
