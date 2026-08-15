# 建筑 Blueprint 诊断报告（对照 building-blueprint-diagnostics skill 复盘）

本报告按 `.codex/skills/building-blueprint-diagnostics/SKILL.md` 的"证据/假设/根因分类/修复层级"格式，复盘本次会话的两个真实缺陷，并核对修复是否满足该 skill 的"规则升级标准"。

---

## 案例一：单面墙请求被回退成别墅

### 结论
骨架阶段的复杂度校验 `evaluate_skeleton_complexity` 把"用户明确只要一面墙"的极简结构，误判成"模型未兑现方案复杂度目标"，触发了 `build_deterministic_skeleton` 体量化回退，导致输出一整栋别墅。

### 证据
- 用户输入：`生成一个玻璃幕墙，只要一面墙就可以`。
- 日志：`模型骨架未达到组合体量与结构数量目标，正在启用体量化安全回退...`（`skeleton_node.py`）。
- 代码入口：`app/agent/architecture_plan.py::evaluate_skeleton_complexity`。
  - 该函数对"非 detailed"档位也执行 `realization_checks`，其中 `storey_wall_levels` 要求 `expected_wall_base_levels ⊆ wall_base_levels`；单面墙只有 `{0}`，而默认 `standard` 方案期望 `{0, 3.2}`（两层），故 `meets_target=False`。
- 触发回退的根因：`resolve_complexity_profile` 只区分 `simple/standard/detailed`，没有识别"极简结构"（一面墙/一堵墙/单个构件）这一档。

### 影响
- 结构语义：用户要的"单面幕墙墙"被替换成完整体量化建筑，几何与意图完全不符。
- 后续组件生成：基于错误骨架继续生成门窗屋顶，放大偏差。
- 保存门禁：回退后的建筑通过校验并保存，掩盖了意图丢失。

### 分类
`model_instruction`（模型遵守了用户要求，但程序缺少可判定的复杂度档位门禁）。

### 修复层级
`prompt/协议约束` + `deterministic fix`（新增复杂度档位 + 复杂度判定豁免）。

### 建议（已实施）
1. `_COMPLEXITY_PROFILES` 新增 `minimal` 档（`target_structural_elements=1, min_volumes=1, min_detail_packages=0`）。
2. `resolve_complexity_profile` 识别极简关键词（一面墙/一堵墙/单面墙/只要一面/单个构件…）→ `minimal`。
3. `_default_detail_packages` 对 `minimal` 返回空（不附加 canopy/balcony 等）。
4. `evaluate_skeleton_complexity` 对 `minimal` 直接 `meets_target=True`。

### 未确认
- 需要真实生成验证：`minimal` 档位下，后续 door/window/roof 组件节点仍会按 `required_components` 派发，可能与"只要一面墙"的最终期望仍有出入（见"遗留"）。

---

## 案例二：高层玻璃幕墙没用上玻璃

### 结论
两个独立缺陷叠加：(a) `evaluate_skeleton_complexity` 对 `schematic`（高层示意）仍执行 `volume_plan_conformance` 与 `storey_wall_levels` 两项"完整模式"检查，误杀连续外壳墙骨架并回退；(b) 材质方案把 `wall → facade_primary → wall_finish`，没有任何"玻璃幕墙 → 外墙用 glass"的映射，导致外墙是不透明墙板。

### 证据
- 用户输入：`生成一个高层玻璃幕墙商业综合体`；方案 `massing.representation_mode=schematic`（30 层、modeled_floors=10）。
- 日志：`模型骨架未达到组合体量与结构数量目标...`（同案例一）。
- 最终 Blueprint：外墙 `material: "wall_finish"`（非 glass），32 扇窗稀疏分布。
- 代码入口：
  - `app/agent/architecture_plan.py::evaluate_skeleton_complexity`：`schematic` 时 `storey_wall_levels` 仍要求逐层墙标高（连续外壳墙只有 `{0}`，期望 `{0,4,...,116}`），`volume_plan_conformance` 要求逐层楼板精确匹配（代表性楼板不匹配）。
  - `app/agent/nodes/material_plan_node.py`：`ELEMENT_ROLE["wall"]="facade_primary"` → `wall_finish`，无幕墙分支。

### 影响
- 视觉/结构语义：应呈现玻璃幕墙的建筑变成混凝土/抹灰实体墙。
- 与既有约定不一致：`merge_node._validate_design_brief_constraints` 第 381 行**已经**用 `representation_mode == "full"` 守卫逐层检查，`resolve_facade_layout` 也通过 `_expand_schematic_facade_storeys` 处理 schematic——`evaluate_skeleton_complexity` 是漏掉该守卫的唯一入口。

