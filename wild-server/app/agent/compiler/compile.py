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
from copy import deepcopy
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
from app.agent.generation.components import COMPONENT_REGISTRY
from app.agent.generation.material_plan import (
    apply_resolved_material_plan,
    material_role_specs,
)
from app.agent.generation.slot_utils import component_slots
from app.agent.validation.design_constraints import (
    design_quota_shortfalls,
    validate_design_brief_constraints,
)
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
    "elevator": "decisions.circulation.vertical_strategy",
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

#: 电梯：住宅电梯的标准轿厢尺寸（设备规格,不随建筑缩放）
_ELEVATOR_WIDTH_DEFAULT = 1.4
_ELEVATOR_DEPTH_DEFAULT = 1.6
_ELEVATOR_HEIGHT_DEFAULT = 2.2
_ELEVATOR_CAB_CLEARANCE = 0.15  # 轿厢高度要比层高小这个值


# ── 屋顶派生：本模块唯一新增的派生逻辑 ──


def _roof_plan(plan: dict[str, Any]) -> dict[str, Any]:
    roof = plan.get("roof")
    return roof if isinstance(roof, dict) else {}


def _roof_overhang(plan: dict[str, Any]) -> float:
    """挑出距离，钳到 0.15~0.8。

    ``facade.py:205`` 有一份同样的钳制。两条路径**互斥**
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

    为什么要有"要么满足下限、要么一个都不产"这道门（数量缺口已不阻断，
    但这道门仍有存在理由）：``_capability_gaps`` 只看"该类型是否已经出现过"。
    若派生 1 个（下限 4），该类型就进了 ``produced`` → 不再进 ``uncompiled``
    → 模型通道不会被告知名它补齐。宁可一个不产、把缺口完整交给模型通道，
    也不要"半吊子派生把点名信号吃掉"。
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


def _derive_elevators(
    plan: dict[str, Any],
    blueprint: dict[str, Any],
    brief: dict[str, Any],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """电梯派生：从骨架核心筒确定性生成电梯组件。

    前置条件：骨架必须有 ``wall_core_*`` 井道围合（即 ``vertical_strategy`` 为 
    ``core_and_stair``）。无井道时返回空列表并标记为 ``uncompiled``，
    由模型通道补（或标记为能力缺失）。

    与檐口/烟囱/灯具同一道下限门：只有配额下限能被满足时才产出。
    """

    from app.tools.component_tools import _resolve_core_shaft

    minimum = _quota_min(brief, "elevator")
    if minimum <= 0 or any(item.get("type") == "elevator" for item in existing):
        return []

    # 从骨架反推井道几何
    shaft = _resolve_core_shaft(blueprint)
    if shaft is None:
        # 骨架没有核心筒 → 电梯无依托，标记为 uncompiled
        return []

    bays = shaft.get("bays") or []
    floor_height = shaft.get("floor_height")
    floor_count = shaft.get("floor_count")

    if not bays or not floor_height or not floor_count:
        return []

    # 按配额下限生成：每格井道放一台（但不超过下限要求的数量）
    candidates: list[dict[str, Any]] = []
    for idx, bay in enumerate(bays[:minimum], start=1):
        x0, x1, z0, z1 = bay
        center_x = round((x0 + x1) / 2, 3)
        center_z = round((z0 + z1) / 2, 3)

        # 轿厢尺寸：取默认值并夹到井格净空内
        available_width = max(0.6, (x1 - x0) - 0.1)
        available_depth = max(0.6, (z1 - z0) - 0.1)
        cab_width = min(_ELEVATOR_WIDTH_DEFAULT, available_width)
        cab_depth = min(_ELEVATOR_DEPTH_DEFAULT, available_depth)
        cab_height = floor_height - _ELEVATOR_CAB_CLEARANCE

        candidates.append({
            "type": "elevator",
            "id": f"elevator_{idx:02d}",
            "position": [center_x, 0.0, center_z],
            "dimensions": {
                "width": round(cab_width, 3),
                "depth": round(cab_depth, 3),
                "height": round(cab_height, 3),
            },
            "floorHeight": floor_height,
            "floorCount": floor_count,
            "initialFloor": 0,
        })

    # 应用下限门：配额要 N 台但只能放 M < N 台 → 一台都不产
    return candidates if len(candidates) >= minimum else []


# ── 接线：一次编译 ──


#: 显式实例的字段里凡是"材质"的，值都可能是**设计侧角色名**。值为字段名 → 该字段的
#: 默认角色（角色名认不出时的兜底，保证落下来的永远是蓝图认得的键）。
_INSTANCE_MATERIAL_FIELDS: dict[str, str] = {
    "material": "structure",
    "frameMaterial": "frame",
    "leafMaterial": "door",
    "glassMaterial": "glass",
    "railingMaterial": "frame",
}


def _material_name_for_role(
    role: Any,
    materials: dict[str, Any],
    default_role: str = "structure",
) -> str:
    """设计侧**材质角色名** → 蓝图**材质名**（``blueprint.materials`` 的键）。

    🔴 两个词表不是一回事：``ComponentInstance.material_role`` 用的是设计侧角色名
    （``frame`` / ``door`` / ``glass`` / ``roof`` / ``structure`` …），而构件字段
    （``frameMaterial`` / ``leafMaterial`` / ``material`` …）引用的是 ``blueprint.materials``
    的**键**（``metal`` / ``wood`` / ``glass`` / ``roof`` / ``concrete`` …）。直接把角色名
    写进去，``validate_reference_integrity`` 会报"未在 Blueprint.materials 中定义" ——
    而两个名字**看起来都对**，排查时最容易往材质方案那边找。

    映射表**不在这里重抄一份**：唯一来源是 `material_plan.ROLE_SPECS` 的 ``materialId``。
    该字段名不在 ``materials`` 里时（例如 ``floor`` → ``floor_finish`` 不在默认六件套中）
    继续退到 ``default_role``，最后才退到任意一个已定义的键。
    """

    from app.agent.generation.material_plan import ROLE_SPECS

    known = materials if isinstance(materials, dict) else {}
    if str(role or "") in known:
        return str(role)  # 已经是蓝图材质名，不要再查一遍
    for candidate in (str(role or ""), str(default_role or "")):
        name = str((ROLE_SPECS.get(candidate) or {}).get("materialId") or "")
        if name and name in known:
            return name
    return sorted(known)[0] if known else "default"


def _resolve_instance_materials(
    item: dict[str, Any],
    materials: dict[str, Any],
) -> dict[str, Any]:
    """把构件里的材质**角色名**统一换成蓝图**材质名**（就地把关，不逐建造器各查一次）。"""

    for field, default_role in _INSTANCE_MATERIAL_FIELDS.items():
        value = item.get(field)
        if isinstance(value, str) and value and value not in materials:
            item[field] = _material_name_for_role(value, materials, default_role)
    return item


def _opening_expression(
    inst: dict[str, Any], walls: dict[str, Any], plan: dict[str, Any] | None = None,
) -> tuple[str | None, int]:
    """解析实例 ``host`` → ``(墙 id, 同墙第几条)``。

    ``None`` 表示 host 解析不到任何墙 —— 宿主对齐类实例随即整条丢弃并记入
    ``stats["dropped"]``（宁缺毋错，对齐 ``_derive_attachments`` 的口径）。
    第二返回值是**同墙出现序**（1 起）：``host="wall_front_2"`` 命中该墙第 1 条
    派生结果，``host="wall_front_2:2"`` 命中第 2 条 —— 旧实现里两个实例会配对到
    同一条派生结果，第二条替换空转，该删的那条还删不掉。

    识别的格式（与 :class:`app.design.contracts.ComponentInstance` 的 host 语义一致）：

    - ``wall_<face>_<level>`` —— 骨架墙 id，直接命中；
    - ``slot_<face>_<bay>`` —— 槽位 id，``slot`` → ``wall`` 换前缀；
    - ``<id>_L<floor>_<face>`` —— 按真实体量边界和楼层标高解析，必须唯一命中。
      跨越多个体量的合并墙不猜测归属，留给缺陷报告处理。
    """

    host = str(inst.get("host") or "").strip()
    if not host:
        return None, 1
    occurrence = 1
    if ":" in host:
        host, _, tail = host.rpartition(":")
        if tail.isdigit():
            occurrence = max(1, int(tail))
    if host in walls:
        return host, occurrence
    if host.startswith("slot_"):
        wall_id = f"wall_{host[len('slot_'):]}"
        if wall_id in walls:
            return wall_id, occurrence
    if "_L" in host and plan:
        volume_id, _, suffix = host.rpartition("_L")
        level, _, face = suffix.partition("_")
        volume = next((v for v in plan.get("volumes", []) if v.get("id") == volume_id), None)
        if not volume or not level.isdigit() or face not in {"front", "back", "left", "right"}:
            return None, occurrence
        floor = int(level)
        if not int(volume["start_floor"]) <= floor <= int(volume["end_floor"]):
            return None, occurrence
        height = float(plan["massing"]["floor_height"])
        base_y = (floor - 1) * height
        axis, along = (2, 0) if face in {"front", "back"} else (0, 2)
        x, z = float(volume["x"]), float(volume["z"])
        width, depth = float(volume["width"]), float(volume["depth"])
        boundary = {"front": z, "back": z + depth, "left": x, "right": x + width}[face]
        low, high = (x, x + width) if along == 0 else (z, z + depth)
        tolerance = 0.01
        matches = []
        for wall_id, wall in walls.items():
            frm, to = wall.get("from"), wall.get("to")
            if not isinstance(frm, list) or not isinstance(to, list) or len(frm) != 3 or len(to) != 3:
                continue
            if (
                abs(min(frm[1], to[1]) - base_y) <= tolerance
                and abs(max(frm[1], to[1]) - (base_y + height)) <= tolerance
                and abs(frm[axis] - boundary) <= tolerance
                and abs(to[axis] - boundary) <= tolerance
                and min(frm[along], to[along]) >= low - tolerance
                and max(frm[along], to[along]) <= high + tolerance
            ):
                matches.append(wall_id)
        if len(matches) == 1:
            return matches[0], occurrence
    return None, 1


def _template_for(
    geometry: dict[str, Any],
    component_type: str,
    wall_id: str | None = None,
    occurrence: int = 1,
) -> dict[str, Any] | None:
    """同类型的**派生**构件（用作显式实例的落位模板）。

    ``wall_id`` 给出时按 ``parentWall`` 对齐 —— host 就是它要覆盖的那片墙，
    派生结果里"同类型 + 同墙"的那一条正是**批准槽位上的那个构件**；``wall_id``
    为 ``None``（或该类型没有 ``parentWall`` 字段，如灯具）时取第 ``occurrence``
    条派生结果。

    沿用派生几何是必须的：实例自算的位置（墙面中点）与槽位不是同一个点，
    ``validate_design_brief_constraints`` 会报"未落实批准槽位"。
    """

    seen = 0
    for item in geometry.get("components") or []:
        if not isinstance(item, dict) or item.get("type") != component_type:
            continue
        if wall_id and item.get("parentWall") != wall_id:
            continue
        seen += 1
        if seen >= occurrence:
            return item
    return None


def _positive_float(value: Any, fallback: float) -> float:
    """能转成正数就用它，否则退回 ``fallback``（图纸字段是不可信输入）。"""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


#: **形态表态白名单**（§3.4：实例只表态形态与材质，几何全部由派生链拥有）。
#: 键是实例 ``form`` 里认得的字段；白名单**外**的 form 键一律丢弃并记入
#: ``stats["form_ignored"]``。
#:
#: 为什么是白名单不是透传：引擎对每个构件类型有**字段闭集**，透传任意键会让
#: 整份蓝图 ``schema_invalid``。旧实现里 ``canopy.slope`` / ``chimney.capType`` /
#: ``cornice.width`` 都不在闭集内（实测 ``wild-core`` 构件参数与
#: ``validate_blueprint_schema.component_allowed``），正是字段映射各写一份的恶果。
#:
#: ``mode`` / ``hingeSide`` / ``openAngle`` 属于 ``interaction``（走
#: :func:`_apply_instance_form` 的改道路由）；``ridge_axis`` / ``ridgeHeight``
#: 是图纸词汇，引擎字段是 ``ridgeAxis`` / ``height``（roof 是元素，只有 height）。
_INSTANCE_FORM_FIELDS: dict[str, frozenset[str]] = {
    "door": frozenset({
        "mode", "hingeSide", "openAngle", "frameWidth", "frameDepth",
        "leafDepth", "leafMaterial", "leafRows",
    }),
    "window": frozenset({
        "verticalMullions", "horizontalMullions",
        "frameWidth", "frameDepth", "glassDepth", "glassMaterial",
    }),
    "balcony": frozenset({"slabThickness", "railingHeight", "postSpacing", "railingMaterial"}),
    "railing": frozenset({
        "postSpacing", "postRadius", "railRadius", "railLevels",
        "infillType", "infillMaterial",
    }),
    "roof": frozenset({"roofType", "ridge_axis", "overhang", "ridgeHeight"}),
    "canopy": frozenset({"depth", "thickness", "supportCount", "supportSize"}),
    "light": frozenset({"fixtureType", "initiallyOn"}),
    "cornice": frozenset({"profile"}),
    "chimney": frozenset({"width", "depth", "height"}),
}

#: 白名单键 → 落点的改道/改名规则。其余键**同名**落构件字段。
#: - ``mode``：interaction 唯一规则函数（facade），只覆写 mode 不重建 interaction；
#: - ``hingeSide`` / ``openAngle``：属于 ``interaction``，写顶层会被字段闭集拒掉；
#: - ``ridge_axis`` → ``ridgeAxis``、``ridgeHeight`` → ``height``：图纸词 ≠ 引擎词。
_INSTANCE_FORM_ROUTES: dict[str, tuple[str, str]] = {
    "mode": ("interaction_fn", ""),
    "hingeSide": ("interaction", "hingeSide"),
    "openAngle": ("interaction", "openAngle"),
    "ridge_axis": ("field", "ridgeAxis"),
    "ridgeHeight": ("field", "height"),
}


def _apply_instance_form(
    component: dict[str, Any],
    inst: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """把实例的形态表态落进**派生模板的拷贝**（白名单过滤 + 改道路由）。

    返回 ``(落地的键, 丢弃的键)`` 给 stats。丢弃比透传安全（整份蓝图非法），
    也比中断符合编译器既有口径（``split_opening``：认不出就降级，不抛异常）。
    """

    component_type = str(component.get("type") or "")
    allowed = _INSTANCE_FORM_FIELDS.get(component_type, frozenset())
    form = inst.get("form") if isinstance(inst.get("form"), dict) else {}
    applied: list[str] = []
    ignored: list[str] = []
    for key, value in form.items():
        if key not in allowed:
            ignored.append(key)
            continue
        route, target = _INSTANCE_FORM_ROUTES.get(key, ("field", key))
        if route == "interaction_fn":
            continue  # 统一在循环后走 _apply_opening_form，避免逐键重建 interaction
        if route == "interaction":
            interaction = component.get("interaction")
            interaction = dict(interaction) if isinstance(interaction, dict) else {}
            interaction[target] = value
            component["interaction"] = interaction
        else:
            component[target] = value
        applied.append(key)
    if "mode" in form and "mode" in allowed:
        from app.agent.generation.architecture.facade import _apply_opening_form

        _apply_opening_form(component, str(form["mode"]), str(component.get("id") or "instance"))
        if "mode" not in applied:
            applied.append("mode")
    return applied, ignored


def _host_lookup(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """宿主查找表：开口/构件在 ``components``，屋顶在 ``elements`` —— 两张表都要看。

    屋顶是**元素**（`conform_roofs_to_slots` 把它放进 `geometry.elements`），
    而雨篷的宿主按定义是门窗、檐口/烟囱的宿主按定义是屋顶。只看 `components`
    会让后者永远解析不到宿主、静默返回 ``None``：表现为"实例清单里写了却没产出"，
    且没有任何报错——比报错更难发现。
    """

    return [
        *(geometry.get("components") or []),
        *(geometry.get("elements") or []),
    ]


def _opening_defaults(
    component_type: str,
    inst: dict[str, Any],
    wall: dict[str, Any],
) -> dict[str, Any]:
    """门窗实例**追加**时的最小几何：墙面中线 + 类型默认尺寸。

    只在宿主墙存在、但该墙没有任何同类型派生结果时调用 —— 此时实例没有可顶替的
    批准槽位，``size`` 是合法的尺寸来源（没有槽位约束会被它破坏）。沿墙长度从
    **骨架墙**算出，实例不写世界坐标。
    """

    frm = wall.get("from") if isinstance(wall.get("from"), list) else [0.0, 0.0, 0.0]
    to = wall.get("to") if isinstance(wall.get("to"), list) else [0.0, 0.0, 0.0]
    try:
        length = math.hypot(float(to[0]) - float(frm[0]), float(to[2]) - float(frm[2]))
    except (TypeError, ValueError, IndexError):
        length = 0.0
    size = inst.get("size") if isinstance(inst.get("size"), dict) else {}
    along = round(max(0.3, length / 2), 3)
    if component_type == "door":
        bottom, width, height = 0.0, 1.2, 2.1
        extra: dict[str, Any] = {
            "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 90},
        }
    elif component_type == "window":
        bottom, width, height = 0.9, 1.0, 1.2
        extra = {"verticalMullions": 1, "horizontalMullions": 0}
    else:  # balcony
        bottom, width, height = 3.2, 2.4, 0.0
        extra = {"slabThickness": 0.15, "railingHeight": 1.05, "postSpacing": 1.5}
    component = {
        "type": component_type,
        "id": f"{component_type}_instance_{inst.get('_seq', 1):02d}",
        "parentWall": str(wall.get("id") or ""),
        "from": [along, bottom, 0.0],
        "width": _positive_float(size.get("width"), width),
        "height": _positive_float(size.get("height"), height),
        "frameMaterial": str(inst.get("material_role") or "frame"),
        **extra,
    }
    if component_type == "balcony":
        component["depth"] = _positive_float(size.get("depth"), 1.2)
        component["railingMaterial"] = "frame"
        component.pop("height", None)
    return component


def _compile_from_instances(
    instances: list[dict[str, Any]],
    blueprint: dict[str, Any],
    materials: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """从实例清单编译构件（§3.4 覆盖层）。

    🔴 **唯一规则：实例 = 派生模板 + 形态/材质表态。** 几何一律沿用派生结果
    （位置/主尺寸/宿主引用），实例不再自己算几何 —— 旧实现里 8 个 per-type
    builder 各写一套"宿主解析 + 位置计算 + 字段映射"，与派生链是 8 份重复实现，
    且产出字段屡屡越出引擎闭集（canopy.slope / chimney.capType / light 的五个
    幽灵字段都是这么进来的）。实例的 ``size`` 在**有模板**时被忽略（有槽位时
    几何以槽位为准），只在**追加**（该墙没有同类型派生结果）时作为尺寸来源。

    派生链**先跑完**（``_compose`` 里的 ``conform_*`` / ``_derive_*``），
    本函数只做四件事：

    1. **配对**：``host`` → 派生模板（:func:`_opening_expression` +
       :func:`_template_for`）；灯具没有 ``parentWall``，按出现序对齐；
    2. **追加**：宿主墙解析得到、但该墙没有同类型派生结果的门窗/阳台，按
       :func:`_opening_defaults` 追加（§3.4"找不到就追加"）；宿主都解析不到的
       实例整条丢弃并记入 ``stats["dropped"]``；
    3. **表态**：白名单内的 form 字段覆写模板拷贝（:func:`_apply_instance_form`），
       材质角色名由 :func:`_resolve_instance_materials` 统一换蓝图材质名；
    4. **顶替**：配对成功的模板记进 ``replaced``（identity 定位），由
       :func:`_apply_instance_overrides` 从派生结果里摘掉 —— 覆盖层不是替换层。

    返回 ``(构件列表, 被顶替的派生结果, 统计)``。
    """

    components: list[dict[str, Any]] = []
    replaced: list[dict[str, Any]] = []
    form_applied: dict[str, list[str]] = {}
    form_ignored: dict[str, list[str]] = {}
    dropped: list[str] = []

    geometry = blueprint.get("geometry", {})
    walls = {
        str(item.get("id")): item
        for item in geometry.get("elements", [])
        if item.get("type") == "wall"
    }

    by_type: dict[str, list[dict[str, Any]]] = {}
    for inst in instances:
        if isinstance(inst, dict) and str(inst.get("type", "")):
            by_type.setdefault(str(inst["type"]), []).append(inst)

    for component_type, type_instances in sorted(by_type.items()):
        for occurrence, inst in enumerate(type_instances, start=1):
            inst = dict(inst)
            inst["_seq"] = occurrence
            wall_id, nth = _opening_expression(inst, walls, plan)
            component: dict[str, Any] | None = None

            if component_type in {"door", "window", "balcony"}:
                template = (
                    _template_for(geometry, component_type, wall_id, nth)
                    if wall_id
                    else None
                )
                if isinstance(template, dict):
                    component = deepcopy(template)
                    replaced.append(template)
                elif wall_id and isinstance(walls.get(wall_id), dict):
                    component = _opening_defaults(component_type, inst, walls[wall_id])
            elif component_type == "light":
                # 灯具没有 parentWall：按出现序对齐派生结果。host 解析不出墙
                # 也照样配对（灯具是追加型，位置反正沿用派生）。
                template = _template_for(geometry, "light", None, nth)
                if isinstance(template, dict):
                    component = deepcopy(template)
                    replaced.append(template)
            elif component_type == "roof":
                template = next(
                    (
                        item
                        for item in (geometry.get("elements") or [])
                        if isinstance(item, dict) and item.get("type") == "roof"
                    ),
                    None,
                )
                if isinstance(template, dict):
                    component = deepcopy(template)
                    replaced.append(template)
                elif occurrence == 1:
                    # 骨架没出屋顶（quota.min == 0 的无屋盖场景）却写了屋顶实例：
                    # 与 `_single_roof` 同口径的兜底——位置/跨度只有 massing 知道，
                    # 实例自算必然与 massing 分叉，这里只给引擎三要素的最小占位。
                    component = {
                        "type": "roof",
                        "id": "roof_instance_01",
                        "roofType": _FLAT_ROOF,
                        "span": 10.0,
                        "depth": 10.0,
                        "height": 0.0,
                        "thickness": _DEFAULT_ROOF_THICKNESS,
                        "material": _roof_material(materials),
                        "position": [5.0, 0.0, 5.0],
                    }
            elif component_type == "railing":
                template = _template_for(geometry, "railing", None, occurrence)
                if isinstance(template, dict):
                    component = deepcopy(template)
                    replaced.append(template)
            elif component_type == "canopy":
                # 追加型：宿主是门窗。优先顶替同门的**派生**雨棚；没有派生雨棚时
                # 以宿主门窗为基准现算一条（位置=门顶、宽度=门宽微加宽）——
                # 实例的 size.depth / size.thickness / form 才是可表态的部分。
                template = next(
                    (
                        item
                        for item in _host_lookup(geometry)
                        if item.get("type") == "canopy"
                        and item.get("parentOpening") == str(inst.get("host") or "")
                    ),
                    None,
                )
                host_opening = next(
                    (
                        item
                        for item in _host_lookup(geometry)
                        if item.get("id") == str(inst.get("host") or "")
                        and item.get("type") in {"door", "window"}
                    ),
                    None,
                )
                if isinstance(template, dict):
                    component = deepcopy(template)
                    replaced.append(template)
                elif isinstance(host_opening, dict):
                    opening_from = (
                        host_opening.get("from")
                        if isinstance(host_opening.get("from"), list)
                        else [0.0, 0.0, 0.0]
                    )
                    size = inst.get("size") if isinstance(inst.get("size"), dict) else {}
                    component = {
                        "type": "canopy",
                        "id": f"canopy_{occurrence:02d}",
                        "parentWall": host_opening.get("parentWall"),
                        "from": [
                            float(opening_from[0]),
                            float(opening_from[1]) + _positive_float(host_opening.get("height"), 2.0),
                            float(opening_from[2]),
                        ],
                        "width": _positive_float(host_opening.get("width"), 1.0) + 0.3,
                        "depth": _positive_float(size.get("depth"), 1.2),
                        "thickness": _positive_float(size.get("thickness"), 0.15),
                        "material": "roof",
                    }
            elif component_type in {"cornice", "chimney"}:
                # 追加型：宿主是屋顶。模板取同屋顶同类型的那条派生结果，几何全沿用。
                template = next(
                    (
                        item
                        for item in _host_lookup(geometry)
                        if item.get("type") == component_type
                        and item.get("parentRoof") == str(inst.get("host") or "")
                    ),
                    None,
                ) or _template_for(geometry, component_type, None, occurrence)
                if isinstance(template, dict):
                    component = deepcopy(template)
                    replaced.append(template)

            if component is None:
                dropped.append(f"{component_type}:{inst.get('host', '?')}")
                continue

            # 显式实例统一改名：与派生产物的 id 词表（*_planned_* / *_synthesized_*）
            # 区分开，审计时一眼认出哪条来自实例清单。
            component["id"] = (
                f"{component_type}_{occurrence:02d}"
                if component_type != "roof"
                else f"roof_{occurrence:02d}"
            )

            applied, ignored = _apply_instance_form(component, inst)
            if inst.get("material_role"):
                if component_type in {"door", "window"}:
                    component["frameMaterial"] = str(inst["material_role"])
                else:
                    component["material"] = str(inst["material_role"])
            components.append(component)

            if applied:
                form_applied[component_type] = sorted(
                    set(form_applied.get(component_type, [])) | set(applied)
                )
            if ignored:
                form_ignored[component_type] = sorted(
                    set(form_ignored.get(component_type, [])) | set(ignored)
                )

    # 材质角色名 → 蓝图材质名（唯一换名点；写角色名进蓝图会被引用完整性校验拒掉）。
    components = [
        _resolve_instance_materials(item, materials)
        for item in components
        if isinstance(item, dict)
    ]
    return components, replaced, {
        "form_applied": form_applied,
        "form_ignored": form_ignored,
        "dropped": dropped,
    }


def _apply_instance_overrides(
    explicit: list[dict[str, Any]],
    replaced: list[dict[str, Any]],
    declared_types: set[str],
    derived_components: list[dict[str, Any]],
    derived_elements: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """把显式实例**叠加**到派生结果上（§3.4「轴网为主、显式为例外」）。

    🔴 这是**叠加**，不是替换层。某一实例顶替成功，就**只**换掉它顶替的那一条
    （``replaced``，按对象 identity 定位），其余派生结果**照留**。

    最初的写法是"按类型整批换掉"。实测代价：一张只写了**一盏灯**的清单会把四个
    立面的灯全删了，``validate_design_brief_constraints`` 接着报"light 数量 1 少于
    设计下限 2" —— 报的是**配额**，而错在实例清单的覆盖粒度，查起来会往派生链那边找。

    一条都配对不上的类型**保留派生结果**，记进 ``kept_derived`` ——
    一条错实例不该把该类型的默认产物全带走。

    屋顶落在 ``geometry.elements`` 而不是 ``components``，所以按类型分池子。
    """

    replaced_ids = {id(item) for item in replaced}
    components = [item for item in derived_components if id(item) not in replaced_ids]
    elements = [item for item in derived_elements if id(item) not in replaced_ids]
    explicit_kinds: dict[str, int] = {}
    replaced_kinds: dict[str, int] = {}
    for item in explicit:
        if not isinstance(item, dict):
            continue
        component_type = str(item.get("type") or "")
        if not component_type:
            continue
        (elements if component_type == "roof" else components).append(item)
        explicit_kinds[component_type] = explicit_kinds.get(component_type, 0) + 1
    for item in replaced:
        if isinstance(item, dict) and item.get("type"):
            kind = str(item["type"])
            replaced_kinds[kind] = replaced_kinds.get(kind, 0) + 1

    return components, elements, {
        "explicit": explicit_kinds,
        "replaced": replaced_kinds,
        "kept_derived": sorted(declared_types - set(explicit_kinds)),
    }


def _compose(
    plan: dict[str, Any],
    user_message: str,
    material_plan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """把既有确定性部件串成一次编译，返回 ``(blueprint, design_brief, stats)``。

    **只归一化一次**：``build_deterministic_skeleton`` 内部也会归一化，但屋顶派生
    与立面解析都要读归一化后的 ``massing`` —— 各归一化一次会让两条路径读到不同的值，
    这正是本仓库记录过的"同一参数被两处夹取就分叉"。所以这里先归一化，全流程共用。

    **实例清单是覆盖层，不是替换层**（§3.4）：派生链先跑完，再让显式实例按类型覆盖
    它点名的那几类（见 ``_apply_instance_overrides``）。
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
    
    # §3.4: 检查是否有实例清单
    component_instances = normalized.get("components") or []
    use_instance_list = isinstance(component_instances, list) and len(component_instances) > 0
    
    components: list[dict[str, Any]] = []  # ← 模型产出置空：编译器不依赖任何模型输出

    # 派生是**默认**，无论有没有实例清单都先跑一遍：`conform_openings_to_slots` 把立面
    # pattern 变成门窗、`conform_*_to_slots` 把槽位变成阳台/栏杆 —— 那是图纸的**主**。
    # 显式实例只在**后面**覆盖它，而不是取代它（§3.4「轴网为主、显式为例外」）。
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

    # 电梯要读**骨架核心筒**（wall_core_*），所以必须排在骨架之后。
    elevators = _derive_elevators(normalized, blueprint, brief, components)
    components = [*components, *elevators]

    # §3.4：显式实例**覆盖**同类型的派生结果。必须排在所有派生之后 ——
    # 排在前面会被随后的派生原样盖掉（那正是"清单看着生效了、其实没生效"）。
    instance_stats: dict[str, Any] = {}
    if use_instance_list:
        explicit, replaced, instance_stats = _compile_from_instances(
            component_instances,
            # 宿主查找要看到**当前**已落地的构件与元素：屋顶在 `elements` 里，
            # 雨篷/檐口/烟囱的宿主按定义就是门窗或屋顶，晚一步就一个都解析不到。
            {**blueprint, "geometry": {**geometry, "components": components, "elements": elements}},
            materials,
            plan=normalized,
        )
        components, elements, overrides = _apply_instance_overrides(
            explicit,
            replaced,
            {
                str(inst.get("type") or "")
                for inst in component_instances
                if isinstance(inst, dict)
            },
            components,
            elements,
        )
        instance_stats = {**instance_stats, **overrides}

    # 配额上限剔除已删除（用户决策 2026-09-29）：max 只是参考值，产物数量
    # 不再被剃；下限仍由 _validator_defects 的 deferable 降级把关。

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
        # 直接数**实际落地**的构件：先前的写法在实例模式下数的是电梯数（统计口径写反了），
        # 在配额模式下又重算一遍 `_derive_lights`，两者都不等于 `components` 里的真实条数。
        "light": sum(1 for item in components if item.get("type") == "light"),
        "elevator": len(elevators),
        "from_instances": use_instance_list,
        "instance_overrides": instance_stats,
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
) -> list[CompileDefect]:
    """把既有校验器的输出统一成结构化缺陷。

    两个来源：

    - **交付流水线**（`:mod:`app.agent.compiler.pipeline_defects`）：§2.5 的"唯一口径"。
      原先这里手挑了两个校验器（尺寸／引用）直接调，而线上那条流水线跑的是十四个步骤
      ——同一口径两处实现，改了一处另一处不跟。现在整条流水线投影过来，
      代码名就是**交付步骤名**，报出的缺陷与 ``final_validate`` 逐字对得上。
    - **设计清单约束**（``validate_design_brief_constraints``）：空间/结构状态错误
      （标高缺失、超墙容量、批准槽位未落实），``error``。
    - **配额数量缺口**（``design_quota_shortfalls``）：数量不足是"模型补量"问题，
      不是"蓝图非法"问题（用户决策 2026-09-29，废除数量硬闸）→ 恒 ``warn``。
      缺口同时体现在 ``uncompiled``（配额点名但零产出）与修复环条目上，
      模型通道负责补；以 error 面世只会把"交给模型补"变成"阻断交付"。
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
        defects.append(
            CompileDefect(
                code="design_constraint",
                severity="error",
                target="blueprint",
                evidence=str(message)[:500],
                design_field=_design_field_of_issue(str(message), blueprint),
            )
        )
    for message in design_quota_shortfalls(blueprint, brief) or []:
        text = str(message)[:500]
        named = text.split(maxsplit=1)[0] if text else ""
        defects.append(
            CompileDefect(
                code="design_constraint",
                severity="warn",
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

    ⚠️ 开放集通道（用户决策 2026-09-29）：配额点名的任何类型都放行进入归一化与
    plan 条目（构件白名单闸已删），编译器没产出的类型一律进 ``uncompiled`` 交模型
    通道尝试；``unsupported`` 保留为协议字段，从此恒空。
    """

    geometry = blueprint.get("geometry") or {}
    produced = {
        str(entity.get("type"))
        for entity in [*(geometry.get("elements") or []), *(geometry.get("components") or [])]
        if isinstance(entity, dict)
    }
    quota = brief.get("component_quota") if isinstance(brief.get("component_quota"), dict) else {}
    unsupported: list[str] = []
    uncompiled: list[str] = []
    for component_type, limits in sorted((quota or {}).items()):
        minimum = int((limits or {}).get("min") or 0) if isinstance(limits, dict) else 0
        if minimum <= 0 or component_type in produced:
            continue
        # 开放集通道（用户决策 2026-09-29：删除构件白名单）：配额点名而编译器没产出的
        # 类型一律交模型通道尝试（字段契约靠知识库检索），校验与修复环兜底。
        # ``unsupported`` 保留为协议字段，从此恒空（红线：能力缺失只标记不阻断）。
        uncompiled.append(component_type)
    return unsupported, uncompiled


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
    unsupported, uncompiled = _capability_gaps(brief, blueprint)
    # 收缺陷的顺序即"从粗到细"：整图 schema → 逐构件必填/枚举 → 交付流水线 + 设计清单。
    # §2.5 的口径统一在这里：三处校验（skeleton 预检 / spatial_tools / final_validate）
    # 全部由 compile_design 一次产出，`final_validate` 退化为"再跑一次同样的校验 + 出交付清单"。
    defects = [
        *_schema_defects(blueprint),
        *_structure_defects(blueprint),
        # 数量缺口在 _validator_defects 内部恒为 warn（不依赖这里的缺口分类）。
        *_validator_defects(blueprint, brief),
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
