"""P4：设计履约验收 —— 最终 Blueprint 有没有兑现**批准的设计**。

## 为什么要有这一层

:func:`app.design.completeness.evaluate_design`（P2A）判的是**设计层字段**：
``/decisions/massing/floors`` 写了 2 就判 ``satisfied``。它证明"设计文档里这么写了"，
**不证明**蓝图里真的长出两层。编译降级、修复环改动、宿主解析失败都会让实体偏离设计，
所以同一条要求需要**两份证据**：设计层一份、实现层一份。
🔴 **设计层 satisfied 不能直接复制成最终通过** —— 那是本阶段存在的唯一理由。

## 三条边界

1. **不阻断**：履约不通过产出 ``status="open"``，**不**进 ``validation_results`` 那个几何门禁。
   进了就会撞上 ``WARNING_GATE_MAX=20`` 的保存门禁，把"合法但不完整"变成"不许保存"，
   与 P4「合法但不完整的产物可按既有政策交付并展示缺口」相反。
2. **不冒充**：判不了的路径一律 ``unsupported`` / ``needs_review``。缺一条证据不等于满足。
3. **不新建一套要求**：要求集合就是 ``DesignDocument.constraints``（P2A），状态枚举复用
   :class:`~app.design.contracts.DesignGap`。本模块只把观察面从**设计字段**换成**实体**。

## 复用而不是另建

目标字段是否合法、值怎么算相等，都直接问 :mod:`app.design.completeness`
（:func:`path_schema` / :func:`value_matches`，P2A 已在用）—— 同一份实现，
不复制第二套字段目录，也不建第二套要求对象。
"""
from __future__ import annotations

from typing import Any

from .completeness import path_schema, value_matches
from .contracts import DesignDocument, DesignGap, ObjectDecisions
from .openings import opening_kind

#: 履约判据口径。改动实体侧判定语义时递增，让旧报告自动失效（与
#: ``validation.diagnostics.VALIDATOR_VERSION`` 同类做法，但**独立**——几何校验器
#: 版本不该因为履约口径变化而失效，反之亦然）。
FULFILLMENT_VERSION = "entity-fulfillment/4"

#: 几何量的比较容差（米）。比 :func:`value_matches` 的 0.001 宽：实体坐标是
#: 墙顶/板底累加出来的，设计值是名义尺寸，0.05 以内不算"没兑现"。
_GEOM_TOLERANCE = 0.05

_OPENING_TYPES = frozenset({"door", "window", "bay_window"})


# ── 实体侧读取（只读几何事实，不做解释）──────────────────────────────


def _entities(blueprint: dict, kind: str) -> list[dict]:
    geometry = blueprint.get("geometry") or {}
    if kind == "element":
        return [item for item in geometry.get("elements") or [] if isinstance(item, dict)]
    return [item for item in geometry.get("components") or [] if isinstance(item, dict)]


def _by_type(blueprint: dict, *types: str) -> list[dict]:
    wanted = set(types)
    return [
        item
        for item in (*_entities(blueprint, "element"), *_entities(blueprint, "component"))
        if item.get("type") in wanted
    ]


def _bbox(blueprint: dict) -> tuple[float, float, float, float] | None:
    """建筑轮廓的 XZ 包围盒；**只取墙**，没有墙时退回楼板。

    🔴 屋顶**不能**参与：出檐本来就比墙体外扩（`overhang` 默认 0.55m），
    把它算进去会让"设计 width=18"永远判不满足。阳台/雨篷同理，故一律不取。
    """
    for kinds in (("wall",), ("wall", "floor"), ("floor", "column")):
        points: list[tuple[float, float]] = []
        for item in _by_type(blueprint, *kinds):
            for key in ("from", "to"):
                vector = item.get(key)
                if isinstance(vector, list) and len(vector) == 3 and all(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    for value in vector
                ):
                    points.append((float(vector[0]), float(vector[2])))
        if points:
            xs = [point[0] for point in points]
            zs = [point[1] for point in points]
            return (min(xs), min(zs), max(xs), max(zs))
    return None


def _floor_levels(blueprint: dict) -> list[float]:
    levels = {
        round(float(item["from"][1]), 2)
        for item in _by_type(blueprint, "floor")
        if isinstance(item.get("from"), list)
        and len(item["from"]) == 3
        and isinstance(item["from"][1], (int, float))
        and not isinstance(item["from"][1], bool)
    }
    return sorted(levels)


