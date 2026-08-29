"""风格确认后的 Decor IR 与确定性装配器。"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from app.agent.plan2build.gates import GateIssue, GateReport, gate_g5_roof, gate_g6_references


class DecorAssemblyError(ValueError):
    def __init__(self, report: GateReport):
        self.report = report
        super().__init__("；".join(issue.message for issue in report.issues) or "装饰装配未通过 G7")


def _elements(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    return blueprint.setdefault("geometry", {}).setdefault("elements", [])


def _components(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    return blueprint.setdefault("geometry", {}).setdefault("components", [])


def _roof_operations(blueprint: dict[str, Any], package: dict[str, Any]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    roof_style = package["roof"]
    for roof in (item for item in _elements(blueprint) if item.get("type") == "roof"):
        target = {
            "roofType": roof_style["type"],
            "height": round(max(0.08, min(float(roof["span"]), float(roof["depth"])) * roof_style["height_ratio"]), 3),
        }
        if roof_style["type"] == "chinese_curved":
            target.update({
                "eaveCurveHeight": roof_style["eave_curve_height"],
                "curveProfile": "concave_eave",
            })
        operations.append({"op": "set_roof", "target_id": roof["id"], "values": target})
    return operations


def _cornice_operations(blueprint: dict[str, Any], package: dict[str, Any]) -> list[dict[str, Any]]:
    config = package["decor"]["cornice"]
    if not config["enabled"]:
        return []
    operations: list[dict[str, Any]] = []
    for index, roof in enumerate((item for item in _elements(blueprint) if item.get("type") == "roof"), start=1):
        position = roof.get("position")
        if not isinstance(position, list) or len(position) != 3:
            continue
        half_x = float(roof["span"]) / 2
        half_z = float(roof["depth"]) / 2
        x, y, z = (float(value) for value in position)
        width = float(config["width"])
        height = float(config["height"])
        # parentRoof 的 path 契约是“屋顶中心局部坐标”，不是世界坐标。
        # flat/gable/hip 可由编译器确定性投影到屋面；中式曲面屋顶尚不支持
        # parentRoof 局部依附，因此保留世界坐标且不写 parentRoof。
        supports_local_attachment = package["roof"]["type"] in {"flat", "gable", "hip"}
        if supports_local_attachment:
            path = [
                [-half_x, 0.0, -half_z], [half_x, 0.0, -half_z],
                [half_x, 0.0, half_z], [-half_x, 0.0, half_z],
                [-half_x, 0.0, -half_z],
            ]
        else:
            path = [
                [x - half_x, y, z - half_z], [x + half_x, y, z - half_z],
                [x + half_x, y, z + half_z], [x - half_x, y, z + half_z],
                [x - half_x, y, z - half_z],
            ]
        component = {
            "type": "cornice",
            "id": f"decor_{package['id']}_cornice_{index:02d}",
            "path": path,
            "profile": [[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]],
            "closedProfile": True,
            "material": "accent",
        }
        if supports_local_attachment:
            component["parentRoof"] = str(roof["id"])
        operations.append({"op": "sweep", "component": component})
    return operations


def _main_entrance(blueprint: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    walls = {
        str(item.get("id")): item
        for item in _elements(blueprint)
        if item.get("type") == "wall" and item.get("id")
    }
    doors = [item for item in _components(blueprint) if item.get("type") == "door"]
    doors.sort(key=lambda item: (float((item.get("from") or [0, 0, 0])[1]), str(item.get("id") or "")))
    for door in doors:
        wall = walls.get(str(door.get("parentWall") or ""))
        if wall:
            return door, wall
    return None


def _entrance_operations(blueprint: dict[str, Any], package: dict[str, Any]) -> list[dict[str, Any]]:
    entrance = _main_entrance(blueprint)
    if entrance is None:
        return []
    door, wall = entrance
    start, end = wall["from"], wall["to"]
    dx, dz = float(end[0]) - float(start[0]), float(end[2]) - float(start[2])
    length = math.hypot(dx, dz)
    if length <= 0:
        return []
    ux, uz = dx / length, dz / length
    along = float(door["from"][0]) + float(door["width"]) / 2
    entrance_x = float(start[0]) + ux * along
    entrance_z = float(start[2]) + uz * along
    all_walls = [item for item in _elements(blueprint) if item.get("type") == "wall"]
    center_x = sum((float(item["from"][0]) + float(item["to"][0])) / 2 for item in all_walls) / max(1, len(all_walls))
    center_z = sum((float(item["from"][2]) + float(item["to"][2])) / 2 for item in all_walls) / max(1, len(all_walls))
    nx, nz = -uz, ux
    if (entrance_x + nx - center_x) ** 2 + (entrance_z + nz - center_z) ** 2 < (entrance_x - nx - center_x) ** 2 + (entrance_z - nz - center_z) ** 2:
        nx, nz = -nx, -nz

    canopy_config = package["decor"]["entrance_canopy"]
    operations: list[dict[str, Any]] = []
    canopy_width = min(length, float(door["width"]) + 0.8)
    canopy_bottom = float(door["from"][1]) + float(door["height"]) + 0.18
    canopy_left = max(0.0, min(along - canopy_width / 2, length - canopy_width))
    if canopy_config["enabled"]:
        operations.append({
            "op": "anchor",
            "component": {
                "type": "canopy",
                "id": f"decor_{package['id']}_entrance_canopy",
                "parentWall": str(wall["id"]),
                "from": [round(canopy_left, 3), round(canopy_bottom, 3), 0.0],
                "width": round(canopy_width, 3),
                "depth": canopy_config["depth"],
                "thickness": canopy_config["thickness"],
                "supportCount": 0,
                "material": "accent",
            },
        })

    column_config = package["decor"]["facade_columns"]
    if column_config["enabled"] and column_config["count"] > 0:
        spacing = canopy_width / max(1, column_config["count"] - 1)
        start_offset = -canopy_width / 2
        for index in range(column_config["count"]):
            lateral = start_offset + spacing * index if column_config["count"] > 1 else 0.0
            operations.append({
                "op": "array",
                "element": {
                    "type": "column",
                    "id": f"decor_{package['id']}_entrance_column_{index + 1:02d}",
                    "base": [
                        round(entrance_x + ux * lateral + nx * 0.45, 3),
                        round(float(door["from"][1]), 3),
                        round(entrance_z + uz * lateral + nz * 0.45, 3),
                    ],
                    "height": round(max(0.5, canopy_bottom - float(door["from"][1])), 3),
                    "bottomRadius": column_config["radius"],
                    "topRadius": round(column_config["radius"] * 0.88, 3),
                    "style": column_config["style"],
                    "material": "accent",
                },
            })
    return operations


def build_decor_ir(blueprint: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    operations = [
        *_roof_operations(blueprint, package),
        *_cornice_operations(blueprint, package),
        *_entrance_operations(blueprint, package),
    ]
    for material_id, base_color in package["palette"].items():
        operations.append({"op": "set_material", "target_id": material_id, "baseColor": base_color})
    return {
        "schema_version": "1.0",
        "style_package_id": package["id"],
        "operations": operations,
    }


def _apply_decor_ir(blueprint: dict[str, Any], decor_ir: dict[str, Any]) -> None:
    elements = _elements(blueprint)
    components = _components(blueprint)
    by_element_id = {str(item.get("id")): item for item in elements if item.get("id")}
    for operation in decor_ir["operations"]:
        op = operation["op"]
        if op == "set_roof":
            target = by_element_id.get(str(operation["target_id"]))
            if target:
                target.update(deepcopy(operation["values"]))
        elif op in {"sweep", "anchor"}:
            components.append(deepcopy(operation["component"]))
        elif op == "array":
            elements.append(deepcopy(operation["element"]))
        elif op == "set_material":
            material = blueprint.setdefault("materials", {}).setdefault(operation["target_id"], {
                "roughness": 0.62, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            })
            material["baseColor"] = deepcopy(operation["baseColor"])


def gate_g7_style(blueprint: dict[str, Any], package: dict[str, Any]) -> GateReport:
    issues: list[GateIssue] = []
    expected_roof = package["roof"]["type"]
    roofs = [item for item in _elements(blueprint) if item.get("type") == "roof"]
    for roof in roofs:
        if roof.get("roofType") != expected_roof:
            issues.append(GateIssue("style_roof_mismatch", f"屋顶 {roof.get('id')} 未应用风格包屋顶 {expected_roof}", entity_ids=(str(roof.get("id") or "?"),)))
    roofs_by_id = {str(item.get("id")): item for item in roofs if item.get("id")}
    for cornice in (item for item in _components(blueprint) if item.get("type") == "cornice"):
        cornice_id = str(cornice.get("id") or "?")
        parent_id = str(cornice.get("parentRoof") or "")
        if not parent_id:
            continue
        parent = roofs_by_id.get(parent_id)
        if parent is None:
            continue  # G6 会报告悬空引用。
        if parent.get("roofType") not in {"flat", "gable", "hip"}:
            issues.append(GateIssue(
                "unsupported_roof_attachment",
                f"檐口 {cornice_id} 不能以 parentRoof 局部坐标依附 {parent.get('roofType')} 屋顶",
                entity_ids=(cornice_id, parent_id),
            ))
            continue
        half_x = float(parent.get("span") or 0) / 2
        half_z = float(parent.get("depth") or 0) / 2
        for index, point in enumerate(cornice.get("path") or []):
            try:
                outside = (
                    not isinstance(point, list) or len(point) != 3
                    or abs(float(point[0])) > half_x + 1e-6
                    or abs(float(point[2])) > half_z + 1e-6
                )
            except (TypeError, ValueError, IndexError):
                outside = True
            if outside:
                issues.append(GateIssue(
                    "cornice_outside_parent_roof",
                    f"檐口 {cornice_id}.path[{index}] 超出父屋顶 {parent_id} 的局部平面边界",
                    entity_ids=(cornice_id, parent_id),
                ))
                break
    ids: set[str] = set()
    for item in [*_elements(blueprint), *_components(blueprint)]:
        item_id = str(item.get("id") or "")
        if item_id in ids:
            issues.append(GateIssue("decor_duplicate_id", f"装饰构件 ID 重复：{item_id}", entity_ids=(item_id,)))
        ids.add(item_id)
    for report in (gate_g5_roof(blueprint), gate_g6_references(blueprint)):
        issues.extend(report.issues)
    return GateReport(
        gate="G7",
        name="风格与装饰闭环",
        passed=not any(issue.severity == "error" for issue in issues),
        issues=tuple(issues),
        metrics={
            "style_package_id": package["id"],
            "decor_component_count": sum(1 for item in _components(blueprint) if str(item.get("id") or "").startswith("decor_")),
        },
    )


def assemble_decor(
    body_blueprint: dict[str, Any],
    package: dict[str, Any],
    *,
    enforce_gate: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], GateReport]:
    blueprint = deepcopy(body_blueprint)
    decor_ir = build_decor_ir(blueprint, package)
    _apply_decor_ir(blueprint, decor_ir)
    report = gate_g7_style(blueprint, package)
    if enforce_gate and not report.passed:
        raise DecorAssemblyError(report)
    return blueprint, decor_ir, report
