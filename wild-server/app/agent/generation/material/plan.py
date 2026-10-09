"""材质计划的受控归一化与 Blueprint 应用逻辑。"""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from .recipes import infer_brick_preset, resolve_brick_preset


#: P6-A：用户提了材质/配色要求的**词面信号**。
#:
#: 🔴 这里刻意只判"有没有明确材质要求"，不判"有没有资产"——两件事曾经被绑成同一个
#: 条件（``elif catalog:``），于是**无纹理资产时用户提了配色也被完全无视**。
#: 材质设计决策与资产匹配必须分开判断：没有资产时仍然可以有合法的参数材质
#: （baseColor / roughness / metallic 全是参数，不需要贴图）。
#: 用户**提需求**时用的材质词（含具体材质名）。判"这次要不要做材质设计"用。
_MATERIAL_INTENT_TERMS = (
    "材质", "配色", "色调", "颜色", "色系", "主色", "辅色", "点缀",
    "墙面色", "外墙色", "屋面色", "地面色", "石材", "木色", "砖色", "涂料",
    "红砖", "青砖", "清水混凝土", "微水泥", "防腐木", "格栅", "幕墙",
    "material", "color", "colour", "palette", "texture", "材质搭配",
)

#: 用户**给反馈**时用的材质词。只收"明确在说材质"的决策词，**不收**"木""金属"
#: 这类材质名词做子串匹配 ——
#:
#: 🔴 反例：反馈"把木梁换成混凝土柱"含"木"（名词）却是**几何/结构**变更，不该换材质；
#: 反馈"木门换成玻璃"不含下表任何词却是**明确材质**变更。两类句子靠同一张名词表
#: 根本分不开，只能靠"这句话有没有在说材质"来判。
_MATERIAL_FEEDBACK_TERMS = (
    "材质", "材料", "颜色", "配色", "色调", "色系", "外墙色", "墙面", "幕墙",
    "material", "color", "colour", "palette", "texture",
)

#: 具体材质**名**。单独出现不构成材质决策（"木梁"是结构，"石材地面"才是材质），
#: 只与角色词同时出现时才算"在说材质"。
_MATERIAL_NAMES = (
    "玻璃", "木", "木纹", "金属", "钢", "铝", "石", "石材", "大理石", "砖",
    "混凝土", "涂料", "漆", "塑料", "织物", "布", "毛玻璃", "镜面",
)


def material_mentions(text: str) -> list[str]:
    """文本里出现过的**材质决策词**（给反馈路径用）。

    与 :func:`material_intent_terms` 分开是因为两个场景的词表不同：提需求时
    "红砖外墙"要能触发，判反馈时"红砖"不能触发（那是句子里恰好有的材质名）。

    🔴 **纯决策词覆盖不了"门改成玻璃的"这类句子** —— 它是明确的材质变更，却一个
    决策词都没有。补第二路判据：**材质名 + 角色词同时出现**才算（材质名单独出现
    不算，"把木梁换成混凝土柱"里有"木"和"混凝土"但没有角色词，仍然不算）。
    两路的交集为空，各自都漏，合起来才够用。
    """

    lowered = str(text or "").casefold()
    words = [term for term in _MATERIAL_FEEDBACK_TERMS if term.casefold() in lowered]
    has_material_name = any(word in str(text or "") for word in _MATERIAL_NAMES)
    has_role_word = any(word in str(text or "") for word in _SURFACE_ROLE_WORDS)
    if not words and has_material_name and has_role_word:
        words = ["<材质名+角色词>"]
    return words

#: **表面类**角色的同义词（判"这句话在谈某表面的材质"时只用这张）。
#:
#: 🔴刻意**不含 structure**：反馈"把木梁换成混凝土柱"里有材质名"木/混凝土"，
#: 但它谈的是**结构构件更换**，不是表面材质决策。柱/梁/框架一进来，
#: 这句就会被误判成材质变更，全楼颜色跟着重来一遍。
_SURFACE_ROLE_WORDS = (
    "外墙", "外立面", "墙面", "墙体", "立面", "楼板", "地面", "地板", "楼面",
    "屋面", "屋顶", "檐口", "门", "门扇", "大门", "窗", "窗框", "门框", "龙骨",
)

