---
name: wild-knowledge-ingest
description: 把外部资料（网页、上游 AI 产出的 JSON 描述、规范摘录、用户手写文档）转化为 WildAgent WILD 知识库中可检索、可执行的条目；判断每条声明该落进 knowledge/ 还是 rules/、该保留还是丢弃、该标什么 authority，并验证真实分片与检索用途。
---

# WildAgent 规则知识维护

## 目标与当前设计

知识库帮助模型把本次设计正确表达成 WILD。用户需求与已批准方案决定造型；知识不能把建筑百科、类型样例、风格偏好或默认配色提升为生成要求。当前知识版本为 `rules-v3`，加载器默认仅召回 generation scope 下的 `protocol` / `capability` / `relation`（`app/spec/loader.py` 的 `knowledge_role` 过滤）。

写作目标目录是 **`wild-server/storage/knowledge_base/`**（开发阶段只有这一个版本，不要再造 v2 目录），第一层按"知识 / 规则"二分：

```
knowledge/{protocol,components}   # 操作协议 / 复杂构件表达  —— 描述"是什么、怎么写"
rules/{implementation,conditional,design-choice}  # 实现约束 / 条件约束 / 设计选择 —— 描述"必须成立什么"
```

互斥判据一句话：**「违反了能不能被机器判定」** —— 能被 schema / compiler / resolver / validator 判定则进 `rules/`；
只是"不这样写模型会出错"则进 `knowledge/`。这两类对应检索时的**两次查询**（知识查询 + 规则查询），
不要为了对称把同一内容拆到两边，也不要自创第三个顶层分支。

三类活动内容固定为：Blueprint/ScenePatch 操作协议、当前已实现的复杂构件能力、具有代码执行点的跨构件关系。
尚未实现的规则和组件进入 `docs-dev/knowledge-backlog/`，不得留在活动目录中等待 status 过滤。

## 读取入口

- **知识目录（写作目标，同时也是运行时唯一读取的那一份）**：`wild-server/storage/knowledge_base/`。
  路径级 metadata 在 `config.yaml` 的 `defaults` + `mapping_rules`；人读分类法在该文件的 `classification:` 段；
  完整性清单在 `required_documents`。
  🔴 旧 v1 库已删除、**不存在双库**，所以**改完文档就会直接影响线上检索**——不需要再声明"未接线"这类前提。
  代码里的读取点：`app/services/agent_service.py`（`_KB` 与 `BASE_SPEC_PATHS`）、
  `app/agent/generation/architecture/recipes.py`（幕墙确定性参数）、`app/agent/validation/*`。
  开发阶段不分版本，**不要再新建 `knowledge_base_v2/` 之类的目录**。
- **能力依据（Schema / 合法性）**：`wild-server/storage/knowledge_base/schema.json` —— 唯一不过期的事实源，
  随知识库目录一起分发，后端 `app/utils/blueprint_normalizer.py::SCHEMA_PATH` 直接指向它
  （`app/utils/wild_schema.json` 那份 vendored 副本已删除，不要再引用）。
  前端那份在**独立包 `wild-core/schema.json`**（原 `wild-web/wild-lang/` 目录已删除），
  由 `wild-core/src/primitive/schema-validator.ts` 构建期 import。
  活跃副本只有两份：`wild-core/schema.json` ↔ `wild-server/storage/knowledge_base/schema.json`，
  字节一致、不共享路径；**改 schema 必须同时更新这两处**。
  Schema 只回答"字段名、枚举取值、必填项、结构形状是否合法"。
- **约束执行依据（Validator / 关系）**：`app/agent/validation/`（`structure.py` 结构合法性、
  `design_constraints.py` 设计约束、`component_trace.py` 构件溯源、`workflow.py` 编排）、
  `app/design/resolver.py`（引用解析）。Validator 回答的是 Schema 表达不了的**跨对象关系**
  （如"窗必须挂到真实存在且进深足够的墙上"）。
- **权威分级判据**：能在 Schema 里找到字段 → `authority: schema`；能在 validator/compiler 里找到执行点 →
  `authority: engine`；只有提示词说"必须" → 不算已执行（提示词不构成执行证明）。
