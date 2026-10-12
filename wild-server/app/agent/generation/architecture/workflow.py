"""建筑节点形成设计图纸；实现与 WILD 校验由 plan 负责。"""

from __future__ import annotations

import time as _time

from pydantic import ValidationError

from app.agent.generation.architecture import (
    detect_architecture_profile,
    resolve_complexity_profile,
)
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
    """保留字段路径与全部契约错误，供模型定向修订。"""

    if isinstance(exc, KeyError):
        return f"/{exc.args[0]}：缺少必填字段"
    errors = getattr(exc, "errors", None)
    if callable(errors):
        messages = []
        for item in errors():
            conflicts = getattr((item.get("ctx") or {}).get("error"), "conflicts", None)
            if conflicts:
                messages.extend(_coordinate_reasons(conflicts))
                continue
            message = str(item.get("msg") or "").removeprefix("Value error, ").strip()
            if item.get("type") == "missing":
                message = "缺少必填字段"
            if message:
                parts = list(item.get("loc", ()))
                if (
                    len(parts) >= 4
                    and parts[0] == "components"
                    and parts[2] == "size"
                    and parts[-1] == "[key]"
                ):
                    parts.pop()
                path = "/" + "/".join(
                    str(part).replace("~", "~0").replace("/", "~1") for part in parts
                )
                if path.startswith("/roof/volumes/"):
                    message += '；数组项应写对象，例如 {"volume": "体量ID", "type": "自拟屋型"}，引用字段名为 volume'
                if path.startswith("/components/") and "/size/" in path:
                    from app.design.contracts import ComponentPlacement

                    field = str(parts[-1])
                    if field in ComponentPlacement.model_fields:
                        message = f"{field} 是位置参数，应保留原值写在 placement.{field}；sill_height、offset、normal_offset 可以为 0"
                    else:
                        message = f"尺寸必须是有限正数，实际 {item.get('input')!r}"
                if path.startswith("/components/") and path.endswith("/placement/face"):
                    message = (
                        f"face 仅表示 front/back/left/right 四个竖向立面，实际 {item.get('input')!r}；"
                        "屋顶、檐底或天花构件用 placement.position=[x,y,z] 写世界中心坐标，朝向说明写在 form/description"
                    )
                messages.append(f"{path}：{message}")
        if messages:
            return "；".join(dict.fromkeys(messages))
    return " ".join(str(exc).split())[:300]


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

    from app.design.resolver import build_design_document
    from app.design.contracts import MassingDecision, VolumeDecision
    from app.design.coordinates import volume_conflicts

    try:
        return build_design_document(
            plan,
            session_id=session_id,
            source_request=source_request,
            building_type=building_type,
            style_intent=style_intent,
            previous=previous,
            revision_feedback=revision_feedback,
        )
    except (ValidationError, ValueError, KeyError) as exc:
        reasons = [_validation_reason(exc)]
        if isinstance(plan.get("massing"), dict) and isinstance(
            plan.get("volumes"), list
        ):
            try:
                massing = MassingDecision.model_validate(plan["massing"])
                volumes = [
                    VolumeDecision.model_validate(item) for item in plan["volumes"]
                ]
            except ValidationError:
                pass
            else:
                conflicts = volume_conflicts(
                    [v.model_dump(mode="json") for v in volumes],
                    massing.model_dump(mode="json"),
                )
                reasons.extend(
                    reason
                    for reason in _coordinate_reasons(conflicts)
                    if reason not in reasons[0]
                )
        raise DesignContractError("；".join(reasons)) from exc


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
    if isinstance(previous, dict):
        from app.design.contracts import DesignDocument

        previous_plan = architecture_plan_from_document(
            DesignDocument.model_validate(previous)
        )
    else:
        previous_plan = state.get("architecture_plan")

    previous_complexity = (previous_plan or {}).get("complexity") or {}
    selected = resolve_complexity_profile(
        message, state.get("detail_level") or previous_complexity.get("level", "simple")
    )
    complexity = {
        **selected,
        **previous_complexity,
        "level": selected["level"],
        "reason": selected["reason"],
    }
    profile = detect_architecture_profile(
        feedback or message,
        profile_id=(previous_plan or {}).get("profile") or state.get("intent_profile"),
    )

    callback = get_reasoning_callback()
    if callback:
        await callback("architecture:progress", "正在形成完整建筑图纸与构件标记……\n")

    prompt = build_architecture_plan_prompt(
        "",
        profile,
        complexity,
        current_plan=previous_plan,
        revision_feedback=feedback,
        style_preference=state.get("style_preference"),
    )
    accepted = {}

    # 在 draft_design 内部做了契约验证，失败时抛 DesignContractError；这里捕获它并返回可读错误。
    def validate(raw):
        components = raw.get("components") or []
        if not isinstance(components, list) or any(
            not isinstance(item, dict) for item in components
        ):
            raise ValueError("components 必须是构件对象数组")
        if any(not item.get("id") for item in raw.get("components") or []):
            raise ValueError("每个显式构件标记必须有稳定 id；不能只写构件类型与宿主")
        from app.agent.knowledge.component_names import resolve_component_name

        volume_ids = {
            v.get("id") for v in raw.get("volumes", []) if isinstance(v, dict)
        }
        for index, item in enumerate(components):
            placement = item.get("placement") or {}
            if (
                resolve_component_name(item.get("type", ""))["entity_type"]
                in {"door", "window"}
                and item.get("host") in volume_ids
                and isinstance(placement, dict)
                and not placement.get("position")
                and (not placement.get("face") or not placement.get("floor"))
            ):
                raise ValueError(
                    f"/components/{index}/placement：体量内门窗的沿墙定位需要 face 和 floor，"
                    "或写出世界 position；不能仅凭 offset 猜测墙面和楼层"
                )
        plan = {
            "profile": profile["id"],
            **raw,
            "complexity": {
                **complexity,
                **(raw.get("complexity") or {}),
                "level": selected["level"],
                "reason": selected["reason"],
            },
        }
        document = build_design_document_or_error(
            plan,
            session_id=str(
                state.get("session_id") or state.get("request_id") or "unknown"
            ),
            source_request=message,
            building_type=profile["id"],
            style_intent=list(state.get("style_preference") or []),
            previous=previous,
            revision_feedback=feedback,
        )
        resolved = resolve_design(document)
        from app.design.coordinates import opening_coordinate_errors

        coordinate_errors = opening_coordinate_errors(resolved.component_markers)
        if coordinate_errors:
            raise ValueError("；".join(coordinate_errors))
        accepted.update(document=document, resolved=resolved)

    accounting = {"model_calls": 0}
    try:
        raw, diag = await draft_design(
            base_prompt=prompt,
            user_request=message + ("\n本轮修改意见：" + feedback if feedback else ""),
            thinking_mode=True,
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
        total_ms=int((_time.time() - started) * 1000),
        profile=profile["id"],
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
