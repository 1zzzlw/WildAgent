# WILD 规则知识库（rules-v3）

rules-v3 将建筑分类从 RAG 生成知识中彻底移除。大模型负责理解别墅、办公楼、商场等建筑语义；知识库只回答 WildAgent 特有的三个问题：WILD 字段怎样写、当前引擎能表达什么、已选择的构件或系统怎样正确组装。

## 活动知识角色

| knowledge_role | 内容 | 普通生成 |
|---|---|---|
| `protocol` | WILD 字段、坐标、引用和最小输出协议 | 使用 |
| `capability` | 当前实现、合法枚举、参数和能力边界 | 使用 |
| `relation` | 已选系统的宿主、组装与验证关系 | 使用 |
| `strategy` / `example` / `fallback` | 设计策略、案例和人工参考 | 活动库不保存 |
| `navigation` | 目录 | 不使用 |
| `identity` | 旧建筑类型卡角色 | 禁止用于 generation |

普通生成由 Loader 强制限定为 `knowledge_revision=rules-v3`、`doc_scope=generation`、上述三个活动角色、受支持状态和有效权威。旧 revision 即使仍在 Chroma 中也不会进入上下文。

## 建筑分类放在哪里

建筑用途和风格不再使用 Markdown 类型卡或向量检索。`app/agent/architecture_plan.py` 保留少量执行 profile，例如低层居住、普通公共、大跨、高层、地下交通和园林构筑物。这些 profile 只提供当前引擎的尺寸边界、支持形态与确定性失败回退，不承担建筑百科和完整方案设计。

具体层数、轮廓、材料、立面系统和构件选择写入本次 `DesignDocument`。例如“玻璃幕墙写字楼”由模型理解办公语义，由 `DesignDocument` 明确选择 `curtain_wall`，随后才召回幕墙组装关系；“写字楼”三个字本身不能静默启用幕墙。

## 当前目录

- `BLUEPRINT-SPEC-*`：基础协议和完整字段说明。
- `components/`：当前构件能力、字段、禁止项和少量业务名到 WILD 的条件映射。
- `recipes/`：跨构件关系与已选专用系统的组装规则。

当前活动库不建立 `patterns/`，也不保留 `status: proposed` 的文档或分片。旧的高细节策略和门窗屋顶风格参考没有代码消费者，且属于模型已有的一般设计能力，已删除。未来若建立项目专有策略库，调用链必须是“意图提取或初步方案 → 显式策略 ID → reference 检索 → 候选方案比较”，不能指望普通生成查询偶然命中。

原 `building_types/` 已移出活动知识库，保存在 `docs-dev/retired-knowledge/building_types-rules-v2/` 供历史追溯。住宅与公共建筑两份重复材质说明合并为通用 `recipes/material-role-relations.md`。旧建筑分类维护脚本和测试已删除。

## 代码消费链

```text
用户需求
  → 模型理解建筑语义
  → execution profile 选择当前引擎边界
  → ArchitecturePlan / DesignDocument
  → 按已选构件和系统检索 capability / relation
  → skeleton / component generation
  → compiler / validator
```

总体方案节点和计划研究节点不再发出 `doc_type=building_type` 查询。旧的八类生成检索缩减为七类可执行知识查询：组件选择关系、结构、墙、窗、门、栏杆和屋顶。方案、计划和骨架节点统一检索 `supported_assembly_relations`，不再把尚未有 validator 的设计建议当作已执行模板。知识问答节点也只查询 protocol、capability、relation，不再宣称知识库覆盖建筑类型学。知识覆盖判断只检查组件参数与组装关系。

## 扩库门禁

使用 [wild-knowledge-ingest Skill](../../.codex/skills/wild-knowledge-ingest/SKILL.md) 扩库时：

1. 建筑百科、用途分类和风格描述放在扫描目录之外。
2. `building_type + generation` 由 linter 直接报错。
3. 专用系统规则必须有明确 `applies_to`，且触发词只能是系统或构件变体，不能是建筑用途或风格。
4. `engine_hard` 必须能映射到 Schema、compiler 或 validator；提示词中的“必须”不算执行。
5. 数字必须区分 Schema 边界、解析器参数、设计输入和局部示例。
6. 运行时直接解析的参数块继续使用 system scope，不能误删。
7. `status: proposed` 的文件和分片必须放到 `docs-dev/knowledge-backlog/`，不能依赖查询过滤留在活动库。
8. 新增、移动或删除活动 Markdown 时同步更新 `config.yaml.required_documents`；部署按清单逐文件校验，不使用固定篇数阈值。

## 验证与同步

在项目根目录检查文档：

```powershell
wild-server/.venv/Scripts/python.exe -X utf8 wild-server/scripts/rag/lint_wild_rag_docs.py wild-server/storage/knowledge_base --cross-check
wild-server/.venv/Scripts/python.exe -X utf8 .codex/skills/wild-knowledge-ingest/scripts/preview_wild_rag_chunks.py wild-server/storage/knowledge_base --json
```

在 `wild-server` 目录运行代码与检索回归：

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest tests.rag.test_knowledge_rules_v3 -v
.venv/Scripts/python.exe -X utf8 -m pytest tests/rag tests/components/test_architecture_plan.py tests/agent/test_web_research_gate.py -q
.venv/Scripts/python.exe -X utf8 scripts/rag/eval_retrieval.py --sync-index --questions evals/rag_retrieval_cases.json --json-output scripts/reports/rules-v3-retrieval.json
```

索引由 `RAGSpecLoader` 同步。不能手工删除 Chroma 目录；变更后重启后端或显式执行同步，确认 rules-v3 文档已 upsert、退出活动目录的旧分片已删除。若本机 Winsock 阻止 Python 导入 asyncio/Chroma，应记录为运行环境阻断，不能把静态检查说成真实索引验证。

## 生成验收

检索正确只证明类型模板不再进入提示词。生成质量仍需固定模型与采样参数，对同一需求重复生成并同时检查：

- 用户硬约束和批准设计是否保持；
- 宿主、标高、覆盖、碰撞与材质引用是否有效；
- 未限定变量是否在体量、立面节奏、屋顶和入口组织上产生有效差异；
- 差异是否来自设计选择，而非随机挪坐标、换颜色或堆无功能构件。