#: 材质角色的**同义表达** —— 用户说"外墙用红砖"时角色是 ``facade_primary``。
#: 这张表是"用户语义 → 受控角色名"的唯一映射点，不要在别处再写一份。
_ROLE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "facade_primary": ("外墙", "外立面", "墙面", "墙体", "立面", "外墙砖"),
    "structure": ("结构", "柱", "梁", "框架", "混凝土", "水泥"),
    "floor": ("楼板", "地面", "地板", "楼面"),
    "roof": ("屋面", "屋顶", "檐口", "瓦"),
    "frame": ("龙骨", "窗框", "门框", "金属框", "型材"),
    "door": ("门", "门扇", "大门"),
    "glass": ("玻璃", "幕墙玻璃"),
}


def material_intent_terms(user_message: str) -> list[str]:
    """用户话里出现过的材质/配色关键词（去重、保序）。"""

    text = str(user_message or "").lower()
    return [term for term in _MATERIAL_INTENT_TERMS if term.lower() in text]


def named_material_roles(user_message: str, role_specs: dict[str, Any]) -> list[str]:
    """用户明确点名了哪些材质角色（"外墙用红砖"⇒ ``["facade_primary"]``）。

    只认**角色同义词表里有的**说法，不做语义推断 —— 推断属于模型该干的活，
    这里只判"有没有指名道姓"。用于判断"这次生成有没有真的材质变化"。
    """

    text = str(user_message or "")
    return [
        role for role, words in _ROLE_SYNONYMS.items()
        if role in role_specs and any(word in text for word in words)
    ]


def needs_material_design(
    user_message: str,
    role_specs: dict[str, Any],
    *,
    has_catalog: bool,
    procedural_materials_enabled: bool = False,
) -> tuple[bool, str]:
    """这次生成**是否需要材质设计决策**（与"有没有资产可匹配"无关）。

    返回 ``(需要, 原因)``。三个真值：

    - 用户明确提了材质/配色要求 ⇒ 需要（哪怕一张贴图都没有：合法参数材质本身就
      承载设计，忽略用户要求等于把"有墙无洞"式的静默降级又搬回材质层）；
    - 有资产或开了程序化配方 ⇒ 需要（要决定哪张贴图配哪个角色）；
    - 其余 ⇒ 不需要，直接走确定性角色表。

    🔴 **不要在这里判断资产数量来代替判断设计需求**（旧代码就是这么写的）：
    "没有资产所以不需要设计"在无资产目录的机器上会静默吞掉全部配色要求。
    """

    terms = material_intent_terms(user_message)
    roles = named_material_roles(user_message, role_specs)
    if terms or roles:
        detail = "、".join((terms + roles)[:4])
        return True, f"用户明确提到材质/配色（{detail}）"
    if has_catalog:
        return True, "有可匹配的 PBR 资产，需要决定资产与角色的对应"
    if procedural_materials_enabled:
        return True, "程序化材质已启用，需要决定配方与角色的对应"
    return False, "没有材质要求、也没有可匹配资产，走确定性角色表"


