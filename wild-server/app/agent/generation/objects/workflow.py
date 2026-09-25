"""物件场景的方案节点：产出 ObjectDecisions 版本的设计文档。

与 `generation/architecture/workflow.py` 是**并列**的两条方案链，不是它的分支：

    generate + target_kind=object  → 本模块（只做物件清单，无体量/立面/屋顶）
    generate + target_kind=architecture → architecture/workflow.py

两条链在 `design_review` 之后合流：材质、骨架、计划、执行、校验都是同一套。
合流点之所以成立，是因为物件方案也落成 `DesignDocument`——只是 `decisions`
解析成 `ObjectDecisions`（带标签联合的另一支）。

失败语义与建筑链一致，别混：
  - **模型服务故障** → `model_failure_result()`，终止本轮图运行；
  - **输出解析不了** → 走 `normalize_object_plan` 的确定性兜底（按用户点名的
    物件类型生成），**不中断**——"模型格式抖动"不该让用户拿不到一张桌子。
"""

from __future__ import annotations

import time as _time

from loguru import logger

from app.agent.generation.objects.planning import normalize_object_plan
from app.agent.generation.objects.subtypes import subtype_catalog
from app.agent.prompts import build_object_design_prompt
from app.agent.runtime import get_reasoning_callback
from app.agent.state import GenerationState
from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, merge_token_usage
from app.spec.loader import SpecQuery
from app.utils.json_extractor import extract_json_object

#: 物件方案可以引用的材质名。与 `objects/skeleton.py::OBJECT_MATERIALS`
#: 和 `material_plan.OBJECT_ROLE_SPECS` 逐字一致——三处都是这一份清单。
_SCENE_MATERIAL_IDS = ["wood", "metal", "glass", "stone", "fabric", "accent"]


def _furniture_spec(spec_loader) -> str:
    """预取家具构件契约。检索命中为空时返回空串，由确定性兜底顶上。"""

    queries = [
        SpecQuery("家具参数契约", {"doc_type": "component", "entity_type": "furniture"}),
        SpecQuery(
            "家具 桌子 椅子 尺寸 摆位 朝向",
            {"doc_type": "component", "topic": "parameters"},
        ),
    ]
    try:
        return spec_loader.load_many(queries, per_query=2)
    except Exception as exc:  # 检索失败不该阻断方案
        logger.warning(f"[object_design] RAG 检索失败，使用内置子类型表: {exc}")
        return ""


async def object_planner(state: GenerationState) -> dict:
    """输出唯一的物件方案，并落成带 `kind="object"` 的设计文档。"""

    from app.design.resolver import build_design_document, resolve_design
    from app.services.agent_service import agent_service

    started = _time.time()
    user_message = str(state.get("user_message") or "")
    revision_feedback = str(state.get("design_feedback") or "").strip()
    design_request = (
        f"{user_message}\n本轮修订意见：{revision_feedback}"
        if revision_feedback else user_message
    )
    on_reasoning_delta = get_reasoning_callback()

    if on_reasoning_delta:
        await on_reasoning_delta(
            "object_design",
            "\n### 物件方案\n"
            + ("根据修改意见调整物件清单、尺寸与摆位...\n" if revision_feedback
               else "正在确定物件种类、尺寸与摆位...\n"),
        )

    spec_text = _furniture_spec(agent_service.spec_loader)
    material_ids = list(_SCENE_MATERIAL_IDS)
    prompt = build_object_design_prompt(
        spec_text,
        subtype_catalog=subtype_catalog(),
        material_ids=material_ids,
        current_plan=state.get("architecture_plan"),
        revision_feedback=revision_feedback,
    )

    raw_plan = None
    error = None
    token_usage = None
    recovery_diag = None
    llm_ms = 0
    llm_chars = 0
    try:
        llm_started = _time.time()
        llm = create_llm(enable_thinking=bool(state.get("thinking_mode")), streaming=False)
        llm_result = await invoke_llm(
            llm,
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": design_request},
            ],
        )
        llm_ms = int((_time.time() - llm_started) * 1000)
        reply_text = llm_result.content
        llm_chars = len(reply_text)
        token_usage = llm_result.token_usage
        raw_plan = extract_json_object(reply_text)
        if raw_plan is None:
            # 与其他节点一致：先做一次非思考定向格式恢复，再决定是否兜底。
            from app.llm.recovery import recover_single_json

            raw_plan, recovery_diag = await recover_single_json(
                prompt,
                design_request,
                reply_text,
                object_hint="包含 objects 数组的物件方案 JSON 对象",
                extra_instruction=(
                    "- 顶层必须直接包含 kind、concept、objects、design_rationale；\n"
                    "- kind 必须为 \"object\"；objects 每项必须含 subtype/count/width/depth/height；\n"
                    "- 不要输出 massing、volumes、facades、roof 中的任何字段。"
                ),
            )
            token_usage = merge_token_usage(
                token_usage, (recovery_diag or {}).get("token_usage")
            )
            if raw_plan is not None:
                logger.warning("[object_design] 物件方案定向格式恢复成功")
    except Exception as exc:
        logger.warning(f"[object_design] 模型服务故障，已阻断: {exc}")
        from app.llm.errors import model_failure_result

        return model_failure_result(exc)

    plan = normalize_object_plan(raw_plan, user_message)
    used_fallback = raw_plan is None
    if used_fallback:
        logger.info(
            "[object_design] 模型未给出可用物件方案，使用确定性兜底: "
            f"{[item['subtype'] for item in plan['objects']]}"
        )

    if on_reasoning_delta:
        summary = "、".join(
            f"{item['subtype']}×{item['count']}" for item in plan["objects"]
        )
        await on_reasoning_delta(
            "object_design",
            f"\n### 物件方案\n- 清单：{summary}\n"
            + "\n".join(f"- {item}" for item in plan.get("design_rationale", []))
            + "\n- 物件方案已确定；下一节点将解析受控材质并生成可审核的设计文档与图纸。\n",
        )

    document = build_design_document(
        plan,
        session_id=str(state.get("session_id") or state.get("request_id") or "unknown"),
        source_request=user_message,
        building_type="asset",
        style_intent=list(state.get("style_preference") or []),
        previous=state.get("design_document"),
    )
    resolved_design = resolve_design(document).model_dump(mode="json")
    total_ms = int((_time.time() - started) * 1000)
    logger.info(
        f"[object_design] 完成: {len(plan['objects'])} 类物件, "
        f"fallback={used_fallback}, {total_ms}ms"
    )

    return {
        "architecture_plan": plan,
        "design_document": document.model_dump(mode="json"),
        "resolved_design": resolved_design,
        "design_review_status": "pending",
        "design_feedback": "",
        # 物件方案每轮都可能换物件，材质必须跟着重算：复用上一版会给出
        # 一张桌子配"米色外墙漆"这种错位材质。
        "design_material_refresh": True,
        "object_design_diag": {
            "used_fallback": used_fallback,
            "raw_plan": raw_plan,
            "normalized_plan": plan,
            "rag_chars": len(spec_text),
            "prompt_chars": len(prompt),
            "llm_chars": llm_chars,
            "llm_ms": llm_ms,
            "token_usage": token_usage,
            "recovery": recovery_diag,
            "error": error,
            "thinking_enabled": bool(state.get("thinking_mode")),
            "total_ms": total_ms,
        },
    }


__all__ = ["object_planner"]