- **分类路由依据**：`app/agent/generation/architecture/profile.py` 中的有限执行 profile；它不是 RAG 建筑百科。
- **生成协议**：`knowledge/protocol/blueprint-skeleton.md` 固定注入（v1 的
  `BLUEPRINT-SPEC-MINIMAL/FULL.md` 已解散，不要再引用）。
- **消费代码**：`app/spec/loader.py`（分片与过滤，含 `MarkdownChunker._DOCUMENT_METADATA_FIELDS`）、
  `app/spec/query_planner.py`、`app/agent/knowledge/policy.py`、各生成节点，路径均相对 `wild-server/`。

## 外部资料入库流程（主要入口）

用户补充知识库的真实路径是：**上网查某构件/系统怎么组成 → 让上游 AI 基于本项目产出 JSON 描述 →
由本 skill 拆声明、判分类、落位或丢弃**。按下列步骤执行，不要跳过第 2 步直接写文档：

1. **收集资料**：网页、规范摘录、上游 AI 的 JSON、用户手写文档。上游 AI 产出的 JSON 是**中间产物**，
   不是待入库内容——它只是"原始声明"的载体。
2. **拆声明清单**：把资料切成一条条原子声明（"窗由框 + 玻璃 + 竖梃构成""幕墙分格应与楼层对齐"）。
   每条记录：来源位置、声明、证据、拟处置、目标文档。**没有类别的不补写**。
   详细做法见 [source-fidelity-and-composition.md](references/source-fidelity-and-composition.md)。
3. **逐条判定处置**：`preserved`（有依据的事实）/ `normalized`（语义保留、按当前字段重写）/
   `routed`（转到明确目标并说明是否参与生成）/ `downgraded`（说明当前近似表达）/
   `deferred_conflict`（证据不足或冲突，隔离）/ `rejected`（重复、无关或错误，记录原因）。
   **上游 AI 的 JSON 只是"素材"，它给的字段名和数值大概率不符合本项目 Schema，必须逐条改写或拒绝。**
   一份质量平平的资料里的**有用部分要留下、没用的部分要显式丢弃并记录原因**——不要整篇照收，
   也不要因为局部错误就把整份里有效的空间关系一起删掉。
4. **映射到当前引擎**：查 Schema 有没有对应字段、查 validator/resolver 有没有执行点。
   - 有字段 + 有执行点 → `rules/`，`authority: engine|schema`。
   - 有字段、无执行点、只能靠模型自己写对 → `knowledge/`，`authority: schema`。
   - 无字段、产品确实不支持 → 不进活动库，写明限制；不要为"知识完整"编造字段。
5. **落位并按模板写**：目录与文件名用**英文**，H1 标题与正文用**中文**（中文标题才是召回锚点）。
   模板见 [document-templates.md](references/document-templates.md)。
6. **回写 metadata 与清单**：补 frontmatter（见 [metadata-schema.md](references/metadata-schema.md)）；
   增/移/删文档时同步 `config.yaml` 的 `required_documents`。
7. **验证**：跑下面的命令，并如实报告 v2 未接线的限制。

按任务读取引用：分类读 [classification-taxonomy.md](references/classification-taxonomy.md)；重写读 [document-templates.md](references/document-templates.md)；metadata 读 [metadata-schema.md](references/metadata-schema.md)；分片读 [chunk-contract.md](references/chunk-contract.md)；资料转换读 [source-fidelity-and-composition.md](references/source-fidelity-and-composition.md)；设计契约映射读 [design-contract-mapping.md](references/design-contract-mapping.md)；交付读 [rag-readiness-checklist.md](references/rag-readiness-checklist.md)。

## 内容取舍

1. 保留项目特有语法、坐标、引用、能力边界和构件间条件关系。
2. 普通常识不为完整性重复入库；只有能解决具体遗漏、歧义或项目映射问题时才保留。
3. 建筑类型卡、用途百科和风格说明不进入活动知识库。只有项目无法从模型与用户需求稳定得到、并能落到执行字段的条件规则才可进入 `rules/` 或 `knowledge/components/`。
4. 通用规则描述“选用某系统后必须保持的关系”；不要把“现代住宅优先退台”等偏好写成硬规则。
5. 数字须区分 Schema 范围、实际引擎行为、运行配置、领域参考和局部示例。不能把定值机械改成范围或比例当作自由设计；也不能删除引擎真实限制。
6. 局部 JSON 可保留解释字段，但不能携带完整建筑布局。整栋案例、设计策略和失败回退保存在扫描目录之外；只有出现明确消费者和受控检索入口后，才能建立单独的 reference 索引。
7. 先检查代码是否直接解析文档内容。例如建筑 profile 与 recipes 由
   `app/agent/generation/architecture/{profile,recipes}.py` 消费，这类内容不能作为“普通例子”删掉；
   运行配置与模型参考必须分开标注。

