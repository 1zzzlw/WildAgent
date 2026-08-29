# WildAgent 两轮优化总结（LangGraph 生成链路 + 知识库/RAG）

> 本文档记录 2026-08-29 完成的两轮优化：**第一轮针对 LangGraph 建筑生成链路**（降低出错率 + 提升精细度），**第二轮针对知识库内容与 RAG 契约**（消除冲突 + 补齐缺口）。全文按"**问题 → 改动 → 验证**"组织，改动均未触碰 `graph.py` 拓扑和 `ws_agent.py` 协议，可逐文件回滚。
>
> 最终验证：核心测试套件 7 个目录全绿（`agent/blueprint/components/misc/network/repair/validators` 共 354 passed），RAG 单测 45 passed，RAG 评测 Hit@5=85.7% / Recall@5=85.7% / MRR=0.730。

---

## 0. 背景：两条主线为什么这样优化

在动手前，两轮优化共享同一个核心认知，它来自此前对系统的深度扫描：

> **这个系统"安全兜底"非常完备，但兜底的方式是"整体回退到低精度确定性方案"，而回退本身不产生任何诊断、不计入错误。**

具体表现：
- **第一轮（LangGraph）**：LLM 决策层单次调用、解析失败即整份回退；校验器把"孤立端点/悬空/穿墙"标成 ⚠️ 而非 ❌，以 `complete` 交付；callback 复检指纹太粗，可能"修好一个错换成另一个错"。
- **第二轮（知识库）**：文档与代码契约冲突（roofType 3 vs 6、interaction 必填性五方矛盾）；旧版 `opening` 门窗模型残留；别墅等高频主题双源冲突；楼梯/灯具高频构件无知识文档。

两轮的共同对策是：**让"降级"显式化（要么重试、要么报错、要么记录诊断），让"契约"统一（文档与代码对齐）**。

---

# 第一部分：LangGraph 建筑生成链路优化

## 1. 批次 A：校验口径收紧（P0，直接降出错率）

### A1. severity 结构化判定（`app/services/agent_service.py:206`）

**问题**：`run_step` 的 `has_error` 判定是"输出文本里有没有 ❌"，而孤立墙体端点、悬空、穿墙、尺寸越界这些几何问题在 `spatial_tools.py` 里只标 ⚠️。结果是**一面墙 600 米长、楼板 0.01m 厚、柱子悬空、家具穿墙，都会被标记 `status="complete"` 并交付**（`spatial_tools.py:720-724, 1711-1714, 1796-1798`）。

**改动**：新增 `_severity_from_text(output)` 辅助（同时含 ❌ 与 ⚠️ 时按 ❌ 计），把 `run_step` 和所有手写 `"❌" in output` 判定收敛到它。不触碰任何校验器文本输出，只收敛判定侧。

**验证**：`tests/validators/test_validation_pipeline_repairs.py`、`tests/blueprint/test_blueprint_material_validation.py`、`tests/network/test_generation_commit.py` 全绿。

### A2. 交付警告门禁（`app/services/agent_delivery.py:26,121`）

**问题**：`prepare_blueprint_delivery` 只拦 `status != "complete"` 或 `errors > 0`，警告全部放行。

**改动**：新增 `WARNING_GATE_MAX = 20`。`summary.warnings > 20` 时抛 `GenerationRejectedError`，要求先走 callback 修复。正常生成的少量警告不受影响，满屏警告被拦截。

---

## 2. 批次 B：callback 复检指纹盲区（P0）

### B1. 指纹加入消息哈希（`app/agent/validation_issues.py:169-186`）

**问题**：`issue_fingerprints` 只取 `(code, entity_id)`。同一校验器在同一实体上的不同错误（如同一扇门"超出墙右端"与修复后新出现的"与窗重叠"）都落在 `OPENING_FIT` 上，指纹不变 → `compare_issue_sets` 判 `accepted=True`，**旧错误换新错误被提交**。

**改动**：指纹改为 `(code, entity_id, sha1(message)[:12])`。只有错误消息本身减少才算改善。

