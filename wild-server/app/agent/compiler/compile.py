"""通用编译器：设计图纸 → 蓝图（纯函数，**零模型调用**）。

## 这个模块为什么不长

实测结论（探针 ``.workbuddy/diag/probe_deterministic_full_compile.py``）：
"槽位 → 元素"的确定性落地**本来就已经存在**，不需要重写——

| 层 | 已有实现 | 位置 |
| --- | --- | --- |
| A 层派生 | 结构（墙/楼板/柱/梁/楼梯） | ``architecture.skeleton.build_deterministic_skeleton`` |
| A 层派生 | 全部槽位（开口/阳台/屋顶/栏杆） | ``architecture.facade.resolve_facade_layout`` |
| B 层实例化 | 门窗（含凸窗、雨篷、灯） | ``architecture.facade.conform_openings_to_slots`` / ``conform_entrance_accessories`` |
| B 层实例化 | 阳台 / 栏杆 / 屋顶拆分 | ``conform_balconies_to_slots`` / ``conform_railings_to_slots`` / ``conform_roofs_to_slots`` |

这些 ``conform_*`` 全部**接受空输入并从槽位合成**（``tests/components/test_architecture_plan.py:221``
就是拿 ``[]`` 调的）。所以再写一遍"字段来源规则表 / 实例化循环"就是**重复实现**——
违反本仓库"唯一规则函数"的既有纪律。

本模块因此只做三件新事：

1. **接线**：按 ``assembly_workflow.py:275-330`` 的既有顺序，把上面这些串成**一次**编译
   （既有流程里它们是"模型产出之后的吸附/补足"，这里改成"没有模型产出也照样跑"）；
2. **补缺口**：单块屋顶没有槽位（历史上留给模型自由造型）→ 从 ``massing`` 派生；
   檐口 / 烟囱 / 灯具连槽位都没有 → 从**已落地的屋顶与墙面**派生
   （``_derive_attachments`` / ``_derive_lights``，都带"下限不满足就一个都不产"这道门）；
3. **四类诊断**：把散落的 stats 与校验字符串统一成
   ``defects`` / ``defaulted`` / ``unsupported`` / ``uncompiled``（见 ``diagnostics``）。
   ``defaulted`` 的判据取自注册表的 ``optional_fields``——该字段此前从未被读过
   （``components.py`` 里的死字段），本模块把它变成了"设计可表态字段"的唯一事实源。

## 不变式

- **纯函数**：无 IO、无 LLM、无全局状态；同样输入必然得到逐字节相同的产物。
- **不产生设计**：本模块只做映射，任何"图纸该改什么"只以 ``defects`` 报出，不自行修改输入。
"""

from __future__ import annotations

import math
from typing import Any

from loguru import logger

from app.agent.compiler.diagnostics import (
    MODE_FINAL,
    MODES,
    CompileDefault,
    CompileDefect,
    CompileResult,
)
from app.agent.generation.architecture import (
    build_deterministic_skeleton,
    conform_balconies_to_slots,
    conform_entrance_accessories,
    conform_openings_to_slots,
    conform_railings_to_slots,
    conform_roofs_to_slots,
    normalize_architecture_plan,
    resolve_facade_layout,
)
#: 外法向的判断依据（体量联合轮廓的绕向）。**故意**复用 facade 的私有实现而不是
#: 再写一遍 shoelace：本仓库的既有纪律是"唯一规则函数"，抄一份必然与入口雨棚/灯具
#: 的吸附口径分叉。若 facade 把它提为公开名，这里的导入路径要跟着改。
from app.agent.generation.architecture.facade import _plan_winding
#: 屋顶合法类型闭集。从既有定义导入而不是复制——闭集写两份就一定会分叉。
from app.agent.generation.architecture.profile import _SUPPORTED_ROOF_TYPES
from app.agent.generation.assembly import enforce_component_quota, enforce_element_quota
from app.agent.generation.components import COMPONENT_REGISTRY, get_implemented_components
from app.agent.generation.material_plan import (
    apply_resolved_material_plan,
    material_role_specs,
)
from app.agent.generation.slot_utils import component_slots
from app.agent.validation.design_constraints import validate_design_brief_constraints
from app.utils.blueprint_normalizer import _component_schema_key, get_schema

#: 挑出系数默认值。平坦屋顶没有脊高；坡屋顶按跨度取一个保守比例。
_DEFAULT_ROOF_THICKNESS = 0.25
_FLAT_ROOF = "flat"
#: 坡屋顶脊高 = max(下限, 该比例 × 较短跨)。确定性规则，不是让模型猜的造型自由度。
_PITCHED_ROOF_HEIGHT_RATIO = 0.18
_PITCHED_ROOF_HEIGHT_MIN = 0.8
_DEFAULT_OVERHANG = 0.35
_OVERHANG_MIN = 0.15
_OVERHANG_MAX = 0.8

#: 构件类型 → 该改图纸的哪一项。给收敛环定位设计块用；粗粒度但如实。
_DESIGN_FIELD = {
    "door": "decisions.facades.<face>.ground_pattern",
    "window": "decisions.facades.<face>.ground_pattern",
    "bay_window": "decisions.facades.<face>.ground_pattern",
    "roof": "decisions.roof",
    "balcony": "decisions.components[type=balcony]",
    "railing": "decisions.components[type=railing]",
    "canopy": "decisions.components[type=canopy]",
    "cornice": "decisions.roof",
    "chimney": "decisions.roof",
    "light": "decisions.facades.<face>",
}

# ── 附属构件派生（檐口 / 烟囱 / 灯具）──

