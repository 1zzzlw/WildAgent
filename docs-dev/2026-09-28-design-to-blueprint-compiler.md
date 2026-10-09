# 设计图纸 → 蓝图：通用编译器重构（目标形态）

> 2026-09-28。本文描述**终局形态**，不是分期方案。三节是同一件事的三个面：
> 第 1 节定流程，第 2 节定编译器，第 3 节定图纸。三者互相约束，任何一节单独看都不完整。
> 基线：`wild-server/app/agent/graph.py:190-274`。

## 0. 目标一句话

**大模型只产出设计：先用 plan-and-execute 分块写出完备图纸，再由一份通用脚本把图纸全量、确定性地编译成蓝图。**

> ⚠️ **plan-and-execute 不删，换用途。** 见 1.6：条目的执行对象从「生成构件」改成「写图纸的某一块」。
> 被删的是"给构件生成排期"的那一半，不是这套机制。

推论（这是本重构的全部收益）：

|              | 现在                                                       | 目标                                                                     |
| ------------ | ---------------------------------------------------------- | ------------------------------------------------------------------------ |
| 大模型调用点 | architecture / material / plan / 每个 generate / replanner | 每个**设计块**一次（体量/立面/屋顶/构件/材质…）+ 材质 resolve + 缺陷回改 |
| 图纸精度     | 只到"数量配额"，形态靠模型补                               | 完备到能直接编译                                                         |
| 图纸可修     | 不可（批准后冻结）                                         | 可（收敛环内修订，带 revision）                                          |
| 编译         | 结构确定性（`skeleton`）+ 构件靠模型                       | 全量确定性（一个纯函数）                                                 |
| 失败模式     | 执行期分散（生成失败→重试→replanner）                      | 设计期集中（图纸不合格→修订）                                            |
| 耗时         | 构件逐个 LLM，单次 60~100s                                 | 编译是纯 CPU，毫秒级                                                     |

---

## 1. agent 流程（目标拓扑）

```
classifier
  ├─ chat   → END
  ├─ edit   → patch → END
  └─ generate
       ├─ target_kind=architecture → architecture ─┐
       └─ target_kind=object       → object_design ─┤
                                                    ↓
              ┌───────────  设计期 plan-and-execute（见 1.6）  ──────────┐
              │  条目 = 设计块；依赖表是常量（档位决定用哪几块）        │
              │  依赖序：体量 →（结构 | 立面 | 屋顶）→ 构件 → 材质       │
              │  逐块执行（LLM 写这一块）⇄ 逐块校验（未过带证据重出）    │
              │  块间不变量就地拦（如立面开间数 ↔ 体量宽）              │
              └───────────────────────┬─────────────────────────────────┘
                                      ↓ 图纸成稿（材质块即 material_plan）
                            ┌──────── design_convergence（LLM：产出 DesignPatch）
                            │                   ↓
                            │            compile(dry_run)（纯函数，出 defects）
                            │                   ↓
                            └─── defects 非空且预算未尽 ─┘
                                                ↓ defects 收敛
                                        design_review（interrupt，人工审最终图纸）
                                                ↓
                                        compile(final)（纯函数 → Blueprint）
                                                ↓
                                        final_validate → END
```

### 1.1 节点增删

| 节点                             | 处置                                                                 | 依据                                                                                                                                                                             |
| -------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `classifier` / `chat` / `patch`  | 不动                                                                 | —                                                                                                                                                                                |
| `architecture` / `object_design` | 不动（职责变重：不再一次出全图，改为**逐块写**，见 1.6）             | `nodes/architecture_node.py`、`object_design_node.py`                                                                                                                            |
| `material_plan`                  | 保留；被修订触发时重跑                                               | `design_material_refresh` 状态位已存在（`state.py:75`）                                                                                                                          |
| **`design_convergence`**         | **新增**：LLM 读 `defects` 产出 `DesignPatch`                        | 复用 `contracts.py:432 DesignPatch` + `repository.py:98 apply_patch`                                                                                                             |
| `design_review`                  | **位置调整**：从"骨架前"移到"收敛后"                                 | 现在 `graph.py:239-252`，问题见 1.3                                                                                                                                              |
| **`compile`**                    | **新增**：吸收 `skeleton`                                            | 纯函数，两种模式 dry_run / final                                                                                                                                                 |
| `skeleton`                       | **删除**（并入 compile）                                             | —                                                                                                                                                                                |
| `plan` / `execute` / `replanner` | **保留机制、换用途**（见 1.6）：条目从「构件生成任务」改成「设计块」 | `agent/plan/*` 的 `PlanDocument` / `PlanItem` / `store` / `refresh_statuses` / 对账 / 有界终止**原样复用**；`strategy.py` / `expand.py` / `handlers.py` / `replan.py` 换成设计版 |
| `final_validate`                 | 保留，瘦身：只跑校验器 + 出交付清单                                  | `nodes/validate_node.py`                                                                                                                                                         |
| `callback`（定向修复）           | **删除**                                                             | 模型白名单修复是"执行期补设计"，收敛环已覆盖                                                                                                                                     |

### 1.2 整包退场

- `app/agent/generation/component_workflow.py`（per-type LLM 生成 + 校验 —— 构件改由编译器产出）
- `app/agent/generation/assembly_workflow.py`（分片合并 —— 编译器一次出全量蓝图，没有分片）
- `app/agent/generation/skeleton_workflow.py`（骨架节点入口 —— 并入 compile）

**`app/agent/plan/` 不退场**，改用途（1.6）：`contracts` / `store` / `refresh_statuses` / 对账 / 有界终止
原样复用，`strategy` / `expand` / `handlers` / `replan` 换成设计版。

`state.py` 里 `plan` / `plan_events` / `current_item_id` / `tool_trace` 四个字段**保留**，语义从
"构件生成进度"变为"设计分块进度"；另加 `compile_diag`。

### 1.3 为什么 `design_review` 必须往后挪

现状：`design_review`(interrupt) 在 `skeleton` **之前**（`graph.py:239-252`），而 `skeleton` 是全链**唯一的确定性可行性校验**，且**不过就硬失败**（`skeleton_workflow.py:334-339` → `_after_skeleton` 见 `error` 直接 END，`graph.py:121-122`）。

⇒ 人工刚批准的设计，可以被编译器一票否决，**且没有修订通道**。冻结点落在了唯一的校验器前面，这是"设计层与执行层不对称"的根因。

目标：冻结点落在**编译可行性验证之后**。因为 compile 是毫秒级纯函数，收敛环可以先把图纸跑到能编译，再把最终版交给人工——审核价值更高、打断更少。

### 1.4 收敛环的终止

复用现在那套有界思想（`plan/replan.py` 的五重终止就是这个模式），换成：

- 迭代上限（图纸修订次数）
- **缺陷指纹不下降**连续 N 轮 → 停
- LLM 预算耗尽 → 停
- 收敛（`defects` 里不含设计级缺陷）→ 出环

**红线不变**：能力缺失只标记不阻断。编译遇到未实现的构件类型 → 进 `unsupported` 清单 + warn，**不算 defect、不修订、不失败**。

### 1.5 RAG 换位置（不消失）

`component_workflow.py:124-155` 现在在执行期为每个构件检索知识。目标：**同样的知识改在设计期检索**——喂给 `architecture`（能力边界、可写形态枚举）与 `design_convergence`（该类的设计惯例）。

因此 `generation/components.py:64+ _COMPONENT_RULES` 与知识库 `component/entity_type=*` 文档**内容不变、消费方改变**，并且本来就该按 `components.py:47-60` 的既定方向下沉进知识库。

### 1.6 设计期 plan-and-execute（为什么 plan 不删、以及它该长什么样）

**为什么不删**：一次让模型吐全图，模型要在同一个上下文里同时维持体量、立面、构件、材质四层的一致
性——越往后越容易和前文冲突。**分块写、逐块落定、后块只引用前块**，是对"图纸变厚"唯一的可行解法。
所以 plan-and-execute 要从"给构件排期"改成"给设计分块"。

**条目 = 设计块**，依赖表**是常量**（写在代码里，像 `plan/expand.py:46 DETAIL_BUDGET` 那样），
**不由 LLM 产出**——因为"先体量后立面"是物理约束，不是决策；让模型产出它只是白烧一次调用。

| 块                | 写进图纸哪里                               | 依赖                                 | 可并发                    |
| ----------------- | ------------------------------------------ | ------------------------------------ | ------------------------- |
| `massing` 体量    | `massing` + `volumes` + `complexity`       | —                                    | —                         |
| `structure` 结构  | `structural_grid` + `circulation`          | massing                              | 与立面/屋顶并发           |
| `facade` 立面     | `facades`（bays + 带形态的开口）           | massing                              | 与结构/屋顶并发           |
| `roof` 屋顶       | `roof`                                     | massing                              | 与结构/立面并发           |
| `components` 构件 | `components` 实例清单                      | 上面全部                             | —                         |
| `material` 材质   | `materials`（= 现有 `material_plan` 节点） | components（`material_role` 要存在） | —                         |
| `objects` 开放集  | `objects`                                  | —                                    | 物件场景下与 massing 互斥 |

**档位决定用哪几块**：`minimal` 只用 massing + facade；`standard` 全用；`detailed` 追加细节块。
这正好复用现有 `DETAIL_BUDGET` 的单调递增语义。

**执行循环**（直接映射到既有机制）：

| 现在（`agent/plan/*`）                                         | 目标                                                                        |
| -------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `PlanItem` 条目                                                | 设计块                                                                      |
| `strategy.py::request_plan_strategy`（LLM 定策略：做哪些构件） | **删除这次调用**——依赖表是常量；`capability_catalog()` 保留，改喂设计提示词 |
| `expand.py::expand_plan`（按 quota 展开）                      | 按档位 + 常量依赖表展开块                                                   |
| `handlers.py::run_generate`（LLM 生成构件）                    | `run_design_block`（LLM 写这一块）                                          |
| `handlers.py::run_merge`（分片合并）                           | `commit_block`（把这一块写进 DesignDocument 草稿）                          |
| `store.py` / `refresh_statuses` / 对账                         | **原样复用**：依赖落定、状态推进、可执行判定                                |
| `replan.py` 五动作闭集                                         | 换成设计动作：**重出某一逻辑块** / 补块 / 标 unsupported / 收尾             |
| 有界终止（迭代上限 / 无进展 / 预算 / 队列空）                  | **原样复用**                                                                |
| `parallel_group`（`handlers.py:84-106`）                       | 原样复用：结构 / 立面 / 屋顶 三块并发                                       |