### 分类
(a) `model_instruction`（schematic 校验门禁缺失）；(b) `schema_contract`/`model_instruction`（材质角色映射缺失幕墙语义）。

### 修复层级
(a) `deterministic fix`（校验器按 representation_mode 豁免）；(b) `prompt/协议约束`（材质方案增加 curtainWall 语义映射）。

### 建议（已实施）
1. `evaluate_skeleton_complexity` 读取 `massing.representation_mode`，`schematic` 时把 `volume_plan_conformance`、`storey_wall_levels` 置 True（与 `merge_node` 的既有守卫对齐）。
2. `resolve_material_plan` 检测"玻璃幕墙/玻璃幕"→ 方案打 `curtainWall: true`；`apply_resolved_material_plan` 遇 `curtainWall` 时把 `wall` 元素统一指向 `glass` 物理玻璃材质，柱子等结构保持 concrete。

### 未确认
- 需要浏览器验收：玻璃外墙的物理透射（`transmission/ior/thickness`）在 `wild-core` + Three.js 渲染下的实际观感；以及 core 墙是否也应保持不透明（当前是"全部 wall → glass"的近似）。

---

## 与 skill 的"规则升级标准"核对

skill 要求规则满足 5 条才进入代码。逐条核对本次三个修复：

| 规则 | 输入是否可从 Blueprint/方案判定 | 是否≥2 种情况 | 可否复检 | 是否有参数化测试 | 是否改变方案意图 |
|---|---|---|---|---|---|
| `minimal` 复杂度档 | 从 user_message 关键词判定（生成前阶段，无 Blueprint 可依） | 是（一面墙/一堵墙/单面墙/单个构件…） | 是 | `test_minimal_request_keeps_single_wall` | 否（尊重用户极简意图） |
| `schematic` 复杂度豁免 | 从 `massing.representation_mode` 判定 | 是（任意 schematic 高层） | 是 | `test_schematic_highrise_skips_per_floor_checks` | 否（对齐既有 full/schematic 约定） |
| `curtainWall` 材质映射 | 从 user_message 关键词判定 | 是（玻璃幕墙/玻璃幕） | 是 | `test_glass_curtain_wall_maps_facade_to_glass` + `test_non_curtain_wall_keeps_opaque_facade` | 否（落实"wall+material=glass"近似） |

### 结论
三项修复都满足"通用规则 + 参数化测试、不为单栋建筑写特判"的标准；`schematic` 豁免进一步补全了 `merge_node`/`resolve_facade_layout` 已有、而 `evaluate_skeleton_complexity` 遗漏的守卫，属于"重复根因合并到已有校验器"。

---

## 遗留项处理结果（收尾）

| # | 遗留项 | 结论 | 实施 |
|---|---|---|---|
| 1 | `minimal` 档仍派发 door/window/roof | **已修复** | `_dispatch_components` 对 `minimal` 直接短路到 merge；`normalize_architecture_plan` 对 `minimal` 置 `required_components=[]` |
| 2 | 玻璃幕墙窗格密铺 | **推迟（true curtain wall）** | WILD 规范将 `wall + material=glass` 标为"近似，非 true curtain wall"；密铺网格属于未来特性，不在本轮实现 |
| 3 | core 墙也被改成 glass | **已修复** | `apply_resolved_material_plan` 只把"落在水平包围盒边界上的墙"（外墙）指向 glass，核心筒墙保持不透明 |

### 实施细节

**遗留 1（minimal 不派发组件）**
- `app/agent/graph.py::_dispatch_components`：复杂度为 `minimal` 时返回 `"merge"`，跳过门/窗/屋顶派发。
- `app/agent/architecture_plan.py::normalize_architecture_plan`：`minimal` 时 `required_components=[]`，方案自洽。
- 测试：`test_minimal_plan_has_no_required_components`、`test_minimal_complexity_skips_component_dispatch`。

**遗留 3（核心墙不透明）**
- `app/agent/nodes/material_plan_node.py::apply_resolved_material_plan`：用水平包围盒判断"外墙"（边界上的墙），仅外墙指向 glass。
- 测试：`test_curtain_wall_keeps_core_walls_opaque`。

**遗留 2（幕墙网格）**
- 判定为"true curtain wall"未来特性，理由：① WILD 契约明确 `wall + material=glass` 是接受的近似；② 用户核心诉求"外墙用玻璃"已由 glass 映射满足；③ 网格密铺需要新的幕墙窗语义（mullion 框架），属新能力而非缺陷修复。按 skill 的"不为单栋建筑打补丁、新增能力必须解决一类表面"边界，暂不硬编码。