ROLE_SPECS: dict[str, dict[str, Any]] = {
    "facade_primary": {
        "materialId": "wall_finish", "baseColor": [0.84, 0.82, 0.78],
        "roughness": 0.72, "metallic": 0.0,
    },
    "structure": {
        "materialId": "concrete", "baseColor": [0.66, 0.67, 0.68],
        "roughness": 0.76, "metallic": 0.0,
    },
    "floor": {
        "materialId": "floor_finish", "baseColor": [0.52, 0.51, 0.49],
        "roughness": 0.78, "metallic": 0.0,
    },
    "frame": {
        "materialId": "metal", "baseColor": [0.12, 0.13, 0.14],
        "roughness": 0.3, "metallic": 0.8,
    },
    "door": {
        "materialId": "wood", "baseColor": [0.38, 0.22, 0.12],
        "roughness": 0.62, "metallic": 0.0,
    },
    "glass": {
        "materialId": "glass", "baseColor": [0.72, 0.88, 0.96],
        "roughness": 0.08, "metallic": 0.0,
    },
    "roof": {
        "materialId": "roof", "baseColor": [0.27, 0.28, 0.3],
        "roughness": 0.76, "metallic": 0.0,
    },
    "ground": {
        "materialId": "ground", "baseColor": [0.34, 0.38, 0.33],
        "roughness": 0.9, "metallic": 0.0,
    },
    "accent": {
        "materialId": "accent", "baseColor": [0.42, 0.2, 0.09],
        "roughness": 0.5, "metallic": 0.0,
    },
}

ELEMENT_ROLE = {
    "wall": "facade_primary",
    "floor": "floor",
    "stair": "floor",
    "column": "structure",
    "beam": "structure",
    "roof": "roof",
}

#: 物件场景的受控材质角色。**materialId 与
#: `generation/objects/skeleton.py::OBJECT_MATERIALS` 的键逐字一致**——
#: 家具的 `material` 字段引用的是材质名，两边对不上就会出现"引用了一个不存在的材质"。
#:
#: 刻意不含 facade_primary / structure / floor / frame / door / roof / ground：
#: 一张桌子没有外墙与屋顶，为它"补齐"这些角色只会往蓝图里塞一堆用不上的材质，
#: 并让设计审核图纸出现不存在的构件语义。
OBJECT_ROLE_SPECS: dict[str, dict[str, Any]] = {
    "wood": {
        "materialId": "wood", "baseColor": [0.42, 0.26, 0.14],
        "roughness": 0.62, "metallic": 0.0,
    },
    "metal": {
        "materialId": "metal", "baseColor": [0.16, 0.17, 0.18],
        "roughness": 0.32, "metallic": 0.8,
    },
    "glass": {
        "materialId": "glass", "baseColor": [0.72, 0.88, 0.96],
        "roughness": 0.08, "metallic": 0.0,
    },
    "stone": {
        "materialId": "stone", "baseColor": [0.62, 0.60, 0.57],
        "roughness": 0.78, "metallic": 0.0,
    },
    "fabric": {
        "materialId": "fabric", "baseColor": [0.46, 0.44, 0.42],
        "roughness": 0.92, "metallic": 0.0,
    },
    "accent": {
        "materialId": "accent", "baseColor": [0.42, 0.20, 0.09],
        "roughness": 0.50, "metallic": 0.0,
    },
}

#: 角色名里"这一档必须是金属"的集合。`role == "frame"` 是建筑侧的对应写法，
#: 物件侧没有 frame 角色，用 `metal`——两处必须同时生效，否则金属会被
#: 0.15 的通用上限压成塑料。
_METALLIC_ROLES = frozenset({"frame", "metal"})


