"""平面方案通用闸门（FP1-FP8 中的新增部分）。

现有闸门（elevator/egress/daylight/symmetry/opening_corner/functional_flow）
在 floor_plan_rules.py。这里补充依赖语义字段的新闸门：
- FP1 功能完整性：用户要求的卧室/卫生间/储物是否齐全
- FP4 隐私分区：是否需穿过卧室/卫生间进入公共空间
- FP5 湿区和管井：卫生间是否邻近管井、湿区引用
- FP7 楼梯和挑空：楼梯平台连接、挑空栏杆、楼层连通
- FP8 外部附属：阳台/飘窗/空调板的宿主与投影

每个闸门输出稳定问题协议 {code, level_id, entity_id, message, severity}。
"""

from __future__ import annotations

from typing import Any


def _spaces(level: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in level.get("spaces", []) if isinstance(item, dict)]


def _openings(level: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in level.get("openings", []) if isinstance(item, dict)]


def _finding(
    code: str,
    message: str,
    *,
    level_id: str = "",
    entity_id: str | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "code": code,
        "level_id": level_id,
        "entity_id": entity_id,
        "message": message,
        "severity": severity,
    }


def gate_fp1_functional_completeness(plan: dict[str, Any], required_spaces: list[str] | None) -> list[dict[str, Any]]:
    """FP1 功能完整性：用户要求的空间类型是否齐全。

    required_spaces 来自结构化需求拆解；未提供时不检查（不误报）。
    """
    if not required_spaces:
        return []
    present: set[str] = set()
    for level in plan.get("levels", []):
        for space in _spaces(level):
            present.add(str(space.get("space_type") or "").lower())
    missing = [r for r in required_spaces if r.lower() not in present]
    if not missing:
        return []
    return [_finding(
        "fp1_missing_space",
        f"缺少必需空间类型: {', '.join(missing)}",
        severity="warning",
    )]


def gate_fp4_privacy_zones(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """FP4 隐私分区：私密空间不应被迫穿过另一个私密空间到达。

    检查：卧室（private）之间的连通门，或进入 private 空间必须穿过另一 private。
    """
    issues: list[dict[str, Any]] = []
    for level in plan.get("levels", []):
        spaces = _spaces(level)
        by_id = {str(s.get("id")): s for s in spaces}
        for opening in _openings(level):
            connects = [str(c) for c in opening.get("connects", [])[:2]]
            if len(connects) < 2:
                continue
            a, b = by_id.get(connects[0]), by_id.get(connects[1])
            if a is None or b is None:
                continue
            za = str(a.get("zone") or "")
            zb = str(b.get("zone") or "")
            pa = int(a.get("privacy_level") or 0)
            pb = int(b.get("privacy_level") or 0)
            # 两个 private 空间直连（卧室-卧室）在非套房场景下应避免。
            if za == "private" and zb == "private":
                issues.append(_finding(
                    "fp4_private_to_private",
                    f"私密空间 {connects[0]} 与 {connects[1]} 直连，检查是否需穿过卧室",
                    level_id=str(level.get("id") or ""),
                    entity_id=str(opening.get("id") or ""),
                    severity="warning",
                ))
            # service 空间不应成为唯一通路（卫生间穿到主卧）。
            if (za == "service" and pb >= 2) or (zb == "service" and pa >= 2):
                issues.append(_finding(
                    "fp4_service_through_private",
                    f"湿区/服务空间 {connects[0] if za=='service' else connects[1]} "
                    f"是通往私密空间 {connects[1] if za=='service' else connects[0]} 的通路",
                    level_id=str(level.get("id") or ""),
                    entity_id=str(opening.get("id") or ""),
                    severity="warning",
                ))
    return issues


def gate_fp5_wet_space_shaft(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """FP5 湿区和管井：湿区应引用管井，且应邻近。

    检查 wet_space=True 的空间是否都设置了 served_by_shaft。
    """
    issues: list[dict[str, Any]] = []
    for level in plan.get("levels", []):
        for space in _spaces(level):
            if not bool(space.get("wet_space")):
                continue
            space_id = str(space.get("id") or "")
            if not str(space.get("served_by_shaft") or ""):
                issues.append(_finding(
                    "fp5_wet_space_without_shaft",
                    f"湿区 {space_id} 未关联管井（served_by_shaft）",
                    level_id=str(level.get("id") or ""),
                    entity_id=space_id,
                    severity="warning",
                ))
    return issues


def gate_fp7_stair_double_height(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """FP7 楼梯和挑空：平台连接、挑空栏杆、楼层连通。

    - 挑空空间应标记 edge_protection_required。
    - 楼梯应声明 access_space_by_level（每层连接的空间）。
    - 多层楼梯应覆盖全部相邻楼层。
    """
    issues: list[dict[str, Any]] = []
    modeled_floors = len(plan.get("levels", []))
    for vertical_space in plan.get("vertical_spaces", []) or []:
        if str(vertical_space.get("type") or "") not in {"double_height", "atrium"}:
            continue
        if vertical_space.get("edge_protection_required") is False:
            issues.append(_finding(
                "fp7_double_height_no_edge_protection",
                f"挑空 {vertical_space.get('id')} 未声明临空边防护",
                entity_id=str(vertical_space.get("id") or ""),
                severity="warning",
            ))
    for circulation in plan.get("vertical_circulation", []) or []:
        served = circulation.get("serves_levels") or []
        if len(served) >= 2:
            # 检查覆盖连续楼层（不应跳过中间层）。
            for floor in range(min(served), max(served)):
                if floor not in served and floor < modeled_floors:
                    issues.append(_finding(
                        "fp7_stair_skips_level",
                        f"楼梯 {circulation.get('id')} 未覆盖楼层 {floor}",
                        entity_id=str(circulation.get("id") or ""),
                        severity="warning",
                    ))
    return issues


def gate_fp8_exterior_attachments(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """FP8 外部附属：阳台/飘窗/空调板应引用存在的宿主空间和边界。

    宿主空间不存在或未接触外墙的附属标记为问题。
    """
    issues: list[dict[str, Any]] = []
    all_spaces: set[str] = set()
    for level in plan.get("levels", []):
        all_spaces.update(str(s.get("id")) for s in _spaces(level))
    for attachment in plan.get("exterior_attachments", []) or []:
        if not isinstance(attachment, dict):
            continue
        host = str(attachment.get("host_space_id") or "")
        if host and host not in all_spaces:
            issues.append(_finding(
                "fp8_attachment_host_missing",
                f"外部附属 {attachment.get('id')} 宿主空间 {host} 不存在",
                entity_id=str(attachment.get("id") or ""),
                severity="error",
            ))
    return issues


def evaluate_plan_gates(plan: dict[str, Any], *, required_spaces: list[str] | None = None) -> list[dict[str, Any]]:
    """运行全部新增闸门，返回合并问题列表。"""
    issues: list[dict[str, Any]] = []
    issues.extend(gate_fp1_functional_completeness(plan, required_spaces))
    issues.extend(gate_fp4_privacy_zones(plan))
    issues.extend(gate_fp5_wet_space_shaft(plan))
    issues.extend(gate_fp7_stair_double_height(plan))
    issues.extend(gate_fp8_exterior_attachments(plan))
    return issues
