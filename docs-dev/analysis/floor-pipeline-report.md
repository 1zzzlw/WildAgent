# 建筑平面四步链（space_analysis→layout→openings→validate）代码勘察报告

> 勘察范围：wild-server/app/agent/nodes/{floor_space_analysis,floor_layout,floor_openings,floor_validate,floor_plan_review,floor_plan_design}_node.py、app/agent/{spatial_plan,floor_plan_rules,floor_plan_gates,wall_derivation}.py 及相关 tests。只读勘察，未改任何源码。行号均为当前文件行号。

## 1. 各节点职责与 state 读写

### floor_space_analysis（space_analysis_node.py:166-251）
- 读：`architecture_plan`(169)、`user_message`(170)、`thinking_mode`(171)、`style_preference`(196)、`execution_plan`(198)。
- 写：`floor_analysis_result`{category,source,floors,spaces_per_floor,levels?,fallback_reason}(238-239)、`floor_plan_rag_context`(240，一次 RAG 供下游复用)、`floor_space_analysis_diag`(241-250)。
- 模型无效时的确定性兜底 `_fallback_space_analysis`(19-100) 输出 4~6 个模板空间；`_normalize_space_analysis`(103-163) 要求 level 覆盖 1..modeled_floors 完整且每层有空间(145-150)，否则整体返回 None→兜底(228-229)。

### floor_layout（layout_node.py:160-297）
- 读：`architecture_plan`、`floor_analysis_result`、`user_message`、`thinking_mode`、`floor_plan_rag_context`(219)、`execution_plan`。
- 写：`floor_layout_result`{source,fallback_reason?,levels[…]}、`floor_layout_diag`(含 `rag_reused`、`skipped_due_to_upstream_fallback`)。
- 上游非 model 时跳过 LLM 直接产出“竖条带预览”`_build_levels`(55-90，`_layout_spaces`20-52)(181-213)。模型路径 `_normalize_layout`(93-157)：每层空间数必须 ≥ max(2,程序空间数)(123-125)、每个空间必须有 bounds/polygon/polygons(133-143)，缺一层即 None→兜底(264-270)。

### floor_openings（openings_node.py:49-181）
- 读：`architecture_plan`、`floor_layout_result`、`user_message`、`thinking_mode`、`floor_plan_rag_context`(103)、`execution_plan`。
- 写：`floor_openings_result`{source,fallback_reason?,levels[+walls,openings],vertical_spaces,vertical_circulation,exterior_attachments}、`floor_openings_diag`。
- 确定性兜底 `_derive_walls_and_doors`(20-46)：用 `derive_interior_walls` 从空间公共边界成墙，每墙居中开门。`_normalize_openings`(184-233)：层级必须与 layout 完全一致(189-190)、`>1 空间且 walls 为空`直接判无效(216-217)。

### floor_validate（validate_node.py:62-154，无 LLM）
- 读：前三步 result + `architecture_plan`；`_merge_into_floor_plan`(19-59) 按层合并 layout 的 spaces 与 openings 的 walls/openings(26-33)。
- 写：`architecture_plan.spatial_plan`、`floor_plan`、`floor_plan_svg(s)`、`floor_plan_validation`、`floor_plan_notice`、`floor_plan_review_status="pending"`、`floor_plan_auto_repairing=False`、`floor_validate_diag`(136-154)。
- 顺序：merge→`normalize_spatial_plan`(93/157-166)→非 model 来源写固定 notice(94-98)→`auto_repair_floor_plan_rules`(100)→`evaluate_floor_plan_rules`(101)→两次 `validate_spatial_plan`(103-104，规则版与纯几何版)。异常兜底 111-122。

### floor_plan_review（review_node.py:14-106）
- 读：`floor_plan`、`floor_plan_revision`、`floor_plan_validation`、`floor_plan_auto_repair_count`、`floor_plan_review_history`；`is_confirmable_spatial_plan`(19-22)。
- 写：`floor_plan_review_status`(approved/revise)、`floor_plan_feedback`、`floor_plan_revision`、`floor_plan_auto_repairing/count`、历史。仅“rule_* 失败且无几何失败”且轮次<2 才自动回改(37-58)；否则 interrupt(60-65) 等用户。route(103-106)：approved→material_plan，否则→floor_space_analysis。

