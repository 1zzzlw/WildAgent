"""确定性编译：设计图纸 → 蓝图，零模型调用。

它取代的是 ``skeleton`` 在架构链上的位置（**物件链仍走 skeleton**：编译器只认
建筑的体量/立面/屋顶协议，物件没有这些东西）。

为什么单独成节点而不是塞进 ``skeleton/workflow.py``：那里面有四道预检，任一不过就
``status=failed`` 并直接 END（``graph.py`` 的 ``_after_skeleton``），而这四道预检正是
"人工已批准的设计被编译器一票否决、且没有修订通道"的来源。编译节点按用户定的红线
**只标记不阻断**：图纸有问题就写进 ``compile_report`` 交给下游，不把整轮生成掐掉。

实现细节（派生/接线/四类诊断）全在 ``app.agent.compiler``，本模块只做状态读写与
"零模型调用"这一条的守卫。

节点入口见 ``nodes/compile_node.py``（薄壳）。
"""

from __future__ import annotations

from loguru import logger

from app.agent.compiler import compile_design
from app.agent.generation.skeleton.output import build_skeleton_summary
from app.agent.state import GenerationState


async def compile_node(state: GenerationState) -> dict:
    """把图纸编译成蓝图，写回 ``skeleton_blueprint`` 供 ``plan`` 直接消费。"""

    architecture_plan = state.get("architecture_plan") or {}
    user_message = state.get("user_message", "")
    material_plan = state.get("material_plan")

    document_data = state.get("design_document")
    resolved = None
    if document_data:
        from app.design.contracts import DesignDocument
        from app.design.compilation import compile_document, project_compilation, RESOLVER_VERSION
        document = DesignDocument.model_validate(document_data)
        result = compile_document(document)
        resolved = project_compilation(document, result)
        reviewed = state.get("resolved_design") or {}
        if (reviewed.get("resolver_version") != RESOLVER_VERSION
                or reviewed.get("design_hash") != resolved.design_hash):
            # Old approval used a different interpretation. Re-enter the existing review
            # flow, rather than silently replacing its dimensions with the new compiler.
            from app.design.contracts import utc_now_iso
            from app.design.resolver import resolve_design
            payload = document.model_dump(mode="json")
            payload.update(revision=document.revision+1, status="draft", approved_at=None, updated_at=utc_now_iso())
            revised = DesignDocument.model_validate(payload)
            return {"design_document": revised.model_dump(mode="json"),
                    "resolved_design": resolve_design(revised).model_dump(mode="json"),
                    "design_review_status": "pending",
                    "compile_report": {"requires_review": True, "reason": "审核解析版本已变化，请确认当前图纸"}}

    else:
        # Legacy checkpoints with no document retain the old entry point.
        result = compile_design(
            architecture_plan, user_message=user_message,
            material_plan=material_plan if isinstance(material_plan, dict) else None,
        )
    blueprint = result.blueprint
    if blueprint is None:  # mode=final 必出蓝图；走到这里说明接口被改坏了
        raise RuntimeError("compile_design(mode=final) 未返回蓝图")

    design_brief = result.design_brief or {}
    logger.info(f"[compile] {result.summary()}")

    spatial_invariants: dict = {}
    try:
        from app.agent.generation.spatial.invariants import build_spatial_invariants
        from app.tools.spatial_tools import compute_wall_bounding_box

        spatial_invariants = build_spatial_invariants(
            blueprint, compute_wall_bounding_box(blueprint)
        )
    except Exception as exc:  # 不变量只喂提示词，算不出来不该掐掉生成
        logger.warning(f"[compile] 空间不变量计算失败: {exc}")

    return {
        **({"resolved_design": resolved.model_dump(mode="json")} if resolved else {}),
        "skeleton_blueprint": blueprint,
        "skeleton_summary": build_skeleton_summary(blueprint, design_brief),
        "spatial_invariants": spatial_invariants,
        "design_brief": design_brief,
        # 编译器已经把确定性部分全产出来了，没有"建议模型再做一遍"的必要；
        # 剩余缺口由 ``plan`` 从 design_brief 的配额里读（见 compile_report.uncompiled）。
        "suggested_components": [],
        "compile_report": {
            **result.summary(),
            "defects": [item.to_dict() for item in result.defects],
            "defaulted": [item.to_dict() for item in result.defaulted],
        },
    }


__all__ = ["compile_node"]