**验证**：更新 `tests/repair/test_targeted_repair_tools.py` 的指纹断言，并新增"同 code 同实体、消息变了也拒绝"的用例。`tests/repair/` 全绿（25 passed）。

---

## 3. 批次 C：消除静默降级（P0）

### C1. 组件 JSON 提取失败显式化（`app/agent/nodes/base_component_node.py:49,250`）

**问题**：组件 gen 节点 JSON 解析失败时返回空分片并只写 `error="JSON 提取失败"`，不设 `model_error`、不设 terminal。格式故障被静默降级为"组件缺失"，走配额缺失 → callback `add_entity` 的几何路径；若配额 `min=0` 则彻底静默消失。

**改动**：
- 新增 `_recover_component_json`：解析失败时用**一次非思考调用**做定向格式恢复，要求输出单一 JSON 数组/对象。
- 恢复仍失败时，diag 增加 `"json_parse_failed": True` 和 `model_error: {category: "json_parse", terminal_current_run: False, retryable: True}`——**不设 terminal**，避免 merge 误判为服务故障。

### C2. merge 侧可诊断（`app/agent/nodes/merge_node.py`）

**改动**：新增 `_collect_json_parse_failures`。`json_parse_failed=True` 的组件：配额 `min>0` 时生成设计配额级错误交给 callback `add_entity`；`min=0` 时记 `logger.warning`。格式故障与几何问题区分开。

### C3. 计划层格式恢复 + invoke_llm 退避重试（`app/agent/llm_invocation.py:18,93`、`app/agent/format_recovery.py:17`）

**问题**：四个计划节点（architecture / floor_plan_design / material_plan / execution_planner）全是单次 try/except + 走确定性回退，零重试。偶发抖动直接把 LLM 设计整份丢弃，精细度塌缩但用户无感知。`model_errors.py:73-79` 里 `terminal_current_run` 恒为 True，限流/5xx/超时这些 `retryable` 错误在计划节点既不重试也不上报。

**改动**：
- `invoke_llm` 对 `classify_model_error` 判定 `retryable=True` 的异常（429/5xx/超时）加**最多 2 次指数退避重试**（1s/2s），`LlmResult.retry_count` 记录重试次数。
- 新增 `app/agent/format_recovery.py` 的 `recover_single_json`：用一次非思考调用恢复为单一 JSON 对象。
- 四个计划节点接入 `recover_single_json`，解析失败先做定向恢复，恢复失败才走既有确定性回退。

**验证**：`tests/agent/test_agent_graph_routing.py`、`tests/components/test_material_plan.py`、`tests/agent/test_execution_plan.py` 全绿（52 passed）。

---

## 4. 批次 D：确定性几何（P1，精细度最大收益）

### D1. volumes 逐项修复而非整体回退（`app/agent/architecture_plan.py:863`）

**问题**：`_normalize_volumes` 对任一正面积重叠/缺层**整份 `return fallback`**，丢弃 LLM 全部体量设计。

**改动**：新增 `_repair_volume_overlaps`（按优先级保留主体积，把次级体积沿重叠方向推移出界）和 `_repair_volume_floor_gaps`（缺层时扩展最近体积的 end_floor）。仍无法修复才整体回退。

### D2. G3 槽位容差匹配（`app/agent/plan2build/gates.py`）

**问题**：G3 槽位→组件匹配用 `round(x,3)` 精确比较，0.5mm 级漂移即误判"已批准槽位未生成"。

**改动**：新增 `_OPENING_SLOT_TOLERANCE = 1e-2` 容差比较（`_signature_matches`），槽位签名与组件在 1cm 内匹配即通过。

### D3. 外法向几何判定（`app/agent/architecture_plan.py:3303`）

**问题**：`_entrance_anchor` 假设"墙按逆时针围合，外法向=沿墙方向右旋 90°"。LLM 的 volumes 组合出顺时针或凹形轮廓时，**入口雨棚/柱/灯会被放到室内一侧**。