**这比"一次出全图"精细在哪**（逐条）：

1. **引用不悬空**：第 5 块（构件）生成时，前四块已定稿，`host` 是确定的——模型只需引用，不必编造。
   悬空引用正是现在执行期最典型的失败（`canopy` 找不到门、`window` 找不到墙）。
2. **重试粒度到块**：某块不过，只重出那一块，不重出整份图纸。
3. **可观测**：`defects` 带 `design_field` → 能直接映射回"是哪一块的哪一项"。
4. **短输出**：每块都短，长输出可靠性下降的问题被切碎。

**它与 `design_convergence` 是同一个机制的两半**：

- **首次成图**：逐块写（本节的 plan-and-execute）
- **缺陷回改**：编译出 `defects` → 按 `design_field` 找到受影响的块 → **只重出那几块** → 再编译

⇒ 两半共用一个"块"的定义和一套有界终止。`design_convergence` 不是新发明，它就是这套循环在"编译反馈"下的第二次进入。

**必须付的代价**：块之间的一致性需要额外机制——`facades` 的开间数必须与 `massing.width` 匹配、
`components[].host` 必须已提交、`material_role` 必须已解析。这些是**块间不变量**，在 `commit_block`
时就地拦下（不是等编译）。这是分块唯一的真实成本，也是它必须配一套不变量表的原因。

> **落地状态（2026-09-28 晚）**：上面这张"执行循环"映射表的前三行与最后两行已实现，见 **§5.14**。
> 未落地的是 `material` / `objects` 两个块（`DESIGN_BLOCKS` 目前只有 5 块）与 `replan` 五动作的设计版映射。

---

## 2. 编译器脚本

### 2.1 关键前提：这一步只填参数，不算几何

蓝图元素是**参数记录**，几何由引擎（TypeScript 侧）生成。所以编译器只需要知道**每类构件要哪些字段、每个字段填什么值**——而字段契约**已经存在**：

| 数据源          | 内容                                                                                 | 位置                                                           |
| --------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| schema 字段契约 | 每类有哪些字段、必填、枚举取值                                                       | `wild-core/schema.json` ↔ `storage/knowledge_base/schema.json` |
| 构件元数据表    | `component_type` / `entity_type` / `required_fields` / `is_element` / `dependencies` | `generation/components.py::ComponentConfig` + 15 行注册        |
| 字段来源规则    | 每个字段的值从哪来                                                                   | **新增**（见 2.3）                                             |

三张表里前两张现已存在，**但现在只喂给大模型看，没有任何代码拿它们生成元素**。编译器就是把这条缺的链路补上。

### 2.2 两层结构

```
compile_design(document, schema, registry) -> (blueprint, defects)
    │
    ├─ A 层 派生（derivation）  图纸的抽象描述 → 实例清单
    │    · 结构：massing + volumes        → wall / floor / column / beam / stair
    │    · 开口：facades × bays           → opening slot（位置 + 尺寸）
    │    · 构件：document.components      → 每个实例的 host + 相对位置
    │    · 物件：document.objects         → furniture / primitive / body 实例
    │
    └─ B 层 实例化（instantiation）  实例 + schema → 完整元素   ← 全部通用，一个循环
```

**A 层是几何推导，必须有代码**，但它不是"15 个 per-type builder"，而是**一组通用算子 + 一张"用哪些算子"的数据表**：扫掠、阵列、周边、宿主定位、随宿主尺寸派生。这正对应既有红线「禁按 `roofType`/构件类型写专属分支加能力 → 抽成通用算子」。

**B 层完全通用**：读 schema 拿字段表，逐字段按来源规则取值，校验必填齐全，输出元素。

### 2.3 字段来源规则表（新增，是编译器的核心）

每个字段的来源只有这几类，**逐类一行数据，不是逐类一段代码**：

| 来源       | 含义                      | 例子                                               |
| ---------- | ------------------------- | -------------------------------------------------- |
| `derived`  | A 层算好的位置/尺寸       | 门的 `from[]` / `width` / `height`                 |
| `host`     | 从宿主反查                | `parentWall`、`frameDepth` = 父墙 `thickness`      |
| `material` | 按 `material_role` 取材质 | `frameMaterial` / `glassMaterial`                  |
| `form`     | 图纸里写的形态            | `interaction.mode`、`leafRows`、`verticalMullions` |
| `constant` | schema 默认值             | 省略即默认                                         |
| `enum`     | 需闭集校验的取值          | `roofType`                                         |

抽 `door` 验证（规则原文 `components.py:65-79`）：`from[]`/`width`/`height`/数量/宿主 → `derived`；`frameMaterial`/`glassMaterial` → `material`；`frameDepth`/`leafDepth` → `host`；只剩 `interaction.mode` 与 `leafRows` → `form`（且 `leafRows` 有默认值）。

⇒ **门这一类约八成字段是"抄/算"，只有一两个需要图纸给。** 屋顶更极端：`roofType` 图纸已给（`planning.py:629`），`span`/`depth`/`position` 由体量轮廓算 → 零判断。

### 2.4 接口与模式

```python
CompileDefect = {code, severity, target, evidence, design_field}   # design_field 指出该改图纸哪里

compile_design(document, *, mode) -> CompileResult
    mode       : "final" | "dry_run" | "probe"   # probe = 只回诊断、不回蓝图（设计期试算用，见 2.7）
    blueprint  : dict                 # mode=final 时才有
    defects    : list[CompileDefect]  # 图纸错了 → 必须改
    defaulted  : list[CompileDefault] # 图纸没说、用了默认值 → 档位决定要不要让模型补（见 2.6）
    unsupported: list[str]            # 能力缺失 → 只标记不阻断
```

- **纯函数**：无 IO、无 LLM、无全局状态。`build_deterministic_skeleton`（`architecture/skeleton.py:705`）已经是这个形态，直接吸收。
- `mode="dry_run"`：跑全部校验器，返回 `defects` + `defaulted`，供收敛环消费（不出蓝图）。
- `mode="probe"`：同上，供设计节点当 tool 试算（2.7）。
- `mode="final"`：输出蓝图，同时带上 `defects`（若仍非空说明图纸没修完）与 `unsupported`。

### 2.5 校验器并入编译器

现在校验散在三处：`skeleton` 的四道预检（`skeleton_workflow.py:269-418`）、`tools/spatial_tools.py` 的尺寸/引用校验、`final_validate` 的 `run_validation_pipeline`。

目标：**全部由 `compile_design(validate=True)` 统一产出 `defects`**。这样"能否编译"和"图纸是否合格"是同一个函数的两半，`final_validate` 退化为"再跑一次同样的校验 + 出交付清单"。

`defects` 必须**结构化且带 `design_field`**——它是收敛环的输入，也是人工审核的依据。现在的 `error` 是一句中文串（如 `f"骨架几何预检未通过: {dimension_validation}"`），模型看不懂要改哪。

### 2.6 编译输出是四类，不是一类（"全量映射不可能"要拆成两句话）

用户担心"复杂建筑下脚本全量映射出错率高"。这句话要拆：

> **全量映射成「合法蓝图」是可能的**（schema 规定每类构件的字段，缺的用默认值填就能产出合法元素，编译永远有结果）；
> **不可能的是「全量映射且每一处都好看」。** 差别是 **合法 vs 好**，不是 **能 vs 不能**。

所以问题不是"脚本能不能完成"，而是"**默认值够不够好**"。据此，编译器输出四类：

| 输出          | 含义                                                          | 谁处理                                                     |
| ------------- | ------------------------------------------------------------- | ---------------------------------------------------------- |
| `blueprint`   | 编译好的蓝图                                                  | ——                                                         |
| `defects`     | 图纸**错了**：引用悬空 / 尺寸越界 / 枚举越界 / 必填缺失       | 必须改图纸 → 修订                                          |
| `defaulted`   | 图纸**没说**，编译器按默认值填了（如 `leafRows`、`mullions`） | **档位决定**：低档接受默认；高档让模型把值补进图纸后重编译 |
| `unsupported` | 能力缺失（引擎做不到）                                        | 只标记不阻断（红线），进交付清单                           |
| `uncompiled`  | 编译器**暂无派生规则**（≠ 能力缺失，引擎是能做的）            | 走模型通道补；对应的"配额没满足"缺陷降级为 `warn`，不阻断  |

`defaulted` 这一栏就是"借助大模型力量"的**唯一合法入口**，而且天然有界——只有编译报出来的字段才有讨论余地，
模型不必（也不许）去改别的。

> **实现注记（2026-09-28）**：`defaulted` 的判据**不是**"schema 允许但产物没有"，而是注册表的
> `ComponentConfig.optional_fields`。前者实测 299 条、几乎全是 `floor.radius` / `wall.curve` /
> `stair.stepCount` 这类**引擎内部字段**，它们根本不存在"图纸表不表态"的问题，混进来只会淹掉
> 真正该问模型的那几条。后者只列"模型/设计可表态"的字段——墙/楼板/楼梯不在注册表里，
> 由确定性骨架完全拥有，一条 `defaulted` 都不产生。
>
> 同理 `uncompiled` 与 `unsupported` 必须分开：前者是"代码还没写规则"，后者是"引擎没这能力"。
> 两者的处置都是**不阻断**，但只有前者会随规则补齐而缩小。当前 `unsupported` **恒为空集**
> （注册表 15 类全部已实现）。

### 2.7 编译器同时是一个 tool——但调用方向要反过来

**接受**"把脚本做成 tool 给模型调用"；**不接受**"脚本完不成的地方模型自己补蓝图"。两条理由：

- 仓库已有明文规则：`plan/handlers.py:8` 的边界表写着 repair 是"模型出白名单动作、程序执行，**模型不许直接写蓝图**"。
  编译比 merge/validate 更靠底层，更不能让模型手写产物。
- 模型一旦能改蓝图，**蓝图就脱离图纸**：这个元素为什么长这样，事后无法追溯；同一份图纸两次编译结果不同，回归与门禁全部失效。

正确的方向是**把"模型补"发生的位置从蓝图侧移到图纸侧**：

| 调用方                                   | 用途                            | 拿到什么                                       | 性质         |
| ---------------------------------------- | ------------------------------- | ---------------------------------------------- | ------------ |
| pipeline 的 `compile` 节点               | **必经**，一票定终局            | `(blueprint, defects, defaulted, unsupported)` | 不可跳过     |
| 设计节点的 tool：`compile_design(draft)` | **试算**（"开间改成 5 会怎样"） | 只要 `defects` + `defaulted`，不要蓝图         | 可选、可多次 |