def _facing(element: dict, bbox: tuple[float, float, float, float] | None) -> str:
    """轴对齐墙的外向面：front=最小 Z、back=最大 Z、left=最小 X、right=最大 X。

    🔴 这是**几何推导**，不是设计意图：L 形建筑的"内院侧墙"会按它离包围盒中心
    的方向被判成某个面。判定因此只用于"该面开口数是否达到 bays"这类**计数**核对，
    且推不出面时返回空串（调用方降级为 ``needs_review``），不硬凑。
    """
    start, end = element.get("from"), element.get("to")
    if not (isinstance(start, list) and isinstance(end, list) and len(start) == 3 and len(end) == 3):
        return ""
    if bbox is None:
        return ""
    min_x, min_z, max_x, max_z = bbox
    center_x, center_z = (min_x + max_x) / 2, (min_z + max_z) / 2
    dx, dz = float(end[0]) - float(start[0]), float(end[2]) - float(start[2])
    mid_x, mid_z = (float(start[0]) + float(end[0])) / 2, (float(start[2]) + float(end[2])) / 2
    if abs(dx) >= abs(dz):
        return "front" if mid_z < center_z else "back"
    return "left" if mid_x < center_x else "right"


def _openings_by_facing(blueprint: dict) -> dict[str, dict[float, list[dict]]]:
    """``{面: {楼层标高: 开口列表}}``。

    分层的理由：``facades.<face>.bays`` 是**每层**的槽位数（`FacadeDecision.bays`
    配合 ``ground_pattern`` / ``upper_pattern`` 两层各一份）。不按层分组就会把
    两层的开口加起来去比 ``bays``，2 层住宅必然误判。楼层取**宿主墙的底标高**
    （开口自身的 ``from[1]`` 带窗台高，取整会漂）。
    """
    walls = {item.get("id"): item for item in _by_type(blueprint, "wall") if item.get("id")}
    bbox = _bbox(blueprint)
    grouped: dict[str, dict[float, list[dict]]] = {}
    for opening in _by_type(blueprint, *_OPENING_TYPES):
        parent = walls.get(opening.get("parentWall"))
        if parent is None:
            continue
        facing = _facing(parent, bbox)
        base = parent.get("from")
        if not facing or not (isinstance(base, list) and len(base) == 3):
            continue
        grouped.setdefault(facing, {}).setdefault(round(float(base[1]), 2), []).append(opening)
    return grouped


# ── 单条要求的实体侧判定 ────────────────────────────────────────────


def _close(actual: float, expected: float) -> bool:
    return abs(float(actual) - float(expected)) <= _GEOM_TOLERANCE


def _numeric_check(actual: float | None, expected: Any, check: str) -> str:
    """数值判据；``actual is None`` 表示实体侧量不出来（→ 交给调用方标 needs_review）。"""
    from math import isfinite
    if (actual is None or not isinstance(expected, (int, float))
            or isinstance(expected, bool) or not isfinite(expected)):
        return "needs_review"
    if check == "minimum":
        return "satisfied" if actual >= float(expected) else "open"
    if check == "equals":
        return "satisfied" if _close(actual, expected) else "open"
    return "needs_review"