#: 支持"局部依附"的屋顶类型闭集。**镜像**引擎
#: ``wild-core/src/compiler/components/attachedToSurface.ts::attachPointsToRoof``——
#: 它对闭集外的 roofType（``dome`` / ``chinese_curved`` / ``chinese_pagoda``）
#: 直接抛 ``ComponentCompileError``，那**会让整份蓝图在引擎里编译失败**。
#: ⇒ 派生的檐口 / 烟囱只能挂在这个闭集内的屋顶上；引擎侧放宽时必须同批放宽这里。
_ROOF_LOCAL_ATTACH = frozenset({"flat", "gable", "hip"})

#: roofType → 该屋顶的**檐边**，用「局部轴 + 符号」表达：
#: ``("x", -1)`` = 局部 ``x = -span/2`` 且沿 z 走向的那条边。
#:
#: 为什么不能"四条边都是檐口"：``roof.ts::roofSurfaceHeight`` 里
#: ``gable`` 的高度按 ``|localX| / (span/2)`` 衰减 ⇒ 坡向沿 x、屋脊沿 z，
#: 只有 ``x = ±span/2`` 两条边落在最低处（真正的檐口）；
#: ``z = ±depth/2`` 那两条是**山墙端**（由 ``gableEndPanels`` 表达，不是檐口）。
#: ``hip`` 按 ``max(|x|,|z|)`` 衰减 ⇒ 四条边都在最低处，四条都是檐边。
#: ``flat`` 是平屋面 ⇒ 四周都要一圈线脚。
_ROOF_EAVES: dict[str, tuple[tuple[str, int], ...]] = {
    "flat": (("x", -1), ("x", 1), ("z", -1), ("z", 1)),
    "gable": (("x", -1), ("x", 1)),
    "hip": (("x", -1), ("x", 1), ("z", -1), ("z", 1)),
}

#: 檐口参考截面（8 点，抄自知识库《檐口 cornice》的示例）。
#: X 是水平外挑量、Y 是竖向偏移；点的顺序构成闭合轮廓（``closedProfile``）。
_CORNICE_PROFILE: tuple[tuple[float, float], ...] = (
    (-0.16, -0.14), (0.16, -0.14), (0.16, -0.07), (0.10, -0.07),
    (0.10, 0.0), (0.05, 0.0), (0.05, 0.08), (-0.16, 0.08),
)

#: 烟囱是**设备尺寸**：按层数缩放，**不**按建筑宽深缩放（与核心筒井道同一口径）。
_CHIMNEY_SIZE_BASE = 0.45
_CHIMNEY_SIZE_PER_FLOOR = 0.12
_CHIMNEY_SIZE_MIN = 0.6
_CHIMNEY_SIZE_MAX = 0.9
_CHIMNEY_HEIGHT_BASE = 1.0
_CHIMNEY_HEIGHT_PER_FLOOR = 0.25
#: 必须小于 width/depth 的一半，否则引擎按壁厚校验抛错。
_CHIMNEY_WALL_THICKNESS = 0.12
_CHIMNEY_CAP_HEIGHT = 0.08
#: 沿屋脊自屋顶中心偏移的系数——避免正好压在正脊中心（也是屋面最高点）。
_CHIMNEY_RIDGE_OFFSET = 0.6

#: 灯具：入口壁灯的安装高度与外挑距离，与 ``conform_entrance_accessories``
#: 的吸附口径取同一组数（0.35 是外挑量、1.8 是门顶以上的安装高度）。
_LIGHT_WALL_OFFSET = 0.35
_LIGHT_MOUNT_HEIGHT = 1.8


# ── 屋顶派生：本模块唯一新增的派生逻辑 ──


def _roof_plan(plan: dict[str, Any]) -> dict[str, Any]:
    roof = plan.get("roof")
    return roof if isinstance(roof, dict) else {}


def _roof_overhang(plan: dict[str, Any]) -> float:
    """挑出距离，钳到 0.15~0.8。

    ⚠️ ``facade.py:205`` 有一份同样的钳制。两条路径**互斥**
    （有 ``roof_slots`` 就绝不会走单块分支），所以当前不会分叉；
    若将来要改，两处必须同批改。
    """

    raw = _roof_plan(plan).get("overhang")
    try:
        value = float(raw) if raw is not None else _DEFAULT_OVERHANG
    except (TypeError, ValueError):
        value = _DEFAULT_OVERHANG
    return max(_OVERHANG_MIN, min(_OVERHANG_MAX, value))


def _roof_type(plan: dict[str, Any]) -> str:
    """屋顶形态**来自图纸**（``decisions.roof.type``）——不是默认值。"""

    raw = str(_roof_plan(plan).get("type") or "").lower()
    return raw if raw in _SUPPORTED_ROOF_TYPES else _FLAT_ROOF


def _roof_material(materials: dict[str, Any]) -> str:
    if "roof" in materials:
        return "roof"
    return sorted(materials)[0] if materials else "default"


def _roof_style(plan: dict[str, Any], materials: dict[str, Any]) -> dict[str, Any]:
    """屋顶的风格字段（形态/厚度/材质）：多体量拆分时当模板用。

    脊高先置 0，拆分后由 :func:`_apply_pitched_heights` 按每块自己的跨度算——
    模板拿不到分块尺寸，写死一个值会在多体量下失真。
    """

    return {
        "type": "roof",
        "id": "roof_style_template",
        "roofType": _roof_type(plan),
        "height": 0.0,
        "thickness": _DEFAULT_ROOF_THICKNESS,
        "material": _roof_material(materials),
    }