两个调用方是**同一个纯函数**。tool 版本只回诊断、不回蓝图，所以模型再怎么调也污染不了产物；
而"模型补的值"落进**图纸**（走 `DesignPatch` 新 revision），再由必经的编译产出蓝图。

⇒ 于是**链路始终是：图纸 →（编译器）→ 蓝图**，模型只在图纸侧活动。这既拿到了你要的"借助大模型力量"，
又同时保住了"图纸是唯一事实源"和"蓝图可复现"。

### 2.8 "复杂建筑出错率高"打的是图纸，不是编译器

|              | 编译器（纯函数）                       | 图纸生成（模型）                    |
| ------------ | -------------------------------------- | ----------------------------------- |
| 同样输入     | 永远同样输出                           | 每次可能不同                        |
| 错误性质     | 代码 bug                               | 设计不合（漏写/自相矛盾/引用悬空）  |
| 怎么修       | 写一条单测，一次修好永久修好           | 分块 + 逐块校验 + 块间不变量（1.6） |
| 复杂度的影响 | 只增加**分支数**（正是该补测试的地方） | 显著增加出错率                      |

⇒ 本重构的**根本收益其实就是这一条**：把最容易出错的那部分，从"模型手写、错了没人知道"的蓝图侧，
搬到"纯函数 + 可单测 + 错了必然报 defects"的编译器侧。复杂度越高，这个搬家的收益越大。

---

## 3. 设计图纸怎么设计

### 3.1 第一原则：图纸写语义，编译器算坐标

大模型最不可靠的行为就是写坐标——`MEMORY.md` 第二节整节都是 `from[]` 语义踩坑记录（墙底/墙顶、开口左边缘、法向偏移）。所以：

> **图纸里不出现世界坐标。** 实例用 `host` 引用宿主，位置用相对语义（"南立面第 2 开间"、"入口门上方"）；坐标由编译器算。

这一条同时解决三件事：模型输出更短、更不容易错、图纸可读可审。

### 3.2 图纸应有的分层

```
DesignRequirements    用户需求原文、建筑类型、profile、风格      （已有，不动）
DesignDecisions
  ├─ massing          体量：形状/宽/深/层数/层高/对称性          （已有，不动）
  ├─ volumes          体量分解                                   （已有，不动）
  ├─ complexity       档位与结构构件目标                          （已有，不动）
  ├─ structural_grid  结构体系与开间数                            （已有，不动）
  ├─ envelope         围护体系（实墙 / 幕墙）                      （已有，不动）
  ├─ facades          立面：开间数 + 每开间的开口（**要升级**，见 3.3）
  ├─ roof             屋顶：类型/朝向/挑出                        （已有，不动）
  ├─ circulation      竖向交通策略                                （已有，不动）
  ├─ components       构件实例清单（**新增**，见 3.4）
  ├─ objects          开放集物件                                 （已有，见 3.5）
  └─ materials        材质意图与解析结果                          （已有，不动）
```

现有类型定义在 `app/design/contracts.py`。

### 3.3 立面开口：从三值枚举升成"带形态的开口"

现状：`OpeningKind = Literal["door","window","empty"]`（`contracts.py:79`），`facades[face].ground_pattern / upper_pattern` 是它的列表。

⇒ 图纸只说了"这个开间是窗"，没说"什么窗"。于是 `interaction.mode`、`verticalMullions` 全靠模型猜——这是执行期最不稳定的一段。

目标：

```jsonc
"facades": {
  "front": {
    "bays": 4,
    "entrance_bay": 2,
    "ground_pattern": ["window:casement", "door:swing", "window:casement", "empty"],
    "upper_pattern":  ["window:sliding",  "window:sliding", "window:sliding", "window:sliding"]
  }
}
```

- 字符串简写 `"<kind>:<form>"`，`form` 是**闭集枚举**（门的 `swing/slide/lift`，窗的 `casement/sliding/fixed`…）；也允许展开成对象写更多参数（`mullions`、`sillRatio`）。
- 兼容旧值：不带冒号时按默认形态。
- 升级之后，门窗这一类的 `form` 字段全部来自图纸，编译器零判断。

### 3.4 构件：从"数量配额"升成"实例清单"

现状：`component_quota`（`contracts.py:105`）只给每类的 `min/max` 数量。**编译器拿到"3 个阳台"却不知道哪个、在哪、什么形态**，所以现在只能交给模型。旁边还有一堆散落字段：`balcony_access_count`、`balcony_width`、`detail_packages`。

目标：一个统一段取代它们。

```jsonc
"components": [
  { "type": "balcony",  "host": "volume_primary_L3_south", "size": {"width": 3.6, "depth": 1.4},
    "form": {"infillType": "glass", "railingHeight": 1.05}, "material_role": "accent" },
  { "type": "canopy",   "host": "door_front_02",          "size": {"depth": 1.2, "thickness": 0.15},
    "material_role": "roof" },
  { "type": "roof",     "host": "volume_primary",         "form": {"roofType": "gable", "ridge_axis": "x", "overhang": 0.55} }
]
```

规则：

| 字段            | 语义                                    | 谁算                     |
| --------------- | --------------------------------------- | ------------------------ |
| `type`          | 必须命中构件注册表且 `implemented`      | 图纸给，编译器校验       |
| `host`          | 宿主**语义 id**（体量 / 墙 / 门窗槽位） | 图纸给，编译器解析成坐标 |
| `size`          | 相对宿主的尺寸                          | 图纸给                   |
| `form`          | 形态参数，逐类闭集（来自 schema）       | 图纸给                   |
| `material_role` | 材质角色名（`contracts.py:162`）        | 图纸给，编译器据此取材质 |

**抽象与显式并存**：立面轴网（bays + pattern）作为**默认生成器**（"这个面 4 个开间都是窗"），`components` 用来**显式覆盖**个别槽位。抽象为主、显式为例外。

### 3.5 开放集物件：保持现状，代价照付

`furniture` / `primitive` / `body` 是**开放集**（用户点名"一个小人"、"一个花瓶"）——没有类型契约可查，几何必须由图纸直接给出。`ComponentObject`（`contracts.py:226`）已经这么设计了：`kind` + `subtype` + `parts`（局部坐标的零件表）+ `size` + `placement`。

要点：

- `furniture` 走 `subtype` 预设（引擎有原生 builder）→ 编译器零判断；
- `primitive` / `body` 的 `parts` / `params` 就是几何本身 → 编译器**原样搬运**，不解释；
- ⇒ 即使做到终局，**`objects` 这一段仍是模型产出的唯一"近似几何"入口**。这是开放集的固有代价，不是设计缺陷。

### 3.6 契约不变量要扩

`DesignDocument._architecture_semantics_are_valid`（`contracts.py:375-423`）现在校验体量覆盖、立面完整、开口数与配额一致。要扩：

- 每个 `components[i].host` 必须存在于本图纸（体量 / 墙 / 槽位）
- `components[i].size` 必须落在宿主范围内（如雨篷深度不超体量进深）
- `components[i].type` 必须在注册表且 `implemented`
- `components[i].material_role` 必须在 `materials` 里有对应解析结果
- 每条开口的 `form` 必须在该 `kind` 的形态闭集内

这些**现在有一部分只写在提示词里**（例如"雨棚必须有真实遮蔽对象"，`components.py:118-120`），只有模型读得到、校验器查不到 ⇒ 必须升级成契约不变量。

### 3.7 大模型友好 = 五条可执行的约束

1. **闭集枚举**，不用自由文本；
2. **引用而非复制**（实例引宿主 id，不重复写坐标）；
3. **省略即默认**（默认值来自 schema，模型不必写全）；
4. **分块字段**（体量 / 立面 / 构件 / 物件 / 材质），每块可独立校验、可独立恢复；
5. **每块有各自的不变量**，错了能指出是哪一块的哪一项。

第 4、5 条同时是"图纸变厚之后可靠性怎么办"的答案：**不靠一次写对，靠分块校验 + 收敛环修订**（第 1 节的 `design_convergence`）。图纸越厚，收敛环越重要——这是同一套设计的另一半。

---

## 4. 影响面与红线

### 4.1 必须同批改的地方

| 类别     | 具体                                                                                                                                   |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| 设计契约 | `app/design/contracts.py`（`OpeningKind`、新增 `ComponentInstance`、扩不变量）、前端类型、SVG 预览、`ResolvedDesign`                   |
| 编译器   | 新增 A/B 两层；吸收 `architecture/skeleton.py`、`architecture/facade.py`                                                               |
| 流程     | `graph.py` 节点与边；`state.py` 字段                                                                                                   |
| 知识库   | `_COMPONENT_RULES` + `component/entity_type=*` 文档的**消费方**从执行期改到设计期；改完 md 必须 `scripts/kb/resync_knowledge_index.py` |
| schema   | 若新增契约字段，**三处白名单**：`blueprint_parser.py::component_allowed`、`spatial_tools.py` 枚举白名单、`schema.json` 两副本          |
| 门禁     | `scripts/check-*.mjs` 硬编码期望值、`verify_wild_blueprint.py`、`tests/agent/*`                                                        |

### 4.2 红线（不得被本重构绕开）

-  **能力缺失只标记、不阻断**：编译遇到未实现能力 → `unsupported` + warn，不修订、不失败。
-  **禁按构件类型/`roofType` 写专属分支加能力** → 一律抽成通用算子（这正是 A 层算子表的依据）。
-  **唯一事实源**：图纸的唯一载体是 `DesignDocument`（带 revision/locks/rule_trace）；编译器**不产生设计**，只做映射。修订必须走 `apply_patch` 产生新 revision。
-  **KB 是"什么算合法"的第二实现**：改几何口径/必填/枚举 → 必须同批改知识库文档。
-  **生成链改动必须拿真模型跑**：`tests/agent/test_plan_chain_e2e.py` 把节点整替成桩件，节点内校验一行都不执行；须用 `.workbuddy/diag/probe_*_chain_live.py`。

### 4.3 已知的、必须承认的代价

- **模型通道删不掉**：`objects`（开放集）永久保留 LLM 产出。终局是"脚本接管大部分 + 模型保留一条窄道"，复杂度是加法。
- **失败从"分散"变"集中"**：细节全部前移到图纸，等于要求图纸一次写对更多字段。缓解手段在设计里（分块 + 不变量 + 收敛环），不在分期里。
- **图纸可读性下降**：实例清单会让文档变长。用"抽象轴网为主、显式实例为例外"压住膨胀。

