---
entity_name: knowledge_base_readme
status: supported
authority: maintainer
primary_terms:
  - WILD 知识库
  - 知识库维护
  - 知识库分类
synonyms: []
---

# WILD 知识库 — 开发者手册

> 这份文档的作用：**让维护者快速读懂当前知识库的架构，知道新内容该放哪、改完怎么验证。**
> 它本身是 `knowledge_role: navigation`，不会被召回进生成上下文——它只给人看。

**三分钟上手路径**：§1 架构 → §2 索引 → §4 新增流程 → §6 验证。
只想改一条内容的话，直接看 §4 的决策表 + §6 的命令。

---

## 1. 架构：两个轴，一次二分

### 第一层怎么分——一句话判据

> **这条内容"违反了能不能被机器判定"？**
> 能判定（Schema / compiler / resolver / validator 会拦下来）→ `rules/`
> 只是"不这样模型会写错" → `knowledge/`

| 目录 | 中文 | 装什么 |
|---|---|---|
| `knowledge/` | 知识内容 | 模型无法可靠推断的**事实**：字段名、枚举、坐标语义、构件参数、能力边界 |
| `rules/` | 规则性质 | 必须成立、且**可被代码执行**的**关系** |

### 第二层怎么分

| 目录 | 中文 | 装什么 | 例子 |
|---|---|---|---|
| `knowledge/protocol/` | 操作协议 | 顶层结构、字段、枚举、坐标系、引用格式 | `from` 是三元素数组；`meta` 七个字段 |
| `knowledge/components/` | 复杂构件表达 | 单个/组合构件的最小可用 JSON、可替换参数、能力边界 | 10 个组合构件的参数与限制 |
| `rules/implementation/` | 实现约束 | **无前提**的参数与引用关系 | 窗必须引用有效墙宿主 |
| `rules/conditional/` | 条件约束 | **有前提**的跨构件触发：选了 A 就必须落实 B | 选了多层交通 ⇒ 落实楼层连接 |
| `rules/design-choice/` | 设计选择 | 明确留给模型的**自由变量**（边界声明，不是约束） | 是否用阳台、退台 |

**两个容易搞错的点**

1. **"确定性关系"不是第三个分支**——它就是 `rules/` 这一支。
   判断方式是问"去掉前提这句还成立吗"：成立 → `implementation/`；不成立 → `conditional/`。
2. **`design-choice/` 严格说不是约束**，它是"这里不约束"的声明。
   它存在的价值是防止模型把设计自由度误当成硬规则（比如"别墅资料里有阳台"≠ 本次要有阳台）。

---

## 2. 索引（英文名 ↔ 中文）

| 路径 | 中文 | 内容 | 检索角色 |
|---|---|---|---|
| `README.md` | 开发者手册 | 本文件 | navigation（不召回） |
| `config.yaml` | 配置 | 路径级 metadata 规则 + 分类法说明 | — |
| `schema.json` | 校验模式 | JSON Schema，前端 `schema-validator.ts` 直接 import | 事实源（非 md，不入库） |
| `knowledge/protocol/blueprint-skeleton.md` | 蓝图骨架 | 顶层 7 字段、`meta` 7 字段、几何公共字段、材质与资产四字段分工 | protocol |
| `knowledge/protocol/templates-and-instances.md` | 模板与实例 | `templates` / `instances` / 模板 id 规则 / `materialOverride` | protocol |
| `knowledge/protocol/placements.md` | 布局放置 | `placements` 网格批量生成（铺瓦、砖缝、地砖） | protocol |
| `knowledge/protocol/component-parameters.md` | 构件参数 | 11 类构件（wall…primitive）的完整参数表 | capability |
| `knowledge/protocol/material-parameters.md` | 材质参数 | 基础材质、五种效果层、嵌入式图像、PBR 纹理通道、资产清单 | protocol |
| `knowledge/protocol/behavior-instructions.md` | 动态指令 | 作用范围、物理属性、动画控制参数、交互脚本指令集 | protocol |
| `knowledge/protocol/scene-patch-protocol.md` | 增量修改协议 | 不重新生成整份蓝图，只输出增量 operations | protocol |
| `knowledge/components/capability-boundaries.md` | 引擎能力边界 | 哪些构件/字段已实现、哪些没有、如何降级 | capability |
| `rules/implementation/door-window-depth.md` | 门窗深度约定 | `frameDepth` / `leafDepth` / `glassDepth` 与父墙厚度的交叠约束 | relation |
| `rules/implementation/assembly-relations.md` | 构件组装关系 | 引用顺序、墙体与开口、墙挂组件、墙角闭合、柱梁吸附、楼板补全 | relation |
| `rules/implementation/validation-rules.md` | 运行时校验 | 必填字段、ID 唯一性、引用完整性、数值边界、几何约束 | relation |
| `rules/conditional/pending.md` | 条件约束 | 目录占位，条目待定 | relation |
| `rules/design-choice/free-variables.md` | 设计选择 | 哪些不构成约束 + 两条禁止（不得照搬资料补构件） | capability |