def _apply_pitched_heights(elements: list[dict[str, Any]]) -> int:
    """给坡屋顶按自己的跨度补脊高；平坦屋顶保持 0。

    图纸协议里没有"屋顶高度"这一项（``decisions.roof`` 只有 type/ridge_axis/overhang），
    所以脊高必须是**规则算出**的，不能留空等模型。返回改动条数。
    """

    changed = 0
    for element in elements:
        if not isinstance(element, dict) or element.get("type") != "roof":
            continue
        if str(element.get("roofType") or _FLAT_ROOF) == _FLAT_ROOF:
            element["height"] = 0.0
            continue
        try:
            span = float(element.get("span") or 0.0)
            depth = float(element.get("depth") or 0.0)
        except (TypeError, ValueError):
            continue
        if span <= 0 or depth <= 0:
            continue
        element["height"] = round(
            max(_PITCHED_ROOF_HEIGHT_MIN, _PITCHED_ROOF_HEIGHT_RATIO * min(span, depth)), 3
        )
        changed += 1
    return changed


def _single_roof(plan: dict[str, Any], materials: dict[str, Any]) -> dict[str, Any]:
    """单一体量的整块屋顶。

    多体量时 ``resolve_facade_layout`` 会给出 ``roof_slots``（逐块无重叠），
    但**单一体量没有槽位**——既有设计把"整块屋顶的造型自由"留给了模型。
    编译器这一侧必须自己补上，否则"零模型"就永远缺一块屋顶。

    位置与尺度全部由 ``massing`` 算出：
    ``position[1]`` = 建模层数 × 层高（承托墙顶），``span/depth`` = 体量宽深 + 双侧挑出。
    """

    massing = plan.get("massing") if isinstance(plan.get("massing"), dict) else {}
    width = float(massing.get("width") or 10.0)
    depth = float(massing.get("depth") or 10.0)
    modeled_floors = int(massing.get("modeled_floors") or massing.get("floors") or 1)
    floor_height = float(massing.get("floor_height") or 3.2)
    overhang = _roof_overhang(plan)
    roof_type = _roof_type(plan)
    span = round(width + 2 * overhang, 3)
    span_depth = round(depth + 2 * overhang, 3)
    height = (
        0.0 if roof_type == _FLAT_ROOF
        else round(
            max(_PITCHED_ROOF_HEIGHT_MIN, _PITCHED_ROOF_HEIGHT_RATIO * min(span, span_depth)), 3
        )
    )
    return {
        "type": "roof",
        "id": "roof_01",
        "roofType": roof_type,
        "span": span,
        "depth": span_depth,
        "height": height,
        "thickness": _DEFAULT_ROOF_THICKNESS,
        "material": _roof_material(materials),
        "position": [
            round(width / 2, 3),
            round(modeled_floors * floor_height, 3),
            round(depth / 2, 3),
        ],
    }


# ── 附属构件派生（檐口 / 烟囱 / 灯具）──


def _quota_min(brief: dict[str, Any], kind: str) -> int:
    """该类型的设计下限；不在配额里、或 min<=0，都算"图纸没要求"。"""

    quota = brief.get("component_quota")
    limits = quota.get(kind) if isinstance(quota, dict) else None
    if not isinstance(limits, dict):
        return 0
    raw = limits.get("min")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0
    return max(0, int(raw))


def _millimetre_inward(value: float) -> float:
    """向内取整到毫米。

    引擎对 ``parentRoof`` 局部路径的边界检查是 ``abs(local) <= half + 1e-6``。
    直接把 ``span / 2`` 写进路径时，只要 ``span`` 带 4 位以上小数就会被浮点顶出去
    （``round(5.8505, 3) == 5.851 > 5.8505``）→ 引擎抛
    ``ComponentCompileError('超出父屋顶平面边界')`` → **整份蓝图编译失败**。
    向内取整到毫米既保证不越界，又让产物可读、可逐字节复现。
    """

    return math.floor(value * 1000) / 1000


def _roofs_of(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in elements if isinstance(item, dict) and item.get("type") == "roof"]


def _cornice_candidates(
    roofs: list[dict[str, Any]],
    materials: dict[str, Any],
) -> list[dict[str, Any]]:
    """每条檐边一段线脚，用 ``parentRoof`` 局部坐标给出（Y 是屋面高度偏移）。

    为什么走 ``parentRoof`` 而不是自己算世界坐标：KB《檐口 cornice》明文
    "建筑檐口应优先指定 ``parentRoof``"，且引擎会据此把路径贴到**已计算屋面**上
    （坡屋顶的檐边不是一条水平线）。代价是可用屋顶类型收窄到
    ``_ROOF_LOCAL_ATTACH``——闭集外的屋顶这段线脚留给模型通道。
    """

    material = _roof_material(materials)
    candidates: list[dict[str, Any]] = []
    for roof in roofs:
        roof_type = str(roof.get("roofType") or _FLAT_ROOF)
        edges = _ROOF_EAVES.get(roof_type)
        if edges is None:
            continue
        try:
            span = float(roof.get("span") or 0.0)
            depth = float(roof.get("depth") or 0.0)
        except (TypeError, ValueError):
            continue
        if span <= 0 or depth <= 0:
            continue
        # 平屋面的"檐"在板顶；坡屋面在屋面最低处（``roofSurfaceHeight`` 在边界上为 0）。
        local_y = (
            float(roof.get("thickness") or _DEFAULT_ROOF_THICKNESS)
            if roof_type == _FLAT_ROOF
            else 0.0
        )
        half_w = _millimetre_inward(span / 2)
        half_d = _millimetre_inward(depth / 2)
        for axis, sign in edges:
            # 路径跨满整条檐边（与 KB 示例一致）；截面自带外挑，转角自然搭接。
            if axis == "x":
                fixed = round(sign * half_w, 3)
                path = [[fixed, local_y, round(-half_d, 3)], [fixed, local_y, round(half_d, 3)]]
            else:
                fixed = round(sign * half_d, 3)
                path = [[round(-half_w, 3), local_y, fixed], [round(half_w, 3), local_y, fixed]]
            candidates.append({
                "type": "cornice",
                "id": f"cornice_{roof.get('id')}_{axis}{'p' if sign > 0 else 'n'}",
                "parentRoof": str(roof.get("id") or ""),
                "path": path,
                "profile": [[float(x), float(y)] for x, y in _CORNICE_PROFILE],
                "closedProfile": True,
                "material": material,
            })
    return candidates