---

## 5. 已落地（2026-09-28）

### 5.1 代码

| 文件                                                                     | 作用                                                                                                                                   |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `wild-server/app/agent/compiler/diagnostics.py`                          | 四类输出的数据契约：`CompileDefect` / `CompileDefault` / `CompileResult`（含 `.ok` / `.summary()`）+ 三档模式常量                      |
| `wild-server/app/agent/compiler/compile.py`                              | 编译器本体：`compile_design(plan, *, mode, user_message) -> CompileResult`；含附属构件派生（`_derive_attachments` / `_derive_lights`） |
| `wild-server/app/agent/nodes/compile_node.py`                            | graph 节点入口：编译 → 写 `skeleton_blueprint` / `design_brief` / `compile_report`                                                     |
| `wild-server/app/agent/nodes/design_review_node.py::route_design_review` | 建筑 → `compile`；物件 → `skeleton`（`_compiles_deterministically`）                                                                   |
| `wild-server/app/agent/plan/expand.py::_drop_produced`                   | 已产出的类型不再派 `generate`；**两条策略路径共用的唯一闸口**（见 §5.8）                                                               |
| `wild-server/app/agent/graph.py`                                         | 注册 `compile` 节点 + `design_review` 路由分支（与 `skeleton` 并列）                                                                   |
| `tests/compiler/test_compile_design.py`                                  | 编译器行为契约 47 条                                                                                                                   |
| `tests/compiler/test_compile_wiring.py`                                  | 接线契约 11 条                                                                                                                         |
| `wild-server/app/agent/generation/architecture/design_blocks.py`         | **设计块表**（常量依赖表 + 档位闭集 + 字段→块 / `design_field`→块 映射），§1.6 的唯一事实源                                            |
| `wild-server/app/agent/generation/architecture/design_workflow.py`       | **逐块起草执行器**：`draft_design_blocks` + 块契约 `check_block_contract`（首次成图与收敛环共用）                                      |
| `wild-server/app/agent/generation/architecture/convergence.py`           | **收敛环**：`converge_design`（缺陷 → 只重出受影响的块 → 再编译，有界终止），见 §5.7                                                   |
| `wild-server/app/agent/nodes/design_convergence_node.py`                 | 收敛环节点入口（薄适配层；实现留在领域层，受"节点入口 ≤100 行"契约约束）                                                               |
| `wild-server/app/agent/generation/architecture/probe_tool.py`            | **试算工具**（§2.7）：`probe_compile_design` / `probe_design_text` —— 只回诊断、不回蓝图，且在任何输入下都不抛异常                     |
| `wild-server/app/agent/compiler/pipeline_defects.py`                     | **交付流水线 → 编译期缺陷的唯一投影**（§2.5）：`pipeline_defect_messages`；在深拷贝上跑，只诊断不修复                                  |
| `tests/compiler/test_pipeline_defects.py`                                | §2.5 验收 5 条（编译缺陷 ≡ 流水线 error 行 / 不改入参 / schema 收口抓 ID 重复 / 产物零缺陷）                                           |
| `tests/agent/test_design_blocks.py`                                      | 块表与块契约 26 条                                                                                                                     |
| `tests/agent/test_design_probe_tool.py`                                  | 试算工具 14 条（全函数 / 只回诊断 / 可调用性 / 两条通道的接线）                                                                        |
| `tests/agent/test_design_convergence.py`                                 | 收敛环 25 条（有界终止 / 定向重出 / 不猜块 / 模型故障不阻断 / 真编译器接线）                                                           |
| `.workbuddy/diag/probe_deterministic_full_compile.py`                    | 零模型探针（退出码即结果，**直接调 `compile_design`，不复制组合逻辑**；`--dump` 可导出 `.wild` 喂真实引擎）                            |
| `.workbuddy/diag/probe_compile_path_plan.py`                             | 整路探针：`compile_node → expand_plan → run_validation_pipeline → merge_fragments`                                                     |
| `.workbuddy/diag/negative_check_compiler_attachments.py`                 | 负例验证：7 个 mutation 逐个注回，确认红点集合**恰好**等于对应用例                                                                     |

**实测覆盖范围**（探针 + 测试，零模型调用）：

| 类别                                | 能否确定性产出                                                                                   |
| ----------------------------------- | ------------------------------------------------------------------------------------------------ |
| 墙 / 楼板 / 楼梯                    | ✅ `build_deterministic_skeleton`                                                                 |
| 门 / 窗（含凸窗）                   | ✅ `conform_openings_to_slots`                                                                    |
| 入口雨篷                            | ✅ `conform_entrance_accessories` 吸附                                                            |
| 屋顶（单体积派生 / 多体量逐块拆分） | ✅ 本模块新增的 `_single_roof` + 既有 `conform_roofs_to_slots`                                    |
| 阳台 / 栏杆                         | ✅ `conform_balconies_to_slots` / `conform_railings_to_slots`                                     |
| 檐口                                | ✅ `_cornice_candidates`：沿檐边挂 `parentRoof` 局部路径（`flat`/`gable`/`hip`）                  |
| 烟囱                                | ✅ `_chimney_candidates`：落在屋脊最高处，基座贴屋面（`flat`/`gable`/`hip`）                      |
| 灯具                                | ✅ `_derive_lights`：每个外墙面一盏，入口墙那盏复用既有吸附                                       |
| 坡道                                | ❌ → `uncompiled`：**没有场地标高就没有可派生的高差**，硬造一个落差就是"产生设计"                 |
| 电梯 / 家具                         | ❌ → `uncompiled`：电梯要井道配套与 `vertical_strategy` 联动；家具缺的是**房间划分**（P2 未实现） |


### 5.2 接线：**没有开关**

> 2026-09-28 修订：原设计带一个 `WILD_DETERMINISTIC_COMPILE` 环境开关（默认关闭）。
> **已删除**——原因：回滚能力由 git 提供，多一个开关只多一条"线上跑的是哪条路"的不确定性，
> 而且会让每个用例都要在两种模式下各跑一遍。现在**建筑一律走编译**，没有第二态。

架构链：`design_review → compile → plan → execute ⇄ replanner → final_validate`。
编译器一次算完结构/门窗/屋顶/阳台/栏杆/雨篷/檐口/烟囱/灯具，`plan` 只对**产物里还没有**的
类型派发 `generate`。

**物件链不受影响**：编译器只认建筑的体量/立面/屋顶协议，
`app/design/resolver.py::is_object_plan` 命中即留在 `skeleton`。
这也是 `skeleton` 节点**仍然存活**的唯一理由。

### 5.3 还没做（明确记账）

- ✅ **收敛环已落地（2026-09-28）**：`compile_design(dry_run)` 的 **error 级、且能映射回设计块**的缺陷，
  已经会驱动"只重出受影响的块 → 合回图纸 → 再编译"，见 §5.7。
-  **`defaulted` 回灌图纸：前置未满足，现在做不了——它不是一个独立可做项**（2026-09-28 实测，见 §5.12）。
  `defaulted` 不是 error 缺陷（没有 severity），进不了收敛环；§2.6 说的"高档位让模型把值补进图纸"
  要先把 `defaulted` 提升成一种**可修订项**。但**图纸层目前没有任何承接这些字段的通道**——
  实测 65 条 `defaulted` **全部**落在注册表 `optional_fields`（`window.frameDepth/frameWidth/glassDepth`、
  `door.doorStyle/frameDepth/leafDepth/leafRows/openingStyle`），而图纸协议里与构件有关的通道
  只有 `component_quota: {type:{min,max,note}}`（**计数**，不是实例参数）、立面槽位是 `list[str]`。
  ⇒ 回灌的前置 = **§3.3（开口升成 `"<kind>:<form>"`）+ §3.4（构件升成实例清单）**。
  **它是 §3 的产物，不是 §2.6 的一个尾项。**
- ✅ **`uncompiled`（电梯/家具/坡道）不需要"回灌"**：它本来就走模型通道补上，
  真模型探针实测 `uncompiled ⊆ dispatched`（§5.5/§5.9）。§5.3 原来把它和 `defaulted` 并列是**记账不准**。
- **`skeleton_workflow.py` 内部的建筑分支已不可达，但没删**（2026-09-28 实测）：
  `skeleton_generator`（549 行）用一个 `deterministic_primary` 同时服务三种情况——
  ① 物件 → `build_object_skeleton`；② 建筑 → `build_deterministic_skeleton`（**现在不可达**，建筑已改走 `compile`）；
  ③ 无方案的旧入口 → LLM 兼容路径。三者交织在同一个函数体里（`if deterministic_primary` 出现在 8 处），
  且 `build_deterministic_skeleton` 现在被 `compile.py` 复用 ⇒ **不能简单地"删掉建筑分支"**，
  要先把这个函数的三种模式拆开。牵连 13 个测试文件。**不能盲删**，需单独一轮。
- **`component_workflow` / `assembly_workflow` 未删——而且现在**删不得**（2026-09-28 实测，
  这是 §1.2 的**硬依赖**，不是"工作量太大"）**：两者仍有**活跃调用点**，服务的正是编译器
  声明"没有派生规则"的那几类构件：
  `plan/handlers.py:43`（`create_component_generator`）、
  `:53`（`create_component_validator`）、
  `:239`（`merge_fragments_node` 的 `SCOPE_BATCH` 合并）。
  即 `uncompiled = ['elevator', 'furniture']`（+ 坡道）那条**只此一条**的通道。
  §1.2 的前提是"构件改由编译器产出"——**规则补齐之前删掉它们，那几类构件会直接缺席**，
  与"能力缺失只标记不阻断"的红线直接冲突（静默不派比报错更糟）。
  另：`skeleton_workflow` 也删不得，`nodes/skeleton_node.py:6` 仍用它跑**物件链**。
  ⇒ §1.2 的**可执行前置条件**是：编译器补齐 坡道/电梯/家具 的派生规则
  （电梯需井道配套 + `vertical_strategy` 联动；家具缺的是**房间划分**，P2 未实现）。
  在此之前它牵连的 41（`agent.plan`）+ 19（`replanner`）+ 12 + 11 个测试文件迁移**都无法开始**。
- **§3 的图纸分层未落地**：`OpeningInstance` / `ComponentInstance` / 契约不变量扩容都还只在文档里；当前编译器消费的是**现有** `architecture_plan` 协议。
- **收敛环（§1.6 设计期 plan-and-execute）未实现**：设计侧仍是"一次定稿 → 人工审核"，`defects.design_field` 已经把定位信息准备好了，但还没人消费。
  > **已作废（2026-09-28 当晚）**：收敛环已落地，见 §5.7；`design_field` 的消费点就是 `convergence.py::design_level_defects`。