## 2. “模型设计被丢弃”的确切位置

**合并**：validate_node.py:86 `candidate = _merge_into_floor_plan(analysis, layout, openings, architecture_plan)`；合并后 source 为三份 source 的全模型判定(validate_node.py:35-48)。

**整体替换点**：在 `normalize_spatial_plan`（spatial_plan.py:499-830）内部，非规则类“几何校验”失败后：

```python
# spatial_plan.py:821-829
issues = validate_spatial_plan(candidate, include_rules=False)
if issues:
    candidate = _repair_plan_geometry(candidate)      # 局部修复
    candidate["rule_review"] = evaluate_floor_plan_rules(candidate)
    issues = validate_spatial_plan(candidate, include_rules=False)
if issues or len(levels) != modeled_floors:
    reason = issues[0]["message"] if issues else "模型未覆盖全部显式楼层"
    return fallback_spatial_plan(massing, reason, volumes)   # ← 整份替换
```

**替换成什么**：`fallback_spatial_plan`(157-188) 每层只放 1 个“主要空间”、walls=[]、openings=[]（`_fallback_level` 77-107，98-103/104-105）。若 2 层建筑 → summary 即“2 个空间、0 面内墙、0 个洞口”（spatial_plan.py:1303-1305 跨层求和）。这就是观察到的“几十个空间→只剩 2 个”的来源：不是删墙，而是整份候选被 1 空间/层的 fallback 替换，`fallback_reason`=首个几何问题的 message。

**局部修复只做三件事**（`_repair_plan_geometry` 833-875）：内墙端点吸附(849-855)、无内墙时补推导墙(857-862)、洞口宿主不存在时指到 repaired[0](866-874)。**从不修复空间几何**（重叠/缝隙/覆盖缺口/门位不符/不连通），因此这些错误必然走整体替换。

**触发后如何展示**：floor_validate 发现 source≠model 即写 notice：validate_node.py:94-98“模型没有产出可验证的完整平面；当前仅显示确定性故障预览，不可确认，也不会进入三维装配。”；normalize 抛异常时 111-122 同样替换并给该 notice。`is_confirmable_spatial_plan`(479-496) 只认 `source ∈ {model, deterministic_template}` 且无 error 级问题 → fallback 永远不可确认。

**佐证测试（这正是被测的“有意”行为）**：tests/components/test_spatial_plan.py:86-95（几何坏→deterministic_fallback、reason=首条 message、每层 1 空间 0 墙）、98-124（门位不符→整体 fallback）；test_floor_confirmable.py:52-75（链式 fallback 不得伪装 model）；test_floor_plan_plan_mode.py:76-96（全 fallback 链→不可确认预览）。

## 3. 内墙校验失败点（wall_not_space_boundary）

**消息出处**：`validate_spatial_plan`，spatial_plan.py:996-1030。逐段取墙路径上每段中点，向法向两侧各推 `probe=max(0.08, thickness)`（默认 0.12，994 行），要求两侧都严格包含至少一个空间（`boundary=False` 的 `contains`，1005-1011）；任一侧无空间则仅当该侧紧贴 void（中庭/井道）才放行(1012-1027)：

```python
# spatial_plan.py:1028-1029
if boundary_failed:
    issues.append({"code": "wall_not_space_boundary", ..., "message": f"内墙 {entity_id} 没有位于两个空间的公共边界上"})
```

**触发的几何条件**（任一即失败，且与“整体替换”联动）：
- 模型墙距真实公共边界 >0.25m（吸附容差，wall_derivation.py:162/189）或墙穿过 T 字交点、跨多空间边界、落在组合轮廓外沿（一侧无空间且非 void）。
- 吸附只吸“端点→边界交点”（wall_derivation.py:187-204），不保证整条墙落在公共边上；端点吸上但墙身斜穿空间也会失败。
- 空间间存在 >EPSILON(0.01m, spatial_geometry.py:13) 缝隙/坐标不一致时：墙派生与“两侧空间”判定都可能失配；未建模成空间的走道/缝会让一侧无空间。
- 同层若有重叠空间（`space_overlap` 972-974）、覆盖缺口（`incomplete_space_coverage` 975-977）、门位与 connects 两侧不符（`door_connection_mismatch` 1099-1101）、从入口不可达（`disconnected_spaces` 1117-1119）——任何一个存在，_repair 无法修复 → 整份替换（见 §2），表现为“内墙全部消失”。