def _chimney_candidates(
    roofs: list[dict[str, Any]],
    plan: dict[str, Any],
    materials: dict[str, Any],
) -> list[dict[str, Any]]:
    """每个体量的屋脊上立一根烟囱；位置相对屋顶中心，基座由引擎贴到屋面。

    落点取**屋面最高处**再沿屋脊偏移 ``_CHIMNEY_RIDGE_OFFSET``：``gable`` 的屋脊
    是局部 ``x = 0`` 这条线（高度不随 z 变），``hip`` / ``flat`` 的最高点在中心。
    基座位于最高处 ⇒ 筒身两侧都落在坡面**之上**，不会与屋面穿插
    （KB 也明写烟囱"不执行屋顶布尔穿透"，所以绝不能让它埋在屋面里）。
    """

    massing = plan.get("massing") if isinstance(plan.get("massing"), dict) else {}
    modeled_floors = int(massing.get("modeled_floors") or massing.get("floors") or 1)
    size = round(
        min(
            _CHIMNEY_SIZE_MAX,
            max(
                _CHIMNEY_SIZE_MIN,
                _CHIMNEY_SIZE_BASE + _CHIMNEY_SIZE_PER_FLOOR * modeled_floors,
            ),
        ),
        3,
    )
    height = round(_CHIMNEY_HEIGHT_BASE + _CHIMNEY_HEIGHT_PER_FLOOR * modeled_floors, 3)
    material = _roof_material(materials)
    candidates: list[dict[str, Any]] = []
    for roof in roofs:
        roof_type = str(roof.get("roofType") or _FLAT_ROOF)
        if roof_type not in _ROOF_LOCAL_ATTACH:
            continue
        try:
            depth = float(roof.get("depth") or 0.0)
        except (TypeError, ValueError):
            continue
        if depth <= 0:
            continue
        offset = 0.0
        if roof_type == "gable":
            offset = min(
                round(_CHIMNEY_RIDGE_OFFSET * depth / 2, 3),
                _millimetre_inward(depth / 2),
            )
        candidates.append({
            "type": "chimney",
            "id": f"chimney_{roof.get('id')}",
            "parentRoof": str(roof.get("id") or ""),
            "position": [0.0, 0.0, offset],
            "width": size,
            "depth": size,
            "height": height,
            "wallThickness": _CHIMNEY_WALL_THICKNESS,
            "capHeight": _CHIMNEY_CAP_HEIGHT,
            "material": material,
        })
    return candidates


def _wall_run_and_normal(
    plan: dict[str, Any],
    wall: dict[str, Any],
) -> tuple[float, float, float, float] | None:
    """墙的 ``(沿墙单位向量 ux,uz, 外法向单位向量 nx,nz)``。

    外法向**不能**假设"墙按逆时针围合"：体量拼出顺时针或凹形轮廓时，固定右旋 90°
    会把灯放到室内。绕向判定复用 ``facade._plan_winding``（与入口雨棚/灯具吸附
    同一依据），顺时针取反。
    """

    frm, to = wall.get("from"), wall.get("to")
    if not (isinstance(frm, list) and isinstance(to, list)):
        return None
    if len(frm) != 3 or len(to) != 3:
        return None
    try:
        dx = float(to[0]) - float(frm[0])
        dz = float(to[2]) - float(frm[2])
    except (TypeError, ValueError):
        return None
    length = math.hypot(dx, dz)
    if length < 1e-6:
        return None
    ux, uz = dx / length, dz / length
    sign = 1.0 if _plan_winding(plan, frm, ux, uz) >= 0 else -1.0
    return ux, uz, uz * sign, -ux * sign