---

## 3. 检索怎么用这份知识库

检索侧有 **5 组硬编码过滤对**，是固定入口。改 `doc_type` / `knowledge_role` 会让对应查询**直接查空**。

| 查询 | 过滤条件 | 覆盖目录 |
|---|---|---|
| 知识查询 · 协议 | `doc_type=blueprint_spec` + `knowledge_role=protocol` | `knowledge/protocol/` |
| 知识查询 · 能力 | `doc_type=component` + `knowledge_role=capability` | `knowledge/components/`、`rules/design-choice/` |
| 规则查询 | `doc_type=recipe` + `knowledge_role=relation` | `rules/implementation/`、`rules/conditional/` |
| 点名校验（组装） | `doc_type=recipe` + `entity_name=supported_assembly_relations` | `rules/implementation/assembly-relations.md` |
| 点名校验（参数） | `doc_type=component` + `topic=parameters` | `knowledge/protocol/component-parameters.md` |

代码位置：`app/agent/knowledge/policy.py:61-69`、`app/agent/planning/workflow.py:60-65`、
`app/services/agent_service.py:1185-1193`。

**目录名和文件名都不进向量**——进向量的只有 `> 知识路径：<祖先标题 > 当前标题>` + 正文。
真正让"目录=分类"生效的是 `config.yaml` 的 `mapping_rules`（`path_pattern` → metadata），
合并顺序是 `defaults` → 命中的 `mapping_rules`（后者覆盖前者）→ 文件 frontmatter（最高优先级）。

---

## 4. 新增内容放哪——决策流程

**走三步**：

1. 违约能被机器判定吗？不能 → `knowledge/`；能 → `rules/`
2. `knowledge/` 内部：讲"字段/结构怎么写" → `protocol/`；讲"某个构件是什么样、能不能做" → `components/`
3. `rules/` 内部：有"如果选了 X"这个前提吗？没有 → `implementation/`；有 → `conditional/`；
   是"这里明确不约束" → `design-choice/`

**例子**：

| 想加的内容 | 判定 | 落点 |
|---|---|---|
| 新增材质效果层 `woodgrain` 的字段表 | 字段怎么写 | `knowledge/protocol/material-parameters.md` |
| 屋顶新增支持 `mansard` 样式 | 能力边界 | `knowledge/components/capability-boundaries.md` |
| 阳台必须贴外墙且不得跨层 | 有前提（选了阳台） | `rules/conditional/` |
| 檐口必须沿屋面边界环扫掠 | 无前提的参数关系 | `rules/implementation/` |
| "现代建筑通常简洁"这类风格套话 | 不属两类 | **不要进库**（见 `config.yaml` 的 `excluded_content`） |

**放新文件还是放进已有文件？**
优先放进已有文件的对应 `###` 小节；只有当新内容**不与现有任何小节共享召回意图**时才新建文件。
新建文件后必须做两件事：加 frontmatter，并在 `config.yaml` 的 `required_documents` 里登记。

---

## 5. 改内容时的硬约束

### 元数据模板

每个参与检索的 md 必须在首行开始写 frontmatter：

```yaml
---
doc_type: component            # 与 §3 的过滤对强绑定
knowledge_role: capability     # protocol | capability | relation | navigation
doc_scope: generation          # generation | system | index
knowledge_layer: wild_schema   # wild_schema | constraint | navigation
entity_type: component         # 实体种类，用于点名校验
entity_name: component_parameters
topic: parameters              # 与 entity_name 一样可被硬过滤，取值要对上
wild_version: "1.1"
status: supported              # supported | experimental | proposed | deprecated
authority: maintainer          # schema | engine | verified | maintainer | domain | imported | inferred
primary_terms:
  - 检索词
  - search term
synonyms: []
---
```

**六条纪律**

1. **只用白名单键**（`MarkdownChunker._DOCUMENT_METADATA_FIELDS`，共 15 个）。
   写了白名单外的键不会被消费。
2. **`status` / `authority` 必须用上面列出的合法值**——它们参与成熟度惩罚
   （`loader.py:181`），取值不在表内会按**未知值加罚**，把片段排到后面去。
3. **不写 `source`**：前后端分离部署后前端路径无意义，而且它不在白名单里，
   写了只留一个无用的 `declared_source` 痕迹。
4. **路径级默认值写在 `config.yaml` 的 `mapping_rules`**，按书写顺序后者覆盖前者；
   单篇要覆盖时才写 frontmatter。