## 执行流程

1. 检查 Git 状态，读取现有同主题知识及实际消费者。保留用户文件和无关改动。
2. 建立来源声明清单：来源位置、声明、证据、处置与目标。原始建筑语义与 WILD 实现分别判定；错误字段不导致有效空间关系一并丢失。
3. 依据源码核验能力；用户明确设计要求可覆盖旧模板偏好，但不改变引擎事实。无法验证的能力移入 `docs-dev/knowledge-backlog/`，不伪装成 supported/engine，也不把 proposed 分片留在活动库。
4. 共享字段放 `knowledge/protocol` 或 `knowledge/components`，共享关系放 `rules/implementation` 或 `rules/conditional`；策略、案例和建筑语义资料放到扫描目录之外。不为每种建筑复制相同门窗规则。
5. 每个实体使用真实 Markdown 标题，说明适用条件、WILD 映射、能力边界和自由变量。复杂构件只保留单个构件及必要宿主的最小 JSON；专业系统语义不能只保留名称，必须解释项目如何表达。
6. 配置 `knowledge_role`、`applies_to` 和来源。`applies_to` 只包含能显式选择专用系统或构件变体的术语，不能写建筑用途、风格、"生成、建筑、wall"等泛词。目录能给出的字段交给 `config.yaml` 的 `mapping_rules`，不要在每个文件里重复抄一遍。
   新增、移动或删除活动 Markdown 时，同步维护 `config.yaml` 的 `required_documents`，该清单是**真门禁**
   （`scripts/deploy/deployment_preflight.py`，Jenkinsfile 部署前调用，当前硬编码指向 v1 `storage/knowledge_base`）。
   🔴 **只列 `.md`**：preflight 断言每条都以 `.md` 结尾、非绝对路径、不含 `..`、不重复 —— 别把 `schema.json` 写进去。
7. 用户已授权全量更新或入库时直接整合并适配消费者。授权仅讨论时提供诊断与可审阅方案。不要重复请求已给出的授权。
8. 搜索提示词中重复的固定数量、固定尺寸、对称方式或风格套餐；实现代码只应保留字段、宿主、编译及已批准槽位约束。
9. 执行静态检查、真实分片预览和与改动相关的检索/代码回归。失败时继续修正可处理部分；系统环境阻断须如实报告，不把静态检查当作运行验证。

## 设计契约与执行映射

从建筑长文、规范或模型回答中提取的声明，入库前必须生成声明清单。每条声明至少记录 `claim_id`、分类、`applies_when`、来源状态、目标字段 JSON Pointer、执行位置与自由变量。

**「强制强度」与「v2 目录」的对应关系**（两套轴不是同一件事，落位时按下表换算）：

| 强制强度 | v2 目录 | 判定 |
|---|---|---|
| `engine_hard` | `rules/implementation/` | 无前提就成立的参数与引用关系，Schema/compiler/validator 至少一处执行 |
| `conditional` | `rules/conditional/` | 必须声明 `applies_when` 触发条件；未选中该系统则不生效 |
| `preference` | `knowledge/components/` 或 `rules/design-choice/` | 只影响候选评分，不能锁字段或成为交付门禁 |
| `reference` | 不进活动库（扫描目录之外） | 百科、案例、风格；无消费者 |
| `unsupported` | `docs-dev/knowledge-backlog/` | 能力缺口，禁止伪编译 |

- `engine_hard` 必须落在 Schema、compiler 或 validator 中；只有提示词说明的不算已执行。
- `conditional` 必须声明触发条件。系统未被本次方案或用户请求选择时，不进入活动约束；建筑类别和风格不能替代该选择。
- `preference` 只能影响候选评分，不能锁定目标字段或成为交付门禁。
- `reference` 与 `unsupported` 不进入生成上下文；保留在隔离资料或 backlog 文档中。
- 新增或变更目标字段属于代码契约变更，必须同时更新 Pydantic 类型、`schema.json`、前端 TypeScript 类型、版本迁移和回归；Skill 不得只写 Markdown 后宣称生效。
- 自由变量必须显式列出，说明规则没有决定哪些造型参数，以免共享系统知识演变成固定模板。