def _light_candidates(
    plan: dict[str, Any],
    blueprint: dict[str, Any],
    brief: dict[str, Any],
) -> list[dict[str, Any]]:
    """每个外立面一盏壁灯；有门的墙优先落在门中，其余落在墙中。

    位置只做"贴墙外 0.35m、门高以上 1.8m"这一层粗对齐，**精对齐交给既有的**
    ``conform_entrance_accessories``——它已负责把入口墙上的灯吸附到门轴线，
    在这里再算一遍就是同一件事两个实现。
    """

    facade_plan = brief.get("facade_plan") if isinstance(brief.get("facade_plan"), dict) else {}
    walls = {
        str(item.get("id")): item
        for item in (blueprint.get("geometry") or {}).get("elements") or []
        if isinstance(item, dict) and item.get("type") == "wall"
    }
    doors: dict[str, dict[str, Any]] = {}
    for slot in brief.get("opening_slots") or []:
        if isinstance(slot, dict) and slot.get("type") == "door" and slot.get("wall_id"):
            doors.setdefault(str(slot["wall_id"]), slot)

    facing_order = {"front": 0, "back": 1, "left": 2, "right": 3}
    ordered = sorted(
        (
            (str(wall_id), item)
            for wall_id, item in facade_plan.items()
            if isinstance(item, dict) and item.get("facing") != "internal"
        ),
        # 主立面排最前、其次按 facing：配额上限裁剪时先保住入口那盏。
        key=lambda pair: (
            0 if pair[1].get("is_main_facade") else 1,
            facing_order.get(str(pair[1].get("facing")), 4),
            pair[0],
        ),
    )
    candidates: list[dict[str, Any]] = []
    for index, (wall_id, _wall_plan) in enumerate(ordered, start=1):
        wall = walls.get(wall_id)
        if not isinstance(wall, dict):
            continue
        run = _wall_run_and_normal(plan, wall)
        if run is None:
            continue
        ux, uz, nx, nz = run
        frm, to = wall["from"], wall["to"]
        try:
            base_y = min(float(frm[1]), float(to[1]))
            top_y = max(float(frm[1]), float(to[1]))
            length = math.hypot(float(to[0]) - float(frm[0]), float(to[2]) - float(frm[2]))
        except (TypeError, ValueError):
            continue
        door = doors.get(wall_id)
        if door is not None:
            along = float((door.get("from") or [0.0])[0]) + float(door.get("width") or 0.0) / 2
        else:
            along = length / 2
        along = max(0.15, min(along, max(0.15, length - 0.15)))
        candidates.append({
            "type": "light",
            "id": f"light_synthesized_{index:02d}",
            "position": [
                round(float(frm[0]) + ux * along + nx * _LIGHT_WALL_OFFSET, 3),
                round(min(base_y + _LIGHT_MOUNT_HEIGHT, top_y - 0.3), 3),
                round(float(frm[2]) + uz * along + nz * _LIGHT_WALL_OFFSET, 3),
            ],
            "fixtureType": "bulb",
            "initiallyOn": True,
        })
    return candidates


def _derive_attachments(
    plan: dict[str, Any],
    brief: dict[str, Any],
    elements: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    materials: dict[str, Any],
) -> list[dict[str, Any]]:
    """派生檐口与烟囱，**只在下限能被满足时才产出**。

    为什么要有"要么满足下限、要么一个都不产"这道门：
    ``validate_design_brief_constraints`` 对"配额下限没满足"报 ``error``，
    而 ``_capability_gaps`` 只看"该类型是否已经出现过"。
    ⇒ 下限 4 却只产出 1 个，会让这类型从 ``uncompiled``(warn) 掉进 (error)，
    **部分派生比完全不派生更糟**。差值交给模型通道补，所以这里宁可不产。
    """

    roofs = _roofs_of(elements)
    if not roofs:
        return []
    produced = {str(item.get("type")) for item in existing}
    derived: list[dict[str, Any]] = []
    for kind, candidates in (
        ("cornice", _cornice_candidates(roofs, materials)),
        ("chimney", _chimney_candidates(roofs, plan, materials)),
    ):
        minimum = _quota_min(brief, kind)
        if minimum <= 0 or kind in produced:
            continue
        if len(candidates) >= minimum:
            derived.extend(candidates)
    return derived


