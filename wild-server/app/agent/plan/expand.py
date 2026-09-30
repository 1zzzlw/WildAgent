"""把方案与骨架产物确定性展开为条目列表。

对应《动态节点设计规划》§3.2/§3.3：**模型定策略、程序定条目**。

本模块不调用模型。本次要覆盖哪些构件，来自骨架节点已经产出的
``suggested_components`` 与设计清单 ``component_quota``（这两者本身就是模型的策略输出），
因此从"策略"到"条目"的这一步可以完全确定性地完成：

- 同一份 state 两次展开必须得到逐字节相同的条目序列；
- 条目 id 形如 ``generate_window_01`` / ``merge_window_01`` / ``merge_all_01``，可读且可追溯；
- 容器顺序决定执行顺序，不做排序也不依赖字典遍历顺序。

条目形态（§3.3）：**每组一条 generate + 一条批次 merge**，末尾收尾一条 merge + 一条 validate::

    generate_door_01 → merge_door_01 → generate_window_02 → merge_window_02 → merge_all_01 → validate_all_01

批次 merge 只"并入"，收尾 merge 才"归一"（配额强制 + 全局归一化 + 校验修复循环）——
判据见 ``generation/assembly_workflow.py`` 的模块说明。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.agent.generation.components import (
    get_implemented_components,
    resolve_component_suggestions,
)
from app.agent.plan.capability import capability_gap_items, object_gap_items
from app.agent.plan.contracts import (
    ItemRun,
    PlanDocument,
    PlanHistoryEntry,
    PlanItem,
    PlanKindStrategy,
    PlanStrategy,
)
from app.agent.plan.store import new_plan
from app.agent.generation.slot_utils import component_slots, slot_ids_for

#: 档位预算（§3.5）。数值单调递增，且每档都有上限——高档位是"允许更贵"，不是"不设限"。
#:
#: 迭代上限必须高于**最坏重试路径**（条目数 × per-item 重试上限 + merge/validate 两步）：
#: 否则一条顽固条目会把队列后半段锒死，用户拿到的是"没跑完"而不是"局部失败但交付"。
#: 数值是初值，双跑实测后修正，调整时保持单调。
DETAIL_BUDGET: dict[str, dict[str, int]] = {
    "minimal": {"iterations": 4, "llm_calls": 6, "max_items": 8},
    "simple": {"iterations": 6, "llm_calls": 10, "max_items": 12},
    "standard": {"iterations": 12, "llm_calls": 24, "max_items": 24},
    "detailed": {"iterations": 20, "llm_calls": 40, "max_items": 40},
}


def plan_budget(level: str) -> dict[str, int]:
    """按档位取预算；未知档位按 standard 处理（不猜测、不报错）。"""

    return dict(DETAIL_BUDGET.get(level, DETAIL_BUDGET["standard"]))


def resolve_detail_level(state: dict[str, Any]) -> str:
    """从已批准方案里读档位；读不到时按 standard 兜底。

    档位由界面给定并写进方案，节点只读不推断（§3.5）。
    """
    # 默认使用标准档位（粒度选择已下线，2026-09-30）
    return "standard"


def _component_order() -> dict[str, int]:
    """构件类型在注册表里的顺序，用作确定性排序键。"""

    return {
        config.component_type: index
        for index, config in enumerate(get_implemented_components())
    }


def compile_gap_summary(state: dict[str, Any]) -> dict[str, Any]:
    """从 ``compile_report`` 提取**图纸级缺口**的紧凑摘要（纯函数）。

    用户指令：plan 不该只数配额——每个生成条目要知道自己在
    补图纸上的哪个洞。唯一事实源是编译节点的诊断：

    - ``uncompiled``：配额点名但编译器没有派生规则的类型 → 交模型通道补；
    - ``defects``：编译器报出的图纸缺陷（schema/结构/约束）→ 生成与修复都该看到。

    返回空 dict 表示"图纸没有缺口或编译报告不存在"，两个消费点（条目参数、
    策略提示词）都按"无缺口"处理。
    """

    report = state.get("compile_report")
    if not isinstance(report, dict):
        return {}
    gaps: dict[str, Any] = {}
    uncompiled = [str(kind) for kind in (report.get("uncompiled") or []) if kind]
    if uncompiled:
        gaps["uncompiled"] = uncompiled
    defects = [
        defect for defect in (report.get("defects") or [])
        if isinstance(defect, dict)
    ]
    if defects:
        gaps["defect_count"] = len(defects)
        gaps["defects"] = [
            {
                "code": str(defect.get("code") or ""),
                "severity": str(defect.get("severity") or ""),
                "evidence": str(defect.get("evidence") or "")[:200],
            }
            for defect in defects[:8]
        ]
        if len(defects) > 8:
            gaps["defects_truncated"] = True
    return gaps


def _requested_kinds(state: dict[str, Any]) -> list[str]:
    from app.design.resolver import is_object_plan

    plan = state.get("architecture_plan")
    design_brief = state.get("design_brief")
    quota = design_brief.get("component_quota", {}) if isinstance(design_brief, dict) else {}
    # 物件场景必须显式告诉归一器"这里没有基础组件"：否则"一条建议都没有"会落到
    # 门/窗/屋顶这个建筑默认值上，一个物件场景凭空长出三扇门和一个屋顶。
    # 判据复用 `is_object_plan`，与方案层、材质层同源，不在这里另判一次。
    object_scene = is_object_plan(plan if isinstance(plan, dict) else None)
    resolved = resolve_component_suggestions(
        list(state.get("suggested_components") or []),
        state.get("user_message", ""),
        quota if isinstance(quota, dict) else {},
        object_scene=object_scene,
    )
    order = _component_order()
    # 开放集通道（用户决策 2026-09-29）：未注册类型不再被 `kind in order` 丢弃——
    # 它们排在已知类型之后（generic_component_config 兜底生成）。
    return sorted(
        set(resolved),
        key=lambda kind: (order.get(kind, len(order)), kind),
    )


def _produced_kinds(blueprint: Any) -> set[str]:
    """骨架/编译蓝图里**已经存在**的构件类型。

    建筑链批准后走确定性编译，结构/门窗/屋顶/阳台/栏杆/雨篷都是一次算完的；再为这些
    类型派 ``generate`` 条目就是让模型把同样的东西重做一遍，还要多付一轮 merge + 校验。
    实测（2026-09-28 真模型探针）：编译已产出 door/window/roof，plan 仍派
    ``generate_door`` / ``generate_window`` / ``generate_roof``，白烧约 200s 模型时间，
    且窗被生成两遍（27 → 54）。

    物件链的骨架是空容器（``elements``/``components`` 皆空）⇒ 这里恒为空集，
    ``generate`` 条目照常派发，**不改变物件链的行为**。
    """

    if not isinstance(blueprint, dict):
        return set()
    geometry = blueprint.get("geometry") or {}
    return {
        str(entity.get("type"))
        for entity in [
            *(geometry.get("elements") or []),
            *(geometry.get("components") or []),
        ]
        if isinstance(entity, dict) and entity.get("type")
    }


def _drop_produced(
    entries: list[PlanKindStrategy], state: dict[str, Any]
) -> tuple[list[PlanKindStrategy], list[str]]:
    """剔除"产物里已经有了"的类型，返回 ``(保留的策略, 被剔除的类型名)``。

    这是**唯一**的抑制闸口，两条策略路径都从它过：

    - 模型给了策略时走 ``ordered_kinds(strategy)``；
    - 模型不可用时走确定性降级（``_requested_kinds``）。

    原先只有第二条路径带这个过滤，因为当初的判据是"常规通路下产物里没有构件"；
    建筑链改走确定性编译后该前提已不成立（编译产物就含门/窗/屋顶），
    过滤必须提到两条路径的公共收口处，否则模型策略路径会重复派发。
    """

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


def _slot_ids_for(design_brief: Any, kind: str) -> list[str]:
    """取任意构件类型在设计清单中的精确槽位 id。"""

    return slot_ids_for(design_brief, kind)


def _quota_for(design_brief: Any, kind: str) -> dict[str, Any]:
    if not isinstance(design_brief, dict):
        return {}
    quota = design_brief.get("component_quota", {})
    if not isinstance(quota, dict):
        return {}
    entry = quota.get(kind)
    return dict(entry) if isinstance(entry, dict) else {}


def ordered_kinds(strategy: PlanStrategy) -> list[PlanKindStrategy]:
    """按注册表顺序排列策略：条目顺序只由程序决定，与模型输出顺序无关。"""

    order = _component_order()
    return sorted(
        strategy.kinds,
        key=lambda entry: (order.get(entry.kind, len(order)), entry.kind),
    )


def expand_plan(
    state: dict[str, Any],
    *,
    strategy: PlanStrategy | None = None,
    detail_level: str | None = None,
) -> PlanDocument:
    """展开条目列表：每个构件一条 generate 紧跟一条批次 merge，末尾收尾 merge + validate。

    **策略进、条目出**：``strategy`` 是模型给的"做什么"，本函数只做
    "怎么排"。没给策略时用确定性降级（骨架建议），两条路径产出同一种数据结构。

    条目形态:

        generate_door_01 → merge_door_01 → generate_window_02 → merge_window_02
                        → merge_all_01 → validate_all_01

    为什么每组都要跟一条 merge：批次合并让"产物已并进蓝图"成为分组级的可观测事实，
    对账（``reconcile``）才能按组判定完成，而不是等最后一刻一把梭。批次合并本身
    **不删不改**，所以未到场分组不会被误伤（见 ``generation/assembly_workflow.py``）。

    最后追加的是**能力缺口条目**：命中已知做不到的能力（房间平面、家具、
    场地语义）时生成 ``unsupported`` 条目。它们是终态，不会被派发，只进交付清单。
    """

    # 定档位和预算
    level = (
        detail_level
        or (strategy.detail_level if strategy is not None else None)
        or resolve_detail_level(state)
    )
    budget = plan_budget(level)

    # 有策略 → ordered_kinds：按注册表顺序重排，条目顺序只由程序定，与模型输出顺序无关
    # 没策略 → _requested_kinds：从骨架建议 suggested_components + 配额推导
    design_brief = state.get("design_brief")
    entries = (
        ordered_kinds(strategy)
        if strategy is not None
        else [PlanKindStrategy(kind=kind) for kind in _requested_kinds(state)]
    )

    # 产物里已有的类型一律不再派 generate——两条策略路径共用这一个闸口，
    entries, suppressed = _drop_produced(entries, state)
    if suppressed:
        logger.info(
            f"[plan] 编译器/骨架已产出 {', '.join(sorted(suppressed))}，"
            "不再派发这些类型的 generate 条目"
        )

    labels = {config.component_type: config.label for config in get_implemented_components()}
    blueprint_gaps = compile_gap_summary(state)
    uncompiled_kinds = set(blueprint_gaps.get("uncompiled") or [])
    items: list[PlanItem] = []
    generate_ids: list[str] = []
    batch_merge_ids: list[str] = []

    for index, entry in enumerate(entries, start=1):
        kind = entry.kind
        source_slots = _slot_ids_for(design_brief, kind)
        quota = _quota_for(design_brief, kind)
        slot_count = len(component_slots(design_brief, kind))
        batch_size = slot_count or int(quota.get("min") or quota.get("max") or 1)
        item_id = f"generate_{kind}_{index:02d}"
        generate_ids.append(item_id)
        params = {
            "component_type": kind,
            "subtype": entry.subtype,
            "guidance": entry.guidance,
            "reason": entry.reason,
            "execution_mode": entry.execution_mode,
            "parallel_group": entry.parallel_group,
            "batch_reason": entry.batch_reason,
        }
        if kind in uncompiled_kinds:
            # 图纸缺口注入：条目要知道自己在补哪个洞——
            # 编译器点名了该类型却没产出，这条 generate 就是模型通道的补洞任务。
            params["blueprint_gap"] = (
                "编译器没有产出该类型（compile_report.uncompiled）："
                "本条目负责把它补进蓝图，先按知识库检索到的契约生成。"
            )
        items.append(
            PlanItem(
                id=item_id,
                op="generate",
                kind=kind,
                label=(
                    f"批量生成{labels.get(kind, kind)} × {batch_size}"
                    if batch_size > 1 else f"生成{labels.get(kind, kind)}"
                ),
                target={
                    "source_slots": source_slots,
                    "quota": quota,
                    "batch_size": batch_size,
                },
                params=params,
                run=ItemRun(max_attempts=3),
            )
        )

        merge_id = f"merge_{kind}_{index:02d}"
        batch_merge_ids.append(merge_id)
        items.append(
            PlanItem(
                id=merge_id,
                op="merge",
                kind=kind,
                label=f"并入{labels.get(kind, kind)}",
                target={"fragments": [item_id], "component_types": [kind]},
                params={"scope": "batch", "component_types": [kind]},
                depends_on=[item_id],
                run=ItemRun(max_attempts=1),
            )
        )

    merge_id = "merge_all_01"
    items.append(
        PlanItem(
            id=merge_id,
            op="merge",
            kind="all",
            label="收尾合并与归一",
            target={"fragments": list(batch_merge_ids)},
            params={"scope": "final"},
            depends_on=list(batch_merge_ids),
            run=ItemRun(max_attempts=1),
        )
    )

    items.append(
        PlanItem(
            id="validate_all_01",
            op="validate",
            kind="all",
            label="全量校验",
            target={"blueprint": "merged_blueprint"},
            depends_on=[merge_id],
            params={"validators": "all"},
            run=ItemRun(max_attempts=1),
        )
    )

    # 脚本映射节点化：编译报告有缺陷时就地派 repair 条目——
    # "大模型调用脚本工具（fix_*），脚本实现不了的模型按蓝图语言规则补充"。
    # 依赖只挂收尾合并（不挂 validate）：validate 报错是**预期输入**而不是失败，
    # 挂在它上面会让 repair 永远 blocked。校验干净时该条目是廉价空转（无模型调用）。
    if blueprint_gaps.get("defect_count"):
        items.append(
            PlanItem(
                id="repair_compile_defects_01",
                op="repair",
                kind="all",
                label="脚本工具修复编译缺陷，剩余由模型补充",
                target={"blueprint": "merged_blueprint"},
                params={
                    "source": "compile_report.defects",
                    "defect_count": blueprint_gaps.get("defect_count"),
                },
                depends_on=[merge_id],
                run=ItemRun(max_attempts=1),
            )
        )

    # 迭代预算必须覆盖"每条条目各跑一次"这条最短路径。条目数从 N+2 变成 2N+2 之后，
    # 档位值（按旧形态标定）会先于队列跑空触发收尾，用户拿到的是"没跑完"。
    # 档位值继续作为上限的参考，只抬高不压低。能力缺口条目是终态、不会被派发，不计入。
    budget["iterations"] = max(budget["iterations"], len(items) + 4)

    # 能力缺口：标记而不阻断。放在最后，顺序固定，不参与执行顺序。
    items.extend(capability_gap_items(state.get("user_message", "")))
    # 物件侧的同类缺口：部位不同（本轮方案里"点名了但表达不了"的物件），
    # 口径相同——终态、不派发、只进交付清单。见 `capability.object_gap_items`。
    items.extend(object_gap_items(state.get("architecture_plan")))

    plan = new_plan(items, detail_level=level, budget=budget)
    if strategy is not None:
        # 策略来源进审计：交付清单要能回答"这次为什么做这些构件"。
        plan.history.append(
            PlanHistoryEntry(
                revision=plan.revision,
                action=f"strategy:{strategy.source}",
                item_ids=list(generate_ids),
                reason=strategy.notes or _strategy_reason(strategy),
            )
        )
    if suppressed:
        # 抑制也要进审计：模型"要了别的构件"与"程序没给它派"是两回事，
        # 交付清单要能回答"模型点名 X 为什么没有条目"。
        plan.history.append(
            PlanHistoryEntry(
                revision=plan.revision,
                action="suppress:produced",
                reason=f"产物已包含 {', '.join(sorted(suppressed))}，不再派发 generate",
            )
        )
    return plan


def _strategy_reason(strategy: PlanStrategy) -> str:
    parts = [entry.reason for entry in strategy.kinds if entry.reason]
    return "；".join(parts)[:500]
