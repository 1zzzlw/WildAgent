"""不依赖 Web 框架的物品资产导入校验。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MAX_ITEM_PARTS = 512
ENGINE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "storage" / "knowledge_base" / "schema.json"
)


def inspect_item_asset(blueprint: Any) -> list[str]:
    """返回会导致物品导入被拒绝的问题清单。"""

    issues: list[str] = []
    if not isinstance(blueprint, dict):
        return ["顶层不是 JSON 对象"]
    meta = blueprint.get("meta")
    if not isinstance(meta, dict):
        issues.append("缺少 meta")
    elif meta.get("type") != "asset":
        issues.append(f"meta.type 是 {meta.get('type')!r}，物品应当是 'asset'")
    geometry = blueprint.get("geometry")
    elements = geometry.get("elements") if isinstance(geometry, dict) else None
    if not isinstance(elements, list) or not elements:
        issues.append("geometry.elements 为空")
    else:
        if len(elements) > MAX_ITEM_PARTS:
            issues.append(f"物品零件超过上限 {MAX_ITEM_PARTS}")
        seen_ids: set[str] = set()
        for index, element in enumerate(elements):
            if not isinstance(element, dict):
                issues.append(f"elements[{index}] 不是对象")
                continue
            if element.get("type") not in {"primitive", "solid"}:
                issues.append(
                    f"elements[{index}].type = {element.get('type')!r}，"
                    "物品只允许 primitive / solid"
                )
            element_id = element.get("id")
            if not isinstance(element_id, str) or not element_id:
                issues.append(f"elements[{index}] 缺少 id")
            elif element_id in seen_ids:
                issues.append(f"elements[{index}].id 重复: {element_id}")
            else:
                seen_ids.add(element_id)

        for index, element in enumerate(elements):
            if not isinstance(element, dict):
                continue
            if element.get("type") == "solid" and element.get("kind") == "boolean":
                for operand in element.get("operands") or []:
                    if operand not in seen_ids:
                        issues.append(
                            f"elements[{index}].operands 引用了不存在的零件 {operand!r}"
                        )

    if isinstance(geometry, dict):
        for field in ("components", "templates", "instances", "placements"):
            if geometry.get(field):
                issues.append(
                    f"geometry.{field} 暂不属于物品资产；"
                    "请先展开为 primitive / solid"
                )
    if blueprint.get("behaviors"):
        issues.append("behaviors 暂不能随物品实例安全命名空间化；请导入纯几何物品")

    materials = blueprint.get("materials")
    assets = blueprint.get("assets")
    if assets is not None and not isinstance(assets, dict):
        issues.append("assets 必须是对象")
        assets = {}
    if blueprint.get("materialLibraries"):
        issues.append("materialLibraries 暂不能随物品实例导入；请把材质定义写入 materials")
    if materials is not None and not isinstance(materials, dict):
        issues.append("materials 必须是对象")
    elif isinstance(elements, list):
        declared = set(materials or {})
        for index, element in enumerate(elements):
            if not isinstance(element, dict):
                continue
            for key, value in element.items():
                if (
                    (key == "material" or key.endswith("Material"))
                    and isinstance(value, str)
                    and value not in declared
                ):
                    issues.append(f"elements[{index}].{key} 引用了未声明材质 {value!r}")
        for name, material in (materials or {}).items():
            texture_set = (
                material.get("textureSet") if isinstance(material, dict) else None
            )
            if isinstance(texture_set, str) and texture_set not in (assets or {}):
                issues.append(
                    f"materials.{name}.textureSet 引用了未声明资产 {texture_set!r}"
                )

    try:
        import jsonschema

        schema = json.loads(ENGINE_SCHEMA_PATH.read_text(encoding="utf-8"))
        for error in jsonschema.Draft202012Validator(schema).iter_errors(blueprint):
            location = "/".join(map(str, error.path))
            issues.append(f"/{location}: {error.message}")
    except Exception as error:  # noqa: BLE001 - 无法校验就不能写入正式目录
        issues.append(f"结构校验未执行: {error}")
    return issues


__all__ = ["MAX_ITEM_PARTS", "inspect_item_asset"]