**改动**：新增 `_plan_winding`（用体量联合轮廓的有向面积/shoelace 判定绕向）和 `_convex_hull`。逆时针用右旋，顺时针取反。

### D4. 构造网格吸附（`app/agent/spatial_geometry.py:21`、`app/agent/architecture_plan.py:2679,2884`）

**问题**：没有构造网格吸附机制，只有 `round(x,3)` 到毫米；窗宽 `bay_width*0.62` 等魔数导致开间不均分、窄开间窗被压成 0.5m 或被静默丢弃；槽位重叠直接 `continue` 丢弃。

**改动**：
- 新增 `snap_to_grid(value, step=0.1)`（吸附到 0.1m 构造网格）。
- 窗宽、槽位 `from[0]`、`left` 吸附到 0.1m 网格。
- 新增 `_retry_slot_position`：槽位重叠时先向相邻 bay 重排一次，不再直接丢弃。
- 内墙端点（`apply_spatial_plan_to_blueprint`）吸附到网格。

### D5. 确定性装配纳入碰撞校验 G8（`app/agent/plan2build/gates.py:398`）

**问题**：确定性装配路径（G1-G6）**不跑碰撞检测**——`approved_plan_assembler_node` 只返回 G1-G6，碰撞/悬空/法向偏移在装配路径是盲区。

**改动**：`evaluate_body_gates` 追加 `gate_g8_collision`，调用 `validate_collision` + `validate_opening_coords`（取 `@tool` 的 `.func`），把 ❌/⚠️ 行转为 GateIssue。G8 是**报告级**，不阻塞装配（装配失败已有 fail 路径）。

**验证**：`tests/components/test_plan2build_pipeline.py`、`tests/components/test_architecture_plan.py` 全绿（59 passed）。更新了 1 个断言（G8 加入门禁列表）。

---

## 5. 批次 E：校验维度补齐（P2，长线）

### E1. 组件几何合理性（`app/tools/component_tools.py`）

**问题**：`validate_cornice_placement` 只查 `len(path)>=2`/`len(profile)>=3`；`fix_cornice_placement` 直接写死默认 `path=[[0,0,0],[5,0,0]]`，产出"合法但错误"的几何。

**改动**：
- cornice 校验增加 path 每段总长度 ≥0.05m、profile 非退化（`_profile_is_degenerate` 用 shoelace 面积判共线）。
- `fix_cornice_placement` 按宿主屋顶范围推导保守默认 path（`_default_path_for`），不再写死。
- light 校验增加 position 有限性、Y 不落地下。

### E2. 风格预选前移（`app/agent/nodes/classifier_node.py`、`app/agent/prompts.py`）

**问题**：风格选择发生在主体装配完成之后（`style_review`），而 architecture / floor_plan / material 三个节点生成时完全不知道最终风格包。LLM 画平屋顶、风格包却要求中式坡屋顶，只能靠 G7 事后拦。

**改动**：
- `classifier_node` 对 generate 意图用 `style_registry.recommend` 做规则预选，输出 `style_preference`（候选风格 id 列表，不调 LLM）。
- `graph_state.py` 新增 `style_preference` 字段。
- `build_architecture_plan_prompt` / `build_floor_plan_prompt` / `build_material_plan_prompt` 注入 `_style_preference_section`（候选风格及其屋顶/体量倾向约束）。
- `style_review` 仍由用户最终确认/改选。

### E3. RAG 事实校验接入流水线（`app/services/agent_service.py`）

**问题**：`FactualValidator`（`app/agent/validators/factual_validator.py`）是死代码，从未接入生成校验。

**改动**：`run_validation_pipeline` 追加 Step 11 `validate_domain_facts`，按 `domain_schema.yaml` 的实体尺寸约束校验 Blueprint。**绕过** `FactualValidator.validate_batch`（它内部 `asyncio.run` 无法在 LangGraph 事件循环内执行），改为同步调用 `_validate_ranges`/`_validate_enums`。

**验证**：真实装配输出 Step 11 通过（38 个实体，0 错误）。

---