def _entity_check(
    blueprint: dict,
    document: DesignDocument,
    target: str,
    expected: Any,
    check: str,
    instance_entities: list[dict[str, Any]] | None = None,
    roof_slots: list[dict[str, Any]] | None = None,
) -> tuple[str, Any, str]:
    """返回 ``(status, actual, evidence)``；``status`` 复用 :class:`DesignGap` 的枚举。"""
    tokens = target.strip("/").split("/")
    if len(tokens) < 2 or tokens[0] != "decisions":
        return "unsupported", None, f"{target} 不是设计决策路径，实体侧无对应物"
    root = tokens[1]

    # ── 体量：层数 / 尺寸 ──
    if root == "massing":
        field = tokens[2] if len(tokens) > 2 else ""
        if field == "floors":
            levels = _floor_levels(blueprint)
            representation = getattr(document.decisions, "massing", None)
            mode = getattr(representation, "representation_mode", "full")
            if mode != "full":
                return (
                    "needs_review", levels,
                    f"设计声明 representation_mode={mode}，示意模式不要求逐层楼板实体",
                )
            status = _numeric_check(float(len(levels)), expected, check)
            evidence = f"楼板标高 {levels}"
            return status, len(levels), evidence
        if field in {"width", "depth"}:
            bbox = _bbox(blueprint)
            if bbox is None:
                return "needs_review", None, "蓝图没有可取包围盒的实体"
            min_x, min_z, max_x, max_z = bbox
            actual = (max_x - min_x) if field == "width" else (max_z - min_z)
            status = _numeric_check(round(actual, 3), expected, check)
            return status, round(actual, 3), f"墙体包围盒 {field}={round(actual, 3)}"
        if field == "floor_height":
            levels = _floor_levels(blueprint)
            if len(levels) < 2:
                return "needs_review", None, f"楼板标高只有 {len(levels)} 层，算不出层高"
            heights = [round(levels[index + 1] - levels[index], 2) for index in range(len(levels) - 1)]
            statuses = [_numeric_check(height, expected, check) for height in heights]
            status = "open" if "open" in statuses else "needs_review" if "needs_review" in statuses else "satisfied"
            return status, heights, f"层高 {heights}"
        return "unsupported", None, f"massing.{field} 在实体侧没有可核对的对应物"

    # ── 屋顶：形态 ──
    if root == "roof":
        field = tokens[2] if len(tokens) > 2 else ""
        if field == "volumes":
            return _roof_volume_check(blueprint, tokens, expected, check, document, roof_slots)
        if field != "type":
            return (
                "unsupported", None,
                f"roof.{field} 由派生规则决定（实体侧无独立字段）：出檐与脊高是算出来的，"
                "逐体量差异走 roof.volumes",
            )
        roofs = _by_type(blueprint, "roof")
        if not roofs:
            return "open", None, "蓝图里没有屋顶实体"
        actual = sorted({str(item.get("roofType") or "") for item in roofs})
        ids = [str(item.get("id")) for item in roofs]
        if check == "contains":
            return ("satisfied" if expected in actual else "open"), actual, f"屋顶实体 {ids}"
        if check != "equals":
            return "needs_review", actual, f"屋顶形态检查 {check} 不适用"
        # 🔴 P5-A：图纸声明了逐体量覆盖时，``roof.type`` 是**模板**而不是"整栋唯一形态"。
        # 判据不是"覆盖条数 < 屋面条数"（那是数数，不是语义），而是**每个与模板不同的
        # 形态都能被某条已声明的覆盖解释**：解释得了就是兑现了另一条要求，不该在这里
        # 再报一次缺失；解释不了的（凭空冒出第三种形态）才是真缺口。
        overrides = getattr(document.decisions, "roof", None)
        declared_types = {
            str(item.type)
            for item in (getattr(overrides, "volumes", None) or [])
            if isinstance(getattr(item, "type", None), str) and item.type
        }
        if declared_types:
            if not roof_slots or len(roof_slots) != len(roofs):
                return "needs_review", actual, "逐体量屋面映射不完整，不能凭形态集合证明覆盖位置正确"
            for index, slot in enumerate(roof_slots, 1):
                entity = _entity_by_id(blueprint, f"roof_planned_{index:02d}")
                if not entity or entity.get("roofType") != slot.get("roofType", expected):
                    return "open", actual, f"体量 {slot.get('volume')} 最终屋型与其槽位不一致"
            return "satisfied", actual, "模板与逐体量覆盖已按槽位逐一核对最终屋面"
        status = "satisfied" if actual == [str(expected)] else "open"
        return status, actual, f"屋顶实体 {ids} 的 roofType"

    # ── 立面：每面槽位数 / 开敞表态 ──
    if root == "facades":
        if len(tokens) < 4:
            return "unsupported", None, f"{target} 未指到具体面"
        face, field = tokens[2], tokens[3]
        if field in {"ground_pattern", "upper_pattern"}:
            return _envelope_check(blueprint, document, face, field, expected, check)
        if field != "bays":
            return (
                "unsupported", None,
                f"facades.{face}.{field} 是开口类型序列，实体侧只能核对数量，不能按名逐槽核对",
            )
        facade = document.decisions.facades.get(face)
        if facade is None or any(opening_kind(token) not in {"door", "window"}
                                 for token in [*facade.ground_pattern, *facade.upper_pattern]):
            return "needs_review", None, "开间包含实墙或开敞槽位，不能用门窗数量代替开间数"
        grouped = _openings_by_facing(blueprint)
        if face not in grouped:
            return "needs_review", 0, f"蓝图里没有可判定为 {face} 面的墙（几何推不出朝向）"
        levels = sorted({round(float(w["from"][1]), 2) for w in _by_type(blueprint, "wall")
                         if isinstance(w.get("from"), list) and len(w["from"]) == 3})
        per_level = {level: len(grouped[face].get(level, [])) for level in levels}
        if not per_level:
            return "needs_review", None, "缺少楼层标高，无法逐层核对开间"
        if check == "minimum":
            worst = min(per_level.values())
            status = _numeric_check(float(worst), expected, check)
        elif check == "equals":
            # 每层都要等于 bays：任一层少了就是立面节奏错位。
            status = "satisfied" if all(
                count == expected for count in per_level.values()
            ) else "open"
        else:
            return "needs_review", per_level, f"{face} 面槽位检查 {check} 不适用"
        ids = [str(item.get("id")) for items in grouped[face].values() for item in items]
        return (
            status, per_level,
            f"{face} 面逐层开口数 {per_level}；开口实体 {ids[:12]}",
        )

    # ── 竖向交通 ──
    if root == "circulation":
        field = tokens[2] if len(tokens) > 2 else ""
        if field != "vertical_strategy":
            return "unsupported", None, f"circulation.{field} 在实体侧无对应物"
        if str(expected) == "core_and_stair":
            return "needs_review", None, "楼梯存在不能证明核心筒交通策略已兑现"
        stairs = _by_type(blueprint, "stair")
        wants_stair = str(expected) in {"stair", "core_and_stair"}
        if check == "contains":
            wants_stair = True
        if str(expected) == "none" or (check == "contains" and expected == "none"):
            return ("satisfied" if not stairs else "open"), len(stairs), f"stair 实体 {len(stairs)} 个"
        if not wants_stair:
            return "unsupported", None, f"vertical_strategy={expected!r} 尚无实体侧判据"
        return (
            ("satisfied" if stairs else "open"), len(stairs),
            f"stair 实体 {[str(item.get('id')) for item in stairs]}",
        )

    # ── 配额与必需构件（数量级）──
    if root in {"component_quota", "required_components"}:
        if root == "required_components":
            if check == "absent" and isinstance(expected, str):
                present = _by_type(blueprint, expected)
                return ("open" if present else "satisfied"), len(present), f"最终 {expected} 实体 {len(present)} 个"
            if check != "contains":
                return "needs_review", None, f"required_components 的 {check} 检查无实体侧判据"
            if not isinstance(expected, str) or not expected:
                return "needs_review", None, "contains 需要一个构件类型名称"
            present = _by_type(blueprint, expected)
            return ("satisfied" if present else "open"), len(present), f"最终 {expected} 实体 {len(present)} 个"
        component_type = tokens[2] if len(tokens) > 2 else ""
        bound = tokens[3] if len(tokens) > 3 else ""
        if component_type and bound not in {"min", "max"}:
            return "unsupported", None, f"component_quota.{component_type}.{bound} 不是数量界"
        actual = len(_by_type(blueprint, component_type))
        if bound == "max":
            from math import isfinite
            if (isinstance(expected, bool) or not isinstance(expected, (int, float))
                    or not isfinite(expected) or expected < 0 or check != "equals"):
                return "needs_review", actual, "数量上限需要非负有限数值及 equals 判据"
            return (
                ("satisfied" if actual <= float(expected) else "open"), actual,
                f"{component_type} 实体 {actual} 个（上限 {expected}）",
            )
        if not component_type or bound != "min":
            return "needs_review", actual, "数量要求必须定位到具体构件的 min/max"
        status = _numeric_check(float(actual), expected, "minimum" if check == "equals" else check)
        return status, actual, f"{component_type} 实体 {actual} 个（下限 {expected}）"

    # ── 实例清单：靠编译器给出的「实例索引 → 实体 id」映射逐条核对 ──
    if root == "components" and len(tokens) == 2 and isinstance(expected, list) and check == "equals":
        rows = []
        used = set()
        declared = document.decisions.components
        if len(expected) != len(declared):
            return "open", len(declared), "已采用的实例数组长度改变，不能用部分成员冒充整组兑现"
        for expected_instance in expected:
            if not isinstance(expected_instance, dict):
                rows.append(("unsupported", None, "实例要求不是对象"))
                continue
            matches = [i for i, inst in enumerate(declared) if i not in used and (
                inst.id == expected_instance["id"] if expected_instance.get("id") else
                value_matches(inst.model_dump(mode="json", exclude_none=True), expected_instance))]
            if len(matches) != 1:
                rows.append(("open", None, "实例绑定缺失或重复，不能借用同类型旧实体"))
                continue
            i = matches[0]
            used.add(i)
            rows.append(_instance_check(blueprint, ["decisions", "components", str(i)],
                                        expected_instance, check, instance_entities))
        return _aggregate(rows)
    if root == "components":
        return _instance_check(blueprint, tokens, expected, check, instance_entities)

    if root == "materials" and len(tokens) >= 4 and tokens[2] == "regions" and tokens[3].isdigit():
        from app.agent.generation.material.plan import material_region_field
        index = int(tokens[3])
        intent = document.decisions.materials
        if index >= len(intent.regions) or not intent.resolved_plan or check != "equals":
            return "needs_review", None, "材质区域或已解析方案缺失，或判据不适用"
        if len(tokens) > 4 and tokens[4] not in {"role", "type"}:
            return "needs_review", None, "该材质字段不是可核对的实体绑定"
        region = intent.regions[index]
        declared = region.model_dump(mode="json") if len(tokens) == 4 else getattr(region, tokens[4], None)
        if not value_matches(declared, expected):
            return "open", declared, "当前材质绑定不符合要求"
        role = next((item for item in intent.resolved_plan.roles if item.role == region.role), None)
        field = material_region_field(region.role, region.type)
        if role is None or field is None:
            return "unsupported", None, "该区域的材质角色或引用字段不受支持"
        entities = _by_type(blueprint, region.type)
        actual = {item["id"]: item.get(field) for item in entities}
        matched = bool(entities) and all(ref == role.materialId for ref in actual.values())
        matched = matched and value_matches((blueprint.get("materials") or {}).get(role.materialId), role.material)
        return ("satisfied" if matched else "open"), actual, f"逐实体核对 {field} 与材质 {role.materialId} 参数"

    if root in {"volumes", "structural_grid", "materials"}:
        return (
            "needs_review", None,
            f"{root} 的实体侧核对依赖尚未建立的映射（体量/轴网/材质），按红线不做文案关键词匹配",
        )

    return "unsupported", None, f"{target} 没有登记实体侧判据"


