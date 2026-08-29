"""把已确认风格包编译成 Decor IR，并确定性写回主体。"""

from __future__ import annotations

import time

from app.agent.graph_state import GenerationState
from app.agent.plan2build.decor_assembler import DecorAssemblyError, assemble_decor
from app.agent.plan2build.style_registry import style_registry
from app.agent.runtime_context import get_reasoning_callback


async def decor_assembler(state: GenerationState) -> dict:
    started = time.perf_counter()
    callback = get_reasoning_callback()
    if state.get("style_review_status") != "approved":
        return {"error": "风格尚未确认，禁止装配装饰", "status": "failed"}
    package = style_registry.get(str(state.get("style_package_id") or "modern"))
    if callback:
        await callback("decor_assembly", f"正在应用“{package['name']}”风格包：屋顶、檐口、入口锚点和柱列均由参数化规则生成……\n")
    try:
        blueprint, decor_ir, report = assemble_decor(state["skeleton_blueprint"], package)
    except DecorAssemblyError as exc:
        if callback:
            await callback("decor_assembly", f"G7 未通过，已停止交付：{exc}\n")
        return {
            "error": f"装饰装配未通过：{exc}",
            "status": "failed",
            "style_gate_report": exc.report.to_dict(),
        }
    if callback:
        await callback("decor_assembly", f"装饰装配完成，{len(decor_ir['operations'])} 项参数化操作，G7 通过。\n")
    return {
        "skeleton_blueprint": blueprint,
        "decor_ir": decor_ir,
        "style_gate_report": report.to_dict(),
        "decor_diag": {
            "style_package_id": package["id"],
            "operation_count": len(decor_ir["operations"]),
            "gate_report": report.to_dict(),
            "llm_ms": 0,
            "token_usage": {},
            "total_ms": int((time.perf_counter() - started) * 1000),
        },
    }
