"""ScenePatch 的确定性操作、材质检查和场景摘要。"""
import math
from copy import deepcopy


_MATERIAL_REFERENCE_FIELDS = (
    "material", "frameMaterial", "leafMaterial", "glassMaterial",
    "supportMaterial", "railingMaterial", "capMaterial",
    "baseMaterial", "shadeMaterial",
)


_TUNABLE_MATERIAL_FIELDS = (
    "baseColor", "roughness", "metallic", "albedo", "emissive",
    "opacity", "normalScale", "uvScale",
)


_MATERIAL_OPTIMIZATION_SUBJECTS = (
    "材质", "纹理", "贴图", "质感", "PBR", "pbr", "粗糙度",
    "金属度", "法线强度", "纹理比例",
)


_MATERIAL_OPTIMIZATION_ACTIONS = (
    "优化", "提升", "增强", "调整", "改善", "升级", "更真实", "真实一点",
)


def _is_material_optimization_request(message: str) -> bool:
    return (
        any(subject in message for subject in _MATERIAL_OPTIMIZATION_SUBJECTS)
        and any(action in message for action in _MATERIAL_OPTIMIZATION_ACTIONS)
    )


def _normalized_selection(selection: list[str] | None) -> list[str]:
    result: list[str] = []
    for item in selection or []:
        if isinstance(item, str) and item.strip() and item not in result:
            result.append(item)
    return result


def _material_display_fields(material: object) -> dict:
    """只把可调数值和资产引用交给模型，不暴露 Base64 或图片 URL。"""
    if not isinstance(material, dict):
        return {}
    fields = {
        key: material[key]
        for key in (*_TUNABLE_MATERIAL_FIELDS, "textureSet")
        if key in material
    }
    if isinstance(material.get("textures"), dict):
        fields["textureChannels"] = sorted(material["textures"])
    if material.get("embeddedImage"):
        fields["embeddedImage"] = "legacy-present"
    return fields