def _entity_by_id(blueprint: dict, entity_id: str | None) -> dict | None:
    if not entity_id:
        return None
    for item in (*_entities(blueprint, "element"), *_entities(blueprint, "component")):
        if item.get("id") == entity_id:
            return item
    return None


def _envelope_check(
    blueprint: dict,
    document: DesignDocument,
    face: str,
    field: str,
    expected: Any,
    check: str,
) -> tuple[str, Any, str]:
    """``/decisions/facades/<面>/<pattern>``：能不能核对应的那一面**有没有墙**。

    🔴 判据只能来自几何：某个朝向在**该 pattern 对应的楼层**上一根墙都没有 ⇒ 开敞。
    这是"有墙 vs 无墙"在实体上唯一能测出来的差别；反过来"有墙"推不出"这一格是
    有墙无洞还是开了窗"（那要按槽位逐个核对），所以只判开敞这一侧。

    🔴 **必须按楼层筛**：``ground_pattern`` 只管首层。写"首层开敞"而上层照常有墙是
    正常设计，不筛楼层会把上层那堵墙算成"没兑现"（实测：背面首层开敞时被上层
    ``wall_back_2`` 判成 open）。楼层取墙自己的 ``from[1]`` 底标高。
    """

    from .openings import is_open_side

    facade = getattr(document.decisions, "facades", {}).get(face)
    pattern = getattr(facade, field, None) if facade is not None else None
    if not isinstance(pattern, list) or not pattern:
        return "needs_review", None, f"facades.{face}.{field} 不在设计契约里，无法核对"
    if check != "equals" or not value_matches(pattern, expected):
        return "needs_review", pattern, "当前立面声明与要求不一致或判据不适用，不能据此证明实体履约"
    wants_open = is_open_side(pattern)
    bbox = _bbox(blueprint)
    floors = _floor_levels(blueprint)
    walls = []
    for item in _by_type(blueprint, "wall"):
        if _facing(item, bbox) != face:
            continue
        base = item.get("from")
        if not (isinstance(base, list) and len(base) == 3 and isinstance(base[1], (int, float))):
            continue
        level = round(float(base[1]), 2)
        if field == "ground_pattern" and floors and level != floors[0]:
            continue  # 上层墙不算首层开敞的证据
        if field == "upper_pattern" and floors and level <= floors[0]:
            continue  # 首层墙不属于 upper_pattern 的管辖范围
        walls.append(item)
    # 🔴 只判"声明开敞"这一侧：声明有墙而实体无墙，可能是修复环删了墙（几何门禁
    # 会报），也可能是朝向推导不出（L 形内院面）——两种都判不了，不猜。
    if not wants_open:
        return (
            "needs_review", len(walls),
            f"facades.{face}.{field} 声明为有墙（该面可判定为 {face} 的墙 {len(walls)} 根）；"
            "「哪一格是有墙无洞」需要逐槽核对，实体侧无对应字段",
        )
    if walls:
        return (
            "open", len(walls),
            f"facades.{face}.{field} 声明开敞无墙，但实体在该朝向仍有 {len(walls)} 根墙："
            f"{[item.get('id') for item in walls]}",
        )
    return (
        "satisfied", 0,
        f"facades.{face}.{field} 声明开敞无墙，实体在该朝向确无墙",
    )