# 第二部分：知识库 / RAG 优化

## 6. 设计评估结论（先看全貌再动）

审计确认知识库**整体设计合理成熟**：分层（MINIMAL 注入 system / FULL+RAG / README 导航）、config.yaml+frontmatter 双层 metadata、`<!-- rag-meta -->` 实体级 metadata、分片器保护 JSON/表格、内容哈希去重、成熟度惩罚排序、访问控制、RAGTrace 观测——都是一线 RAG 系统的正确做法。

三类实质问题按影响排序：
1. **契约冲突（P0）**：roofType 枚举、interaction/initiallyOn 必填性、别墅双源、opening 残留。
2. **缺失与分片（P1）**：无 stair/light 知识文档、天窗无受支持 recipe、超大 JSON 块。
3. **metadata 打磨（P2）**：topic 错位、primary_terms 混入未实现字段、v1.0 遗留未标注。

检索链路另有 **5 处死代码未接入**（hybrid_retriever、query_rewriter、query_planner、config.rerank、rag_calibration 自动回写）——本轮不动，列为下一阶段。

## 7. 批次 K1：统一契约冲突（P0）

### K1-1. roofType 枚举统一（`storage/knowledge_base/BLUEPRINT-SPEC-FULL.md`）

**问题**：FULL 只列 3 种 `roofType`（gable/hip/flat），MINIMAL 和代码 `spatial_tools.py:1005` 都是 6 种（含 dome/chinese_curved/chinese_pagoda）。LLM 读到 FULL 会漏掉中式屋顶。

**改动**：FULL 补全为 6 类，与 MINIMAL/编译器对齐。

### K1-2. interaction / initiallyOn 必填性闭环（文档 + 校验器）

**问题**：door/window `interaction` 必填性**五方矛盾**——MINIMAL（window 必填）/ FULL（都可选）/ registry（door 必填、window 非必填）/ spatial_tools 校验器（都不强制）/ windows-supported（可选）。`light.initiallyOn` 三处矛盾。

**改动**（对齐代码实现的权威口径）：
- MINIMAL：window interaction 从"必填"改"推荐可选"；door 保持必填并加"与编译器校验一致"说明；light.initiallyOn 从"必填"改"可选，默认 true"。
- **`app/tools/spatial_tools.py:1111`：door 必填字段加入 `interaction`**（与 registry `component_registry.py:156` 一致），window 不加。
- FULL / windows-supported 保持一致（可选）。

结果："文档要求 + registry 契约 + 校验器强制"三方对 door 一致。

### K1-3. 消除别墅双源（`storage/knowledge_base/building_types/catalog/villas.md`）

**问题**：`catalog/villas.md` 用 `opening×N` 老模型，`residential/villas.md` 明确禁止 `opening` 当门窗——同一知识库对"别墅门/窗怎么写"给出两个相反答案。

**改动**：`catalog/villas.md` 降级为**纯路由入口**（保留 frontmatter + 语义说明，删除变体 A/B/C 构件清单和最少可行 JSON），指向 `residential/villas.md`。

### K1-4. 清理 opening 残留（catalog 五文件 + FULL）

**改动**：
- `cabins.md` / `courtyards.md` / `towers.md`：`opening×N` 门窗写法改为 `door`/`window` 组件（`opening` 只用于真正的裁洞，如箭孔）。
- FULL 的 `2.2.3 开口 (Opening)` 段标注作用边界：`opening` 只用于"在墙上裁洞"，门窗用 `geometry.components` 的 `door`/`window` 组合构件。

## 8. 批次 K2：补齐缺失文档（P1）

### K2-1. 新增 `components/stair.md`

**问题**：`stair` 是 stable 元素且有专门 resolver/校验，但 KB 无 `components/stair.md`。楼梯的直跑限制、踏步推算、两端落地约束等关键规则缺失。

**内容**：必填字段与语义、硬约束（`from[1] < to[1]`）、踏步推算（rise 0.14-0.20m、单段 ≤12-14 步）、多段折跑/带平台拼接配方、常见错误表。

