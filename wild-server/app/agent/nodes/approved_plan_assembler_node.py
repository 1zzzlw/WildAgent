"""确认后主体装配节点：不调用 LLM，只消费已批准方案。"""

from __future__ import annotations

import time

from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.plan2build.assembler import (
    ApprovedPlanAssemblyError,
    assemble_approved_plan,
)
from app.agent.runtime_context import get_reasoning_callback
from app.agent.spatial_invariants import build_spatial_invariants
from app.tools.spatial_tools import compute_wall_bounding_box


def _summary(blueprint: dict, reports: list[dict], stats: dict[str, int]) -> str:
    elements = blueprint.get("geometry", {}).get("elements", [])
    components = blueprint.get("geometry", {}).get("components", [])
    type_counts: dict[str, int] = {}
    for item in [*elements, *components]:
        item_type = str(item.get("type") or "unknown")
        type_counts[item_type] = type_counts.get(item_type, 0) + 1
    counts = "、".join(f"{key}×{value}" for key, value in sorted(type_counts.items()))
    gates = "、".join(
        f"{item['gate']} {'通过' if item['passed'] else '未通过'}" for item in reports
    )
    return (
        f"已按确认平面确定性装配主体：{counts or '无构件'}。"
        f"新增门窗 {stats.get('opening_synthesized', 0)} 个、屋顶 {stats.get('roof_synthesized', 0)} 个；"
        f"入口壁灯 {stats.get('light_synthesized', 0)} 个；"
        f"质量闸门：{gates}。"
    )


async def approved_plan_assembler(state: GenerationState) -> dict:
    """FloorPlanIR → 主体 Blueprint → G1~G6；失败时有限终止。"""

    started = time.perf_counter()
    callback = get_reasoning_callback()
    if callback:
        await callback(
            "skeleton",
            "已收到确认平面，正在按墙线、楼板、洞口槽位和标高装配三维主体……\n",
        )
    plan = state.get("architecture_plan")
    if not isinstance(plan, dict) or state.get("floor_plan_review_status") != "approved":
        return {
            "error": "没有已确认的平面方案，禁止进入三维主体装配",
            "status": "failed",
            "deterministic_body_complete": False,
        }

    try:
        blueprint, design_brief, gate_reports, stats = assemble_approved_plan(
            plan,
            state.get("material_plan"),
            state.get("user_message", ""),
        )
    except ApprovedPlanAssemblyError as exc:
        reports = [report.to_dict() for report in exc.reports]
        if callback:
            await callback("skeleton", f"主体闸门未通过，流程已停止：{exc}\n")
        return {
            "error": f"主体装配未通过：{exc}",
            "status": "failed",
            "body_gate_reports": reports,
            "deterministic_body_complete": False,
            "skeleton_diag": {
                "mode": "approved_plan_assembler",
                "gate_reports": reports,
                "total_ms": int((time.perf_counter() - started) * 1000),
            },
        }
    except Exception as exc:
        logger.exception(f"[approved_plan_assembler] 装配失败: {exc}")
        return {
            "error": f"主体装配失败：{exc}",
            "status": "failed",
            "deterministic_body_complete": False,
        }

    reports = [report.to_dict() for report in gate_reports]
    bbox = compute_wall_bounding_box(blueprint)
    invariants = build_spatial_invariants(blueprint, bbox)
    summary = _summary(blueprint, reports, stats)
    if callback:
        await callback("skeleton", summary + "\n")
    return {
        "skeleton_blueprint": blueprint,
        "skeleton_summary": summary,
        "wall_bounding_box": bbox,
        "spatial_invariants": invariants,
        "suggested_components": [],
        "design_brief": design_brief,
        "body_gate_reports": reports,
        "deterministic_body_complete": True,
        "skeleton_diag": {
            "mode": "approved_plan_assembler",
            "llm_ms": 0,
            "token_usage": {},
            "gate_reports": reports,
            "assembly_stats": stats,
            "element_count": len(blueprint.get("geometry", {}).get("elements", [])),
            "component_count": len(blueprint.get("geometry", {}).get("components", [])),
            "total_ms": int((time.perf_counter() - started) * 1000),
        },
    }