def _roof_volume_check(
    blueprint: dict,
    tokens: list[str],
    expected: Any,
    check: str,
    document: DesignDocument,
    roof_slots: list[dict[str, Any]] | None,
) -> tuple[str, Any, str]:
    """``/decisions/roof/volumes/<i>/<字段>``（P5-A 逐体量覆盖）。

    证据是编译下发的 ``design_brief.roof_slots``：槽位序即屋面元素序
    （``conform_roofs_to_slots`` 按 ``enumerate(slots, start=1)`` 命名
    ``roof_planned_NN``），所以第 i 条槽位对应 ``roof_planned_{i+1}``。
    🔴 不靠这个**约定**去反推体量——槽位自带 ``volume`` 字段，直接按体量 id 找，
    序只是把体量映射到实体 id 的手段；槽位不在场就 needs_review。
    """

    raw_index = tokens[3] if len(tokens) > 3 else ""
    field = tokens[4] if len(tokens) > 4 else ""
    if not raw_index.isdigit():
        return "unsupported", None, f"/decisions/roof/volumes/{raw_index} 不是覆盖下标"
    index = int(raw_index)
    overrides = getattr(document.decisions, "roof", None)
    entries = list(getattr(overrides, "volumes", None) or [])
    if index >= len(entries):
        return "needs_review", None, f"图纸只声明了 {len(entries)} 条逐体量覆盖，第 {index} 条不存在"
    entry = entries[index]
    volume = str(getattr(entry, "volume", "") or "")
    if field not in {"type", "overhang"}:
        return "unsupported", None, f"roof.volumes.<i>.{field} 不在逐体量覆盖的可表态范围内"
    if not roof_slots:
        return (
            "needs_review", None,
            f"体量 {volume} 的逐体量覆盖没有对应的编译槽位证据（roof_slots 为空），"
            "无法确认这一块屋面是否独立生成",
        )
    slot = next((item for item in roof_slots if isinstance(item, dict) and item.get("volume") == volume), None)
    if slot is None:
        return (
            "needs_review", None,
            f"体量 {volume} 没有独立屋面槽位（可能是非顶层体量或形态不可分段），"
            "这条覆盖无从核对",
        )
    roof = _entity_by_id(blueprint, f"roof_planned_{roof_slots.index(slot) + 1:02d}")
    if roof is None:
        return (
            "needs_review", None,
            f"体量 {volume} 的槽位在最终 Blueprint 里找不到对应屋面元素（修复环可能改过产物）",
        )
    if field == "type":
        actual = str(roof.get("roofType") or "")
        return (
            ("satisfied" if actual == str(expected) else "open"), actual,
            f"体量 {volume} 的屋面 {roof.get('id')} roofType = {actual!r}"
            f"（跨度 {roof.get('span')}×{roof.get('depth')}）",
        )
    if check not in {"equals", "minimum"}:
        return "needs_review", None, f"出檐检查 {check} 尚无实体侧判据"
    intent = slot.get("overhang")
    if not isinstance(intent, (float, int)):
        return "needs_review", None, "旧槽位未保留出檐参数，需重新编译"
    # 槽位表达相邻边收口后的目标外轮廓；必须同时验证最终实体，不能仅相信槽位。
    actual = {key: roof.get(key) for key in ("position", "span", "depth")}
    matched = all(value_matches(actual[key], slot.get(key)) for key in actual)
    status = _numeric_check(intent, expected, check) if matched else "open"
    return status, actual, f"体量 {volume} 出檐 {intent}m 的目标轮廓与最终屋面核对；相邻体量接缝不外扩"