def _build_scene_summary(
    blueprint: dict,
    selection: list[str] | None = None,
) -> str:
    """从 Blueprint 生成场景摘要文本（注入 user message 供 AI 参考）"""
    geometry = blueprint.get("geometry", {})
    elements = geometry.get("elements", [])
    components = geometry.get("components", [])
    lines = [f"当前场景包含 {len(elements)} 个基础构件和 {len(components)} 个组合构件："]
    for el in elements:
        el_id = el.get("id", "?")
        el_type = el.get("type", "?")
        extras = []
        if el_type == "wall":
            extras.append(f"from={el.get('from', '?')}, to={el.get('to', '?')}")
            extras.append(f"thickness={el.get('thickness', '?')}")
        elif el_type == "column":
            extras.append(f"base={el.get('base', '?')}, height={el.get('height','?')}")
        elif el_type == "roof":
            extras.append(
                f"position={el.get('position', '?')}, "
                f"span={el.get('span','?')}, depth={el.get('depth','?')}"
            )
        elif el_type == "floor":
            extras.append(f"from={el.get('from', '?')}, to={el.get('to', '?')}")
        elif el_type == "opening":
            extras.append(
                f"parentWall={el.get('parentWall','?')}, from={el.get('from','?')}, "
                f"width={el.get('width','?')}, height={el.get('height','?')}"
            )
        else:
            for field_name in ("position", "base", "dimensions", "width", "height", "depth"):
                if field_name in el:
                    extras.append(f"{field_name}={el[field_name]}")
        lines.append(
            f"  - [{el_id}] type={el_type}"
            + (f" ({'; '.join(extras)})" if extras else "")
        )
    for component in components:
        component_id = component.get("id", "?")
        component_type = component.get("type", "?")
        extras = []
        if component_type in {"door", "window"}:
            extras.append(f"parentWall={component.get('parentWall', '?')}")
            extras.append(f"from={component.get('from', '?')}")
            extras.append(
                f"width={component.get('width', '?')}, height={component.get('height', '?')}"
            )
        elif component_type == "railing":
            extras.append(f"pathPoints={len(component.get('path', []))}")
        lines.append(
            f"  - [component:{component_id}] type={component_type}"
            + (f" ({'; '.join(extras)})" if extras else "")
        )
    materials = blueprint.get("materials", {})
    if materials:
        lines.append(f"已有材质: {', '.join(materials.keys())}")
    assets = blueprint.get("assets", {})
    if assets:
        lines.append(f"已有 PBR 资产: {', '.join(assets.keys())}")
    selected_ids = _normalized_selection(selection)
    if selected_ids:
        lines.append(f"当前选中构件: {', '.join(selected_ids)}")
        entities = {
            item.get("id"): item
            for item in [*elements, *components]
            if isinstance(item, dict) and item.get("id")
        }
        for entity_id in selected_ids:
            entity = entities.get(entity_id)
            if entity is None:
                lines.append(f"  - [{entity_id}] 不存在于当前 Blueprint")
                continue
            material_refs = {
                field_name: entity[field_name]
                for field_name in _MATERIAL_REFERENCE_FIELDS
                if isinstance(entity.get(field_name), str) and entity[field_name]
            }
            lines.append(
                f"  - [{entity_id}] 可调材质字段: "
                + (str(material_refs) if material_refs else "无")
            )
            for field_name, material_name in material_refs.items():
                material = materials.get(material_name)
                lines.append(
                    f"    {field_name}={material_name}: "
                    f"{_material_display_fields(material)}"
                )
                texture_set = material.get("textureSet") if isinstance(material, dict) else None
                asset = assets.get(texture_set) if isinstance(texture_set, str) else None
                if isinstance(asset, dict):
                    lines.append(
                        f"      asset={texture_set}, maps={sorted(asset.get('maps', {}))}, "
                        f"license={asset.get('license', '?')}"
                    )
    return "\n".join(lines)


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _validate_material_tuning_changes(changes: object, prefix: str) -> list[str]:
    if not isinstance(changes, dict) or not changes:
        return [f"{prefix} 必须是非空对象"]
    issues: list[str] = []
    unknown = sorted(set(changes) - set(_TUNABLE_MATERIAL_FIELDS))
    if unknown:
        issues.append(f"{prefix} 包含不允许的字段: {unknown}")

    for field_name in ("roughness", "metallic", "albedo", "opacity"):
        if field_name in changes and not (
            _is_finite_number(changes[field_name])
            and 0 <= changes[field_name] <= 1
        ):
            issues.append(f"{prefix}.{field_name} 必须是 0–1 有限数字")
    if "normalScale" in changes and not (
        _is_finite_number(changes["normalScale"])
        and 0 <= changes["normalScale"] <= 4
    ):
        issues.append(f"{prefix}.normalScale 必须是 0–4 有限数字")
    for field_name in ("baseColor", "emissive"):
        value = changes.get(field_name)
        if field_name in changes and not (
            isinstance(value, list)
            and len(value) == 3
            and all(_is_finite_number(channel) and 0 <= channel <= 1 for channel in value)
        ):
            issues.append(f"{prefix}.{field_name} 必须是 3 个 0–1 有限数字")
    uv_scale = changes.get("uvScale")
    if "uvScale" in changes and not (
        isinstance(uv_scale, list)
        and len(uv_scale) == 2
        and all(_is_finite_number(value) and 0 < value <= 64 for value in uv_scale)
    ):
        issues.append(f"{prefix}.uvScale 必须是两个 0–64 的正有限数字")
    return issues


def _validate_material_optimization_patch(
    patch: dict,
    selection: list[str],
) -> list[str]:
    """材质优化模式只能作用于选中目标，并且只能使用 tune_material。"""
    selected_ids = set(selection)
    if not selected_ids:
        return ["材质优化前必须先选中一个构件"]
    issues: list[str] = []
    for index, operation in enumerate(patch.get("operations", []), start=1):
        prefix = f"operations[{index}]"
        if not isinstance(operation, dict) or operation.get("op") != "tune_material":
            issues.append(f"{prefix} 材质优化模式只允许 tune_material")
        elif operation.get("id") not in selected_ids:
            issues.append(f"{prefix}.id 必须是当前选中构件")
    return issues


def _enrich_material_tuning_operations(blueprint: dict, patch: dict) -> None:
    """补入由当前 Blueprint 推导的只读前值，供确认界面稳定展示差异。"""
    geometry = blueprint.get("geometry", {})
    entities = {
        item.get("id"): item
        for item in [
            *geometry.get("elements", []),
            *geometry.get("components", []),
        ]
        if isinstance(item, dict) and item.get("id")
    }
    materials = blueprint.get("materials", {})
    for operation in patch.get("operations", []):
        if not isinstance(operation, dict) or operation.get("op") != "tune_material":
            continue
        entity = entities.get(operation.get("id"))
        material_field = operation.get("material_field", "material")
        source_name = entity.get(material_field) if isinstance(entity, dict) else None
        source = materials.get(source_name) if isinstance(materials, dict) else None
        changes = operation.get("changes")
        if isinstance(source_name, str) and isinstance(source, dict) and isinstance(changes, dict):
            operation["source_name"] = source_name
            operation["before"] = {key: source.get(key) for key in changes}