“内墙 spatial_wall_1_wall_L1_A …”里的 id 是 normalize 加前缀后的模型墙 id（spatial_plan.py:652-655 `_stable_id("spatial_wall_{level}", …)`），说明该墙由模型产出（开洞步骤）、随后几何校验不过，首条错误 message 被当作 fallback_reason 展示在故障预览里。

## 4. 冗余 / 重复

1. **多套互不相通的确定性平面实现**：
   - 空间清单模板 `_fallback_space_analysis`（space_analysis_node.py:19-100，7 类关键词模板）；
   - 竖条带布局 `_layout_spaces/_build_levels`（layout_node.py:20-90）；
   - 每层单空间 `fallback_spatial_plan`（spatial_plan.py:157-188）；
   - 面积自适应 2/3/4 分区 `deterministic_baseline_spatial_plan`（191-223）与 `recover_confirmable_spatial_plan`（456-476）——**生产代码无任何调用者**（仅 tests/components/test_floor_plan_design.py、test_spatial_plan.py:251 直接测它们），是闲置的“可确认兜底”通道。
2. **同一段内墙推导逻辑被 4 处重复调用**：openings 兜底（openings_node.py:20-46）、normalize 无墙时（spatial_plan.py:679-691）、_repair 无内墙时（857-862）、auto_repair 电梯后再修一次（floor_plan_rules.py:572-575）。墙“吸附”也会被跑两遍（normalize 685、_repair 853）。
3. **规则评估重复多次**：normalize 内(820/825)、fallback 构造(187)、auto_repair(509/578)、validate_node.py:101、summary(1299)、validate_spatial_plan→rule_gate_issues(floor_plan_rules.py:333-351) 各自再 evaluate；单轮 pipeline 重复执行约 5-8 次（每次含质心/多边形/路径计算）。
4. **层结构与 envelope/elevation/height 重复推算**：_build_levels(79-89) 算一遍，normalize 又用 `_level_regions/_level_envelopes`（507-508/142-154）重建一遍并覆盖 raw（750-751）。
5. **冗余/死 prompt**：`build_floor_validate_prompt`（prompts.py:576）定义后无任何调用（floor_validate 早已不调 LLM，注释见 validate_node.py:80-82）；旧 `build_floor_plan_prompt` 仅供旧节点。
6. **state 旧键/兼容键**：graph_state.py:68 `floor_plan_design_diag` 与新四键(71-78)并存；`floor_plan*` 输出键由旧 floor_plan_design 与新 floor_validate 两套节点写同一组 key（graph_state.py:80-90），靠“不在同一路径”避免冲突。
7. **RAG**：四步链已做去重（第一步检索并存 `floor_plan_rag_context`，layout/openings 复用，为空才补查一次，layout_node.py:219-232 / openings_node.py:103-112）；但旧 floor_plan_designer 自己另发 3 个 query（design_node.py:57-61），与新链不共享。

## 5. 明确的 Bug / 自相矛盾点