def _aggregate(rows: list[tuple]) -> tuple[str, Any, str]:
    if not rows:
        return "needs_review", [], "没有可核对的子项"
    statuses = [r[0] for r in rows]
    status = next((s for s in ("open", "unsupported", "needs_review") if s in statuses), "satisfied")
    return status, [{"status": s, "actual": a, "evidence": e} for s, a, e in rows], "逐子项核对；未知子项不被成功项覆盖"


def _instance_check(
    blueprint: dict,
    tokens: list[str],
    expected: Any,
    check: str,
    instance_entities: list[dict[str, Any]] | None,
) -> tuple[str, Any, str]:
    """``/decisions/components/<i>[/字段]`` 的实体侧核对。

    🔴 证据只认编译器给的 ``instance_entities``（实例索引 → 产出实体 id + 宿主意图）。
    本层**不自己解析** ``main_L2_roof`` 这类体量级宿主拼法 —— 那是编译器的解析规则，
    这里重写一遍必然分叉；映射不在就 ``needs_review``，不按"看起来对"判过。
    """
    if not instance_entities:
        return (
            "needs_review", None,
            "实例级宿主/位置证据需要实例→实体 ID 映射（compile_report.instance_entities），"
            "当前实体侧只有类型级证据，不足以判定这条要求",
        )
    raw_index = tokens[2] if len(tokens) > 2 else ""
    if not raw_index.isdigit():
        return "unsupported", None, f"/decisions/components/{raw_index} 不是实例下标"
    index = int(raw_index)
    field = "/".join(tokens[3:])
    entry = next(
        (item for item in instance_entities if item.get("index") == index), None,
    )
    if entry is None:
        return (
            "needs_review", None,
            f"第 {index} 条实例在编译记录里查不到（编译报告只覆盖实例清单命中的类型）",
        )
    label = f"第 {index} 条实例（图纸类型 {entry.get('declared_type')}）"
    if entry.get("outcome") == "dropped":
        return (
            "open", None,
            f"{label}整条未落地：宿主 {entry.get('declared_host') or '未指定'} 解析不到，"
            "编译期已丢弃（见 compile_report.instance_dropped）",
        )
    entity_id = entry.get("entity_id")
    entity = _entity_by_id(blueprint, entity_id)
    if entity is None:
        return (
            "open", entity_id,
            f"{label}在编译期映射到实体 {entity_id}，但最终 Blueprint 里找不到这条实体"
            "（修复环改动过产物或映射已过期），不能判它兑现",
        )

    if not field and isinstance(expected, dict):
        rows = []
        for key, value in expected.items():
            if key == "size" and isinstance(value, dict):
                rows.extend(_instance_check(blueprint, tokens[:3]+["size", k], v, check, instance_entities)
                            for k, v in value.items())
            else:
                rows.append(_instance_check(blueprint, tokens[:3]+[key], value, check, instance_entities))
        return _aggregate(rows)
    if not field:
        return "needs_review", entity_id, "实例要求不是可逐字段核对的对象"
    if field == "id":
        return ("satisfied" if entity_id == expected else "open"), entity_id, "核对稳定实例实体 ID"
    if field == "relation":
        from .relations import evaluate_support
        if not isinstance(expected, dict) or not value_matches(entry.get("relation"), expected):
            return "open", entry.get("relation"), "支撑关系声明不符合要求"
        evidence = evaluate_support(blueprint, entity_id, expected)
        return evidence["status"], evidence, evidence["reason"]

    if field == "type":
        actual = entity.get("type")
        if check == "contains":
            return (
                ("satisfied" if isinstance(actual, str) and isinstance(expected, str) and expected in actual else "open"), actual,
                f"{label}实体 {entity_id} 的 type = {actual!r}",
            )
        return (
            ("satisfied" if actual == expected else "open"), actual,
            f"{label}实体 {entity_id} 的 type = {actual!r}（图纸声明 {expected!r}）",
        )

    if field == "host":
        declared = entry.get("declared_host")
        if declared is None:
            return (
                "needs_review", None,
                f"{label}没有声明宿主，这条要求无法在实体侧核对",
            )
        intent = entry.get("host_intent")
        actual = entity.get(entry.get("entity_host_field"))
        if check != "equals":
            return "needs_review", actual, f"宿主检查 {check} 尚无实体侧判据"
        if intent == "resolved" and entry.get("relation"):
            evidence = _entity_by_id(blueprint, declared)
            return ("satisfied" if declared == expected and evidence else "open"), declared, "核对关系实例的真实宿主引用"
        if intent == "resolved":
            return (
                ("satisfied" if expected == declared and actual == entry.get("entity_host")
                 and _entity_by_id(blueprint, actual) is not None else "open"), actual,
                f"{label}宿主 {declared} 按原意解析到实体 {entity_id} 的 "
                f"{entry.get('entity_host_field')} = {actual}",
            )
        if intent == "fallback":
            return (
                "open", actual,
                f"{label}宿主 {declared} 没解析到，退用了第 {entry.get('host_sequence')} 条同类派生结果："
                f"实体 {entity_id} 实际挂在 {entry.get('entity_host_field')} = {actual} 上（错位）",
            )
        return (
            "needs_review", actual,
            f"{label}声明了宿主 {declared}，但该类型不按宿主对齐（编译器记为 host_intent={intent}），"
            "实体侧无从判断这条要求",
        )

    if field.startswith("form/"):
        from app.agent.compiler.compile import _INSTANCE_FORM_ROUTES
        key = field.split("/", 1)[1]
        route, mapped = _INSTANCE_FORM_ROUTES.get(key, ("field", key))
        container = entity.get("interaction", {}) if route in {"interaction", "interaction_fn"} else entity
        if route == "interaction_fn":
            mapped = "mode"
        if mapped not in container:
            return "needs_review", None, "该形态字段没有可核对的实体值"
        actual = container[mapped]
        return ("satisfied" if value_matches(actual, expected) else "open"), actual, "核对最终实体形态字段"
    if field == "form" and isinstance(expected, dict):
        if not expected:
            return "satisfied", {}, "未声明额外形态约束"
        return _aggregate([_instance_check(blueprint, tokens[:3]+["form", k], v, check, instance_entities)
                           for k, v in expected.items()])
    if field.startswith("size/"):
        key = field.split("/", 1)[1]
        if key not in entity:
            return (
                "unsupported", None,
                f"{label}实体 {entity_id} 没有 {key} 字段，尺寸无法核对",
            )
        actual = entity[key]
        status = _numeric_check(actual, expected, check) if isinstance(actual, (int, float)) else (
            "satisfied" if value_matches(actual, expected) else "open"
        )
        return status, actual, f"{label}实体 {entity_id}.{key} = {actual!r}（图纸声明 {expected!r}）"

    return (
        "needs_review", None,
        f"/decisions/components/<i>/{field} 在实体侧没有判据（实例映射只覆盖 type / host / size）",
    )