-  **编译通路不落地材质方案（2026-09-28 实测，真回归）**：`skeleton_generator` 有一步
  `apply_resolved_material_plan(blueprint, material_plan, role_specs=…)`（`skeleton_workflow.py:271`），
  `compile_design` **没有**；而 `build_deterministic_skeleton`（`skeleton.py:1139`）的材质是**硬编码 6 个**
  （`concrete / wall_finish / wood / metal / glass / roof`），从不读图纸材质。
  探针 `.workbuddy/diag/probe_material_landing.py`（退出码 0 = 缺口在）实测：编译产物缺
  `floor_finish` / `ground` / `accent` 三个角色材质；**部署资产后还会丢 `textureSet` / `procedural`**。
  建筑链以前走 `skeleton`（开关关闭时也是）时材质**是**落地的 ⇒ 属编译器工作带进来的回归。
  修法 = `compile_design` 加 `material_plan` 入参，在 `build_deterministic_skeleton` 之后、
  `conform_*` 之前调用（`conform_openings_to_slots` 要从 `materials` 取材质，晚了就没意义）。**待定夺。**
  > ✅ **已修（2026-09-28）**：`_compose` 已加该步、`compile_node` 传 `state["material_plan"]`。
  > 探针 `.workbuddy/diag/probe_material_landing.py`（退出码 0 = 已落地）+ `tests/compiler` 6 条。
  > 附带更正一个误判：**`materialId` 由 `ROLE_SPECS` 固定、模型改不了**（模型只能选 `assetId`）⇒
  > 这一修的真实收益是 **`textureSet` / `procedural` / `blueprint["assets"]` 落地**，
  > 不是"元素材质改名"。

---

### 5.7 设计收敛环（§1.6 的第二半，2026-09-28）

**位置**：`material_plan → design_convergence → design_review`（`graph.py`）。

这一环解的是 §1.3 那个不对称：冻结点（`design_review`）原先落在**唯一的确定性可行性校验之前**，
人工刚批准的设计可以被编译器一票否决且没有修订通道。现在审核的是**已经跑过编译可行性验证**的图纸。

**循环**（`convergence.py::converge_design`）：

```
compile_design(plan, dry_run) → 取 severity=error 的缺陷
    → 按 design_field 映射回块（block_of_design_field）
    → 只重出那几块（draft_design_blocks(only_blocks=...)）
    → 合回 raw 草稿 → normalize → 再编译
```

**四种停法**（都实测过，见 `tests/agent/test_design_convergence.py`）：

| stop_reason                                                       | 触发                                                                                                      |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `converged`                                                       | 没有能映射回块的 error 缺陷（**含"只剩整图级缺陷"**——它不属于任何块，重出任何一块都解决不了，只能交人工） |
| `max_rounds`                                                      | 迭代上限（默认 3）。**预算为 0 时一次模型调用都不发**                                                     |
| `no_progress`                                                     | 连续 2 轮缺陷**条数**不下降                                                                               |
| `no_draft` / `model_error` / `invalid_revision` / `outside_scope` | 模型一块没写出来 / 模型服务故障 / 归一化抛错 / 缺陷落在调用方划定的块之外                                 |

 **判进展只看缺陷条数，不用指纹集合**：`evidence` 里嵌着具体数值，改对一点点整串就变样，
集合的"相等/包含"关系极不稳定。

 **`normalize_architecture_plan` 必须单独护住**：模型给的草稿是**不可信输入**，
实测它能抛出 `IndexError: list assignment index out of range`（`planning.py:615`
的 `ground[entrance_bay - 1] = "door"`）。异常若穿出节点就会把整轮生成掐掉，
而上一版图纸本来是可编译的 —— 这正是"收敛失败不阻断"要挡住的事。
**编译器本身不护**：它的崩溃是我们自己的 bug，必须暴露。

**与 §1.6 设计稿的两处偏离（如实记账）**：

1. **没有复用 `app/agent/plan/*` 的 store/status/replan 机制**，而是写了一个专用环。
   理由：`plan` 那套是为**并发构件生成 + 分片合并**设计的（条目有 `op`、要 merge、要落盘
   `PlanDocument`）；设计块是**严格串行的依赖链**，落定就是往一个 dict 里写几个字段，
   没有分片、没有合并、不需要跨轮持久化。复用会引入一份持久化的 `PlanDocument` 来表示
   一个在进程内几秒钟就跑完的东西。**代价**：`no_progress` / 迭代上限这套要自己维护（已做且有用例钉）。
   §1.6 想要的"有界终止"语义**已等价实现**，但没有复用同一份代码。
2. **没有走 `DesignPatch` + `design_repository.apply_patch`**：`apply_patch` 是**仓储接口**
   （`self.get(session_id)` 从 `storage/designs/` 读盘），而收敛环在图里跑、文档未必已落盘。
   改为"重出块字段 → 合回 raw → 重新 `normalize` → 重新 `build_design_document`"，结果同样落进
   `architecture_plan` / `design_document` / `resolved_design` 三个状态位。
   `_EDITABLE_ROOTS` 允许的 `/decisions` 与块字段是对得上的，将来若要走 patch 通道，语义上可行。

**验收**：`probe_architecture_chain_live.py` 增补了两条断言 —— `design_blocks` 诊断必须存在
（证明分块真的生效），且 `design_convergence.stop_reason` 必须是 `converged`
（这就是"人工审的是能编译的图纸"的实测形式）。

### 5.4 两个必须记下来的实现发现

1. **`components.py::optional_fields` 此前是死字段**（全仓库无人读）。本次它成为 `defaulted` 的唯一判据 → 从"死字段"变成"设计可表态字段的唯一事实源"。**改它等于改编译诊断的口径**，不要再让它变回无人读的装饰。
2. **`normalize_architecture_plan` 会静默丢弃认不出的配额键**（实测 `{"garage": …}` 归一化后消失）。所以"引擎没这个概念"的东西根本到不了 `_capability_gaps`，`unsupported` 恒为空集。若将来要让这类诉求可见，应改归一化的**白名单策略**，而不是在编译器里加特例。

### 5.5 整路验证（`compile → plan → 交付校验`，零模型调用）

探针 `.workbuddy/diag/probe_compile_path_plan.py`（退出码即结果）。一份三层别墅图纸（带 `component_quota` 点名檐口/烟囱）：

| 环节     | 结果                                                                                                |
| -------- | --------------------------------------------------------------------------------------------------- |
| 编译     | 24 个结构元素 + 42 个构件（door 1 / window 38 / cornice 2 / chimney 1），`ok=True`，`uncompiled=[]` |
| plan     | 条目 2 条，`generate` **0 条**——门窗、屋顶、檐口、烟囱全部已由编译产出，无一被重复派发              |
| 交付校验 | `run_validation_pipeline` **24 步全绿**（0 error / 0 warning）                                      |
| merge    | 空片段合并后与编译产物逐字节一致                                                                    |

⇒ 这一份图纸上**模型调用为 0**：从"门窗+屋顶+附属十来类"降到"什么都不用模型做"。

 **由此发现一个必须记下来的边界（2026-09-28 二次核实后更正了措辞）**：`run_validation_pipeline`（24 步）单独跑时，把 `conform_openings_to_slots` 整段去掉（图纸点了 1 门 39 窗、产物一个没有）**仍然全绿**。也就是说：

| 校验层                                            | 管什么                                                   | 不管什么                     |
| ------------------------------------------------- | -------------------------------------------------------- | ---------------------------- |
| `run_validation_pipeline`（交付流水线，24 步）    | 这份蓝图**合不合法**（结构/引用/坐标/碰撞/覆盖）         | 图纸点名的构件**是否都到位** |
| `validate_design_brief_constraints`（设计符合性） | 图纸**有没有被落实**（配额下限、必填、批准槽位逐一对齐） | ——                           |

⚠️ **但"交付层看不见"是错的**：`validate_node` 实际判的是**两条一起**（`validation/workflow.py:85`
跑流水线 + `:88` 跑 `validate_design_brief_constraints`），所以**真正的交付判定不会漏**。
负例实测（`.workbuddy/diag/negative_check_delivery_blindspot.py`，退出码 0 = 复现盲区）：
去掉门窗合成后交付判定报出 4 条设计约束错误（`door 数量 0 少于设计下限 1`、
`window 数量 0 少于设计下限 38`、`door 未落实 1 个批准槽位`）⇒ **退出码 1，盲区不成立**。

⇒ 结论：① 编译器 `defects` 与交付层的设计约束**是同一口径的两处实现**，§2.5 要做的是**收敛成一处**，
不是补一个缺失的判定；② 写"产物可交付"的断言必须自己钉**产物非退化**——
因为 `run_validation_pipeline` 单独用时不具备这个能力；③ `uncompiled` 的降级必须继续**只覆盖
"缺编译规则"这一种情形**，一旦放宽到"任何配额没满足"，缺构件就会被交付层放行、且无人再发现。

> ✅ **已做（2026-09-28，§5.10）**：①的"收敛成一处"已落地——编译期不再手挑校验器，
> 改为把**整条交付流水线**投影成缺陷（`compiler/pipeline_defects.py`），
> 口径复用 `agent_service._final_errors`，并叠加 `validate_blueprint_schema` 收口。

### 5.6 附属构件派生（檐口 / 烟囱 / 灯具；坡道故意不做）

补这三类是为了把 `uncompiled` 从 6 类收到 3 类。规则都建在**已落地的屋顶与墙面**上，不新增槽位：

| 构件 | 规则                                                                    | 为什么是这个规则                                                                                                                                                                        |
| ---- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 檐口 | 每块屋顶的**每条檐边**一段线脚；`parentRoof` 局部坐标，Y = 屋面高度偏移 | KB《檐口 cornice》明文"建筑檐口应优先指定 `parentRoof`"；引擎据此把路径贴到**已计算屋面**（坡屋顶的檐边不是水平线）                                                                     |
| 烟囱 | 每块屋顶的屋脊**最高处**立一根；位置相对屋顶中心                        | 基座在最高处 ⇒ 筒身两侧都在坡面之上。KB 明写烟囱"不执行屋顶布尔穿透"⇒ 埋在屋面里就是穿帮                                                                                                |
| 灯具 | 每个外墙面一盏壁灯；有门的墙优先落在门中                                | 位置只做"贴墙外 0.35m、门高以上 1.8m"的**粗对齐**，精对齐复用既有的 `conform_entrance_accessories`（唯一规则函数）                                                                      |
| 坡道 | **不派生**                                                              | 设计协议里没有场地标高 ⇒ 没有可派生的高差。引擎要求 `from`/`to` 有水平投影、KB 要求"必须有高度差"，硬造一个落差就是**产生设计**，违反本模块不变式 ⇒ 如实报 `uncompiled`（warn）交给模型 |

