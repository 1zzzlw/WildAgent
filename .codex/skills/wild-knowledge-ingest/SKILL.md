---
name: wild-knowledge-ingest
description: 审查并扩充 WildAgent 的 WILD 能力与条件组装关系；隔离建筑百科、整栋案例、风格策略及无依据参数，并验证真实分片和检索用途。
---

# WildAgent 规则知识维护

## 目标与当前设计

知识库帮助模型把本次设计正确表达成 WILD。用户需求与已批准方案决定造型；知识不能把建筑百科、类型样例、风格偏好或默认配色提升为生成要求。当前知识版本为 `rules-v3`，加载器默认仅召回 generation scope 下的 protocol、capability、relation。

三类活动内容固定为：Blueprint/ScenePatch 操作协议、当前已实现的复杂构件能力、具有代码执行点的跨构件关系。尚未实现的规则和组件进入 `docs-dev/knowledge-backlog/`，不得留在活动目录中等待 status 过滤。

## 读取入口

- 知识目录：`wild-server/storage/knowledge_base/`，公共 metadata 在 `config.yaml`；活动目录只包含协议、构件能力和组装关系。
- 能力依据：`wild-web/wild-lang/schema.json`、`wild-web/src/wild-core/types.ts`、primitive 注册表与 resolver、组件编译器。
- 分类路由依据：`app/agent/architecture_plan.py` 中的有限执行 profile；它不是 RAG 建筑百科。
- 生成协议：`BLUEPRINT-SPEC-MINIMAL.md` 固定注入；完整字段说明在 `BLUEPRINT-SPEC-FULL.md`。
- 消费代码：`app/spec/loader.py`、`app/spec/query_planner.py`、`app/agent/knowledge_policy.py`、`app/agent/component_registry.py`、各生成节点、`app/agent/facade_recipe.py`，路径均相对 wild-server。

按任务读取引用：分类读 [classification-taxonomy.md](references/classification-taxonomy.md)；重写读 [document-templates.md](references/document-templates.md)；metadata 读 [metadata-schema.md](references/metadata-schema.md)；分片读 [chunk-contract.md](references/chunk-contract.md)；资料转换读 [source-fidelity-and-composition.md](references/source-fidelity-and-composition.md)；设计契约映射读 [design-contract-mapping.md](references/design-contract-mapping.md)；交付读 [rag-readiness-checklist.md](references/rag-readiness-checklist.md)。

## 内容取舍

1. 保留项目特有语法、坐标、引用、能力边界和构件间条件关系。
2. 普通常识不为完整性重复入库；只有能解决具体遗漏、歧义或项目映射问题时才保留。
3. 建筑类型卡、用途百科和风格说明不进入活动知识库。只有项目无法从模型与用户需求稳定得到、并能落到执行字段的条件规则才可进入 recipe/component。
4. 通用规则描述“选用某系统后必须保持的关系”；不要把“现代住宅优先退台”等偏好写成硬规则。
5. 数字须区分 Schema 范围、实际引擎行为、运行配置、领域参考和局部示例。不能把定值机械改成范围或比例当作自由设计；也不能删除引擎真实限制。
6. 局部 JSON 可保留解释字段，但不能携带完整建筑布局。整栋案例、设计策略和失败回退保存在扫描目录之外；只有出现明确消费者和受控检索入口后，才能建立单独的 reference 索引。
7. 先检查代码是否直接解析文档内容。例如幕墙参数 JSON 由 facade_recipe.py 使用，不能作为“普通例子”删掉；运行配置与模型参考必须分开标注。

## 执行流程

1. 检查 Git 状态，读取现有同主题知识及实际消费者。保留用户文件和无关改动。
2. 建立来源声明清单：来源位置、声明、证据、处置与目标。原始建筑语义与 WILD 实现分别判定；错误字段不导致有效空间关系一并丢失。
3. 依据源码核验能力；用户明确设计要求可覆盖旧模板偏好，但不改变引擎事实。无法验证的能力移入 `docs-dev/knowledge-backlog/`，不伪装成 supported/engine，也不把 proposed 分片留在活动库。
4. 将共享字段放 component/protocol，共享关系放 recipe；策略、案例和建筑语义资料放到扫描目录之外。不为每种建筑复制相同门窗规则。
5. 每个实体使用真实 Markdown 标题，说明适用条件、WILD 映射、能力边界和自由变量。复杂构件只保留单个构件及必要宿主的最小 JSON；专业系统语义不能只保留名称，必须解释项目如何表达。
6. 配置 knowledge_role、applies_to 和来源。applies_to 只包含能显式选择专用系统或构件变体的术语，不能写建筑用途、风格、“生成、建筑、wall”等泛词。
7. 用户已授权全量更新或入库时直接整合并适配消费者。授权仅讨论时提供诊断与可审阅方案。不要重复请求已给出的授权。
8. 搜索组件注册表和提示词中重复的固定数量、固定尺寸、对称方式或风格套餐；实现代码只应保留字段、宿主、编译及已批准槽位约束。
9. 执行静态检查、真实分片预览和与改动相关的检索/代码回归。失败时继续修正可处理部分；系统环境阻断须如实报告，不把静态检查当作运行验证。

## 设计契约与执行映射

从建筑长文、规范或模型回答中提取的声明，入库前必须生成声明清单。每条声明至少记录 `claim_id`、分类、`applies_when`、来源状态、DesignDocument JSON Pointer、执行位置与自由变量。

- `engine_hard` 必须落在 Schema、compiler 或 validator 中；只有提示词说明的不算已执行。
- `conditional` 必须声明触发条件。系统未被本次 DesignDocument 或用户请求选择时，不进入活动约束；建筑类别和风格不能替代该选择。
- `preference` 只能影响候选评分，不能锁定 DesignDocument 字段或成为交付门禁。
- `reference` 与 `unsupported` 不进入生成上下文；保留在隔离资料或 proposed 文档中。
- 新增或变更 DesignDocument 字段属于代码契约变更，必须同时更新 Pydantic Schema、前端类型、版本迁移和回归；Skill 不得只写 Markdown 后宣称生效。
- 自由变量必须显式列出，说明规则没有决定哪些造型参数，以免共享系统知识演变成固定模板。

## 验证命令

```powershell
wild-server/.venv/Scripts/python.exe -X utf8 wild-server/scripts/rag/lint_wild_rag_docs.py wild-server/storage/knowledge_base --cross-check
wild-server/.venv/Scripts/python.exe -X utf8 .codex/skills/wild-knowledge-ingest/scripts/preview_wild_rag_chunks.py wild-server/storage/knowledge_base --json
```

索引由 Loader 同步，不手写 Chroma。内容和 metadata 更新后必须确认同步；rules-v3 过滤会阻止旧版本向量继续进入生成。不要宣称“添加 metadata 即生效”，必须核查查询过滤与实际索引。

## 交付

说明活动知识变动、来源处置、消费者适配、检查结果和未验证项。文档被拆分或移动时同步更新检索评测答案，按所需事实与不应召回内容检查，不能只追求旧文件命中率。生成质量同时看约束满足、几何有效性和有效结果间的形态差异。