# ── 阶段入口 ────────────────────────────────────────────────────────


def evaluate_fulfillment(
    document: DesignDocument,
    blueprint: dict | None,
    design_hash: str,
    instance_entities: list[dict[str, Any]] | None = None,
    roof_slots: list[dict[str, Any]] | None = None,
) -> list[DesignGap]:
    """逐条判定**已支持的要求**在最终 Blueprint 上是否兑现。

    与 :func:`evaluate_design` 同源同枚举，只是观察面不同：
    ``layer="design"`` 看设计字段，本函数 ``layer="implementation"`` 看实体。

    - 不可靠的路径给 ``needs_review`` / ``unsupported``，**不**按"看起来没问题"算满足；
    - ``superseded`` 的决定不计入缺口，只在摘要里单独计数（显式取代不是"默默删掉"）。

    ``instance_entities`` 是编译器产出的「实例索引 → 实体 id + 宿主意图」映射
    （``compile_report.instance_entities``）。**缺它时实例级要求一律 needs_review** ——
    类型级证据不足以定位到具体实例。
    ``roof_slots`` 是逐体量屋面槽位（P5-A），缺它时 ``/decisions/roof/volumes/*``
    同样 needs_review。
    """
    if isinstance(getattr(document, "decisions", None), ObjectDecisions) or not isinstance(blueprint, dict):
        return []

    gaps: list[DesignGap] = []
    for constraint in document.constraints:
        if constraint.id == "request.source" or constraint.kind in {"engine_hard", "system_required"}:
            continue
        if constraint.adoption == "superseded":
            continue
        base = dict(
            constraint_id=constraint.id,
            layer="implementation",
            design_hash=design_hash,
            target=constraint.target,
            expected=constraint.expected,
        )
        if constraint.check == "manual" or constraint.adoption == "proposed":
            gaps.append(DesignGap(
                id="gap.impl." + constraint.id, status="needs_review", actual=None,
                evidence=f"{constraint.expression}：没有可靠的自动判定方法（check={constraint.check}，"
                         f"adoption={constraint.adoption}），需要人工确认",
                **base,
            ))
            continue
        # 目标字段必须真的存在于设计契约里，否则是"能力不支持"而不是"没做到"。
        if path_schema(document, constraint.target) is None:
            gaps.append(DesignGap(
                id="gap.impl." + constraint.id, status="unsupported", actual=None,
                evidence=f"{constraint.target}：目标字段不在当前设计契约中，无法核对",
                **base,
            ))
            continue
        status, actual, evidence = _entity_check(
            blueprint, document, constraint.target, constraint.expected, constraint.check,
            instance_entities, roof_slots,
        )
        gaps.append(DesignGap(
            id="gap.impl." + constraint.id,
            status=status,
            actual=actual,
            evidence=f"{constraint.expression}：{evidence}",
            **base,
        ))
    return gaps


