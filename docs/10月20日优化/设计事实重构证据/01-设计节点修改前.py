"""建筑节点形成设计图纸；实现与 WILD 校验由 plan 负责。"""

from __future__ import annotations

import time as _time

from pydantic import ValidationError

from app.agent.generation.architecture import resolve_complexity_profile
from app.agent.generation.architecture.design_workflow import draft_design
from app.agent.state import GenerationState
from app.agent.prompts import build_architecture_plan_prompt
from app.agent.runtime import get_reasoning_callback


class DesignContractError(RuntimeError):
    """设计方案不满足 DesignDocument 业务不变量时抛出的可读业务错误。"""


def _coordinate_reasons(conflicts: list[dict]) -> list[str]:
    messages = []
    for conflict in conflicts:
        path = conflict.get("conflict_path", conflict["path"]).removeprefix(
            "/decisions"
        )
        if "actual_extent" in conflict:
            messages.append(
                f"{path}：全部体量的包络为 {conflict['actual_extent']:g} 米，"
                f"当前总体尺寸为 {conflict['conflict_value']:g} 米。"
                "若该尺寸是用户硬要求，应修订体量布局；否则显式修订总体尺寸，保留未受影响的设计。"
            )
        else:
            messages.append(f"{path}：{conflict['reason']}")
    return messages


def _validation_reason(exc: Exception) -> str:
    """只翻译契约路径与错误；字段定义和计算规则各由一处负责。"""
    if isinstance(exc, KeyError):
        return f"/{exc.args[0]}：缺少必填字段"
    if getattr(exc, "conflicts", None):
        return "；".join(_coordinate_reasons(exc.conflicts))
    errors = getattr(exc, "errors", None)
    if callable(errors):
        messages = []
        for item in errors():
            conflicts = getattr((item.get("ctx") or {}).get("error"), "conflicts", None)
            if conflicts:
                messages.extend(_coordinate_reasons(conflicts))
                continue
            parts = list(item.get("loc", ()))
            if parts and parts[0] == "decisions":
                parts.pop(0)
                if parts and parts[0] == "architecture":
                    parts.pop(0)
            path = "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)
            message = "缺少必填字段" if item.get("type") == "missing" else str(item.get("msg", "")).removeprefix("Value error, ")
            messages.append(f"{path}：{message}")
        return "；".join(dict.fromkeys(messages))
    return str(exc)


def _material_role_conflicts(components):
    import re

    families = {
        "wood": r"木|\b(?:wood|timber)\b",
        "stone": r"石|\b(?:stone|marble|granite)\b",
        "metal": r"金属|钢|铝|\b(?:metal|steel|aluminum|aluminium)\b",
        "concrete": r"混凝土|\bconcrete\b",
        "brick": r"砖|\bbrick\b",
        "glass": r"玻璃|\bglass\b",
        "fabric": r"织物|布料|\b(?:fabric|cloth)\b",
    }
    groups = {}
    for item in components:
        role, form = item.get("material_role"), item.get("form")
        material = form.get("material") if isinstance(form, dict) else None
        if (
            isinstance(role, str)
            and role
            and isinstance(material, str)
            and material.strip()
        ):
            matches = [
                name
                for name, pattern in families.items()
                if re.search(pattern, material, re.I)
            ]
            # 只拦截能明确区分的材料类别；同类描述、未知或复合材料不靠字符串差异判为冲突。
            if len(matches) == 1:
                groups.setdefault(role, {}).setdefault(matches[0], set()).add(
                    material.strip()
                )
    errors = []
    for role, materials in groups.items():
        if len(materials) > 1:
            errors.append(
                f"/components：material_role={role!r} 同时引用明确不同的材料类别 {sorted(materials)}，"
                f"材料描述 {sorted(name for names in materials.values() for name in names)}；"
                "同一角色只绑定一种实际材质。若这些名称指同一材质，请统一 form.material 名称；"
                "若材料不同，分别选择已有匹配角色或省略不合适的 material_role，由构件实现独立材质。"
                "不能仅在文字中保留木、石而仍共用一个角色"
            )
    return errors


def build_design_document_or_error(
    plan: dict,
    *,
    session_id: str,
    source_request: str,
    building_type: str,
    style_intent: list[str],
    previous: object,
    revision_feedback: str = "",
):
    """
    构造设计契约；不满足业务不变量时抛 `DesignContractError`。

    未捕获的 Pydantic 异常会直接终止整轮生成，用户只看到一条 ValidationError。
    这里把它转成受控业务错误，让节点能给出明确原因并走正常失败分支。
    """

    from app.design.resolver import build_design_document, prepare_architecture_plan

    try:
        return build_design_document(
            prepare_architecture_plan(plan),
            session_id=session_id,
            source_request=source_request,
            building_type=building_type,
            style_intent=style_intent,
            previous=previous,
            revision_feedback=revision_feedback,
        )
    except (ValidationError, ValueError, KeyError) as exc:
        raise DesignContractError(_validation_reason(exc)) from exc