### K2-2. 新增 `components/light.md`

**问题**：`light` 是 components 支持类型，但无独立参数契约文档。

**内容**：必填/可选字段、fixtureType（bulb/table_lamp）与 lightType（point/spot）不混用、initiallyOn 权威语义（可选、默认 true）、常见错误。

### K2-3. 天窗降级 recipe（`components/windows.md`）

**问题**：天窗用 `opening.parentRoof` 是 proposed 且引擎明确不支持（`engine-capability-boundaries.md:157`）。

**改动**：改为受支持的近似——屋顶上方用 `primitive.box` 材质 `glass` 组透光外壳；标注"几何近似，不产生真实开洞；window 不能挂 roof"。

### K2-4. 超大 JSON 标注（`residential/villas.md`）

**改动**：完整 `.wild` 参考蓝图标注"参考用，不需逐字复制；生成时按需求精简字段"。

## 9. 批次 K3：metadata 打磨（P2）

- **topic 修正**：catalog 五文件 `topic: definition` → `assembly`（实际内容是构件清单/组装而非定义）。
- **primary_terms 清理**：`windows.md` 剔除 `mullion`/`sashType`（未实现字段），`doors.md` 剔除 `leafCount`/`hingeSide`。
- **v1.0 遗留标注**：FULL 的 `behaviors.scripts.on_click` 标注为遗留，指向现行 `interaction.mode` / `light` 组件。
- **补 rag-meta**：给 catalog 各变体（四角亭/八角亭/廊架/标准木屋/前廊木屋/四合院/地中海庭院/中世纪石塔）补 `<!-- rag-meta -->`，使"中式八角凉亭"等可独立召回。

---

# 第三部分：验证与学到的教训

## 10. 最终验证

### 测试套件（核心 7 目录）

```
agent:      44 passed
blueprint:  29 passed
components: 123 passed
misc:       40 passed
network:    40 passed
repair:     28 passed
validators: 50 passed
--------------------------------
合计:       354 passed, 0 failed
```

另：RAG 单测 45 passed（排除 `test_eval_retrieval_metrics.py`——它是集成评测脚本，会生成 report.md 干扰 pytest 汇总行）。

### RAG 评测（`scripts/rag/eval_retrieval.py`，hash 模式 + 临时索引，60 条用例）

```
Hit@5=85.7%   Recall@5=85.7%   MRR=0.730   空召回 0/60 (0.0%)   异常 0
```

对照 `evals/rag_quality_gate.json` 门槛（min_hit_at_k=0.55 / min_recall_at_k=0.50 / min_mrr=0.35）**全部达标**。关键命中确认：bt_villa 正确命中 `residential/villas.md`（catalog 降级后路由生效）、bt_pavilion 命中 `pavilions.md`。

> 注：hash 模式是关键词向量（`HashEmbeddingFunction`），真实语义 embedding（`qwen3.7-text-embedding`）下指标通常更高。hash 模式用于验证流程与回归。

### 测试基础设施备注

- pytest 需 `PYTHONPATH=.`（`pyproject.toml` 未配置 pythonpath）。
- Windows 上 `-p no:capture` 可能触发 pytest capture I/O 崩溃；分目录跑更稳。
- `test_eval_retrieval_metrics.py` 运行会生成 `report.md`，不影响代码，可清理。

## 11. 学到的教训（本轮反复出现的模式）

1. **校验器"判定口径"比"校验内容"更关键**。系统有完善的校验器，但 severity 判定依赖文本 emoji（`"❌" in output`），导致一堆 ⚠️ 级几何错误以 `complete` 交付。**判定要结构化，不要依赖文本格式**。
2. **"整体回退"是精细度的最大杀手**。volumes 一重叠就整份丢弃 LLM 设计 → 改为逐项修复后，LLM 的设计得以保留。**能局部修复就别整体回退**。
3. **文档与代码必须同源**。roofType/interaction 的冲突全来自"文档要求"和"代码实现"不同步。**改代码契约时要同步改文档，反之亦然**（本轮通过让 spatial_tools 与 registry 对齐 + 文档对齐，三方闭环）。
4. **"只写了代码没接入"是隐性债务**。HybridRetriever、QueryRewriter、QueryPlanner、rag_calibration、config.rerank 都写了但没接入主链路。**接入比新写更有价值**。
5. **`asyncio.run` 不能在事件循环内调用**。`FactualValidator.validate_batch` 因此在 LangGraph 里崩溃，需改用同步内部方法。
6. **知识库双源/旧模型残留会污染召回**。别墅双源给 LLM 两个相反答案，降级为路由入口后，评测确认命中正确指向详细配方。

