"""生成图纸的确定性验收入口。"""

from __future__ import annotations

import json

from pydantic import ValidationError

from agent.state import GenerationState
from agent.utils.design.contracts import DesignDocument, ResolvedDesign


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
                    from agent.utils.design.contracts import ComponentPlacement

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


def _build_design_document(
    plan: dict,
    *,
    session_id: str,
    source_request: str,
    building_type: str,
    style_intent: list[str],
):
    """
    构造设计契约；不满足业务不变量时抛 `DesignContractError`。

    未捕获的 Pydantic 异常会直接终止整轮生成，用户只看到一条 ValidationError。
    这里把它转成受控业务错误，让节点能给出明确原因并走正常失败分支。
    """

    from agent.utils.design.resolver import build_design_document
    from agent.utils.design.contracts import MassingDecision
    from agent.utils.design.contracts import VolumeDecision
    from agent.utils.design.coordinates import volume_conflicts

    try:
        return build_design_document(
            plan,
            session_id=session_id,
            source_request=source_request,
            building_type=building_type,
            style_intent=style_intent,
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


def validate_design_draft(
    raw: dict,
    state: GenerationState,
    *,
    profile_id: str,
    object_scene: bool,
) -> tuple[DesignDocument, ResolvedDesign]:
    """从候选稿建立设计文档，再检查解析后的空间与构件关系。"""
    from agent.utils.design.resolver import resolve_design
    from agent.utils.design.coordinates import (
        component_dimension_conflicts,
        roof_span_conflicts,
    )
    from agent.utils.design.spatial import execution_view

    try:
        if object_scene:
            from agent.utils.design.objects.planning import normalize_object_plan

            if "objects" not in raw and "unsupported_objects" not in raw:
                raise ValueError("物件图纸必须声明 objects 或 unsupported_objects")
            plan = normalize_object_plan(raw, state["user_message"])
        else:
            plan = {"profile": profile_id, **raw}
        document = _build_design_document(
            plan,
            session_id=str(
                state.get("session_id") or state.get("request_id") or "unknown"
            ),
            source_request=state["user_message"],
            building_type="asset" if object_scene else profile_id,
            style_intent=list(state.get("style_preference") or []),
        )
        resolved = resolve_design(document)
        if object_scene:
            return document, resolved
        drawing = execution_view(document.decisions.model_dump(mode="json"))
        errors = _material_role_conflicts(raw.get("components") or [])
        errors.extend(component_dimension_conflicts(drawing))
        errors.extend(roof_span_conflicts(resolved.component_markers))
        if errors:
            raise ValueError("；".join(errors))
    except (DesignContractError, ValueError) as exc:
        raise ValueError(_validation_reason(exc)) from exc
    return document, resolved