def _derive_lights(
    plan: dict[str, Any],
    blueprint: dict[str, Any],
    brief: dict[str, Any],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """灯具派生。与檐口/烟囱同一道下限门（见 :func:`_derive_attachments`）。"""

    minimum = _quota_min(brief, "light")
    if minimum <= 0 or any(item.get("type") == "light" for item in existing):
        return []
    candidates = _light_candidates(plan, blueprint, brief)
    return candidates if len(candidates) >= minimum else []


# ── 接线：一次编译 ──


def _compose(
    plan: dict[str, Any],
    user_message: str,
    material_plan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """把既有确定性部件串成一次编译，返回 ``(blueprint, design_brief, stats)``。

    **只归一化一次**：``build_deterministic_skeleton`` 内部也会归一化，但屋顶派生
    与立面解析都要读归一化后的 ``massing`` —— 各归一化一次会让两条路径读到不同的值，
    这正是本仓库记录过的"同一参数被两处夹取就分叉"。所以这里先归一化，全流程共用。
    """

    complexity = plan.get("complexity") if isinstance(plan.get("complexity"), dict) else None
    normalized = normalize_architecture_plan(plan, user_message, complexity)

    blueprint = build_deterministic_skeleton(normalized, user_message)
    # 已批准的材质方案必须落地在**任何按材质取名的步骤之前**：
    # `conform_openings_to_slots` / `_derive_lights` / `_roof_material` 都从
    # `blueprint["materials"]` 取名字，晚一步它们拿到的就是骨架硬编码的那 6 个
    # （`concrete/wall_finish/wood/metal/glass/roof`），材质方案等于白批。
    # `role_specs` 必须与产出该方案的 `resolve_material_plan` 用同一份角色表，否则
    # 物件场景的角色会被建筑白名单挡掉（既有注释已记过这个坑）。
    if isinstance(material_plan, dict) and material_plan:
        blueprint = apply_resolved_material_plan(
            blueprint, material_plan, role_specs=material_role_specs(normalized)
        )
    brief = resolve_facade_layout(blueprint, normalized)
    materials = blueprint.get("materials") if isinstance(blueprint.get("materials"), dict) else {}
    materials = materials or {}
    geometry = blueprint.setdefault("geometry", {})
    elements = list(geometry.get("elements") or [])
    components: list[dict[str, Any]] = []  # ← 模型产出置空：编译器不依赖任何模型输出

    components, opening_layout = conform_openings_to_slots(components, brief, materials)
    # 灯具先落位，再由既有的入口吸附器把入口墙那盏对齐到门轴线（顺序不能倒）。
    lights = _derive_lights(normalized, blueprint, brief, components)
    components = [*components, *lights]
    components, entrance_layout = conform_entrance_accessories(components, brief, blueprint)
    components, balcony_layout = conform_balconies_to_slots(components, brief)
    components, railing_layout = conform_railings_to_slots(components, brief)

    quota = brief.get("component_quota") if isinstance(brief.get("component_quota"), dict) else {}
    quota = quota or {}
    roof_slots = brief.get("roof_slots") or []
    roof_min = int((quota.get("roof") or {}).get("min") or 0)
    roof_layout = {"split": 0, "synthesized": 0}
    if roof_slots:
        elements, roof_layout = conform_roofs_to_slots(
            [*elements, _roof_style(normalized, materials)], brief
        )
    elif roof_min > 0:
        # 无屋盖场景（quota.min == 0）不生成——判据取自图纸配额，不在这里另判一次。
        elements = [*elements, _single_roof(normalized, materials)]
        roof_layout = {"split": 0, "synthesized": 1}
    _apply_pitched_heights(elements)

    # 檐口/烟囱要读**已成形的屋顶**，所以必须排在屋盖落地之后。
    attachments = _derive_attachments(normalized, brief, elements, components, materials)
    components = [*components, *attachments]

    if quota and components:
        components, pruned_components = enforce_component_quota(
            components, quota, brief.get("facade_plan") or {}, logger
        )
        if pruned_components:
            logger.info(f"[compile] 配额强制：移除 {pruned_components} 个超额构件")
    if quota and elements:
        elements, pruned_elements = enforce_element_quota(
            elements,
            quota,
            logger,
            slot_kinds={str(slot.get("type")) for slot in component_slots(brief)},
        )
        if pruned_elements:
            logger.info(f"[compile] 配额强制：移除 {pruned_elements} 个超额元素")

    geometry["elements"] = elements
    geometry["components"] = components
    stats = {
        "opening": opening_layout,
        "entrance": entrance_layout,
        "balcony": balcony_layout,
        "railing": railing_layout,
        "roof": roof_layout,
        "cornice": sum(1 for item in attachments if item.get("type") == "cornice"),
        "chimney": sum(1 for item in attachments if item.get("type") == "chimney"),
        "light": len(lights),
    }
    return blueprint, brief, stats


# ── 诊断 ──


def _schema_fields(component_type: str) -> tuple[set[str], set[str], dict[str, Any]]:
    """取某类型的 ``(允许字段, 必填字段, 字段 schema)``。

    ``_component_schema_key`` 处理 ``bay_window → bayWindowComponent`` 这类映射；
    墙/楼板/柱/梁/楼梯/屋顶在 ``$defs`` 里就是类型名本身，故再回退一次。
    """

    defs = get_schema().get("$defs", {})
    key = _component_schema_key(component_type)
    if key not in defs:
        key = component_type
    definition = defs.get(key)
    if not isinstance(definition, dict):
        return set(), set(), {}
    properties = definition.get("properties") or {}
    return set(properties), set(definition.get("required") or []), properties


def _enum_of(prop_schema: Any) -> list[str] | None:
    if isinstance(prop_schema, dict) and isinstance(prop_schema.get("enum"), list):
        return [str(value) for value in prop_schema["enum"]]
    return None


def _structure_defects(blueprint: dict[str, Any]) -> list[CompileDefect]:
    """必填缺失与枚举越界——纯 schema 判定，与具体构件类型无关。

    必填取 **schema 的 ``required`` ∪ 注册表的 ``required_fields``**：
    两者不等价（``door`` 的 ``interaction`` 只在注册表里是必填），
    取并集才既挡住"引擎渲染不了"，又挡住"模型契约缺字段"。
    """

    geometry = blueprint.get("geometry") or {}
    entities = [*(geometry.get("elements") or []), *(geometry.get("components") or [])]
    defects: list[CompileDefect] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        component_type = str(entity.get("type") or "")
        target = str(entity.get("id") or component_type or "?")
        allowed, required, properties = _schema_fields(component_type)
        if not allowed:
            continue
        entry = COMPONENT_REGISTRY.get(component_type)
        if entry is not None:
            required = required | set(entry.required_fields)
        for field_name in sorted(required - set(entity)):
            defects.append(
                CompileDefect(
                    code="required_missing",
                    severity="error",
                    target=target,
                    evidence=f"{component_type} 缺少必填字段 {field_name}",
                    design_field=_DESIGN_FIELD.get(component_type, ""),
                )
            )
        for field_name in sorted(set(entity) & allowed):
            values = _enum_of(properties.get(field_name))
            if values is None or entity[field_name] is None:
                continue
            if str(entity[field_name]) not in values:
                defects.append(
                    CompileDefect(
                        code="enum_invalid",
                        severity="error",
                        target=target,
                        evidence=(
                            f"{component_type}.{field_name}="
                            f"{entity[field_name]!r} 不在闭集 {values}"
                        ),
                        design_field=_DESIGN_FIELD.get(component_type, ""),
                    )
                )
    return defects


#: 结构元素的 id 前缀。它们**完全由确定性骨架拥有**（尺寸/标高/位置全来自体量块），
#: 所以这类元素出的问题统一回指 ``decisions.massing``。
_STRUCTURE_ID_PREFIXES = (
    "wall_",
    "floor_",
    "slab_",
    "column_",
    "beam_",
    "stair_",
    "landing_",
)


def _design_field_of_issue(message: str, blueprint: dict[str, Any]) -> str:
    """把校验器的一句诊断回指到"该改图纸哪一项"。

    命名约定取自 ``spatial_tools`` 的既有文案：

    - ``❌ [component:<id>] …`` → 取该构件的 ``type``，走 :data:`_DESIGN_FIELD`；
    - ``❌ [<element_id>] …`` → 按 id 前缀判归属：
      结构元素 → ``decisions.massing``；幕墙竖梃 → ``decisions.facades``；
      井道墙 → ``decisions.circulation``；
    - 其余（``❌ 缺少顶层字段 'meta'`` 这类蓝图级）→ ``""``。

    🔴 **认不出就返回空串，不猜。** 收敛环拿到空 ``design_field`` 只会"整图重出"；
    猜错则会跑去改**另一个块**——那比不定位更糟（同一参数被两处夹取就会分叉）。
    """

    start = message.find("[")
    end = message.find("]", start + 1) if start >= 0 else -1
    if start < 0 or end < 0:
        return ""

    token = message[start + 1 : end]
    if token.startswith("component:"):
        component_id = token.split(":", 1)[1]
        for item in (blueprint.get("geometry") or {}).get("components") or []:
            if not isinstance(item, dict) or str(item.get("id")) != component_id:
                continue
            kind = str(item.get("type") or "")
            return _DESIGN_FIELD.get(kind) or (
                f"decisions.components[type={kind}]" if kind else ""
            )
        return ""
    if token.startswith("curtain_mullion_"):
        return "decisions.facades"
    if token.startswith(("wall_core_", "shaft_wall_")):
        return "decisions.circulation"
    if token.startswith(_STRUCTURE_ID_PREFIXES):
        return "decisions.massing"
    return ""


def _validator_defects(
    blueprint: dict[str, Any],
    brief: dict[str, Any],
    deferable: frozenset[str] = frozenset(),
) -> list[CompileDefect]:
    """把既有校验器的输出统一成结构化缺陷。

    两个来源：

    - **交付流水线**（`:mod:`app.agent.compiler.pipeline_defects`）：§2.5 的"唯一口径"。
      原先这里手挑了两个校验器（尺寸／引用）直接调，而线上那条流水线跑的是十四个步骤
      ——同一口径两处实现，改了一处另一处不跟。现在整条流水线投影过来，
      代码名就是**交付步骤名**，报出的缺陷与 ``final_validate`` 逐字对得上。
    - **设计清单约束**（``validate_design_brief_constraints``）：它比对的是"图纸点名要什么"
      与"产物里有没有"，输入含 ``brief``，不属于蓝图自身合法性问题，所以在流水线之外。

    ``deferable`` = 编译器**没有派生规则**的类型（``unsupported`` ∪ ``uncompiled``）。
    这些类型的"配额没满足"会被降级为 ``warn``：它已经被 ``uncompiled``/``unsupported``
    如实报出，处置方式是**走模型通道补**（用户定的红线："脚本完不成的地方大模型自己完善"），
    再让同一条约束以 ``error`` 出现就是**同一件事在两个严重度上报两遍**，直接把
    "交给模型补"变成"阻断交付"。降级只覆盖这一种情形——尺寸越界、引用悬空等
    仍然一律 ``error``。

    ⚠️ 类型识别靠消息首 token（``"chimney 数量 0 少于设计下限 1"`` → ``chimney``），
    这是 ``validate_design_brief_constraints`` 现有文案的既定格式；若文案改前缀，
    此处会失效（表现为"降级不再发生"，只会更严不会更松）。
    """

    from app.agent.compiler.pipeline_defects import pipeline_defect_messages

    defects: list[CompileDefect] = [
        CompileDefect(
            code=name,
            severity="error",
            target="blueprint",
            evidence=message[:500],
            design_field=_design_field_of_issue(message, blueprint),
        )
        for name, message in pipeline_defect_messages(blueprint)
    ]

    for message in validate_design_brief_constraints(blueprint, brief) or []:
        text = str(message)[:500]
        named = text.split(maxsplit=1)[0] if text else ""
        defects.append(
            CompileDefect(
                code="design_constraint",
                severity="warn" if named in deferable else "error",
                target="blueprint",
                evidence=text,
                design_field=_DESIGN_FIELD.get(named)
                or (f"decisions.components[type={named}]" if named in COMPONENT_REGISTRY else ""),
            )
        )
    return defects


def _schema_defects(blueprint: dict[str, Any]) -> list[CompileDefect]:
    """整份蓝图的 schema 校验——skeleton 的四道预检之一，原先只有骨架阶段有。

    与交付流水线的 Step 1（``validate_blueprint_structure``）**不是**同一条规则，
    两条都要留：后者查顶层字段的存在性与取值，前者还查 ``meta`` 的类型、
    ``geometry.elements`` 的元素类型与 **id 唯一性**。合成一条会丢掉"ID 重复"——
    那类产物引擎侧渲染不了，且流水线的空间校验也不一定报得出来。

    ``allow_empty_geometry`` 走**默认 False**（交付口径）：建筑链的产物按设计就非空，
    空容器是物件骨架（走 ``skeleton`` 那条链）才有的形态。
    """

    from app.utils.blueprint_parser import validate_blueprint_schema

    return [
        CompileDefect(
            code="schema_invalid",
            severity="error",
            target="blueprint",
            evidence=str(issue)[:500],
            design_field=_design_field_of_issue(str(issue), blueprint),
        )
        for issue in validate_blueprint_schema(blueprint)
    ]


def _field_defaults(blueprint: dict[str, Any]) -> list[CompileDefault]:
    """**图纸没表态**的字段清单。

    判据不是"schema 允许但产物没有"——那一版会把 ``floor.radius``、``wall.curve``、
    ``stair.stepCount`` 这些**引擎内部字段**全算进来（实测 299 条，几乎全是噪声），
    它们根本不存在"图纸表不表态"的问题。

    唯一合法判据是注册表的 ``optional_fields``：只有注册表列出的类型才有
    "模型/设计可表态"的余地；墙/楼板/楼梯不在注册表里（由确定性骨架完全拥有），
    所以它们不产生任何 ``defaulted``。

    ⇒ 这是"借助模型力量"的唯一合法入口：只有这里列出的字段才有讨论余地。
    """

    geometry = blueprint.get("geometry") or {}
    entities = [*(geometry.get("elements") or []), *(geometry.get("components") or [])]
    defaults: list[CompileDefault] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        component_type = str(entity.get("type") or "")
        entry = COMPONENT_REGISTRY.get(component_type)
        if entry is None:
            continue
        target = str(entity.get("id") or component_type or "?")
        present = set(entity)
        for field_name in sorted(set(entry.optional_fields) - present):
            defaults.append(CompileDefault(target=target, field=field_name))
    return defaults


def _capability_gaps(
    brief: dict[str, Any],
    blueprint: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """按配额下限点名、但产物里没有的类型，分成"能力缺失"与"编译器暂无规则"。

    ⚠️ 实测（2026-09-28）：``unsupported`` **当前恒为空集**，因为注册表里 15 个类型
    全部已实现（``get_implemented_components()`` == ``COMPONENT_REGISTRY``）；
    而且 ``normalize_architecture_plan`` 会把配额里认不出的键**静默丢弃**
    （实测 ``{"garage": …}`` 归一化后消失），所以"引擎没这个概念"的东西根本到不了这里。
    这一分类保留是因为它有明确的未来触发点：某类型的引擎实现被摘掉、
    或归一化白名单先于引擎实现放开。**不要**为了让它非空而放宽归一化白名单。
    """

    geometry = blueprint.get("geometry") or {}
    produced = {
        str(entity.get("type"))
        for entity in [*(geometry.get("elements") or []), *(geometry.get("components") or [])]
        if isinstance(entity, dict)
    }
    implemented = {config.component_type for config in get_implemented_components()}
    quota = brief.get("component_quota") if isinstance(brief.get("component_quota"), dict) else {}
    unsupported: list[str] = []
    uncompiled: list[str] = []
    for component_type, limits in sorted((quota or {}).items()):
        minimum = int((limits or {}).get("min") or 0) if isinstance(limits, dict) else 0
        if minimum <= 0 or component_type in produced:
            continue
        # 能力缺失 → 只标记不阻断（红线）；缺规则 → 迁移指示，走模型通道。
        (uncompiled if component_type in implemented else unsupported).append(component_type)
    return unsupported, uncompiled


# ── 公开入口 ──


def compile_design(
    plan: dict[str, Any],
    *,
    mode: str = MODE_FINAL,
    user_message: str = "",
    material_plan: dict[str, Any] | None = None,
) -> CompileResult:
    """把设计图纸确定性编译成蓝图。

    :param plan: 归一化后的图纸协议。目标链上它由
        ``architecture_plan_from_document(converged_document)`` 给出——
        即图纸的唯一事实源是 ``DesignDocument``，本函数只消费、不产生。
    :param mode: ``final`` 出蓝图；``dry_run`` / ``probe`` 只回诊断。
        ``probe`` 供设计节点当 tool 试算：它连蓝图都不回，模型污染不了产物。
    :param user_message: 透传给骨架归一化（尺寸/层数的需求解析）。
    :param material_plan: 已批准的材质方案（``material_plan`` 节点产出）。
        不传则蓝图只用骨架的默认材质；传了就在这里落地——**必须在按材质取名的
        步骤之前**，详见 :func:`_compose` 内的说明。
    """

    if mode not in MODES:
        raise ValueError(f"未知编译模式 {mode!r}，闭集为 {MODES}")

    blueprint, brief, stats = _compose(plan, user_message, material_plan)
    # 先算能力缺口，再收缺陷：缺口类型决定哪些"配额没满足"可以交给模型补（见 _validator_defects）。
    unsupported, uncompiled = _capability_gaps(brief, blueprint)
    # 收缺陷的顺序即"从粗到细"：整图 schema → 逐构件必填/枚举 → 交付流水线 + 设计清单。
    # §2.5 的口径统一在这里：三处校验（skeleton 预检 / spatial_tools / final_validate）
    # 全部由 compile_design 一次产出，`final_validate` 退化为"再跑一次同样的校验 + 出交付清单"。
    defects = [
        *_schema_defects(blueprint),
        *_structure_defects(blueprint),
        *_validator_defects(blueprint, brief, frozenset(unsupported) | frozenset(uncompiled)),
    ]
    result = CompileResult(
        mode=mode,
        blueprint=blueprint if mode == MODE_FINAL else None,
        design_brief=brief if mode == MODE_FINAL else None,
        defects=defects,
        defaulted=_field_defaults(blueprint),
        unsupported=unsupported,
        uncompiled=uncompiled,
        stats=stats,
    )
    logger.info(f"[compile] {mode} → {result.summary()}")
    return result


__all__ = ["compile_design"]