四条硬约束（都撞过或差点撞上）：

1.  **`gable` 的檐边只有两条**（`x = ±span/2`）。`roof.ts::roofSurfaceHeight` 里 gable 的高度按
   `|localX| / (span/2)` 衰减 ⇒ 坡向沿 x、屋脊沿 z；`z = ±depth/2` 那两条是**山墙端**
   （由 `gableEndPanels` 表达），挂线脚就是把线脚钉在山墙面上。
2.  **局部坐标必须向内取整到毫米**。引擎的边界检查是 `abs(local) <= half + 1e-6`，
   而 `round(5.8505, 3) == 5.851 > 5.8505` —— 直接写 `span/2` 会被浮点顶出去，
   引擎抛 `ComponentCompileError` ⇒ **整份蓝图编译失败**（不是"少个线脚"）。
3.  **局部依附的屋顶类型闭集必须镜像引擎**（`_ROOF_LOCAL_ATTACH = flat/gable/hip`
   对应 `attachedToSurface.ts::attachPointsToRoof`）。闭集外的 `dome` / `chinese_curved` /
   `chinese_pagoda` 会让该函数直接抛错，代价同样是整份蓝图编译不出来。
4.  **"产不够下限就一个都不产"**。`validate_design_brief_constraints` 对"配额下限没满足"报 `error`，
   而 `_capability_gaps` 只看"该类型是否出现过"⇒ 下限 4 却产出 1 个，会让这类型从
   `uncompiled`(warn) 掉进 (error)：**部分派生比完全不派生更糟**。差值交给模型通道。

**验证**（全部实跑过）：

| 手段                                                                 | 结果                                                                                                                              |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 正向用例                                                             | `tests/compiler` 46 条                                                                                                            |
| 负例验证（`.workbuddy/diag/negative_check_compiler_attachments.py`） | 7 个 mutation，红点集合**恰好**等于对应用例（含一处如实记录的双红耦合）                                                           |
| 真实引擎重建（`check_blueprint_render.mjs`）                         | **PASS**：檐口扫掠落在 `x=-0.6 / 12.6`（= 屋顶中心 ± span/2）、烟囱基座 `Y=11.44 = 9.6 + 1.836`（正好屋脊顶）、8 盏灯全部在轮廓外 |
| 数据合法性（`verify_wild_blueprint.py`）                             | **PASS**（含"知识库红线：roofType 枚举 / 墙角坐标"）                                                                              |

---

### 5.8 抑制"已产出类型"必须挂在两条路径的公共收口（2026-09-28，真模型探针暴露）

**现象**：真模型探针日志里，编译已产出 `door/window/roof`，`plan` 却仍派了
`generate_door_01(door)` / `generate_window_02(window)` / `generate_roof_03(roof)`：

```
[compile] final → {'ok': True, 'elements': 43, 'components': 28, 'uncompiled': ['elevator','furniture']}
[execute] 本轮 2 条：generate_door_01(door), generate_window_02(window)
[execute] generate_door_01 → failed（45210ms）
[execute] generate_window_02 → succeeded（71613ms）：批量生成窗 × 27
[execute] generate_roof_03 → succeeded（31412ms）：生成屋顶
```

代价：**白烧约 200s 模型时间**，且窗被生成两遍（编译 27 + 模型 27 → 54），把核心筒挤歪。

**根因**（`plan/expand.py`）：抑制判据 `_produced_kinds` 只挂在 `_requested_kinds` 里，
而 `_requested_kinds` **只服务确定性降级路径**：

```python
entries = (
    ordered_kinds(strategy)                                    # ← 模型给了策略时走这条
    if strategy is not None
    else [PlanKindStrategy(kind=k) for k in _requested_kinds(state)]   # ← 过滤只在这条
)
```

`_produced_kinds` 当年的 docstring 写的判据是"常规通路（骨架只产结构元素、`components` 为空）
下这里恒为空集，**不改变今天的行为**"——那是按**物件链**写的。建筑链改走确定性编译后，
该前提已不成立，但过滤没跟着挪。

**修法**（收敛成唯一闸口，两条路径共用）：

```python
def _drop_produced(entries, state) -> tuple[list[PlanKindStrategy], list[str]]:
    produced = _produced_kinds(state.get("skeleton_blueprint"))
    if not produced:
        return entries, []
    kept: list[PlanKindStrategy] = []
    dropped: list[str] = []
    for entry in entries:
        if entry.kind in produced:
            dropped.append(entry.kind)
        else:
            kept.append(entry)
    return kept, dropped
```

① `_requested_kinds` **交出**该职责（它只是"要什么"的解析器，恢复纯净）；
② `expand_plan` 在两条路径合流之后统一调用 `_drop_produced`；
③ 被抑制的类型**进审计**（`PlanHistoryEntry(action="suppress:produced")`）——
"模型要了别的构件"与"程序没给它派"是两回事，交付清单要能回答"点名 X 为什么没有条目"；
④ `plan_diag` 增 `dispatched_kinds`，日志从"要求 N 类"改成"要求 N 类 → 派发 [...]"；
callback 只播报**真的进了计划**的类型（否则等于对用户撒谎）；
⑤ `_produced_kinds` 的 docstring 按建筑链/物件链**两种前提**重写，不再留"恒为空集"的旧判据。

**红线对齐**：抑制只按"**产物里有没有**"判，不写 per-type 分支；且**反向也钉住**——
`compile_report.uncompiled` 里的类型（编译器暂无派生规则：`elevator` / `furniture` / `ramp`）
**必须仍然被派发**，否则那类构件直接缺席。
"不该派的不派"和"该派的必须派"是同一个判据的两面。

**验证**：