def _validate_scene_patch_operations(blueprint: dict, patch: dict) -> list[str]:
    """在应用前校验操作名、必填参数、目标和新增 ID。"""
    geometry = blueprint.get("geometry", {})
    element_ids = {
        item.get("id") for item in geometry.get("elements", [])
        if isinstance(item, dict) and item.get("id")
    }
    component_ids = {
        item.get("id") for item in geometry.get("components", [])
        if isinstance(item, dict) and item.get("id")
    }
    asset_ids = set(blueprint.get("assets", {}))
    materials = blueprint.get("materials", {})
    material_names = set(materials) if isinstance(materials, dict) else set()
    elements_by_id = {
        item.get("id"): item for item in geometry.get("elements", [])
        if isinstance(item, dict) and item.get("id")
    }
    components_by_id = {
        item.get("id"): item for item in geometry.get("components", [])
        if isinstance(item, dict) and item.get("id")
    }
    errors: list[str] = []

    for index, operation in enumerate(patch.get("operations", []), start=1):
        prefix = f"operations[{index}]"
        if not isinstance(operation, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        op_type = operation.get("op")

        if op_type in {"add_element", "add_component"}:
            field_name = "element" if op_type == "add_element" else "component"
            entity = operation.get(field_name)
            if not isinstance(entity, dict):
                errors.append(f"{prefix}.{field_name} 必须是完整对象")
                continue
            entity_id = entity.get("id")
            if not isinstance(entity_id, str) or not entity_id.strip():
                errors.append(f"{prefix}.{field_name}.id 缺失")
                continue
            if not isinstance(entity.get("type"), str) or not entity["type"].strip():
                errors.append(f"{prefix}.{field_name}.type 缺失")
            if entity_id in element_ids or entity_id in component_ids:
                errors.append(f"{prefix} 新增 ID 已存在: {entity_id}")
                continue
            (element_ids if op_type == "add_element" else component_ids).add(entity_id)
            continue

        if op_type in {
            "update_element", "remove_element",
            "update_component", "remove_component",
        }:
            entity_id = operation.get("id")
            target_ids = element_ids if op_type.endswith("element") else component_ids
            if not isinstance(entity_id, str) or entity_id not in target_ids:
                errors.append(f"{prefix} 目标不存在: {entity_id!r}")
                continue
            if op_type.startswith("update_"):
                changes = operation.get("changes")
                if not isinstance(changes, dict) or not changes:
                    errors.append(f"{prefix}.changes 必须是非空对象")
                elif {"id", "type"} & set(changes):
                    errors.append(f"{prefix}.changes 不允许修改 id/type")
            else:
                target_ids.remove(entity_id)
            continue

        if op_type == "upsert_material":
            if not isinstance(operation.get("name"), str) or not operation["name"].strip():
                errors.append(f"{prefix}.name 缺失")
            material = operation.get("material")
            if not isinstance(material, dict):
                errors.append(f"{prefix}.material 必须是对象")
            elif material.get("textureSet") and material["textureSet"] not in asset_ids:
                errors.append(
                    f"{prefix}.material.textureSet 资产不存在: "
                    f"{material['textureSet']}"
                )
            if isinstance(operation.get("name"), str) and operation["name"].strip():
                material_names.add(operation["name"])
            continue

        if op_type == "tune_material":
            entity_id = operation.get("id")
            entity = elements_by_id.get(entity_id) or components_by_id.get(entity_id)
            if entity is None:
                errors.append(f"{prefix} 目标不存在: {entity_id!r}")
                continue
            material_field = operation.get("material_field", "material")
            if material_field not in _MATERIAL_REFERENCE_FIELDS:
                errors.append(f"{prefix}.material_field 不受支持: {material_field!r}")
                continue
            source_name = entity.get(material_field)
            source_material = (
                materials.get(source_name)
                if isinstance(materials, dict) and isinstance(source_name, str)
                else None
            )
            if not isinstance(source_material, dict):
                errors.append(
                    f"{prefix} 目标字段 {material_field} 没有可克隆的现有材质"
                )
            new_name = operation.get("new_name")
            if not isinstance(new_name, str) or not new_name.strip():
                errors.append(f"{prefix}.new_name 缺失")
            elif new_name in material_names:
                errors.append(f"{prefix}.new_name 已存在: {new_name}")
            else:
                material_names.add(new_name)
            changes = operation.get("changes")
            errors.extend(_validate_material_tuning_changes(
                changes,
                f"{prefix}.changes",
            ))
            if isinstance(source_material, dict) and isinstance(changes, dict):
                if all(source_material.get(key) == value for key, value in changes.items()):
                    errors.append(f"{prefix}.changes 没有产生任何材质参数变化")
                texture_set = source_material.get("textureSet")
                texture_asset = (
                    blueprint.get("assets", {}).get(texture_set)
                    if isinstance(texture_set, str)
                    else None
                )
                has_normal_map = bool(
                    isinstance(source_material.get("textures"), dict)
                    and source_material["textures"].get("normal")
                ) or bool(
                    isinstance(texture_asset, dict)
                    and isinstance(texture_asset.get("maps"), dict)
                    and texture_asset["maps"].get("normal")
                )
                if "normalScale" in changes and not has_normal_map:
                    errors.append(
                        f"{prefix}.changes.normalScale 无法生效：当前材质没有 normal 纹理"
                    )
            continue

        if op_type == "upsert_asset":
            asset_id = operation.get("asset_id")
            asset = operation.get("asset")
            if not isinstance(asset_id, str) or not asset_id.strip():
                errors.append(f"{prefix}.asset_id 缺失")
            elif not isinstance(asset, dict):
                errors.append(f"{prefix}.asset 必须是对象")
            elif asset.get("assetId") != asset_id:
                errors.append(f"{prefix}.asset.assetId 必须与 asset_id 一致")
            else:
                asset_ids.add(asset_id)
            continue

        errors.append(f"{prefix}.op 不受支持: {op_type!r}")

    return errors


def _apply_patch_to_blueprint(blueprint: dict, patch: dict) -> dict:
    """将 ScenePatch 应用到 Blueprint 深拷贝，返回修改后的 Blueprint

    支持基础构件、组合构件、材质和资产清单的增量修改。
    """
    bp = deepcopy(blueprint)
    elements = bp.setdefault("geometry", {}).setdefault("elements", [])
    components = bp["geometry"].setdefault("components", [])

    for op in patch.get("operations", []):
        op_type = op.get("op")
        if op_type == "add_element":
            el = op.get("element")
            if el and isinstance(el, dict):
                elements.append(el)
        elif op_type == "update_element":
            el_id = op.get("id")
            changes = op.get("changes", {})
            for el in elements:
                if el.get("id") == el_id:
                    el.update(changes)
                    break
        elif op_type == "remove_element":
            el_id = op.get("id")
            bp["geometry"]["elements"] = [e for e in elements if e.get("id") != el_id]
            elements = bp["geometry"]["elements"]
        elif op_type == "add_component":
            component = op.get("component")
            if component and isinstance(component, dict):
                components.append(component)
        elif op_type == "update_component":
            component_id = op.get("id")
            changes = op.get("changes", {})
            for component in components:
                if component.get("id") == component_id:
                    component.update(changes)
                    break
        elif op_type == "remove_component":
            component_id = op.get("id")
            bp["geometry"]["components"] = [
                component for component in components
                if component.get("id") != component_id
            ]
            components = bp["geometry"]["components"]
        elif op_type == "upsert_material":
            name = op.get("name")
            material = op.get("material")
            if name and isinstance(material, dict):
                bp.setdefault("materials", {})[name] = material
        elif op_type == "tune_material":
            entity_id = op.get("id")
            material_field = op.get("material_field", "material")
            entity = next(
                (
                    item for item in [*elements, *components]
                    if isinstance(item, dict) and item.get("id") == entity_id
                ),
                None,
            )
            if entity is not None:
                source_name = entity.get(material_field)
                source = bp.get("materials", {}).get(source_name)
                new_name = op.get("new_name")
                changes = op.get("changes")
                if isinstance(source, dict) and new_name and isinstance(changes, dict):
                    tuned = deepcopy(source)
                    tuned.update(changes)
                    bp.setdefault("materials", {})[new_name] = tuned
                    entity[material_field] = new_name
        elif op_type == "upsert_asset":
            asset_id = op.get("asset_id")
            asset = op.get("asset")
            if asset_id and isinstance(asset, dict):
                bp.setdefault("assets", {})[asset_id] = asset

    return bp
