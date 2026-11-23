"""为生成请求起草并解析设计图纸。"""

from __future__ import annotations

import time as _time
import asyncio
import json
from typing import get_args

from pydantic import ValidationError

from app.agent.workflows.design.drafting import draft_design
from app.agent.state import GenerationState
from app.agent.prompts import build_architecture_plan_prompt
from app.agent.runtime import get_reasoning_callback
from app.domain.design.types import DetailLevel


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
            message = f"{path}：{conflict['reason']}"
            if "expected" in conflict or "actual" in conflict:
                message += "；" + json.dumps(
                    {
                        key: conflict[key]
                        for key in ("marker_id", "expected", "actual")
                        if key in conflict
                    },
                    ensure_ascii=False,
                )
            if conflict.get("related_paths"):
                message += "；关联修订路径：" + "、".join(
                    p.removeprefix("/decisions") for p in conflict["related_paths"]
                )
            messages.append(message)
    return messages


def _validation_reason(exc: Exception) -> str:
    """保留字段路径与全部契约错误，供模型定向修订。"""

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
                if path.startswith("/roofs/") and path.endswith("/geometry/outline"):
                    message = (
                        '屋面轮廓须为区域对象，例如 {"type":"profile_region","profile":"轮廓ID"}；'
                        "体量并集截面使用 volume_union_section，宿主支承截面使用 host_section"
                    )
                if path.startswith("/components/") and "/size/" in path:
                    from app.domain.design.contracts import ComponentPlacement

                    field = str(parts[-1])
                    if field in ComponentPlacement.model_fields:
                        message = f"{field} 是位置参数，应保留原值写在 placement.{field}；sill_height、offset、normal_offset 可以为 0"
                    else:
                        message = f"尺寸必须是有限正数，实际 {item.get('input')!r}"
                if path.startswith("/components/") and path.endswith("/placement/face"):
                    message = (
                        f"face 仅表示 front/back/left/right 四个竖向立面，实际 {item.get('input')!r}；"
                        "台基、屋顶、檐底等非立面定位用 placement.position=[x,y,z] 写世界中心坐标，朝向说明写在 form/description"
                    )
                if path.startswith("/components/") and "/placement/position" in path:
                    message = (
                        f"position 必须是三个有限数字组成的世界中心 [x,y,z]，实际 {item.get('input')!r}；"
                        "共享参数的计算须使用以 = 开头的表达式并先展开，不能把未计算的字符串交给执行节点"
                    )
                if path.startswith("/components/") and any(
                    path.endswith("/placement/" + field)
                    for field in ("offset", "sill_height", "normal_offset")
                ):
                    field = str(parts[-1])
                    message = (
                        f"{field} 必须是单个有限数字，实际 {item.get('input')!r}；"
                        "offset 是沿墙距离，不是三维向量或 x/y/z 对象。"
                        "世界坐标写 placement.position=[x,y,z]；已有 position 时，未使用的沿墙参数直接省略，不能填 null"
                    )
                if path.startswith("/components/") and path.endswith("/host"):
                    message = (
                        f"host 应为宿主 ID 字符串或 null，实际 {item.get('input')!r}；"
                        "无宿主可省略或写 null/空字符串；位置写 placement，不能把对象、数组或数值填入 host"
                    )
                messages.append(f"{path}：{message}")
        if messages:
            return "；".join(dict.fromkeys(messages))
    return " ".join(str(exc).split())[:300]


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
            material_names = []
            for names in materials.values():
                material_names.extend(names)
            errors.append(
                f"/components：material_role={role!r} 同时引用明确不同的材料类别 {sorted(materials)}，"
                f"材料描述 {sorted(material_names)}；"
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

    from app.domain.design.resolver import build_design_document
    from app.domain.design.contracts import MassingDecision
    from app.domain.design.contracts import VolumeDecision
    from app.domain.design.coordinates import volume_conflicts

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
                # 旧矩形诊断依赖 x/z 等字段。新图纸的体量由空间契约验收。
                if all(volume.geometry is None for volume in volumes):
                    conflicts = volume_conflicts(
                        [volume.model_dump(mode="json") for volume in volumes],
                        massing.model_dump(mode="json"),
                    )
                    reasons.extend(
                        reason
                        for reason in _coordinate_reasons(conflicts)
                        if reason not in reasons[0]
                    )
        raise DesignContractError("；".join(reasons)) from exc


async def architecture_planner(state: GenerationState) -> dict:
    """建筑和独立物件共用的图纸起草入口。"""
    from app.domain.design.resolver import architecture_plan_from_document
    from app.infrastructure.llm.errors import model_failure_result
    from app.domain.blueprint.materials.plan import material_mentions

    started = _time.time()
    message = state["user_message"]
    object_scene = state.get("intent_target_kind") == "object"
    previous = state.get("design_document")
    # 解析上轮设计图纸，或从 state 里取 architecture_plan 作为上轮设计方案。
    if isinstance(previous, dict):
        from app.domain.design.contracts import DesignDocument

        previous_plan = architecture_plan_from_document(
            DesignDocument.model_validate(previous)
        )
    else:
        previous_plan = state.get("architecture_plan")

    detail_level = state.get("detail_level", "minimal")
    if detail_level not in get_args(DetailLevel):
        detail_level = "minimal"

    if previous_plan and (previous_plan.get("target_kind") == "object") != object_scene:
        previous_plan = None
    profile_id = (
        "object"
        if object_scene
        else (previous_plan or {}).get("profile") or state["intent_profile"]
    )

    callback = get_reasoning_callback()
    if callback:
        label = "独立物件图纸" if object_scene else "建筑图纸"
        await callback("architecture:progress", f"正在设计{label}与构件标记……\n")

    from app.agent.runtime import agent_runtime
    from app.infrastructure.retrieval.loader import SpecQuery

    if object_scene:
        queries = [
            SpecQuery(
                f"{message} 物件 参数 尺寸 摆位 形体组合",
                {"doc_type": "component"},
            )
        ]
    else:
        queries = [
            SpecQuery(
                "建筑设计步骤与关系复核 需求形制 体量标高 功能交通 围护开口 屋面附属 材料搭配 字段落地",
                {"entity_name": "architecture_design_process"},
            ),
            SpecQuery(
                f"{message} 建筑设计表达 体量围护 开敞 室内房间 内墙 通行 门窗宿主 平面布局",
                {"entity_name": "architecture_design_expression"},
            ),
            SpecQuery(
                f"{message} {profile_id} 体量组织 楼层标高 逐层轮廓 屋面覆盖",
                {"entity_name": "massing_composition_rules"},
            ),
            SpecQuery(
                f"{message} {profile_id} 建筑形制 形态表达 空间组织 构件组合",
                {"doc_type": "component", "topic": "composition"},
            ),
        ]
    rag_started = _time.time()
    spec_result = await asyncio.to_thread(
        agent_runtime.spec_loader.load_many_result,
        queries,
        per_query=2,
        include_base=False,
    )
    spec_text = spec_result.text
    design_process_hits = [
        hit.id
        for hit in spec_result.hits
        if hit.metadata.get("entity_name") == "architecture_design_process"
    ]
    rag_ms = int((_time.time() - rag_started) * 1000)
    prompt = build_architecture_plan_prompt(
        spec_text,
        profile_id,
        detail_level=detail_level,
        current_plan=previous_plan,
        style_preference=state.get("style_preference"),
        object_scene=object_scene,
    )
    accepted = {}

    # 在 draft_design 内部做了契约验证，失败时抛 DesignContractError；这里捕获它并返回可读错误。
    # 检查通过：正常执行到函数结尾，隐式返回 None
    # 检查失败：raise 抛出异常
    # raw：待检查的完整设计字典
    def validate(raw):
        if object_scene:
            from app.domain.design.objects.planning import normalize_object_plan
            from app.domain.design.resolver import resolve_design

            if "objects" not in raw and "unsupported_objects" not in raw:
                raise ValueError("物件图纸必须声明 objects 或 unsupported_objects")
            plan = normalize_object_plan(raw, message)
            document = build_design_document_or_error(
                plan,
                session_id=str(
                    state.get("session_id") or state.get("request_id") or "unknown"
                ),
                source_request=message,
                building_type="asset",
                style_intent=list(state.get("style_preference") or []),
                previous=previous,
            )
            resolved = resolve_design(document)
        else:
            document, resolved = _validate_architecture_draft(
                raw, state, profile_id, previous
            )
        accepted.update(document=document, resolved=resolved)

    repair_rag_ms = repair_rag_chars = 0

    # 检索修订资料
    async def load_repair_rules(issue):
        nonlocal repair_rag_ms, repair_rag_chars
        started = _time.time()
        rules = await asyncio.to_thread(
            agent_runtime.spec_loader.load_many,
            [
                SpecQuery(
                    "建筑图纸字段与关系修订 " + issue,
                    {"entity_name": "architecture_design_expression"},
                ),
            ],
            per_query=2,
            include_base=False,
        )
        repair_rag_ms += int((_time.time() - started) * 1000)
        repair_rag_chars += len(rules)
        return rules

    accounting = {"model_calls": 0}
    try:
        # 调用异步方法 draft_design，等待它执行结束。
        # raw：通过本轮检查的设计数据；最终失败时是 {}
        # diag：尝试次数、错误、补丁、模型用量等诊断信息
        raw, diag = await draft_design(
            base_prompt=prompt,
            user_request=message,
            thinking_mode=state.get("thinking_mode") is True,
            # 传入一个通知函数，供内部发送思考内容或修订进度
            on_reasoning_delta=callback,
            validate=validate,
            load_repair_rules=load_repair_rules,
            # 传入外层的计数字典。内部修改这个字典，外层也能看到修改后的次数。
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
        rag_chars=len(spec_text),
        rag_ms=rag_ms,
        repair_rag_ms=repair_rag_ms,
        repair_rag_chars=repair_rag_chars,
        detail_level=detail_level,
        design_process_hits=design_process_hits,
        total_ms=int((_time.time() - started) * 1000),
        profile=profile_id,
        raw_plan=raw,
    )
    if not raw:
        return {
            "status": "failed",
            "error": "设计图纸未通过检查：" + diag["last_issue"],
            "architecture_diag": diag,
        }
    document = accepted["document"]
    prior_strategy = (
        (previous or {}).get("decisions", {}).get("design_intent") or {}
    ).get("material_strategy")
    intent = getattr(document.decisions, "design_intent", None)
    strategy = intent.material_strategy if intent else ""
    return {
        "detail_level": detail_level,
        "architecture_plan": architecture_plan_from_document(document),
        "design_document": document.model_dump(mode="json"),
        "resolved_design": accepted["resolved"].model_dump(mode="json"),
        "design_material_refresh": object_scene
        or not previous
        or prior_strategy != strategy
        or bool(material_mentions(message)),
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


def _validate_architecture_draft(raw, state, profile_id, previous):
    """由统一契约检查字段与引用，再用共享空间解析结果检查设计关系。"""
    from app.domain.design.resolver import resolve_design
    from app.domain.design.coordinates import (
        component_dimension_conflicts,
        roof_span_conflicts,
    )
    from app.domain.design.spatial import execution_view

    material_errors = _material_role_conflicts(raw.get("components") or [])
    plan = {"profile": profile_id, **raw}
    try:
        document = build_design_document_or_error(
            plan,
            session_id=str(
                state.get("session_id") or state.get("request_id") or "unknown"
            ),
            source_request=state["user_message"],
            building_type=profile_id,
            style_intent=list(state.get("style_preference") or []),
            previous=previous,
        )
        resolved = resolve_design(document)
        drawing = execution_view(document.decisions.model_dump(mode="json"))
        errors = material_errors + component_dimension_conflicts(drawing)
        errors.extend(roof_span_conflicts(resolved.component_markers))
        if errors:
            raise ValueError("；".join(errors))
    except (DesignContractError, ValueError) as exc:
        raise ValueError(_validation_reason(exc)) from exc
    return document, resolved