| 手段                                    | 结果                                                                                                                                                                                                                                                                           |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/compiler/test_compile_wiring.py` | 新增 `test_model_strategy_cannot_redispatch_compiled_kinds`（**模型策略路径**，原缺陷所在）+ `test_deterministic_path_skips_produced_types_through_the_same_gate`（降级路径）；原 `test_requested_kinds_skips_already_produced_types` 删除——它钉的正是"过滤挂在半条路上"的写法 |
| 全量回归                                | 1057 passed / 1 xfailed                                                                                                                                                                                                                                                        |
| 未定义名扫描                            | `check_undefined_names.py app tests` → 245 文件 / **0 处**                                                                                                                                                                                                                     |
| 真模型探针                              | `.workbuddy/diag/probe_architecture_chain_live.py` 新增 `_report_plan_dispatch`：`dispatched ∩ produced == ∅` 且 `uncompiled ⊆ dispatched`                                                                                                                                     |

---

### 5.9 试算工具已接线（§2.7，2026-09-28）

**做了**：设计块起草默认走**有界工具循环**，模型拿到一个只读工具 `probe_compile_design`。

| 环节     | 位置                                                       | 说明                                                                       |
| -------- | ---------------------------------------------------------- | -------------------------------------------------------------------------- |
| 工具本体 | `generation/architecture/probe_tool.py::probe_design_text` | 归一化草稿 → `compile_design(mode="probe")` → 压成一段文本                 |
| 工具声明 | 同文件 `build_probe_tool` / `DesignToolSpec`               | 参数（用户请求 + 两个 profile）用**闭包**固定，模型只能传图纸              |
| 接线     | `design_workflow.draft_design_blocks`                      | 所有通道：`run_tool_loop(system_prompt=prompt, …, tool_specs=[probe])`     |
| 预算     | `plan/tool_loop.py`                                        | 单条目总预算 `MAX_TOOL_CALLS=3` + 单工具 `max_calls=2`，超限回可读拒绝文本 |

**四条设计取舍（都写进了代码注释）**：

1.  **只回诊断、不回蓝图**：走 `mode="probe"`，该模式 `blueprint`/`design_brief` 恒为 `None`
   ⇒ 模型怎么调都拿不到也改不了产物。链路仍是 图纸 →（编译器）→ 蓝图。
2.  **工具是全函数**：非法 JSON / 非对象 / 归一化抛错 / 编译器抛错，**全部转成可读文本**。
   工具边界上放异常出去＝掐掉整轮生成（`normalize_architecture_plan` 实测有一条越界会抛 `IndexError`）。
3.  **模型故障仍要上抛**：`run_tool_loop` 为 plan 条目设计，内部**吞掉**异常只记 `diag["error"]`；
   设计块路径显式把它翻回 `RuntimeError` —— 否则"服务坏了"会被伪装成"模型不会写这块"，
   白重试 3 次后拿一份默认图纸交付，调用方再没机会走 `model_failure_result`。
4. ~~**流式思考通道不提供该工具**~~ → **已解（2026-09-28 晚，见 §5.11）**：原先认为
   "工具循环经由 `create_agent`，转发不了 reasoning delta"，于是把"思考过程"与"试算工具"
   做成了**二选一**。实测该前提不成立——**回调是模型级的**（挂在 `config["callbacks"]` 上），
   与图级流无关。现在两者兼得，`use_streaming` 只在"没有工具可用"时成立。

**由此带来的桩件迁移（重要，别踩）**：`draft_design_blocks` 的默认调用缝从
`design_workflow.invoke_llm` **变成了 `plan.tool_loop.run_tool_loop`**。
仍把桩件打在 `invoke_llm` 上的测试会绕过桩件**真的去连模型并挂住**（比"用例红了"难查得多）。
已同批迁移：`test_architecture_node_smoke.py`、`test_design_blocks.py`（两条通道都覆盖）、
`test_model_service_block.py`。

**记账**（`plan/tool_loop.py` 的附带修正）：`_sum_usage` 累加 agent 消息的 token 用量。
 必须**逐条归一化再累加**，不能"先按原始键加总、最后归一化一次"——
同一会话里 `prompt_tokens` / `input_tokens` 会混用，而 `_normalize_usage` 两者并存时只认前者
（实测 10+5 变成 5）。

**验证**：`tests/agent/test_design_probe_tool.py` 14 条；全量回归 **1074 passed / 1 xfailed**；
`check_undefined_names.py app tests` → 247 文件 / **0 处**。

**真模型实测**（`probe_architecture_chain_live.py` 第二遍，退出码 0）：模型**确实在用**这个工具——
`[architecture] 设计块 massing 试算了 1 次：['probe_compile_design']`，五个块累计调用 **7 次**
（massing 1 / structure 1 / facade 1 / roof 2 / components 2），定稿 `未定稿=[]`、
收敛 `stop_reason=converged defects 0`。

### 5.10 校验器并入编译器（§2.5，2026-09-28）

**问题**：§2.5 说的"校验散在三处"实测就是三处，而且**其中两处是同一条规则的两个实现**：

| 规则         | 实现 A                                                   | 实现 B                                                            |
| ------------ | -------------------------------------------------------- | ----------------------------------------------------------------- |
| 顶层结构完整 | `blueprint_parser.validate_blueprint_schema`（骨架预检） | `spatial_tools.validate_blueprint_structure`（交付流水线 Step 1） |
| 构件尺寸     | `spatial_tools.validate_element_dimensions`              | 编译期手挑调用（原 `_validator_defects`）                         |
| 引用完整性   | `spatial_tools.validate_reference_integrity`             | 编译期手挑调用（原 `_validator_defects`）                         |

**修法**：不再"编译侧手挑几个校验器调一遍"，而是把**整条交付流水线**投影成编译缺陷。

| 环节     | 位置                                                                                                       |
| -------- | ---------------------------------------------------------------------------------------------------------- |
| 唯一投影 | `compiler/pipeline_defects.py::pipeline_defect_messages`                                                   |
| 口径复用 | `agent_service._final_errors`（按校验器去重、只留修复后的 `[recheck]`）——不另写"哪些步骤算没过"            |
| 接入     | `compile.py::_validator_defects`（流水线部分）+ 新增 `_schema_defects`（`validate_blueprint_schema` 收口） |
| 步骤日志 | `run_validation_pipeline(..., log_steps=False)`：交付路径保持逐步骤日志，编译期关掉                        |

四条实现纪律（都写进了代码注释）：

1.  **在深拷贝上跑**。流水线带 `fix_*` 步骤、会就地修蓝图（交付路径正是靠这个）。
   编译期只要**诊断**；直接吃入参会把 `dry_run` 变成一次隐式修复，而外面拿到的还是原样——
   同一份图纸两次编译结果不同，回归与门禁全部失效。
2.  **判据必须是"同源"而不是"都跑过"**。只要编译期"手挑几个校验器调一遍"，
   交付侧新增一个校验器、编译侧不跟——两处就分叉，而且**不会红**（谁也不报错，
   只是收敛环少看到一类缺陷）。所以 `test_pipeline_defects.py` 的第一条断言是
   **集合相等**：编译缺陷的 `evidence` 集合 ≡ `pipeline_defect_messages` 的返回。
3. **两条 schema 规则都要留**：`validate_blueprint_schema` 抓 `meta` 类型、元素类型与
   **id 唯一性**，是流水线 Step 1 抓不到的一类坏蓝图（实测原文案：`重复的构件 ID: {'floor_1_main'}`）。
   只复用流水线会丢掉这一条。
4. **不加"骨架质量"那一类**：`evaluate_skeleton_complexity`（体量覆盖 / 逐层墙标高 /
   竖向交通 / 结构构件数量）是**模型骨架**的质量门禁，度量的是"模型有没有按方案搭骨架"；
   确定性编译器按构造就满足它，把它搬进来只会产出模型改不动的缺陷。它留在 `skeleton` 那条链上。

**代价（如实记账）**：流水线 Step 1 不过就**短路**，后面的尺寸/引用校验不再跑。
这是交付路径本来就有的行为，照搬不改——"先把顶层结构修好再看细节"。
编译缺陷的 `code` 因此从 `dimension_invalid` / `reference_broken` 变成**交付步骤名**
（`validate_element_dimensions` / `validate_reference_integrity`），报出的缺陷与
`final_validate` 逐字对得上。

**验证**：`tests/compiler/test_pipeline_defects.py` 5 条；全量回归 **1079 passed / 1 xfailed**；
编译器 64 条 2.87s（**无性能退化**：早退的短路步骤 + 1220 项全量 11.04s）；
`check_undefined_names.py app tests` → 249 文件 / **0 处**。

### 5.11 思考过程与试算工具不再二选一（§2.7 遗留项，2026-09-28 晚）

**原判据（错的）**：§5.9 第 4 条写着"工具循环经由 `create_agent`，那条通道转发不了 reasoning
delta"，据此把"界面上的思考过程"与"试算工具"做成了互斥，并记成"已知缺口"。

**实测推翻它的证据**：`agent_service` 的最终回答 agent 早就在用
`self.thinking_llm = create_llm(enable_thinking=True, streaming=True)` +
`agent.ainvoke(..., config={"callbacks": [_ReasoningStreamCallback(...)]})`
（`agent_service.py:1025` / `:1385`）。⇒ **回调是模型级的**，跟图级流（`stream_mode`）无关；
`create_agent` 里的模型调用同样会触发 `on_llm_new_token`。
当初的结论是把"图级 `stream_mode` 拿不到 token"错当成了"agent 通道拿不到 token"。

**改法**（三处，全部向后兼容）：

| 环节     | 位置                                                         | 说明                                                                                                                                                             |
| -------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 规则上移 | `app/llm/reasoning.py::ReasoningDeltaCallback`               | 原 `agent_service._ReasoningStreamCallback` 整段迁出（攒批判据 `FLUSH_CHARS=24` / 句末标点不变），`agent_service` 保留旧名别名。**agent 层不该从服务层导私有类** |
| 回调接线 | `plan/tool_loop.py::run_tool_loop(..., on_reasoning_delta=)` | 挂进 `config["callbacks"]`；`finally` 里 **flush**（失败/超限时缓冲里那半句也要发出去）                                                                          |
| 开流式   | `plan/tool_loop.py::build_tool_agent(..., stream_tokens=)`   | `stream_tokens=True` 才 `create_llm(streaming=True)`——没回调就不开，不开就一次 `on_llm_new_token` 都不会触发                                                     |
| 解互斥   | `design_workflow.py`                                         | `probe_specs` 只看 `allow_probe`；`use_streaming` 只在**没有工具可用**时成立；工具循环那支把转发器包一层 `(channel, delta)` 传下去                               |

**反面判据（同批钉住，别改回互斥）**：
`test_thinking_mode_keeps_both_the_tool_and_the_reasoning_stream` —— 思考模式下必须**同时**
走工具循环（`calls[0]["on_reasoning_delta"] is not None`）**且**不起纯流式通道
（`stream_calls == []`，否则同一个块会调两次模型）。

**没改的部分**：`stream_llm` 那条纯流式通道保留，只在 `allow_probe=False` + 思考模式时走。
另：`ReasoningDeltaCallback` 的攒批阈值（24 字符 / 句末标点）**照抄不改**——
逐 token 直发会把前端 SSE 打爆，攒太久看起来像卡住，这个数是有来历的。

**验证**：`tests/plan/test_plan_tools.py` +3（`stream_tokens` 落到模型工厂 / 回调挂上且失败仍 flush / 不要思考时不挂回调）；
`tests/agent/test_design_probe_tool.py` +2（思考模式两者兼得 / delta 走 `architecture` 通道）−1（原"流式通道跳过工具"那条已翻）；
全量回归 **1084 passed / 1 xfailed**；`check_undefined_names.py app tests` → 250 文件 / **0 处**。

---

### 5.12 `defaulted` 回灌的落点调查（2026-09-28 晚，给 §5.3 那条记账收口）

**先更正我上一轮的说法**：我在 §5.3 写过"`_DESIGN_FIELD` 对 `door`/`window` 都有映射 ⇒ 回灌路径技术上存在"。
**这句说浅了**——映射存在只能说明"缺陷/默认值能定位到某个设计块"，**不等于"图纸装得下那个字段"**。实测不成立。

**三组实测证据**（当前代码，零模型调用）：

| 证据                       | 位置                                              | 说明                                                                                            |
| -------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 立面槽位只装**类型名**     | `planning.py:262-270` `_normalize_pattern`        | 每项走 `str(item).lower()`，不在 `_OPENING_TYPES` 里的一律变 `"empty"` ⇒ **对象项会被直接吃掉** |
| 门窗细部由编译器**派生**   | `facade.py:840-841`（凸窗）、`:948-951`（普通窗） | `frameWidth/frameDepth/frameMaterial/leafMaterial` 全是确定性/变体派生，**不读图纸**            |
| 图纸**没有**逐实例参数通道 | `component_quota` 实测形状                        | 只有 `{min,max,note}`；`detail_packages` 是包名列表。**图纸以"配额"说话，不以"实例参数"说话**   |

实测快照（`.workbuddy/diag/dump_defaulted.py`，三层矩形别墅；另一张图同形不同量）：

```
defaulted 总数: 65
  door    doorStyle / frameDepth / leafDepth / leafRows / openingStyle     各 x1
  window  frameDepth / frameWidth / glassDepth                            各 x20