async def architecture_planner(state: GenerationState) -> dict:
    """一次完整设计，契约失败时局部修订；不通过则保留原因，不降级成默认建筑。"""
    from app.design.resolver import resolve_design
    from app.design.resolver import architecture_plan_from_document
    from app.llm.errors import model_failure_result
    from app.agent.generation.material.plan import material_mentions

    started = _time.time()
    message = state["user_message"]
    feedback = str(state.get("design_feedback") or "").strip()
    previous = state.get("design_document")
    # 解析上轮设计图纸，或从 state 里取 architecture_plan 作为上轮设计方案。
    if isinstance(previous, dict):
        from app.design.contracts import DesignDocument

        previous_plan = architecture_plan_from_document(
            DesignDocument.model_validate(previous)
        )
    else:
        previous_plan = state.get("architecture_plan")

    # 使用 State 中已确定的设计粒度生成复杂度配置。
    complexity = resolve_complexity_profile(state["detail_level"])
    profile_id = (previous_plan or {}).get("profile") or state["intent_profile"]

    callback = get_reasoning_callback()
    if callback:
        await callback("architecture:progress", "正在形成完整建筑图纸与构件标记……\n")

    # 粒度、设计协议与职责固定在提示词；本节点不检索 WILD 实现资料。
    prompt = build_architecture_plan_prompt(
        "", profile_id, complexity,
        current_plan=previous_plan,
        revision_feedback=feedback,
        style_preference=state.get("style_preference"),
    )
    accepted = {}

    def validate(raw):
        """构造契约 → 计算派生数据 → 复核引用与空间；模型仅修订设计矛盾。"""
        document = build_design_document_or_error(
            {"profile": profile_id, **raw,
             "complexity": {**complexity, **(raw.get("complexity") or {}),
                            "level": complexity["level"], "reason": complexity["reason"]}},
            session_id=str(state.get("session_id") or state.get("request_id") or "unknown"),
            source_request=message, building_type=profile_id,
            style_intent=list(state.get("style_preference") or []),
            previous=previous, revision_feedback=feedback,
        )
        from app.agent.knowledge.component_names import resolve_component_name
        from app.design.coordinates import stair_span_conflicts, roof_span_conflicts, component_dimension_conflicts
        from app.design.markers import component_markers

        data = document.decisions.model_dump(mode="json")
        volume_ids = {v["id"] for v in data["volumes"]}
        for index, item in enumerate(data["components"]):
            if not item.get("id"):
                raise ValueError(f"/components/{index}/id：每个显式构件必须有稳定 id")
            placement = item.get("placement") or {}
            if (resolve_component_name(item["type"])["entity_type"] in {"door", "window"}
                    and item.get("host") in volume_ids and not placement.get("position")
                    and (not placement.get("face") or not placement.get("floor"))):
                raise ValueError(f"/components/{index}/placement：体量内门窗需要 face/floor，或世界 position")
        markers = component_markers(document)
        errors = (_material_role_conflicts(data["components"]) + component_dimension_conflicts(data)
                  + stair_span_conflicts(data) + roof_span_conflicts(markers))
        try:
            resolved = resolve_design(document)
        except ValueError as exc:
            errors.append(_validation_reason(exc))
        if errors:
            raise ValueError("；".join(errors))
        accepted.update(document=document, resolved=resolved)

    accounting = {"model_calls": 0}
    try:
        raw, diag = await draft_design(
            base_prompt=prompt,
            user_request=message + ("\n本轮修改意见：" + feedback if feedback else ""),
            thinking_mode=state.get("thinking_mode") is not False,
            on_reasoning_delta=callback,
            current_plan=previous_plan if feedback else None,
            validate=validate,
            call_accounting=accounting,
        )
    except DesignContractError as exc:
        return {"status": "failed", "error": str(exc)}
    except Exception as exc:
        return {
            **model_failure_result(exc),
            "architecture_diag": {
                "model_calls": accounting["model_calls"],
                "last_issue": str(exc),
                "total_ms": int((_time.time() - started) * 1000),
                "settled": False,
            },
        }
    diag.update(
        rag_chars=0,
        rag_ms=0,
        repair_rag_ms=0,
        repair_rag_chars=0,
        detail_level=complexity["level"],
        total_ms=int((_time.time() - started) * 1000),
        profile=profile_id,
        raw_plan=raw,
    )
    if not raw:
        return {
            "status": "failed",
            "error": "建筑图纸未通过检查：" + diag["last_issue"],
            "architecture_diag": diag,
        }
    document = accepted["document"]
    prior_strategy = (
        (previous or {}).get("decisions", {}).get("design_intent") or {}
    ).get("material_strategy")
    strategy = (
        document.decisions.design_intent.material_strategy
        if document.decisions.design_intent
        else ""
    )
    return {
        "architecture_plan": architecture_plan_from_document(document),
        "design_document": document.model_dump(mode="json"),
        "resolved_design": accepted["resolved"].model_dump(mode="json"),
        "design_review_status": "pending",
        "design_feedback": "",
        "design_material_refresh": not previous
        or prior_strategy != strategy
        or bool(material_mentions(feedback)),
        "architecture_diag": diag,
        "component_fragments": {
            k: [] for k in (state.get("component_fragments") or {})
        },
        "component_diagnostics": {
            k: {} for k in (state.get("component_diagnostics") or {})
        },
        "merged_blueprint": {},
        "final_blueprint": {},
        "validation_snapshot": {},
        "repair_audit": {},
        "compile_report": {},
        "error": None,
    }