## 验证命令

```powershell
# 真实分片预览（必跑）：确认标题层级、元数据合并结果、分片没有空壳或断裂
wild-server/.venv/Scripts/python.exe -X utf8 .codex/skills/wild-knowledge-ingest/scripts/preview_wild_rag_chunks.py wild-server/storage/knowledge_base --json
# 检索契约回归（必跑）：5 组硬编码过滤对是否仍有命中（改 metadata 后必跑，否则查询可能直接查空）
wild-server/.venv/Scripts/python.exe -X utf8 ../.workbuddy/diag/check_kb.py
# 语义检查（必跑，它其实是门禁 —— 见下）
wild-server/.venv/Scripts/python.exe -X utf8 wild-server/scripts/rag/lint_wild_rag_docs.py wild-server/storage/knowledge_base
# 真·门禁（CI 会跑）：manifest 完整性 + 语病/围栏/metadata 全绿
wild-server/.venv/Scripts/python.exe -m pytest wild-server/tests/rag/test_knowledge_rules_v3.py -q
# 端到端检索冒烟（临时索引，不碰线上 Chroma，不调远程模型）
wild-server/.venv/Scripts/python.exe wild-server/scripts/rag/smoke_test.py
```

关于 `lint_wild_rag_docs.py` 的**准确定位**（既不要高估也不要低估）：

- 它既是 `scripts/rag/` 下的手动工具，也**确实被当门禁跑**：
  `tests/rag/test_knowledge_rules_v3.py::test_all_active_documents_pass_semantic_linter` 断言它在本库上
  **零 `error`**，而 `Jenkinsfile`（`uv run … pytest tests -q`）会跑这个测试文件。
  因此**本库里它报的 `error` 必须清干净**，否则 CI 直接红。
  （`warning` 不影响：`redundant_path_metadata` / `short_section` / `empty_container_heading` 属内容优化 backlog。）
- 🔴 **`source` 不再是必需键**（`REQUIRED_METADATA` 已移除）。它不在
  `MarkdownChunker._DOCUMENT_METADATA_FIELDS` 白名单里，Loader 根本不读它，对召回零影响；
  前后端分部署后前端路径也失去意义。人工溯源改用 `authority` + `knowledge_revision`。
  **不要为了让脚本变绿把 `source: wild-web/...` 加回文档。**
- 🔴 **代码围栏的两种语言是有分工的**（`lint_wild_rag_docs.py:499` 只严格校验 ` ```json `）：
  - ` ```json ` —— 可被代码解析、或模型能直接照抄的**最小示例**，必须**严格合法 JSON**（不能有 `//` 注释、`...`、尾逗号）。
    `app/agent/generation/architecture/recipes.py` 会用正则抓 ` ```json ` 块，改错语言会让配方失效。
  - ` ```jsonc ` —— 带 `//` 注释或 `...` 省略号的**教学示意/反例**（如"❌ 这样写会……"），不参与严格校验。
  把反例里的注释删掉会丢教学语义；把反例留在 ` ```json ` 里又会让模型误以为 WILD 接受注释。
  加新的 ` ```json ` 块前先自问：**这块能让模型整段复制吗？** 不能就用 ` ```jsonc `。
- 它报的其余问题（章节结构、导航句、跨文档声明）同样按真实问题处理。

索引由 Loader 同步，不手写 Chroma。内容和 metadata 更新后必须确认同步；`rules-v3` 过滤会阻止旧版本向量
继续进入生成。不要宣称"添加 metadata 即生效"，必须核查查询过滤与实际索引。
另外注意 **README 若落在被扫描目录内，自己也会被切块入库**并挤占 `top_k`；导航型文档靠
`config.yaml` 派生的 `knowledge_role: navigation` 才被排除在生成之外。

## 交付

说明活动知识变动、来源处置、消费者适配、检查结果和未验证项。文档被拆分或移动时同步更新检索评测答案，按所需事实与不应召回内容检查，不能只追求旧文件命中率。生成质量同时看约束满足、几何有效性和有效结果间的形态差异。