def material_role_specs(architecture_plan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """按方案是物件还是建筑选择受控角色表。

    判定复用 `design.resolver.is_object_plan`：只有一处判据，
    不会出现"这里当物件、那里当建筑"的分叉。
    """

    from app.design.resolver import is_object_plan

    return OBJECT_ROLE_SPECS if is_object_plan(architecture_plan) else ROLE_SPECS

# 骨架生成器会先用这些受控材质 ID 标记构件的“用途”：例如玻璃幕墙壳体
# 是 glass、龙骨是 metal、核心筒是 concrete。材质规划只能替换该用途对应的
# 具体材质参数，不能再仅凭 element.type 把所有 wall/beam 覆盖成同一种材质。
MATERIAL_ID_ROLE = {
    str(spec["materialId"]): role
    for role, spec in ROLE_SPECS.items()
}


def _element_material_role(element: dict[str, Any], *, curtain_wall: bool) -> str | None:
    """解析骨架构件的稳定材质角色，并修复已知的类型级错误覆盖。"""
    element_id = str(element.get("id") or "")
    element_type = str(element.get("type") or "")
    if curtain_wall and element_type == "wall" and "_shell_" in element_id:
        return "glass"
    if element_id.startswith("curtain_mullion_"):
        return "frame"
    if element_type == "wall" and (
        element_id.startswith("wall_core_") or "shaft_wall" in element_id
    ):
        return "structure"
    explicit_role = MATERIAL_ID_ROLE.get(str(element.get("material")))
    return explicit_role or ELEMENT_ROLE.get(element_type)


def compact_asset_catalog(manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只把选择材质所需的可信元数据交给模型，不暴露 URL。"""
    catalog: list[dict[str, Any]] = []
    for manifest in manifests:
        asset_id = manifest.get("assetId")
        maps = manifest.get("maps")
        if (
            not isinstance(asset_id, str)
            or manifest.get("kind") != "pbr_texture_set"
            or not isinstance(maps, dict)
            or "baseColor" not in maps
        ):
            continue
        classification = manifest.get("classification") or {}
        channels = sorted(maps)
        catalog.append({
            "assetId": asset_id,
            "kind": "pbr_texture_set",
            "name": str(manifest.get("name") or asset_id),
            "materialClass": classification.get("materialClass", "other"),
            "tags": list(classification.get("tags") or []),
            "recommendedRoles": list(classification.get("recommendedRoles") or []),
            "realWorldSizeMeters": manifest.get("realWorldSizeMeters", [1, 1]),
            "defaults": manifest.get("defaults", {}),
            "channels": channels,
            "baseColorOnly": channels == ["baseColor"],
            "sourceType": (manifest.get("source") or {}).get("type", "unknown"),
            "license": manifest.get("license", ""),
        })
    return catalog[:80]


def resolve_material_plan(
    raw_plan: dict[str, Any] | None,
    manifests: list[dict[str, Any]],
    architecture_plan: dict[str, Any] | None = None,
    user_message: str = "",
    *,
    procedural_materials_enabled: bool = False,
    role_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """把模型意图限制为固定角色、真实 assetId 和物理合理参数。

    ``role_specs`` 缺省按方案自动选择（建筑角色 / 物件角色）。显式传入是为了让
    调用方在"方案本身还没落成文档"时也能定住角色集，避免两处各判一次而分叉。
    """
    specs = role_specs or material_role_specs(architecture_plan)
    by_id = {
        item["assetId"]: item
        for item in manifests
        if isinstance(item, dict) and isinstance(item.get("assetId"), str)
    }
    requested_by_role: dict[str, dict[str, Any]] = {}
    raw_roles = raw_plan.get("roles", []) if isinstance(raw_plan, dict) else []
    if isinstance(raw_roles, list):
        for item in raw_roles:
            if isinstance(item, dict) and item.get("role") in specs:
                requested_by_role[str(item["role"])] = item

    roles: list[dict[str, Any]] = []
    resolved_assets: dict[str, dict[str, Any]] = {}
    rejected_asset_ids: list[str] = []
    rejected_procedural_preset_ids: list[str] = []
    automatic_preset = (
        infer_brick_preset(
            f"{user_message}\n{json.dumps(architecture_plan or {}, ensure_ascii=False)}"
        )
        if procedural_materials_enabled else None
    )
    stable_context = json.dumps(
        {"architecture": architecture_plan or {}, "request": user_message},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    for role, fallback in specs.items():
        requested = requested_by_role.get(role, {})
        asset_id = requested.get("assetId")
        asset = by_id.get(asset_id) if isinstance(asset_id, str) else None
        classification = (asset or {}).get("classification") or {}
        recommended_roles = classification.get("recommendedRoles") or []
        if role == "glass" or (asset and recommended_roles and role not in recommended_roles):
            if asset_id:
                rejected_asset_ids.append(str(asset_id))
            asset = None
            asset_id = None
        elif asset_id and asset is None:
            rejected_asset_ids.append(str(asset_id))
            asset_id = None

        preset_id = requested.get("proceduralPresetId") if procedural_materials_enabled else None
        if role == "facade_primary" and not preset_id and not requested.get("procedural"):
            preset_id = automatic_preset
        recipe = None
        if role == "facade_primary" and not asset and preset_id:
            recipe = resolve_brick_preset(
                preset_id,
                requested.get("shaderAdjustments"),
                stable_context=stable_context,
            )
            if recipe is None:
                rejected_procedural_preset_ids.append(str(preset_id))

        defaults = (asset or {}).get("defaults") or {}
        material_class = str(classification.get("materialClass") or "other")
        base_color = _safe_color(
            defaults.get("baseColorTint") if asset else recipe.get("baseColor") if recipe else requested.get("baseColor"),
            [1.0, 1.0, 1.0] if asset else fallback["baseColor"],
        )
        roughness = _unit(
            defaults.get("roughness") if asset else recipe.get("roughness") if recipe else requested.get("roughness"),
            fallback["roughness"],
        )
        metallic = _unit(
            defaults.get("metallic") if asset else requested.get("metallic"),
            fallback["metallic"],
        )
        if material_class == "metal" or role in _METALLIC_ROLES:
            metallic = max(0.5, metallic)
        else:
            metallic = min(0.15, metallic)

        material = {
            "baseColor": base_color,
            "roughness": roughness,
            "metallic": metallic,
            "albedo": 1.0,
            "lightingCondition": "D65_noon",
        }
        if asset:
            material.update({
                "textureSet": asset_id,
                "normalScale": _range(defaults.get("normalScale"), 0, 4, 1),
                "uvScale": _positive_pair(defaults.get("uvScale"), [1, 1]),
            })
            resolved_assets[str(asset_id)] = deepcopy(asset)
        elif role == "facade_primary" and procedural_materials_enabled:
            procedural = recipe.get("procedural") if recipe else _safe_procedural_brick(requested.get("procedural"))
            if procedural:
                material["procedural"] = procedural
        if role == "glass":
            material.update({
                "materialClass": "glass",
                "side": "double",
                "transmission": 0.92,
                "ior": 1.5,
                "thickness": 0.012,
                "attenuationColor": [0.82, 0.94, 1.0],
                "attenuationDistance": 6.0,
                "clearcoat": 0.08,
                "clearcoatRoughness": 0.12,
            })
        roles.append({
            "role": role,
            "materialId": fallback["materialId"],
            "assetId": asset_id,
            "proceduralPresetId": recipe.get("presetId") if recipe else None,
            "material": material,
        })

    concept = str((raw_plan or {}).get("concept") or _fallback_concept(architecture_plan))[:160]
    palette = (raw_plan or {}).get("palette") if isinstance(raw_plan, dict) else []
    if not isinstance(palette, list):
        palette = []
    # 玻璃幕墙：外墙用物理玻璃近似表达（wall + material=glass），而非不透明墙板。
    curtain_wall = "玻璃幕墙" in user_message or "玻璃幕" in user_message
    return {
        "concept": concept,
        "palette": [str(item)[:40] for item in palette[:5]],
        "roles": roles,
        "resolvedAssets": resolved_assets,
        "rejectedAssetIds": sorted(set(rejected_asset_ids)),
        "rejectedProceduralPresetIds": sorted(set(rejected_procedural_preset_ids)),
        "curtainWall": curtain_wall,
    }


def apply_resolved_material_plan(
    blueprint: dict,
    material_plan: dict | None,
    *,
    role_specs: dict[str, dict[str, Any]] | None = None,
) -> dict:
    """按骨架已有的语义材质角色写入方案，模型无法绕过资产白名单。

    ``role_specs`` 必须与产出该方案的 `resolve_material_plan` 用同一份角色表，
    否则物件场景的 wood/metal/glass 角色会被建筑角色白名单挡掉，
    结果是"材质方案批了却没写进蓝图"。
    """
    if not isinstance(material_plan, dict):
        return blueprint
    specs = role_specs or ROLE_SPECS
    materials = blueprint.setdefault("materials", {})
    if not isinstance(materials, dict):
        materials = {}
        blueprint["materials"] = materials
    role_material_ids: dict[str, str] = {}
    for item in material_plan.get("roles", []):
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        material_id = item.get("materialId")
        material = item.get("material")
        if role in specs and isinstance(material_id, str) and isinstance(material, dict):
            materials[material_id] = deepcopy(material)
            role_material_ids[str(role)] = material_id

    for element in blueprint.get("geometry", {}).get("elements", []):
        if not isinstance(element, dict):
            continue
        # 稳定语义 ID 可修复旧版本留下的错误覆盖；其他构件优先采用骨架明确
        # 写出的受控材质角色，最后才按元素类型使用旧版默认角色。
        role = _element_material_role(
            element,
            curtain_wall=material_plan.get("curtainWall") is True,
        )
        if role and role in role_material_ids:
            element["material"] = role_material_ids[role]

    resolved_assets = material_plan.get("resolvedAssets") or {}
    blueprint["assets"] = deepcopy(resolved_assets) if isinstance(resolved_assets, dict) else {}
    return blueprint


def material_region_field(role: str, target_type: str) -> str | None:
    """区域应用与履约共享材质引用落点；不向不支持的构件写虚构 material。"""
    from app.agent.generation.capability import capability_query
    capability = capability_query(target_type)
    fields = (capability.get("capability") or {}).get("fields") or {}
    field = {"frame": "frameMaterial", "door": "leafMaterial", "glass": "glassMaterial"}.get(role)
    return field if field in fields else "material" if "material" in fields else None


def apply_material_regions(
    blueprint: dict,
    regions: list[dict[str, Any]] | None,
    role_material_ids: dict[str, str],
) -> list[dict[str, Any]]:
    """P5-C：把「区域/构件 → 材质角色」的绑定落到已分配好的材质 id 上。

    🔴 这一步**只换引用**，不新增材质：材质实体由 :func:`apply_resolved_material_plan`
    按角色写好了，这里把某个区域/构件的 ``material`` 指向另一个角色的 ``materialId``。
    角色不在方案里 ⇒ **不动**那条构件（保持类型默认角色），并把原因返回给调用方记缺陷
    ——只标记不阻断：材质分区写错不该让整栋房子的墙消失。

    判据用**类型**（``element_type`` / ``component_type``），不用 id 前缀：
    id 命名会随编译演进，按 id 写规则等于把命名约定当契约。
    """
    applied: list[dict[str, Any]] = []
    if not regions:
        return applied
    geometry = blueprint.get("geometry")
    if not isinstance(geometry, dict):
        return applied
    for region in regions:
        if not isinstance(region, dict):
            continue
        role = str(region.get("role") or "")
        # 🔴 ``type`` 是**目标实体类型**（构件类如 railing/balcony，或元素类如
        # wall/floor/roof），不是"要不要按区域扫"的开关。判据是它在**哪张表**里：
        # 元素表（ELEMENT_ROLE）⇒ 只改那些元素；不在 ⇒ 改同名类型的构件。
        # 早先写成"没 type 就扫全部元素"会把 ``role='roof'`` 理解成"改所有元素"，
        # 于是地板楼梯一起被刷成屋顶材质。
        target_type = str(region.get("type") or "")
        material_id = role_material_ids.get(role)
        if not material_id:
            applied.append({
                "role": role, "target": target_type or "（未指定类型）",
                "applied": 0, "reason": f"材质方案里没有角色 {role!r}，该绑定未生效",
            })
            continue
        field_name = material_region_field(role, target_type)
        touched = 0
        for entity in [*(geometry.get("elements") or []), *(geometry.get("components") or [])]:
            if isinstance(entity, dict) and entity.get("type") == target_type and field_name:
                entity[field_name] = material_id
                touched += 1
        applied.append({
            "role": role, "target": target_type or "（未指定类型）", "applied": touched,
            "reason": "" if touched else f"类型 {target_type!r} 无匹配实体或不支持该角色的材质字段",
        })
    return applied

def _safe_color(value: Any, fallback: list[float]) -> list[float]:
    if (
        isinstance(value, list) and len(value) == 3
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    ):
        return [round(min(1.0, max(0.0, float(item))), 4) for item in value]
    return list(fallback)


def _unit(value: Any, fallback: float) -> float:
    return _range(value, 0, 1, fallback)


def _range(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return round(min(maximum, max(minimum, number)), 4)


def _positive_pair(value: Any, fallback: list[float]) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            pair = [float(item) for item in value]
        except (TypeError, ValueError):
            return list(fallback)
        if all(0 < item <= 64 for item in pair):
            return [round(item, 4) for item in pair]
    return list(fallback)


def _safe_procedural_brick(value: Any) -> dict[str, Any] | None:
    """只接收声明式红砖参数，丢弃未知字段并归一化到渲染器安全范围。"""
    if not isinstance(value, dict) or value.get("type") != "brick":
        return None

    raw_size = value.get("brickSize")
    if isinstance(raw_size, (list, tuple)) and len(raw_size) == 2:
        brick_size = [
            _range(raw_size[0], 0.04, 2.0, 0.24),
            _range(raw_size[1], 0.02, 1.0, 0.065),
        ]
    else:
        brick_size = [0.24, 0.065]
    max_mortar_width = min(0.03, min(brick_size) / 2 - 0.0001)
    weathering = value.get("weathering")
    if not isinstance(weathering, dict):
        weathering = {}

    return {
        "type": "brick",
        "seed": int(_range(value.get("seed"), 0, 2_147_483_647, 1)),
        "brickSize": brick_size,
        "mortarWidth": _range(value.get("mortarWidth"), 0.002, max_mortar_width, 0.01),
        "mortarDepth": _range(value.get("mortarDepth"), 0, 0.02, 0.006),
        "bond": value.get("bond") if value.get("bond") in {"running", "stack"} else "running",
        "secondaryColor": _safe_color(value.get("secondaryColor"), [0.68, 0.19, 0.08]),
        "colorVariation": _unit(value.get("colorVariation"), 0.12),
        "roughnessVariation": _unit(value.get("roughnessVariation"), 0.12),
        "edgeWear": _unit(value.get("edgeWear"), 0.05),
        "weathering": {
            "amount": _unit(weathering.get("amount"), 0),
            "scale": _range(weathering.get("scale"), 0.1, 100, 1.8),
            "efflorescence": _unit(weathering.get("efflorescence"), 0),
            "verticalStreaks": _unit(weathering.get("verticalStreaks"), 0),
            "baseDampness": _unit(weathering.get("baseDampness"), 0),
        },
    }


def _fallback_concept(architecture_plan: dict[str, Any] | None) -> str:
    source = json.dumps(architecture_plan or {}, ensure_ascii=False).lower()
    if any(term in source for term in ("chinese", "中式", "传统")):
        return "温润木色与低饱和矿物色形成克制的传统材质层级"
    if any(term in source for term in ("modern", "现代")):
        return "浅色主体、深色金属框和通透玻璃构成清晰的现代材质层级"
    return "耐久中性主材搭配少量深色框架与自然色点缀"
