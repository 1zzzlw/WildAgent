"""编译器的行为契约测试。

这一层钉的是 ``compile_design`` 的**对外语义**，不是内部实现细节：
三模式、幂等、屋顶两个分支、"没表态"与"错了"的边界、以及"缺规则不阻断"这条红线。

每个断言都对应一条已知会被人踩的坑（写在 docstring 里），改实现时先看断言为什么存在。
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.agent.compiler import (
    MODE_DRY_RUN,
    MODE_FINAL,
    MODE_PROBE,
    compile_design,
)
from app.agent.compiler.compile import (
    _design_field_of_issue,
    _structure_defects,
    _validator_defects,
)
from app.agent.generation.architecture import normalize_architecture_plan
from app.agent.generation.components import COMPONENT_REGISTRY
from app.agent.generation.material_plan import (
    ROLE_SPECS,
    apply_resolved_material_plan,
    material_role_specs,
)
from app.tools.spatial_tools import validate_reference_integrity
from app.utils.blueprint_parser import validate_blueprint_schema

_MESSAGE = "生成一个三层别墅"

#: 单体积矩形：走 ``_single_roof``（无 ``roof_slots``）。
_RECT: dict = {
    "massing": {
        "shape": "rect",
        "width": 12,
        "depth": 9,
        "floors": 3,
        "modeled_floors": 3,
        "floor_height": 3.2,
    },
    "facades": {
        "front": {
            "bays": 4,
            "entrance_bay": 2,
            "ground_pattern": ["window", "door", "window", "empty"],
            "upper_pattern": ["window", "window", "window", "empty"],
        },
        "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
        "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
        "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
    },
    "roof": {"type": "gable", "ridge_axis": "x", "overhang": 0.6},
    "circulation": {"vertical_strategy": "stair"},
    "complexity": {
        "level": "standard",
        "min_volumes": 1,
        "grid_bays": [3, 2],
        "min_detail_packages": 2,
        "target_structural_elements": 30,
    },
}

#: 顶层两块体量 + 逐块可平铺的屋顶形态：走 ``conform_roofs_to_slots`` 拆分分支。
_SPLIT: dict = {
    **_RECT,
    "massing": {**_RECT["massing"], "shape": "l_shape", "width": 18, "depth": 14},
    "volumes": [
        {
            "id": "v1",
            "role": "primary",
            "x": 0,
            "z": 0,
            "width": 18,
            "depth": 8,
            "start_floor": 1,
            "end_floor": 3,
        },
        {
            "id": "v2",
            "role": "secondary",
            "x": 0,
            "z": 8,
            "width": 8,
            "depth": 6,
            "start_floor": 1,
            "end_floor": 3,
        },
    ],
    "complexity": {**_RECT["complexity"], "min_volumes": 2},
}

_FLAT: dict = {**_RECT, "roof": {"type": "flat", "overhang": 0.3}}


def _geometry(result) -> tuple[list[dict], list[dict]]:
    blueprint = result.blueprint or {}
    geometry = blueprint.get("geometry") or {}
    return list(geometry.get("elements") or []), list(geometry.get("components") or [])


def _of_type(entities: list[dict], kind: str) -> list[dict]:
    return [item for item in entities if isinstance(item, dict) and item.get("type") == kind]


# ── 一、模式语义 ──


@pytest.mark.parametrize(
    ("mode", "wants_blueprint"),
    [(MODE_FINAL, True), (MODE_DRY_RUN, False), (MODE_PROBE, False)],
)
def test_mode_decides_whether_blueprint_comes_back(mode: str, wants_blueprint: bool) -> None:
    """``probe`` 连蓝图都不回——设计节点当 tool 试算时，模型无从污染产物。

    只诊断不出图这一条如果破了，"脚本试算"就退化成"模型拿到半成品再改"。
    """

    result = compile_design(_RECT, mode=mode, user_message=_MESSAGE)
    assert (result.blueprint is not None) is wants_blueprint
    assert result.mode == mode
    # 诊断在三档下都要产出：dry_run / probe 的价值全在这里。
    assert isinstance(result.defects, list)


def test_unknown_mode_is_rejected() -> None:
    """模式是闭集，不许有第四条隐式通路。"""

    with pytest.raises(ValueError):
        compile_design(_RECT, mode="sketch", user_message=_MESSAGE)


# ── 二、纯函数性 ──


def test_compile_is_deterministic_and_does_not_touch_input() -> None:
    """同样输入 → 逐字节相同的产物；输入不被修改（编译器不产生设计）。

    "同一参数被两处夹取就分叉"是仓库里记录过的老毛病，所以这里同时钉幂等与只读。
    """

    plan = deepcopy(_SPLIT)
    frozen = deepcopy(plan)

    first = compile_design(plan, user_message=_MESSAGE)
    second = compile_design(plan, user_message=_MESSAGE)

    assert plan == frozen, "编译过程修改了输入图纸"
    assert first.blueprint == second.blueprint
    assert [item.to_dict() for item in first.defaulted] == [
        item.to_dict() for item in second.defaulted
    ]


# ── 三、屋顶：本模块唯一新增的派生逻辑 ──


def test_single_volume_roof_is_synthesized_from_massing() -> None:
    """单一体量没有 ``roof_slots``（历史留给模型自由造型）→ 编译器必须自己补。

    这里断了的话，"零模型编译"就永远缺一块屋顶——探针里唯一实测到的缺口。
    """

    result = compile_design(_RECT, user_message=_MESSAGE)
    elements, _ = _geometry(result)
    roofs = _of_type(elements, "roof")
    assert len(roofs) == 1
    assert result.stats["roof"]["synthesized"] == 1
    assert result.stats["roof"]["split"] == 0

    massing = normalize_architecture_plan(_RECT, _MESSAGE)["massing"]
    roof = roofs[0]
    # 承托墙顶 = 建模层数 × 层高。悬空在这里出现就等于屋顶浮在半空。
    assert roof["position"][1] == pytest.approx(
        massing["modeled_floors"] * massing["floor_height"], abs=1e-6
    )
    # 覆盖整个体量并两侧挑出。
    assert roof["span"] > massing["width"]
    assert roof["depth"] > massing["depth"]
    assert roof["roofType"] == "gable"
    assert roof["height"] > 0, "坡屋顶必须有脊高"


def test_multi_volume_roof_is_split_per_volume() -> None:
    """顶层 ≥2 块体量且形态可平铺 → 逐块出屋顶，脊高按**各自**跨度算。

    脊高写死一个值会在多体量下失真（小块屋顶顶着一个大屋脊），
    所以两块屋顶的高度必须不同——这是"按每块自身跨度算"的可观测判据。
    """

    result = compile_design(_SPLIT, user_message=_MESSAGE)
    elements, _ = _geometry(result)
    roofs = _of_type(elements, "roof")
    assert len(roofs) >= 2
    assert result.stats["roof"]["split"] >= 1
    assert result.stats["roof"]["synthesized"] == 0
    assert len({roof["height"] for roof in roofs}) > 1, "多块屋顶共用一个脊高，说明没按各跨算"


def test_flat_roof_has_no_ridge_height() -> None:
    """平坦屋顶的脊高必须是 0，不能套用坡屋顶比例。"""

    result = compile_design(_FLAT, user_message=_MESSAGE)
    elements, _ = _geometry(result)
    roofs = _of_type(elements, "roof")
    assert roofs
    assert all(roof["roofType"] == "flat" for roof in roofs)
    assert all(roof["height"] == 0.0 for roof in roofs)


def test_roof_is_not_reported_as_defaulted() -> None:
    """屋顶的形态/挑出/材质全部落地 → 不该出现在"图纸没表态"清单里。

    如果屋顶进了 ``defaulted``，说明派生丢字段了，收敛环会去问模型要一个本来能算出来的值。
    """

    result = compile_design(_RECT, user_message=_MESSAGE)
    elements, _ = _geometry(result)
    roof_ids = {roof["id"] for roof in _of_type(elements, "roof")}
    assert not [item for item in result.defaulted if item.target in roof_ids]


# ── 四、门窗：无模型产出也必须齐 ──


def test_openings_are_synthesized_without_any_model_output() -> None:
    """``components=[]`` 起手，门窗由槽位合成——编译不依赖任何模型输出。

    数量以图纸配额为准（quota 是"图纸说了要几个"的唯一事实源）。
    """

    result = compile_design(_RECT, user_message=_MESSAGE)
    _, components = _geometry(result)
    assert result.stats["opening"]["synthesized"] > 0
    assert {item["type"] for item in components} <= {"door", "window"}

    plan = normalize_architecture_plan(_RECT, _MESSAGE)
    for kind in ("door", "window"):
        minimum = int((plan["component_quota"].get(kind) or {}).get("min") or 0)
        assert minimum > 0
        assert len(_of_type(components, kind)) == minimum


def test_door_carries_registry_required_interaction() -> None:
    """``interaction`` 只写在注册表必填里（不在 schema 的 ``required``）。

    必填取并集才挡得住"门能开合"这件事被静默丢掉——只认 schema 的话这条永远绿。
    """

    result = compile_design(_RECT, user_message=_MESSAGE)
    _, components = _geometry(result)
    doors = _of_type(components, "door")
    assert doors
    for door in doors:
        assert isinstance(door.get("interaction"), dict), "门缺少 interaction，引擎无法渲染开合"
    # 并集生效的反证：缺一个注册表必填字段必须报错。
    assert not [
        item for item in result.defects if item.code == "required_missing"
    ], "合规产物不该出现必填缺失"


def test_registry_required_field_gap_is_reported() -> None:
    """``interaction`` 只在注册表必填、不在 schema 必填 → 必填判定必须取并集。

    只读 schema 的话，一扇"引擎渲染不出开合"的门会被编译判为合格——
    这条测试就是拿掉并集之后唯一会红的地方。
    """

    blueprint = {
        "geometry": {
            "elements": [],
            "components": [
                {
                    "type": "door",
                    "id": "door_1",
                    "parentWall": "wall_front_1",
                    "from": [1.0, 0.0, 0.0],
                    "width": 0.9,
                    "height": 2.1,
                }
            ],
        }
    }
    missing = {item.evidence for item in _structure_defects(blueprint)}
    assert any("interaction" in evidence for evidence in missing), missing


# ── 五、"图纸没说" vs "图纸错了" ──


def test_defaulted_is_confined_to_registry_optional_fields() -> None:
    """``defaulted`` 只收注册表声明过的可选字段。

    否则它会退化成"schema 里所有没出现的字段"——实测那样有 299 条，
    ``floor.radius`` / ``wall.curve`` / ``stair.stepCount`` 这些引擎内部字段
    根本不存在"图纸表不表态"的问题，混进来只会淹掉真正该问模型的那几条。
    """

    result = compile_design(_SPLIT, user_message=_MESSAGE)
    assert result.defaulted, "至少门窗应有未表态字段，否则这份测试没有区分力"

    for item in result.defaulted:
        entity = _find_entity(result, item.target)
        assert entity is not None, f"defaulted 指向不存在的实体 {item.target}"
        allowed = set(COMPONENT_REGISTRY[str(entity["type"])].optional_fields)
        assert item.field in allowed, f"{entity['type']}.{item.field} 不是设计可表态字段"
        assert item.field not in entity, f"{item.field} 已落地却仍被报成未表态"

    # 墙/楼板/楼梯由确定性骨架完全拥有，不在注册表里 → 一条 defaulted 都不该有。
    assert not [
        item for item in result.defaulted if item.field in {"radius", "curve", "segments"}
    ]


def test_door_defaulted_reflects_unstated_leaf_fields() -> None:
    """门的"没表态"清单应恰好是 ``optional_fields`` 减掉已给出的那几个。

    这条同时钉住两个方向：``interaction`` 既然由合成给了，就不该出现在里面；
    ``leafRows`` 图纸协议里没有对应项，必须如实报出来（卷帘门可辨识度就靠它）。
    """

    result = compile_design(_RECT, user_message=_MESSAGE)
    _, components = _geometry(result)
    door = _of_type(components, "door")[0]
    reported = {item.field for item in result.defaulted if item.target == door["id"]}
    expected = set(COMPONENT_REGISTRY["door"].optional_fields) - set(door)

    assert reported == expected
    assert "interaction" not in reported
    assert "leafRows" in reported


def test_quota_shortfall_for_ruleless_type_is_not_blocking() -> None:
    """编译器没有派生规则的类型 → ``uncompiled`` + 非阻断（走模型通道补）。

    红线：能力缺失只标记不阻断。同一条"配额没满足"如果再以 ``error`` 出现，
    "交给模型补"就变成了"阻断交付"——所以对应的缺陷必须降为 ``warn``，
    ``result.ok`` 仍为 True。注意坡道是**已实现**的构件，这里考的不是能力缺口，
    而是"引擎能做、但编译器没规则去摆它"（坡道要有可派生的高差，见
    ``test_ramp_is_not_derived_without_site_elevation``）。

    ⚠️ 本用例原先拿 ``chimney`` 举例。檐口/烟囱/灯具补上派生规则后，这个举例失效了
    （它们会真的被产出来），改用仍然无规则的 ``ramp``。
    """

    result = compile_design(
        {**_RECT, "component_quota": {"ramp": {"min": 1, "max": 1}}},
        user_message=_MESSAGE,
    )
    assert result.uncompiled == ["ramp"]
    assert result.unsupported == []
    assert result.ok, "缺编译规则只该标注，不该阻断"

    shortfalls = [item for item in result.defects if item.code == "design_constraint"]
    assert shortfalls, "配额没满足必须如实报出，只是不该阻断"
    assert all(item.severity == "warn" for item in shortfalls)


def test_quota_shortfall_is_never_blocking() -> None:
    """数量缺口恒 warn（用户决策 2026-09-29，废除数量硬闸）。

    校验只对**空间/结构状态**（标高缺失、超墙容量、批准槽位未落实）判 error；
    "door 数量 0 少于设计下限 5"这类数量问题是"模型补量"问题——标记出来交给
    模型通道，不许拦下整张蓝图。旧实现按 ``deferable``（编译器有无派生规则）
    区分 error/warn，那仍然会让已实现类型的部分缺口阻断交付。
    """

    empty_blueprint = {"geometry": {"elements": [], "components": []}}
    brief = {"component_quota": {"door": {"min": 5, "max": 5}}}

    defects = _validator_defects(empty_blueprint, brief)
    shortfalls = [item for item in defects if item.code == "design_constraint"]
    assert shortfalls, "数量缺口必须如实报出，只是不该阻断"
    assert all(item.severity == "warn" for item in shortfalls)


# ── 六、产物必须过既有门禁 ──


@pytest.mark.parametrize("plan", [_RECT, _SPLIT, _FLAT])
def test_compiled_blueprint_passes_existing_validators(plan: dict) -> None:
    """编译产物直接喂既有校验器，零问题。

    编译器**不许**另立一套合法性口径——它必须产出与线上同一条链路认得的蓝图。
    """

    result = compile_design(deepcopy(plan), user_message=_MESSAGE)
    blueprint = result.blueprint
    assert blueprint is not None

    assert validate_blueprint_schema(blueprint) == []

    reference_fn = getattr(validate_reference_integrity, "func", validate_reference_integrity)
    report = reference_fn(blueprint)
    assert "❌" not in (report or ""), report
    assert result.ok, [item.to_dict() for item in result.defects]


def _find_entity(result, target: str) -> dict | None:
    elements, components = _geometry(result)
    for entity in [*elements, *components]:
        if entity.get("id") == target:
            return entity
    return None


# ── 七、附属构件派生：檐口 / 烟囱 / 灯具 ──

#: 点名三类**可派生**的附属构件 + 一类故意不派生的坡道：
#: 一次编译就能同时看到"产出"与"仍缺"两条分支的分界。
_ATTACHMENTS: dict = {
    "cornice": {"min": 1, "max": 4},
    "chimney": {"min": 1, "max": 1},
    "light": {"min": 2, "max": 8},
    "ramp": {"min": 1, "max": 1},
}


def _with_quota(plan: dict, quota: dict) -> dict:
    return {**deepcopy(plan), "component_quota": quota}


def test_cornice_attaches_to_each_eave_edge_of_the_roof() -> None:
    """檐口挂在屋顶**檐边**上，且用屋顶局部坐标。

    两件事必须同时成立，否则线上是整份蓝图编译不出来（不是"少个线脚"）：
    ① ``parentRoof`` 指到真实存在的屋顶（KB：建筑檐口应优先指定 parentRoof）；
    ② 路径不能越出 ``|x|<=span/2``、``|z|<=depth/2`` —— 引擎侧
    ``attachPointsToRoof`` 越界即抛 ``ComponentCompileError``，1e-6 容差。
    ``gable`` 的檐边只有 ``x = ±span/2`` 两条；``z = ±depth/2`` 那两条是山墙端。
    """

    result = compile_design(_with_quota(_RECT, _ATTACHMENTS), user_message=_MESSAGE)
    elements, components = _geometry(result)
    roofs = {roof["id"]: roof for roof in _of_type(elements, "roof")}
    cornices = _of_type(components, "cornice")

    assert result.stats["cornice"] == 2, "gable 的檐边只有 x=±span/2 两条"
    for cornice in cornices:
        roof = roofs[cornice["parentRoof"]]
        assert len(cornice["path"]) == 2
        assert len(cornice["profile"]) >= 3, "闭合截面不足三点，引擎直接拒"
        for x, y, z in cornice["path"]:
            # 刻意不带容差：引擎的边界判定只有 1e-6，越界就是整份蓝图编译失败。
            assert abs(x) <= roof["span"] / 2, "局部坐标越界 → 引擎拒绝整份蓝图"
            assert abs(z) <= roof["depth"] / 2
            assert y == 0.0, "坡屋顶的檐边在屋面最低处（局部 Y = 0）"


def test_partial_derivation_is_refused_so_it_stays_a_warning() -> None:
    """产不够下限时**一个都不产**——否则这类型会从 warn 掉进 error。

    ``validate_design_brief_constraints`` 对"配额下限没满足"报 ``error``，
    而 ``_capability_gaps`` 只看"该类型是否已经出现过"。``gable`` 只有 2 条檐边，
    下限写 4 时若真产出 2 个，``cornice`` 就不再算 ``uncompiled``，于是被判 ``error``
    —— **部分派生比完全不派生更糟**。这条测试就是那道门的可观测判据。
    """

    result = compile_design(
        _with_quota(_RECT, {"cornice": {"min": 4, "max": 4}}), user_message=_MESSAGE
    )
    _, components = _geometry(result)

    assert _of_type(components, "cornice") == []
    assert result.uncompiled == ["cornice"]
    assert result.ok, "产不够时必须退回标记，不能阻断交付"


def test_quota_max_no_longer_prunes_derived_attachments() -> None:
    """配额上限已废（用户决策 2026-09-29，删除上限白名单）：max 只是参考值。

    12 道外墙面各一盏灯，配额上限 8 ⇒ 产物仍是 12 盏。数量的强制口径回到
    设计自己的表态（槽位吸附 + 下限校验），上限不再剃产物——密集表达正是
    模型该有的自由度，剃掉它等于替设计做减法。
    """

    result = compile_design(_with_quota(_RECT, _ATTACHMENTS), user_message=_MESSAGE)
    _, components = _geometry(result)
    assert len(_of_type(components, "light")) == 12


def test_chimney_stands_on_the_ridge_line() -> None:
    """烟囱基座落在屋面**最高处**，筒身才不会插进坡屋面。

    KB 明写烟囱"不执行屋顶布尔穿透"⇒ 埋在屋面里就是穿帮。``gable`` 的最高处是
    局部 ``x = 0`` 那条屋脊线（坡向沿 x），落点再沿 z 偏开正中心。
    """

    result = compile_design(_with_quota(_RECT, _ATTACHMENTS), user_message=_MESSAGE)
    elements, components = _geometry(result)
    roofs = {roof["id"]: roof for roof in _of_type(elements, "roof")}
    chimneys = _of_type(components, "chimney")

    assert result.stats["chimney"] == 1
    chimney = chimneys[0]
    roof = roofs[chimney["parentRoof"]]
    x, y, z = chimney["position"]
    assert (x, y) == (0.0, 0.0), "gable 的屋脊是局部 x=0；Y 是屋面高度偏移，交给引擎贴"
    assert 0 < z <= roof["depth"] / 2, "落点必须落在屋面平面内"
    assert chimney["wallThickness"] * 2 < min(chimney["width"], chimney["depth"]), (
        "壁厚超过宽深的一半时引擎按校验抛错"
    )


def test_chimney_size_tracks_floors_not_building_footprint() -> None:
    """烟囱是**设备尺寸**：只随层数变，不随建筑宽深缩放（与核心筒井道同一口径）。

    否则 60m 宽的楼会长出一根粗得离谱的烟囱——这正是仓库里记过的
    "一个数被当两个单位用"。
    """

    wide = {**_RECT, "massing": {**_RECT["massing"], "width": 60, "depth": 40}}
    narrow = {**_RECT, "massing": {**_RECT["massing"], "width": 8, "depth": 6}}
    sizes = []
    for plan in (wide, narrow):
        result = compile_design(_with_quota(plan, _ATTACHMENTS), user_message=_MESSAGE)
        _, components = _geometry(result)
        sizes.append(_of_type(components, "chimney")[0]["width"])

    assert sizes[0] == sizes[1], "层数相同 ⇒ 设备尺寸必须相同"
    assert 0.4 <= sizes[0] <= 1.0


def test_lights_land_outside_the_building_footprint() -> None:
    """灯落在墙**外侧**：外法向由体量轮廓绕向判定，不能固定"沿墙右旋 90°"。

    顺时针轮廓时固定右旋会把灯放进室内。这里用"不许落在平面轮廓内"当判据——
    比逐一比对墙面坐标更抗改动，且直接对准那个真实缺陷。
    """

    result = compile_design(_with_quota(_RECT, _ATTACHMENTS), user_message=_MESSAGE)
    _, components = _geometry(result)
    lights = _of_type(components, "light")

    massing = normalize_architecture_plan(_RECT, _MESSAGE)["massing"]
    width, depth = float(massing["width"]), float(massing["depth"])
    assert lights, "限额下限 2 却一盏都没产出"
    for light in lights:
        x, y, z = light["position"]
        assert not (0.0 < x < width and 0.0 < z < depth), (
            f"{light['id']} 落在建筑轮廓内：{light['position']}"
        )
        assert y > 0.0, "壁灯不该落在地面标高"


def test_entrance_light_is_snapped_to_the_door_axis() -> None:
    """入口墙那盏由**既有**的 ``conform_entrance_accessories`` 吸附到门轴线。

    派生只做"贴墙外 0.35m"的粗对齐，精对齐复用既有实现（唯一规则函数）；
    所以 ``stats["entrance"]["light_snapped"]`` 必须真的动过手 —— 否则说明粗对齐
    的位置已经"恰好"对上了，精对齐这一步其实没生效。
    """

    result = compile_design(_with_quota(_RECT, _ATTACHMENTS), user_message=_MESSAGE)
    _, components = _geometry(result)
    doors = _of_type(components, "door")

    assert doors
    assert result.stats["entrance"]["light_snapped"] > 0
    # 吸附后，前立面（z = -0.35 一侧）那层门高处的灯应当与门共轴。
    door_axis = float(doors[0]["from"][0]) + float(doors[0]["width"]) / 2
    entrance_lights = [
        light for light in _of_type(components, "light")
        if abs(light["position"][2] + 0.35) < 1e-6
        and abs(light["position"][1] - 1.8) < 1e-6
    ]
    assert entrance_lights, "入口墙那盏不见了"
    for light in entrance_lights:
        assert abs(float(light["position"][0]) - door_axis) < 0.01, (
            f"入口灯没对齐到门轴线：{light['position']} vs {door_axis}"
        )


def test_ramp_is_not_derived_without_site_elevation() -> None:
    """坡道**故意**不派生：设计协议里没有场地标高，也就没有可派生的高差。

    引擎要求 ``from``/``to`` 有水平投影，KB 又明写"必须有高度差"。首层恒在 Y=0、
    又没有室外地面标高 ⇒ 想产出坡道只能自己发明一个落差，那就是"产生设计"，
    与本模块"只做映射"的不变式冲突。⇒ 如实报成 ``uncompiled``（warn）交给模型通道。
    """

    result = compile_design(
        _with_quota(_RECT, {"ramp": {"min": 1, "max": 1}}), user_message=_MESSAGE
    )
    _, components = _geometry(result)

    assert _of_type(components, "ramp") == []
    assert result.uncompiled == ["ramp"]
    assert all(
        item.severity == "warn"
        for item in result.defects
        if item.code == "design_constraint"
    )


def test_derived_attachments_pass_existing_validators() -> None:
    """派生构件也必须过**同一条**既有校验链路（编译器不许另立合法性口径）。

    ``parentRoof`` 拼错、局部坐标越界、``profile`` 不足三点、壁厚过大——
    这些都会在这里红。
    """

    result = compile_design(_with_quota(_RECT, _ATTACHMENTS), user_message=_MESSAGE)
    blueprint = result.blueprint
    assert blueprint is not None

    assert validate_blueprint_schema(blueprint) == []

    reference_fn = getattr(validate_reference_integrity, "func", validate_reference_integrity)
    report = reference_fn(blueprint)
    assert "❌" not in (report or ""), report
    assert result.ok, [item.to_dict() for item in result.defects]


def test_attachments_are_skipped_when_quota_does_not_ask_for_them() -> None:
    """配额没点名的类型一个都不产 —— 派生不能变成"顺手多给"。

    否则只要开了这个开关，每栋楼都被塞上檐口和烟囱：那是**产生设计**。
    """

    result = compile_design(_RECT, user_message=_MESSAGE)
    _, components = _geometry(result)
    kinds = {item["type"] for item in components}
    assert not ({"cornice", "chimney", "light"} & kinds), kinds


# ── 八、材质方案落地（2026-09-28 修一个真回归）──


def _resolved_plan(*, texture: str | None = None) -> dict:
    """最小可用的"已批准材质方案"。

    ``texture`` 给定时，对外墙角色挂上 ``textureSet`` —— 模拟"资产目录非空"时
    `resolve_material_plan` 会产出的形态。``materialId`` 一律取 `ROLE_SPECS` 的
    固定值：**模型改不了它**，只能改 `assetId`（因此贴图才挂在材质字典里）。
    """

    def material(role: str) -> dict:
        body = {
            "baseColor": [0.5, 0.5, 0.5],
            "roughness": 0.5,
            "metallic": 0.0,
            "albedo": 1.0,
            "lightingCondition": "D65_noon",
        }
        if texture and role == "facade_primary":
            body.update({"textureSet": texture, "normalScale": 1.0, "uvScale": [2, 2]})
        return body

    roles = [
        {"role": role, "materialId": spec["materialId"], "assetId": None,
         "proceduralPresetId": None, "material": material(role)}
        for role, spec in ROLE_SPECS.items()
    ]
    return {
        "concept": "测试方案",
        "palette": [],
        "roles": roles,
        "resolvedAssets": {"tex_001": {"assetId": "tex_001", "maps": {"baseColor": "a.png"}}}
        if texture else {},
        "rejectedAssetIds": [],
        "rejectedProceduralPresetIds": [],
        "curtainWall": False,
    }


def test_approved_material_plan_lands_in_the_blueprint() -> None:
    """已批准的材质方案必须进蓝图。

    这是 2026-09-28 修的一个真回归：`compile_design` 原来**没有**
    `apply_resolved_material_plan` 这一步（只有 `skeleton_generator` 有），
    于是建筑链退回骨架硬编码的 6 个材质，`floor_finish`/`ground`/`accent`
    三个角色材质根本不会出现，`assets` 也不会写进蓝图。
    """

    result = compile_design(_RECT, user_message=_MESSAGE, material_plan=_resolved_plan())
    materials = result.blueprint["materials"]
    wanted = {spec["materialId"] for spec in ROLE_SPECS.values()}
    assert wanted <= set(materials), sorted(wanted - set(materials))
    assert "floor_finish" in materials


def test_texture_channels_and_asset_table_reach_the_blueprint() -> None:
    """贴图通道与资产表必须落地 —— 这才是"材质方案"的可视价值。

    只让材质**名字**对上不够：资产目录非空时，`resolve_material_plan` 会把
    `textureSet`/`normalScale`/`uvScale` 挂进材质字典，并把 `resolvedAssets`
    交给渲染侧。少这两样，建筑链渲染出来就是"有材质名、没贴图"。
    """

    result = compile_design(
        _RECT, user_message=_MESSAGE, material_plan=_resolved_plan(texture="tex_001")
    )
    blueprint = result.blueprint
    wall = blueprint["materials"]["wall_finish"]
    assert wall["textureSet"] == "tex_001"
    assert wall["uvScale"] == [2, 2]
    assert blueprint["assets"] == {"tex_001": {"assetId": "tex_001", "maps": {"baseColor": "a.png"}}}


def test_omitting_material_plan_leaves_only_the_skeleton_materials() -> None:
    """不传材质方案时，蓝图只能有骨架那 6 个材质、且没有资产表。

    反方向钉住：**不能**为了"补材质"而在编译里凭空造材质或资产。
    """

    result = compile_design(_RECT, user_message=_MESSAGE)
    materials = set(result.blueprint["materials"])
    assert materials <= {"concrete", "wall_finish", "wood", "metal", "glass", "roof"}
    assert not result.blueprint.get("assets")
    assert "floor_finish" not in materials


@pytest.mark.parametrize("plan", [_RECT, _FLAT])
def test_landing_inside_compile_equals_landing_afterwards(plan: dict) -> None:
    """等价性：`compile_design(material_plan=…)` 必须与"编译后再手动落地"逐项一致。

    这条是这次修复的**验收断言**。它同时保证了落地**发生在按材质取名的步骤之前**：
    若晚于 `conform_openings_to_slots`，构件就已经固化了当时的材质名，两边不再相等。
    """

    resolved = _resolved_plan(texture="tex_001")
    inside = compile_design(plan, user_message=_MESSAGE, material_plan=resolved).blueprint

    outside = apply_resolved_material_plan(
        deepcopy(compile_design(plan, user_message=_MESSAGE).blueprint),
        resolved,
        role_specs=material_role_specs(plan),
    )

    assert inside["materials"] == outside["materials"]
    assert inside["assets"] == outside["assets"]


def test_material_landing_is_idempotent() -> None:
    """重复落地不改结果（`apply_resolved_material_plan` 是幂等的覆盖写）。

    否则"编译 + 编排层再落一次"会产出两份不同的蓝图。
    """

    resolved = _resolved_plan(texture="tex_001")
    once = compile_design(_RECT, user_message=_MESSAGE, material_plan=resolved).blueprint
    twice = apply_resolved_material_plan(
        deepcopy(once), resolved, role_specs=material_role_specs(_RECT)
    )
    assert twice["materials"] == once["materials"]
    assert twice["assets"] == once["assets"]


# ── 九、缺陷定位：design_field 必须能让收敛环找到块 ──


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # 结构元素由确定性骨架拥有，尺寸全部来自体量块
        ("❌ [wall_001] from[1] 与宿主墙不匹配", "decisions.massing"),
        ("❌ [floor_f2] thickness 超出范围", "decisions.massing"),
        ("❌ [column_c0] 高度为 0", "decisions.massing"),
        # 幕墙竖梃 / 井道墙各有归属
        ("❌ [curtain_mullion_3] 间距不均", "decisions.facades"),
        ("❌ [wall_core_0] 与门洞碰撞", "decisions.circulation"),
        # 蓝图级：认不出就**留空**，不许猜
        ("❌ 缺少顶层字段 'meta'", ""),
        ("❌ 重复的构件 ID: ['a']", ""),
        ("❌ [mystery_9] 某种未知问题", ""),
        ("没有方括号也没有 ❌", ""),
    ],
)
def test_issue_maps_to_the_block_that_must_change(message: str, expected: str) -> None:
    """`_design_field_of_issue` 只认命名约定里确定的那些，认不出返回空串。

    这条钉的是"**不许猜**"：猜错会让收敛环去改**另一个块**，比不定位更糟。
    """

    assert _design_field_of_issue(message, {}) == expected


def test_component_issue_maps_through_the_component_type() -> None:
    """`[component:<id>]` 要经构件自身类型走 `_DESIGN_FIELD`，而不是拿 id 硬凑。"""

    blueprint = {
        "geometry": {"components": [{"id": "canopy_1", "type": "canopy"}]},
    }
    assert (
        _design_field_of_issue("❌ [component:canopy_1] parentWall 不存在", blueprint)
        == "decisions.components[type=canopy]"
    )
    # 找不到该构件时同样留空（宁可整图重出，也不指错块）
    assert _design_field_of_issue("❌ [component:ghost_9] x", blueprint) == ""


def test_design_constraint_defect_carries_the_design_field() -> None:
    """配额类缺陷必须带 `design_field` —— 它是 `design_convergence` 的输入。

    `validate_design_brief_constraints` 的文案首 token 是构件类型，据此走 `_DESIGN_FIELD`。
    用檐口构造：gable 屋顶只有 2 条檐边，下限写 4 必然不足，且檐口**已实现**（不会降级 warn）。
    """

    plan = {**_RECT, "component_quota": {"cornice": {"min": 4, "max": 8}}}
    result = compile_design(plan, user_message=_MESSAGE)
    constraints = [item for item in result.defects if item.code == "design_constraint"]
    assert constraints, "该图纸应当触发配额类缺陷"
    assert all(item.design_field for item in constraints), [
        (item.evidence, item.design_field) for item in constraints
    ]
    assert "decisions.roof" in {item.design_field for item in constraints}


def test_ruleless_quota_defect_points_at_its_own_component_block() -> None:
    """没有 `_DESIGN_FIELD` 条目的类型，回退成 `decisions.components[type=<t>]`。

    坡道当前没有派生规则（`uncompiled`），它的配额缺陷降为 `warn`，但**定位信息必须还在**。
    """

    plan = {**_RECT, "component_quota": {"ramp": {"min": 1, "max": 1}}}
    result = compile_design(plan, user_message=_MESSAGE)
    ramps = [item for item in result.defects if "ramp" in item.evidence]
    assert ramps, [item.evidence for item in result.defects]
    assert all(item.design_field == "decisions.components[type=ramp]" for item in ramps), [
        (item.evidence, item.design_field) for item in ramps
    ]

