"""将已批准图纸标记展开为可执行任务。"""

from __future__ import annotations

import json
from typing import Any

from agent.utils.planning.contracts import ItemRun
from agent.utils.planning.contracts import PlanDocument
from agent.utils.planning.contracts import PlanItem
from agent.utils.planning.store import new_plan


def compile_gap_summary(state: dict[str, Any]) -> dict[str, Any]:
    """从 ``compile_report`` 提取**图纸级缺口**的紧凑摘要（纯函数）。

    用户指令：plan 不该只数配额——每个生成条目要知道自己在
    补图纸上的哪个洞。唯一事实源是编译节点的诊断：

    - ``uncompiled``：配额点名但编译器没有派生规则的类型 → 交模型通道补；
    - ``instance_dropped``：实例清单里**宿主解析不到、整条丢弃**的条目
      （``类型:宿主``）→ 该类型的生成条目要按真实宿主重写；
    - ``instance_form_rejected``：实例**形态值**不满足引擎字段契约、编译时未采纳
      （``类型.键: 原因``）→ 该类型要按知识库的字段契约重写这一步表态；
    - ``instance_form_unverified``：形态值落了、但引擎 schema 里没有该字段
      （``类型.键``）→ 静默失效，生成条目别依赖它；
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
    # 契约层不再拦宿主引用（见 `contracts._validate_component_instances`），
    # 编译器的 `dropped` 就成了"写是写了、没落地"的**唯一**通道，必须继续往下传。
    instance_dropped = [
        str(item) for item in (report.get("instance_dropped") or []) if item
    ]
    if instance_dropped:
        gaps["instance_dropped"] = instance_dropped
    # 形态表态的两类证据：值被拒（编译器**没落**）与字段闭集外（落了但引擎不认）。
    # 它们和 `instance_dropped` 是同一条口径 —— "只标记不阻断"的标记必须传到消费者手里。
    form_rejected = [
        str(item) for item in (report.get("instance_form_rejected") or []) if item
    ]
    if form_rejected:
        gaps["instance_form_rejected"] = form_rejected
    form_unverified = [
        str(item) for item in (report.get("instance_form_unverified") or []) if item
    ]
    if form_unverified:
        gaps["instance_form_unverified"] = form_unverified
    form_ignored = [
        str(item) for item in (report.get("instance_form_ignored") or []) if item
    ]
    if form_ignored:
        gaps["instance_form_ignored"] = form_ignored
    defects = [
        defect for defect in (report.get("defects") or []) if isinstance(defect, dict)
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


def _unsupported_object_items(plan: dict | None) -> list[PlanItem]:
    """将图纸里未能表达的物件列为交付清单中的不支持项。"""

    if not isinstance(plan, dict):
        return []
    raw = plan.get("unsupported_objects")
    if not isinstance(raw, list):
        return []

    items: list[PlanItem] = []
    for index, entry in enumerate(raw[:24], start=1):
        name = str(entry).strip()[:60]
        if not name:
            continue
        notice = (
            f"本次点名了「{name}」，但它既没有命中可用的物件预设，也没有给出可生成的"
            "几何组合；系统未用品类相近的物件顶替，因此本件没有产出。"
        )
        items.append(
            PlanItem(
                id=f"unsupported_object_{index:02d}",
                op="validate",  # 与能力缺口同处理：这是"判定结论"，不是一件待做的工作
                kind="object_expression",
                label=f"未能表达：{name}",
                target={"capability": "object.expression", "request": name},
                params={"notice": notice, "unsupported": True},
                status="unsupported",
                run=ItemRun(max_attempts=1, evidence=notice),
            )
        )
    return items


def _batch_load(rows: list[dict]) -> dict[str, int]:
    """按本批实际图纸内容计量。"""
    floors = set()
    for marker in rows:
        design = marker.get("design") or {}
        floor = design.get("floor", (design.get("placement") or {}).get("floor"))
        if floor is not None:
            floors.add(floor)
    dependencies = set()
    for marker in rows:
        dependencies.update(marker.get("depends_on") or [])
    return {
        "marker_count": len(rows),
        "marker_chars": len(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        ),
        "host_count": len({m["host"] for m in rows if m.get("host")}),
        "floor_count": len(floors),
        "dependency_count": len(dependencies),
    }


def _marker_batches(rows: list[dict]) -> list[list[dict]]:
    """限制单次图纸负载；单个标记保持完整，输出截断另由执行器拆分。"""
    batches, batch = [], []
    for marker in rows:
        if batch and _batch_load([*batch, marker])["marker_chars"] > 8000:
            batches.append(batch)
            batch = []
        batch.append(marker)
    if batch:
        batches.append(batch)
    return batches


def expand_design_markers(state: dict) -> PlanDocument:
    from agent.utils.components.names import resolve_component_name
    from agent.utils.design.markers import IMPLEMENTATION_STAGES
    from agent.utils.design.markers import implementation_records
    from agent.utils.design.markers import implementation_complete

    markers = (state.get("resolved_design") or {}).get("component_markers") or []
    records = implementation_records(state)
    decisions = (state.get("design_document") or {}).get("decisions", {})
    object_scene = decisions.get("kind") == "object"
    pending = {m["id"]: m for m in markers}
    owners, items = {}, []
    while pending:
        ready = [
            m
            for m in pending.values()
            if set(m.get("depends_on") or []).issubset(owners)
        ]
        if not ready:
            # 互相依附的设计共同交给模型实现，不在设计期按图算法拒绝。
            groups = {"assembly": list(pending.values())}
        elif object_scene:
            groups = {"object": ready}
        else:
            groups = {}
            for marker in ready:
                kind = resolve_component_name(marker["type"])["kind"]
                groups.setdefault(kind, []).append(marker)
        batches = []
        for component_kind, current_rows in groups.items():
            if component_kind == "assembly":
                component_batches = [current_rows]
            else:
                component_batches = _marker_batches(current_rows)
            for batch in component_batches:
                batches.append((component_kind, batch))
        for kind, rows in batches:
            task_id = f"generate_{len(items)+1}"
            complete = all(implementation_complete(records.get(m["id"])) for m in rows)
            naming = resolve_component_name(kind)
            label = "物件实现" if object_scene else naming["label"]
            if not naming["entity_type"] and kind not in {"building_body", "assembly"}:
                labels = [m.get("design", {}).get("name") for m in rows]
                label = next(
                    (
                        name.strip()
                        for name in labels
                        if isinstance(name, str) and name.strip()
                    ),
                    label,
                )
            parallel = not object_scene and kind not in {"building_body", "assembly"}
            dependency_tasks = set()
            if object_scene and items:
                dependency_tasks.add(items[-1].id)
            for marker in rows:
                for dependency in marker.get("depends_on", []):
                    if dependency in owners:
                        dependency_tasks.add(owners[dependency])
            items.append(
                PlanItem(
                    id=task_id,
                    op="generate",
                    kind=kind,
                    label=label,
                    target={"marker_ids": [m["id"] for m in rows]},
                    depends_on=sorted(dependency_tasks),
                    params={
                        "design_markers": True,
                        "design_hash": state["resolved_design"]["design_hash"],
                        "batch_load": _batch_load(rows),
                        "execution_mode": "parallel" if parallel else "serial",
                        "parallel_group": "drawing" if parallel else "",
                    },
                    status="done" if complete else "pending",
                    run=ItemRun(
                        state="succeeded" if complete else "idle", max_attempts=1
                    ),
                )
            )
            for marker in rows:
                owners[marker["id"]] = task_id
                pending.pop(marker["id"])
    # 一次生成、两次局部修订和一次装配修订。
    if object_scene:
        items.extend(_unsupported_object_items(decisions))
    return new_plan(
        items,
        detail_level=state.get("detail_level") or "minimal",
        budget={
            "iterations": len(markers) * (len(IMPLEMENTATION_STAGES) + 1) + 2,
            "llm_calls": len(markers) * (len(IMPLEMENTATION_STAGES) + 1),
            "max_items": len(items),
        },
    )


def _index_compile_gaps(blueprint_gaps):
    """按构件类型索引未解析宿主与被拒的形态值。"""
    dropped_by_kind: dict[str, list[str]] = {}
    for gap_entry in blueprint_gaps.get("instance_dropped") or []:
        kind_name, _, host_name = str(gap_entry).partition(":")
        if (
            kind_name
            and host_name
            and host_name not in dropped_by_kind.setdefault(kind_name, [])
        ):
            dropped_by_kind[kind_name].append(host_name)
    # `类型.键: 原因` → 该类型被拒的形态键清单（同理去重保序）。
    rejected_forms_by_kind: dict[str, list[str]] = {}
    for gap_entry in blueprint_gaps.get("instance_form_rejected") or []:
        kind_name, _, detail = str(gap_entry).partition(".")
        if (
            kind_name
            and detail
            and detail not in rejected_forms_by_kind.setdefault(kind_name, [])
        ):
            rejected_forms_by_kind[kind_name].append(detail)
    return dropped_by_kind, rejected_forms_by_kind


def _component_gap_hint(
    kind, dropped_by_kind, rejected_forms_by_kind, uncompiled_kinds
):
    """说明当前任务应修复的宿主、形态或编译缺口。"""
    params = {}
    dropped_hosts = dropped_by_kind.get(kind) or []
    rejected_forms = rejected_forms_by_kind.get(kind) or []
    if dropped_hosts:
        # 比"编译器没产出该类型"更具体：图纸**写过**这条实例，只是宿主没解析到。
        params["blueprint_gap"] = (
            "实例清单里这些宿主没解析到、该实例已整条丢弃"
            f"（compile_report.instance_dropped）：{'、'.join(dropped_hosts[:4])}。"
            "本条目先按知识库检索到的真实宿主契约重写，不要沿用这些宿主 id。"
        )
    elif rejected_forms:
        # 图纸写过的**形态值**不合引擎字段契约，编译时被拒（值没落，几何仍用派生值）。
        params["blueprint_gap"] = (
            "图纸给这些形态字段写的值不符合引擎字段契约、编译时未采纳"
            f"（compile_report.instance_form_rejected）：{'；'.join(rejected_forms[:4])}。"
            "本条目按知识库检索到的字段契约生成该形态，不要沿用这些值。"
        )
    elif kind in uncompiled_kinds:
        # 图纸缺口注入：条目要知道自己在补哪个洞——
        # 编译器点名了该类型却没产出，这条 generate 就是模型通道的补洞任务。
        params["blueprint_gap"] = (
            "编译器没有产出该类型（compile_report.uncompiled）："
            "本条目负责把它补进蓝图，先按知识库检索到的契约生成。"
        )
    return params.get("blueprint_gap")