plan 顶层键: facades / massing / roof / structural_grid / component_quota / …（**没有** decisions 嵌套）
front.ground_pattern: ["window", "window", "door", "window", "window", "window"]   ← list[str]
```

**结论（三条）**：

1. `defaulted` 的 65（另一张图 119）条**全部**落在图纸层**结构上装不下**的字段上
   ⇒ 现在做"回灌"得到的是**一条空通道**——模型没有地方可写。**不建。**
2. ⇒ 它**不是 §2.6 的尾项，而是 §3.3 + §3.4 的产物**：
   - §3.3 把开口从 `Literal["door","window","empty"]` 升成 `"<kind>:<form>"`（`form` 是闭集）；
   - §3.4 把 `component_quota` 升成**实例清单**（`host` / `size` / `form` / `material_role`）。
   两件都落地后，`defaulted` 才第一次出现"图纸可以表态"的字段。
3. **一条产品判断**：门窗的 `frameDepth` / `glassDepth` 本就该由编译器从**父墙厚度**派生
   （这正是注册表契约里写死的默认，`components.py:73/83`）。**把这些尺寸逼模型表态不是优化，
   是把已经确定的东西推回给模型**。⇒ 即使 §3.3 落地，建议 `defaulted` 只回灌**形态类**
   （`openingStyle` / `doorStyle` / `leafRows`），尺寸类继续由编译器从宿主派生。

**没做的事（明确记账）**：没有扩图纸协议、没有动提示词——那两步都会改变模型输出，属**生成契约变更**，须先定夺。
**"哪几档回灌"这个决策也因此被前置了**：在 §3.3/§3.4 落地之前，闭集里挑哪一档都不会改变任何产物。

> **注（2026-09-28 晚）**：本节开头那句"没有扩图纸协议、没有动提示词"到此**部分作废**——§3.3 就是
> 那个"扩协议 + 动提示词"的前置，已落地，见 §5.13。`defaulted` 回灌本身仍未做。

---

### 5.13 立面开口升成"带形态的开口"（§3.3，2026-09-28 落地）

**一句话**：图纸现在能写 `door:slide` / `window:fixed`，形态会落到蓝图的 `interaction.mode`；
不写冒号的老图纸**一个字节不改**。

**文法唯一事实源**（新模块 `app/design/openings.py`）：
- `split_opening("door:slide") → ("door","slide")`；`opening_kind()` 只取类型；`opening_token()` 反向组合。
- `form` 闭集 = 引擎 `openingInteractionSpec.mode`（`swing/slide/lift`）∪ 哨兵 `fixed`（= 不写 `interaction`）。
- `FORMS_BY_KIND`：门 `{swing,slide,lift}`（**无 `fixed`**，门必能开）；窗 `{swing,slide,fixed}`（**无 `lift`**）。**数据，不是分支**。

**一处更正（第一句）**：§3.3 原文把窗的形态写成 `casement/sliding/fixed`——那是我写文档时拍的，
引擎没有这些值（`interaction.mode` 就 `swing/slide/lift` 三个）。多一层"casement→swing"改名表＝多一个
会漂移的分叉点，且两层名字最终仍要对齐引擎。**已按引擎闭集落地，并回改本节**。`fixed` 不是引擎枚举值，
它是"不可开启 ⇒ 不写 `interaction`"的哨兵。

**四处消费、一处解析**：

| 层       | 位置                                                    | 改法                                                                                                                                                  |
| -------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| 契约     | `contracts.py`                                          | `FacadeDecision` 两个 pattern `list[OpeningKind]` → `list[str]`；validator 只查**类型**合法，形态名写错**不拒**                                       |
| 归一化   | `planning.py::_normalize_pattern`                       | 非法形态→降级纯类型（**只丢形容词、不丢开口**）；计数 / `"door" in ground` 改走 `opening_kind`                                                        |
| 立面编译 | `facade.py`                                             | 槽位带 `form`；`_apply_opening_form` 只覆写 `interaction.mode`（同 mode 保留 `hingeSide`/`openAngle`、非 swing 清掉、`fixed` 摘掉整个 `interaction`） |
| resolver | `resolver.py`                                           | slot 的 `id`/`type` 只用类型，不把形态写进 id                                                                                                         |
| 提示词   | `design_blocks.py` facade 块 + `prompts/planning.py:88` | 写明 `<kind>:<form>` 语法与闭集                                                                                                                       |

**两处偏保守的决策**：
1. **只丢形态、不丢开口**：`window:casement` → `"window"` 照常生成（红线"能力缺失只标记不阻断"）；
   但**写错类型**（`garage`）会被 `check_block_contract` 退给模型重写——**不是**静默变空槽位、偷偷丢一扇窗。
2. **对象形态（`mullions`/`sillRatio`/`doorStyle`）留到 §3.4**：那本质是"逐实例参数"，和 §3.4 的构件实例清单
   是同一件事，不该在 pattern 里再开一个并行表示（两个表示就分叉）。

**验证**：全量 **1138 passed / 1 xfailed**（+54 条 `tests/design/test_opening_forms.py`，含
`test_forms_match_the_engine_interaction_enum` 这个 schema 漂移守卫）；探针
`.workbuddy/diag/probe_opening_forms.py` 退出码 0；`check_undefined_names.py` 252 文件 / 0 处。

**还没跑**：真模型探针——模型在改过的提示词下会不会真的开始写 `:形态`，以及会不会因新语法而重试变多。
这是收尾前要补的最后一环。

### 5.14 设计期 plan-and-execute 落地（§1.6，2026-09-28 晚）

**起因**：用户报「我想让 plan 也参与到设计图纸当中」。查下来 plan 在**构造上**就碰不到图纸：
图纸由 `architecture` 节点逐块起草（块表是常量），`compile` 零模型地把蓝图全算完，
于是 `plan` 只剩编译器暂无派生规则的 `uncompiled` 类型（别墅里**就是雨棚**）。
用户那次的 plan 输出本身**是正确的**，只是职责划分让它天然无活可干。

**落地形态**（新模块 `app/agent/generation/architecture/design_plan.py`）：

| §1.6 的目标                            | 实现                                                                     |
| -------------------------------------- | ------------------------------------------------------------------------ |
| 条目 = 设计块                          | `build_design_plan`：`DESIGN_BLOCKS` → `PlanDocument`，id=`draft_<块名>` |
| 依赖表是常量、不由 LLM 产出            | 依赖直接取块表的 `depends_on`；**没有**为块序新增任何模型调用            |
| `PlanItem` 条目                        | 复用；`op` 取闭集里的 `generate`（不开新 op），`kind`=块名               |
| `expand_plan`                          | `build_design_plan`（确定性展开，只保留计划内的依赖）                    |
| `run_generate`                         | `_draft_one`（LLM 写这一块，带证据重试）                                 |
| `store.py` / `refresh_statuses` / 对账 | **原样复用**                                                             |
| `parallel_group`（结构/立面/屋顶并发） | `next_batch` 按声明派发 ——  **这是本次唯一真正修复的空转声明**           |
| 有界终止                               | `ItemRun.max_attempts`（= `_BLOCK_MAX_ATTEMPTS`）                        |
| `commit_block` 的块间不变量            | `check_block_contract`（已存在，未改）                                   |

 **`parallel_group="shell"` 从落表那天起就没生效过**：`draft_design_blocks` 是纯串行 for 循环，
`ordered_blocks` 的文档里写着"便于外部并发执行"，但没有任何调用方并发。现在三块真并发。

**两个只有跑起来才会暴露的坑**（都已钉进测试）：

1. **试满上限必须落 `abandoned`（终态）**。`refresh_statuses` 把 `abandoned` 当已落定，下游才会继续 ——
   这正好是"留空交下游兜底"那条红线在调度层的表达。写成 `blocked` 会把 `components` **永久锁死**，
   症状是"图纸一直缺构件配额"，而根因在一块早就失败的块上。
2. **子集重出（`only_blocks`）必须裁掉悬空依赖**。收敛环只重出受影响的块，若保留指向计划外条目的
   `depends_on`，`refresh_statuses` 永远推不出 `ready` ⇒ 条目静默丢在 `blocked`，
   症状是**"重出之后图纸一个字节没变，却也不报错"**。

**为什么必须量并发，而不是量产物**：串行也能把五块写完，所以"图纸正确"证明不了调度生效。
守卫 `tests/agent/test_design_blocks.py::DesignPlanSchedulingTest` 量的是**同时进行的模型调用数**
（桩件在 `await asyncio.sleep(0)` 前后计数；串行永远到不了峰值 2）。

**诊断口径**：`architecture_diag.design_blocks.{plan,batches}`（计划全文 + 每批的条目与落定情况），
UI 那一行由 `ws_agent._design_schedule_note` 生成：`设计期 N 批（最宽 M 并发）· 落定 X/Y 块`。
这是"plan 到底参与了没有"唯一可观测的现场。

**验证**：全量 `pytest tests` **1174 passed / 1 xfailed**；新增 6 条调度测试 + 2 条口径测试。

### 5.15 §3.4 实例清单落地：它是**覆盖层**，不是替换层（2026-09-28 晚）

§3.4 的"抽象与显式并存、抽象为主显式为例外"此前被实现成了**按类型整批取代**，
代价实测如下：

| 症状（改前）                         | 根因                                                         |
| ------------------------------------ | ------------------------------------------------------------ |
| `light 数量 1 少于设计下限 2`        | 一张只写一盏灯的清单把**四个立面**的派生灯全删了             |
| 大量 `配额下限没满足` / `ok=False`   | 只写阳台的清单把**门窗**整类删了                             |
| `roof 缺少必填字段 height/thickness` | 屋顶实例自带一套几何，漏掉元素必填字段                       |
| `未在 Blueprint.materials 中定义`    | 把**设计侧角色名**写进了引用**蓝图材质名**的字段             |
| 整份蓝图 `schema_invalid`            | `light` 用了引擎不认的 5 个字段，`lightType="wall"` 违反闭集 |

**改后的规则**：

1. 派生链**先跑完**（立面 pattern → 门窗、槽位 → 阳台/栏杆、屋顶/檐口/烟囱/灯具/电梯派生）；
2. 实例**只顶替它指向的那一条**：门窗按 `parentWall` 对齐（= **批准槽位上的那个构件**），
   灯具/屋顶取该类型的第一条；找不到对应派生结果就**追加**（实例是新增的）；
3. 有模板（= 顶替的是一个批准槽位）时**几何以槽位为准**：
   `validate_design_brief_constraints` 逐槽位同时比对 `from`/`width`/`height`，
   实例改尺寸会让那个槽位"未落实" —— 实例能表态的只有**形态与材质**；
4. 材质字段统一由 `_resolve_instance_materials` 换名，映射表唯一来源是
   `material_plan.ROLE_SPECS[*].materialId`（**不在编译侧重抄一份**）；
5. 屋顶实例只表态造型，几何取自派生模板（`_single_roof`）；`ridgeHeight` → `height`。

 **顺带暴露的测试问题**：`tests/design/test_component_instance_validation.py` 的 6 条 fixture 用
`complexity: "medium"` / `envelope: "modern"`（字符串），而契约要 `ComplexityDecision` /
`EnvelopeDecision` **对象** ⇒ 这 6 条**从来没跑过**（`model_validate` 在更早的字段上就炸了，
断言全在空转）。写契约测试前先确认 fixture 能过 `model_validate`。

 **另一条**：`test_light_instance_compilation` 旧断言 `lightType == "wall"` —— 那是**引擎的闭集外**
取值，断言的不是"实现对了"，而是"实现错得跟测试一样"。已改成钉真正合法的字段
（`position`/`fixtureType`/`initiallyOn`）。

**还没做（明确记账）**：`_compile_*_instance` 那 8 个 per-type builder 仍是既有 `conform_*_to_slots`
的**重复实现**，只是在外面接了覆盖层；它们违反 §3.1"图纸里不出现世界坐标"（自己算了位置）。
正确做法是让实例**只表态**、几何全部走既有派生，下一轮该收。
