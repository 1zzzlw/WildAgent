"""物件场景的最小骨架。

物件链不需要建筑骨架：没有墙、没有楼板、没有层高，也就没有"复杂度达标"
这件事。但下游（组件生成、合并、校验、交付）都建立在"存在一份 Blueprint"之上，
所以这里产出一份**结构合法、几何为空**的骨架：

    meta.type = "asset"，geometry.elements = []，geometry.components = []

`elements` 为空不是"没做完"——家具由后续 `generate_furniture_01` 条目写进
`geometry.elements`，这与 roof 走的是同一条路径（两者都声明 is_element）。

材质调色板刻意用**受控角色 ID**（wood / metal / glass / stone / fabric / accent），
与 `material_plan.OBJECT_ROLE_SPECS` 的 materialId 逐字一致，这样材质节点解析出的
受控方案能直接覆盖到物件上，而不会出现"模型引用了一个骨架里没有的材质名"。
"""

from __future__ import annotations

from typing import Any

#: 物件场景的默认材质调色板。键就是 `material` 字段的合法取值。
#: 参数是**缺省值**，材质节点跑完会被受控材质方案覆盖（见 OBJECT_ROLE_SPECS）。
OBJECT_MATERIALS: dict[str, dict[str, Any]] = {
    "wood": {
        "baseColor": [0.42, 0.26, 0.14], "roughness": 0.62,
        "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
    },
    "metal": {
        "baseColor": [0.16, 0.17, 0.18], "roughness": 0.32,
        "metallic": 0.8, "albedo": 1.0, "lightingCondition": "D65_noon",
    },
    "glass": {
        "baseColor": [0.72, 0.88, 0.96], "roughness": 0.08,
        "metallic": 0.0, "albedo": 1.0,
        "materialClass": "glass", "transmission": 0.92,
        "ior": 1.5, "thickness": 0.012,
        "lightingCondition": "D65_noon",
    },
    "stone": {
        "baseColor": [0.62, 0.60, 0.57], "roughness": 0.78,
        "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
    },
    "fabric": {
        "baseColor": [0.46, 0.44, 0.42], "roughness": 0.92,
        "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
    },
    "accent": {
        "baseColor": [0.42, 0.20, 0.09], "roughness": 0.50,
        "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
    },
}


#: 物件规格里进入提示词的字段。刻意只留这些：`rationale` 是方案层自述、
#: 对"把家具做对"没有约束力，带上只会挤占上下文。
_SPEC_FIELDS = ("kind", "subtype", "count", "width", "depth", "height", "placement")

#: 按 kind 才带上的字段（通用几何通道用）：
#:   name   用户点名的原始名词（"小人"/"花瓶"），生成节点据此写 id 与理由
#:   parts  `kind=primitive` 时的零件表（每个零件是一份 primitive 参数）
#:   params `kind=body` 时的专属参数（build / headShape / armLength …）
#: 家具不带这些，所以不能无脑全带上——一张桌子的规格里出现空 `parts`
#: 只会让模型怀疑自己漏做了什么。
_SPEC_CONDITIONAL_FIELDS = ("name", "parts", "params")


def object_specs(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """物件清单的**逐件规格**，交给构件生成节点逐条照做。

    为什么必须单独带一份，而不是只给 `component_quota`：家具共用 `kind="furniture"`，
    餐桌与椅子会被折进同一个配额条目，于是"1.8 米"和"围在长边两侧"这类
    **逐件信息在配额里被压成一条 note**，用户明写的尺寸就丢了。
    物件侧没有立面槽位可以承载这些信息，所以这里给它们一个专用通道。
    """

    raw_objects = plan.get("objects") if isinstance(plan, dict) else None
    if not isinstance(raw_objects, list):
        return []
    specs: list[dict[str, Any]] = []
    for item in raw_objects:
        if not isinstance(item, dict):
            continue
        spec = {field: item[field] for field in _SPEC_FIELDS if item.get(field) not in (None, "")}
        spec.update(
            {
                field: item[field]
                for field in _SPEC_CONDITIONAL_FIELDS
                if item.get(field) not in (None, "", [], {})
            }
        )
        # 只要求 `kind`：家具靠 subtype 表达形状，primitive/body 靠 parts/params 表达。
        # 早先这里要求 kind 与 subtype 同时存在，于是**通用几何通道的条目被静默丢弃**——
        # 方案批了、配额也派发了，生成节点却拿不到规格，只能自己乱猜。
        if spec.get("kind"):
            specs.append(spec)
    return specs


def build_object_skeleton(plan: dict[str, Any], user_message: str = "") -> dict[str, Any]:
    """从已批准物件方案生成空几何骨架。

    `plan` 只用于取概念名，几何一律不来自它——物件几何是构件生成节点的产物。
    """

    concept = ""
    if isinstance(plan, dict):
        concept = str(plan.get("concept") or "").strip()
    if not concept:
        concept = str(user_message or "").strip()[:40] or "单件场景"

    return {
        "meta": {
            "version": "1.1",
            "type": "asset",
            "name": concept[:80],
        },
        "geometry": {
            "elements": [],
            "components": [],
        },
        "materials": {key: dict(value) for key, value in OBJECT_MATERIALS.items()},
        "behaviors": {},
    }


def object_design_brief(plan: dict[str, Any]) -> dict[str, Any]:
    """物件场景的设计清单。

    与建筑链 `resolve_facade_layout` 的输出**同形**（下游 `expand_plan` /
    `strategy` / `build_skeleton_summary` 都按这几个键读），所以这两个模块不需要
    为物件加分支。区别是物件没有任何槽位集合——家具的数量由 quota 表达。

    刻意不调用 `resolve_facade_layout`：那个函数会从方案里推屋顶槽位与立面轴网，
    对一张桌子做这件事只会产出虚假信息。
    """

    quota: dict[str, dict[str, Any]] = {}
    raw_quota = plan.get("component_quota") if isinstance(plan, dict) else None
    if isinstance(raw_quota, dict):
        for kind, entry in raw_quota.items():
            if isinstance(entry, dict):
                quota[str(kind)] = dict(entry)
    return {
        "facade_plan": {},
        "component_quota": quota,
        "object_specs": object_specs(plan),
        "opening_slots": [],
        "balcony_slots": [],
        "roof_slots": [],
        "railing_slots": [],
        #: 物件场景没有"层"，但 realization 的键必须存在：下游按同一套键读。
        "realization": {
            "floors": 1,
            "modeled_floors": 1,
            "floor_height": 0.0,
            "representation_mode": "full",
            "shape": "object",
            "symmetry": False,
            "volumes": [],
        },
    }


__all__ = [
    "OBJECT_MATERIALS",
    "build_object_skeleton",
    "object_design_brief",
    "object_specs",
]