5. **需要按小节单独检索时**，在标题下方加 `<!-- rag-meta ... -->` 注释块
   （**不经 YAML 解析**，被 Loader 剥离并按标题路径绑定，子节继承父节、更深的覆盖更浅的）：

   ```markdown
   <!-- rag-meta
   entity_type: canopy
   entity_name: wall_canopy_component
   primary_terms:
     - 雨棚
     - canopy
   -->
   ```

6. **frontmatter 用的是 flat `key: value` + `- ` 列表语法，不是通用 YAML**。
   嵌套映射（比如 `metadata: {a: b}`）解析不了，别写。

### 写作红线

| 不要 | 因为 |
|---|---|
| 写"参见 X.md / 详见 X.md"这类**导航指向** | 两个文档都在库里时检索自己会找到，写它只浪费上下文 |
| 正文里出现其他**文件名** | 检索器不解析正文里的文件名，只会抬高这一片的相似度、**挤掉真正有内容的片** |
| 少写 `##` / `###` 标题 | Loader 按标题切块；少一个标题，整段就塌成一个大分块 |
| 不闭合 ```` ``` ```` 代码围栏 | 后续内容全被吞进代码块，渲染和分块一起坏 |
| 在 ` ```json ` 里写 `//` 注释、`...` 省略号或尾逗号 | 它是"模型可直接照抄"的严格 JSON 示例；带注释/省略号的示意与反例要用 ` ```jsonc `（`lint_wild_rag_docs.py` 只严格校验 ` ```json `，而 `app/agent/generation/architecture/recipes.py` 会用正则抓 ` ```json ` 块，选错语言轻则 CI 红、重则配方失效） |
| 把完整案例/风格套话写进来 | 见 `config.yaml` 的 `excluded_content` |
| 把"暂时没用但以后可能扩展"的内容删掉 | 库可以留，留给内容评审决定 |

**分工声明保留**（和导航指向区分开）："本节只给概要，完整定义在别处"这类句子有**防误用**价值，要留。

---

## 6. 改完怎么验证

```bash
cd wild-server
# ① 结构 + 检索契约（退出码即结果，0 = 全绿）
./.venv/Scripts/python.exe ../.workbuddy/diag/check_kb.py
# ② 语义 linter —— 它其实是门禁：tests/rag/test_knowledge_rules_v3.py 断言本库零 error
./.venv/Scripts/python.exe -m pytest tests/rag/test_knowledge_rules_v3.py -q
# ③ 端到端检索冒烟（临时索引，不碰线上 Chroma，不调远程模型）
./.venv/Scripts/python.exe scripts/rag/smoke_test.py
```

`check_kb.py` 用**真实的 `MarkdownChunker`**（不是自写解析）检查 6 件事：

1. 5 组硬编码过滤对**各自至少命中 1 个文件**（命中 0 说明 metadata 被改坏了）
2. frontmatter 与 Loader 的真实解析器 `_parse_metadata_lines` **逐键一致**
3. 每个文件都有 **H1**（否则分片的"知识路径"会退化成文件名）
4. **代码围栏配对**
5. 没有**残留导航句**（"参见/详见 X.md"）
6. `required_documents` **双向同步**（声明的都存在、存在的都声明）

新加文件后如果忘了登记，这条会直接报 `未登记进 required_documents: [...]`。

**改完顺手扫一眼**：`config.yaml` 的 `mapping_rules` 是否覆盖了新目录；
新文件的 `doc_type` + `knowledge_role` 是否能被 §3 里对应的过滤对命中。

---

## 7. 待优化事项（内容取舍，逐条确认后再动）

这些是已知问题，**不是结构问题**，都属于"改内容"范畴：

| 位置 | 事项 |
|---|---|
| `material-parameters.md` | `## 四、标准光照模型` 与 `### 1.2 光照条件` 末段是同一规则的两次陈述 → 两片会抢同一条查询 |
| `material-parameters.md` | 第二章的 `grain` 段没有独立编号（原稿如此），排在章节导语之后 |
| 全部文档 | 尾部 `## 许可` 段落是纯样板（README 已声明 MIT） |
| `capability-boundaries.md` | 🔴 写着"❌ 多门扇（双开门）"，但引擎已实现 `doorStyle: "double"`（`wild-compiler/components/door.ts:30`）→ **过期声明** |
| `validation-rules.md` | 含大量 Python 伪代码，模型无法执行，只会当成"像规范"的错误信号模仿 |
| `placements.md` | 「展开规则」5 步是引擎内部实现，与 `config.yaml` 的 `excluded_content: engine_internals` 冲突 |
| `rules/conditional/` | 只有占位文件，条目待定（候选：楼板与屋顶自动补全、阳台宿主与通行） |
| `rules/design-choice/free-variables.md` | 内容由设计思路推导而来，需核对是否与实际生成行为一致 |