def fulfillment_summary(
    gaps: list[DesignGap],
    *,
    design_hash: str,
    superseded: int = 0,
) -> dict[str, Any]:
    """机器可读履约报告 + 给人看的缺口摘要（交付文案与前端都消费这一份）。"""
    counts = {"satisfied": 0, "open": 0, "needs_review": 0, "unsupported": 0}
    outstanding: list[dict[str, Any]] = []
    for gap in gaps:
        counts[gap.status] = counts.get(gap.status, 0) + 1
        if gap.status != "satisfied":
            outstanding.append({
                "id": gap.id,
                "target": gap.target,
                "status": gap.status,
                "expected": gap.expected,
                "actual": gap.actual,
                "evidence": gap.evidence,
            })
    decided = counts["satisfied"] + counts["open"]
    return {
        "version": FULFILLMENT_VERSION,
        "design_hash": design_hash,
        "total": len(gaps),
        "satisfied": counts["satisfied"],
        "open": counts["open"],
        "needs_review": counts["needs_review"],
        "unsupported": counts["unsupported"],
        "superseded": superseded,
        # 满足率只统计"能判定"的条目；needs_review / unsupported 单列，不混进分母。
        "satisfied_ratio": round(counts["satisfied"] / decided, 3) if decided else None,
        "decided": decided,
        "decidable_coverage": round(decided / len(gaps), 3) if gaps else None,
        "satisfied_ids": [g.id for g in gaps if g.status == "satisfied"],
        "geometry_blocking": False,
        "gaps": outstanding,
    }


def fulfillment_line(summary: dict[str, Any]) -> str:
    """一行摘要，给交付文案用；没有可判定要求时不说话。"""
    if not summary.get("total"):
        return ""
    ratio = summary.get("satisfied_ratio")
    rate = f"{ratio:.0%}" if isinstance(ratio, (int, float)) else "无可判定项"
    parts = [
        f"设计履约：已兑现 {summary['satisfied']}/{summary['total']} 项；"
        f"可判定项满足率 {summary['satisfied']}/{summary.get('decided', summary['satisfied']+summary.get('open', 0))}（{rate}）；"
        f"可判定覆盖 {summary.get('decided', summary['satisfied']+summary.get('open', 0))}/{summary['total']}",
    ]
    if summary.get("open"):
        parts.append(f"未兑现 {summary['open']}")
    if summary.get("needs_review"):
        parts.append(f"待人工确认 {summary['needs_review']}")
    if summary.get("unsupported"):
        parts.append(f"当前不支持 {summary['unsupported']}")
    return "；".join(parts)
