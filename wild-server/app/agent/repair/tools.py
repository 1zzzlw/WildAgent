"""模型可选择、由程序执行的白名单局部修复工具。"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Iterable


REPAIR_TOOL_SPECS = [
    {
        "name": "add_entity",
        "description": "只在设计配额明确缺少某类构件时新增一个完整实体。",
        "arguments": {
            "repair_target": "design:<entity_type>",
            "entity": "complete entity object with a new unique id",
        },
    },
    {
        "name": "remove_entity",
        "description": "只删除本轮结构化问题明确列出的超额实体，删除后必须通过全量复检。",
        "arguments": {
            "entity_id": "string",
        },
    },
    {
        "name": "move_opening",
        "description": "移动一个 door/window/opening，只修改沿墙距离和高程。",
        "arguments": {
            "entity_id": "string",
            "along": "number|null",
            "elevation": "number|null",
        },
    },
    {
        "name": "resize_opening",
        "description": "调整一个 door/window/opening 的宽度或高度。",
        "arguments": {
            "entity_id": "string",
            "width": "positive number|null",
            "height": "positive number|null",
        },
    },
    {
        "name": "reparent_opening",
        "description": "把门窗改挂到一个真实 wall，可同时指定新的局部位置。",
        "arguments": {
            "entity_id": "string",
            "parent_wall": "string",
            "along": "number|null",
            "elevation": "number|null",
        },
    },
    {
        "name": "set_material_reference",
        "description": "把构件材质字段改为 Blueprint.materials 中已存在的 ID。",
        "arguments": {
            "entity_id": "string",
            "field": "material|frameMaterial|leafMaterial|glassMaterial",
            "material_id": "string",
        },
    },
    {
        "name": "patch_entity",
        "description": "修复墙、楼梯、屋顶等非门窗实体的少量几何字段；禁止修改 id/type。",
        "arguments": {
            "entity_id": "string",
            "changes": "object with whitelisted fields",
        },
    },
]

_MATERIAL_FIELDS = {"material", "frameMaterial", "leafMaterial", "glassMaterial"}
_COMPONENT_TYPES = {
    "door", "window", "railing", "canopy", "balcony", "ramp",
    "bay_window", "cornice", "chimney", "light",
}
_PATCH_FIELDS = {
    "from", "to", "position", "base", "width", "height", "thickness",
    "span", "depth", "radius", "bottomRadius", "topRadius", "style",
    "roofType", "parentWall", "parentFloor", "material", "frameMaterial",
    "leafMaterial", "glassMaterial", "crossSection", "dimensions", "overhang",
    "pitch", "rotation", "segmentCount", "steps", "stepCount", "stepHeight",
    "stepDepth", "frameWidth", "frameDepth", "leafDepth", "glassDepth",
}


def extract_repair_actions(text: str) -> list[dict]:
    """从普通输出或 reasoning 中选择最后一个合法的修复动作数组。"""
    if not text:
        return []
    decoder = json.JSONDecoder()
    candidates: list[list[dict]] = []
    for index, char in enumerate(text):
        if char != "[":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, list) or not value:
            continue
        if all(
            isinstance(action, dict)
            and isinstance(action.get("tool"), str)
            and isinstance(action.get("arguments"), dict)
            for action in value
        ):
            candidates.append(value)
    return candidates[-1] if candidates else []


def _entity_index(blueprint: dict) -> dict[str, dict]:
    geometry = blueprint.get("geometry", {})
    entities = [
        *geometry.get("elements", []),
        *geometry.get("components", []),
    ]
    return {
        entity["id"]: entity
        for entity in entities
        if isinstance(entity, dict) and entity.get("id")
    }


def _finite_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _changed_fields(before: dict, after: dict) -> list[str]:
    return sorted(
        key for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    )


def _set_opening_position(entity: dict, *, along=None, elevation=None) -> None:
    if entity.get("type") not in {"door", "window", "opening"}:
        raise ValueError("目标不是门窗/opening")
    position = entity.get("from")
    if not isinstance(position, list) or len(position) != 3:
        raise ValueError("目标缺少三维 from 坐标")
    if along is not None:
        if not _finite_number(along):
            raise ValueError("along 必须是有限数值")
        position[0] = float(along)
    if elevation is not None:
        if not _finite_number(elevation):
            raise ValueError("elevation 必须是有限数值")
        position[1] = float(elevation)


def _apply_action(blueprint: dict, entity: dict, tool_name: str, arguments: dict) -> None:
    if tool_name == "move_opening":
        _set_opening_position(
            entity,
            along=arguments.get("along"),
            elevation=arguments.get("elevation"),
        )
        return

    if tool_name == "resize_opening":
        if entity.get("type") not in {"door", "window", "opening"}:
            raise ValueError("目标不是门窗/opening")
        changed = False
        for field in ("width", "height"):
            value = arguments.get(field)
            if value is None:
                continue
            if not _finite_number(value) or float(value) <= 0:
                raise ValueError(f"{field} 必须是正数")
            entity[field] = float(value)
            changed = True
        if not changed:
            raise ValueError("必须提供 width 或 height")
        return

    if tool_name == "reparent_opening":
        if entity.get("type") not in {"door", "window", "opening"}:
            raise ValueError("目标不是门窗/opening")
        parent_wall = arguments.get("parent_wall")
        parent = _entity_index(blueprint).get(parent_wall)
        if not parent or parent.get("type") != "wall":
            raise ValueError("parent_wall 必须引用真实 wall")
        entity["parentWall"] = parent_wall
        _set_opening_position(
            entity,
            along=arguments.get("along"),
            elevation=arguments.get("elevation"),
        )
        return

    if tool_name == "set_material_reference":
        field = arguments.get("field")
        material_id = arguments.get("material_id")
        if field not in _MATERIAL_FIELDS:
            raise ValueError("材质字段不在白名单")
        materials = blueprint.get("materials", {})
        if material_id not in materials:
            raise ValueError("material_id 未在 Blueprint.materials 中定义")
        entity[field] = material_id
        return

    if tool_name == "patch_entity":
        changes = arguments.get("changes")
        if not isinstance(changes, dict) or not changes:
            raise ValueError("changes 必须是非空对象")
        illegal = set(changes) - _PATCH_FIELDS
        if illegal:
            raise ValueError(f"字段不允许修改: {sorted(illegal)}")
        for field, value in changes.items():
            if field in _MATERIAL_FIELDS:
                if value not in blueprint.get("materials", {}):
                    raise ValueError(f"材质 {value!r} 未定义")
            if field == "parentWall":
                parent = _entity_index(blueprint).get(value)
                if not parent or parent.get("type") != "wall":
                    raise ValueError("parentWall 必须引用真实 wall")
            entity[field] = deepcopy(value)
        return

    raise ValueError(f"未知修复工具: {tool_name}")


def execute_repair_actions(
    blueprint: dict,
    actions: Iterable[dict],
    *,
    allowed_entity_ids: set[str],
    allowed_add_types: set[str] | None = None,
    allowed_remove_ids: set[str] | None = None,
) -> tuple[dict, list[dict]]:
    """在副本上执行模型动作；单个动作失败时自动回滚该动作。"""
    candidate = deepcopy(blueprint)
    reports: list[dict] = []

    for action in actions:
        tool_name = action.get("tool") if isinstance(action, dict) else None
        arguments = action.get("arguments", {}) if isinstance(action, dict) else {}
        entity_id = arguments.get("entity_id") if isinstance(arguments, dict) else None
        if tool_name == "add_entity" and isinstance(arguments, dict):
            new_entity = arguments.get("entity", {})
            entity_id = new_entity.get("id") if isinstance(new_entity, dict) else None
        report = {
            "tool": tool_name,
            "entity_id": entity_id,
            "success": False,
            "changed_fields": [],
            "reason": action.get("reason", "") if isinstance(action, dict) else "",
        }
        try:
            if not tool_name or not isinstance(arguments, dict):
                raise ValueError("动作缺少 tool/arguments")
            if tool_name == "add_entity":
                repair_target = arguments.get("repair_target")
                entity = arguments.get("entity")
                if not isinstance(entity, dict):
                    raise ValueError("entity 必须是完整对象")
                entity_type = entity.get("type")
                if repair_target != f"design:{entity_type}":
                    raise ValueError("repair_target 与 entity.type 不一致")
                if entity_type not in (allowed_add_types or set()):
                    raise ValueError("只能新增设计配额明确缺失的类型")
                if not entity_id or entity_id in _entity_index(candidate):
                    raise ValueError("新增实体必须使用非空且唯一的 id")
                if entity_type in {"door", "window"}:
                    parent = _entity_index(candidate).get(entity.get("parentWall"))
                    if not parent or parent.get("type") != "wall":
                        raise ValueError("新增门窗必须引用真实 parentWall")
                    required = {"from", "width", "height"}
                    if any(field not in entity for field in required):
                        raise ValueError("新增门窗缺少 from/width/height")
                bucket = "components" if entity_type in _COMPONENT_TYPES else "elements"
                candidate.setdefault("geometry", {}).setdefault(bucket, []).append(deepcopy(entity))
                report["success"] = True
                report["changed_fields"] = ["<created>"]
                reports.append(report)
                continue
            if not entity_id or entity_id not in allowed_entity_ids:
                raise ValueError("只能修复本轮明确失败的实体")
            if tool_name == "remove_entity":
                if entity_id not in (allowed_remove_ids or set()):
                    raise ValueError("只能删除本轮明确列出的关联超额实体")
                removed = False
                geometry = candidate.get("geometry", {})
                for bucket in ("elements", "components"):
                    entities = geometry.get(bucket, [])
                    kept = [
                        entity for entity in entities
                        if not (
                            isinstance(entity, dict)
                            and entity.get("id") == entity_id
                        )
                    ]
                    if len(kept) != len(entities):
                        geometry[bucket] = kept
                        removed = True
                if not removed:
                    raise ValueError("目标实体不存在")
                report["success"] = True
                report["changed_fields"] = ["<removed>"]
                reports.append(report)
                continue
            entity = _entity_index(candidate).get(entity_id)
            if entity is None:
                raise ValueError("目标实体不存在")
            before = deepcopy(entity)
            working = deepcopy(entity)
            _apply_action(candidate, working, tool_name, arguments)
            changed = _changed_fields(before, working)
            if not changed:
                raise ValueError("动作没有产生任何修改")
            entity.clear()
            entity.update(working)
            report["success"] = True
            report["changed_fields"] = changed
        except Exception as exc:
            report["error"] = str(exc)
        reports.append(report)

    return candidate, reports