## 12. 后续方向（明确未做，留待下一阶段）

1. **提交固化**两轮改动（改动面大，建议分批 commit）。
2. **检索链路增强**：接入 `hybrid_retriever`（BM25+RRF）、落地 `config.rerank`（bge-reranker）、接入 `query_planner`（确定性别名解析）、校准并启用检索门控（`max_distance` 目前为 None，Gate 形同虚设）、处理 hash fallback 静默降级。
3. **检索评测 top_k 与生产对齐**（eval 默认 5，生产 6）。

---

## 附录：本轮改动文件清单

### 第一轮（LangGraph）
```
M  app/agent/architecture_plan.py      (volumes 逐项修复、外法向判定、网格吸附、槽位重排)
M  app/agent/graph_state.py            (style_preference 字段)
M  app/agent/llm_invocation.py         (invoke_llm 退避重试)
M  app/agent/nodes/architecture_node.py (格式恢复接入)
M  app/agent/nodes/base_component_node.py (组件 JSON 恢复 + json_parse_failed)
M  app/agent/nodes/classifier_node.py  (风格预选)
M  app/agent/nodes/execution_plan_node.py (格式恢复接入)
M  app/agent/nodes/floor_plan_design_node.py (格式恢复接入)
M  app/agent/nodes/material_plan_node.py (格式恢复接入)
M  app/agent/nodes/merge_node.py       (_collect_json_parse_failures)
M  app/agent/plan2build/gates.py       (G3 容差、G8 碰撞校验)
M  app/agent/prompts.py                (风格预选注入)
M  app/agent/spatial_geometry.py       (snap_to_grid)
M  app/agent/spatial_plan.py           (内墙端点吸附)
M  app/agent/validation_issues.py      (指纹加入消息哈希)
A  app/agent/format_recovery.py        (共享格式恢复)
M  app/services/agent_delivery.py      (警告门禁)
M  app/services/agent_service.py       (severity 结构化、Step 11 事实校验)
M  app/tools/component_tools.py        (cornice/light 几何合理性)
M  tests/components/test_plan2build_pipeline.py
M  tests/repair/test_targeted_repair_tools.py
```

### 第二轮（知识库 + 1 校验器字段）
```
M  app/tools/spatial_tools.py          (door 必填加入 interaction)
M  storage/knowledge_base/BLUEPRINT-SPEC-FULL.md    (roofType 6 类、opening 边界、v1.0 标注)
M  storage/knowledge_base/BLUEPRINT-SPEC-MINIMAL.md (interaction/initiallyOn 统一)
M  storage/knowledge_base/building_types/catalog/cabins.md     (opening→door/window、topic、rag-meta)
M  storage/knowledge_base/building_types/catalog/courtyards.md (同上)
M  storage/knowledge_base/building_types/catalog/pavilions.md  (同上)
M  storage/knowledge_base/building_types/catalog/towers.md     (同上)
M  storage/knowledge_base/building_types/catalog/villas.md     (降级为路由入口)
M  storage/knowledge_base/building_types/residential/villas.md (超大 JSON 标注)
M  storage/knowledge_base/components/doors.md    (primary_terms 清理)
M  storage/knowledge_base/components/windows.md  (primary_terms 清理、天窗降级)
A  storage/knowledge_base/components/light.md    (新增灯具参数契约)
A  storage/knowledge_base/components/stair.md    (新增楼梯参数契约)
```