1. **任何单一几何错误即丢弃整份模型设计**（spatial_plan.py:821-829）：几十个空间、几十面墙的方案只因一堵墙离公共边界略远或一个门位不符就整体换成 1 空间/层模板，且用户侧只显示首条错误。修复面(833-875)只管墙不管空间，属于最危险的“宽进严出”。
2. **“可确认兜底”通道从未接入**：deterministic_baseline/recover_confirmable 的文档自称“避免审核流程无出口”(191-201/456-476)，但生产调用链无处调用 → 模型几何失败后只能得到不可确认的 deterministic_fallback，review 又只允许它 revise（review_node.py:71-99），形成无出口死循环，与设计意图直接矛盾。
3. **revise 反馈无人消费**：floor_plan_review 失败后 route 回 floor_space_analysis（review_node.py:103-106、graph.py:455-461），但新四节点 prompt 均不含 `floor_plan_feedback`/旧 `floor_plan`（对比：旧节点 design_node.py:42/76 会吃 feedback）。自动/手动修改只是“盲跑”整条链，最多 2 轮（review_node.py:37-42）后仍照旧失败 → 退化。
4. **“公共边界”两套定义不一致**：成墙/吸附用“轴对齐边重叠采样+端点吸到边界交点”（wall_derivation.py:89-120/158-204，斜边直接跳过 114-116）；校验用“墙每段两侧 0.12m 探针必须各含一空间”（spatial_plan.py:996-1029）。两者没有共享实现，吸附“成功”的墙仍可能校验失败。
5. **楼层数不匹配即整体回退**：normalize 截断 `raw_levels[:modeled_floors]`(587) 且要求 len(levels)==modeled_floors(827)，模型少一层或多出层都会触发整份 fallback，而不是局部修补或给出明确 diff。
6. **默认参数分裂**：layout_node.py:170-171 宽缺省 10m，spatial_plan.py:118-119 宽缺省 8m（深均 8m）——无 massing 时同一条链前后两段可能拿到不同外包矩形。
7. **潜在环导入**：spatial_plan.py:15-19 顶层 import floor_plan_rules，而 floor_plan_rules.py:572 在函数内反向 `from app.agent.spatial_plan import _repair_plan_geometry`（懒加载规避，属脆弱的隐藏环）。
8. **层内空间带语义整体 deepcopy 两次**：layout 归一化(149-153)与 validate 合并(29-33)各复制一遍 spaces/walls/openings，几十空间时内存/耗时翻倍，且 openings 层整层复制 layout 内容（openings_node.py:219-224）后再被 validate 合并——纯粹的重复拷贝。

## 6. 与旧节点 floor_plan_design_node 的关系

- 新四节点**不调用、不复用**旧节点；两者只是共用同一底层库（normalize_spatial_plan / validate_spatial_plan / auto_repair_floor_plan_rules / architecture_plan_to_svgs）。
- 旧节点**仍被 graph 引用**：graph.py:307 注册 `"floor_plan_design"`，graph.py:414 保留在 plan_executor 的可路由表，429-433 有 `floor_plan_design→floor_plan_review` 条件边；nodes/__init__.py:11 仍导出。但新版默认生成意图已绕过它：architecture→floor_space_analysis（graph.py:182-186/384）；新执行计划白名单 DYNAMIC_TASK_PHASES 只含四新步骤（execution_plan.py:25-38），不含 floor_plan_design。因此旧节点仅对**旧 checkpoint/旧计划**中的 floor_plan_design 步骤保持“可续跑”兼容，正常新会话不可达。
- 两套节点写相同的 floor_plan*/architecture_plan.spatial_plan 键（graph_state.py:80-90），属“新旧同键、按路由互斥”的兼容设计。

## 给定位的结论（可执行）

1. 现象根因不在“删墙/删空间”，而在 spatial_plan.py:821-829 的整份回退闸：模型几何只要有一个 wall_not_space_boundary / overlap / coverage / 门位 / 不连通问题，_repair_plan_geometry(833) 修不了空间就会整体丢成 1 空间/层 fallback，并以其首条 message 作为预览提示（含 2 层建筑“2 空间 0 墙 0 洞口”）。
2. 内墙报错出处 = spatial_plan.py:1029；典型触发 = 墙不在真实公共边上（>0.25m 或斜穿/贴外沿/缝隙），成因与 layout/openings 两步 LLM 坐标精度及 wall_derivation 只吸端点直接相关。
3. 建议修复方向：把空间级可修问题纳入 repair 或把 wall 校验改宽松为“两端吸附成功即放行+warning”；为 deterministic_fallback 接入已有的 recover_confirmable 模板通道；让 revise 循环把 floor_plan_feedback 与旧 floor_plan 传入新节点 prompt。
