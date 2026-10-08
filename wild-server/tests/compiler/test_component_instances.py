"""测试§3.4构件实例清单的编译。"""

from app.agent.compiler import compile_design
from app.agent.compiler.compile import (
    _FORM_TARGET_SCHEMA_CACHE,
    _INSTANCE_FORM_FIELDS,
    _INSTANCE_FORM_ROUTES,
    _form_target_schema,
)
from app.agent.generation.architecture import normalize_architecture_plan


def test_component_instances_compile_to_blueprint():
    """实例清单能被编译成蓝图构件。"""
    
    plan = {
        "massing": {"shape": "rectangular", "width": 20, "depth": 15, "floors": 3},
        "components": [
            {
                "type": "balcony",
                "host": "wall_front_2",  # 使用正确的墙id格式
                "size": {"width": 3.6, "depth": 1.4},
                "form": {"infillType": "glass", "railingHeight": 1.05},
                "material_role": "accent",
            },
        ],
    }
    
    normalized = normalize_architecture_plan(plan, "3层住宅带阳台")
    result = compile_design(normalized, user_message="3层住宅带阳台")
    
    assert result.blueprint is not None
    assert result.stats.get("from_instances") is True
    
    components = result.blueprint.get("geometry", {}).get("components", [])
    balconies = [c for c in components if c.get("type") == "balcony"]
    
    # 实例清单产生的阳台应该存在
    assert len(balconies) >= 1


def test_empty_instances_falls_back_to_quota_mode():
    """空实例清单时回退到配额模式。"""
    
    plan = {
        "massing": {"shape": "rectangular", "width": 20, "depth": 15, "floors": 3},
        "components": [],  # 空清单
        "component_quota": {"door": {"min": 1, "max": 3}},
    }
    
    normalized = normalize_architecture_plan(plan, "3层住宅")
    result = compile_design(normalized, user_message="3层住宅")
    
    assert result.blueprint is not None
    assert result.stats.get("from_instances") is False  # 使用配额模式
    
    components = result.blueprint.get("geometry", {}).get("components", [])
    doors = [c for c in components if c.get("type") == "door"]
    
    # 配额模式应该产生门
    assert len(doors) >= 1


def test_multiple_component_types_from_instances():
    """多种构件类型都能从实例清单编译。"""
    
    plan = {
        "massing": {"shape": "rectangular", "width": 20, "depth": 15, "floors": 3},
        "components": [
            {
                "type": "door",
                "host": "wall_front_1",
                "size": {"width": 1.2, "height": 2.1},
                "form": {"mode": "swing", "hingeSide": "right"},
                "material_role": "door",
            },
            {
                "type": "window",
                "host": "wall_front_2",
                "size": {"width": 1.5, "height": 1.4},
                "form": {"verticalMullions": 1, "horizontalMullions": 0},
                "material_role": "glass",
            },
            {
                "type": "balcony",
                "host": "wall_back_2",
                "size": {"width": 2.8, "depth": 1.2},
                "form": {"railingHeight": 1.1},
            },
        ],
    }
    
    normalized = normalize_architecture_plan(plan, "带多种构件的住宅")
    result = compile_design(normalized, user_message="带多种构件的住宅")
    
    # 实例清单模式应该标记
    assert result.stats.get("from_instances") is True
    assert result.blueprint is not None
    
    components = result.blueprint.get("geometry", {}).get("components", [])
    
    # 应该有各种类型的构件
    types = {c.get("type") for c in components}
    assert "door" in types
    assert "window" in types  
    assert "balcony" in types


def test_roof_instance_compilation():
    """屋顶实例能被正确编译。"""
    
    plan = {
        "massing": {"shape": "rectangular", "width": 12, "depth": 10, "floors": 2},
        "components": [
            {
                "type": "roof",
                "host": "volume_primary",
                "form": {
                    "roofType": "gable",
                    "ridge_axis": "x",
                    "ridgeHeight": 2.5,
                    "overhang": 0.6,
                },
                "material_role": "roof",
            },
        ],
    }
    
    normalized = normalize_architecture_plan(plan, "坡屋顶住宅")
    result = compile_design(normalized, user_message="坡屋顶住宅")
    
    assert result.ok
    components = result.blueprint.get("geometry", {}).get("components", [])
    roofs = [c for c in components if c.get("type") == "roof"]
    
    if roofs:
        roof = roofs[0]
        assert roof.get("roofType") == "gable"
        assert roof.get("ridgeAxis") == "x"


def test_canopy_instance_compilation():
    """雨篷实例能被正确编译。"""
    
    plan = {
        "massing": {"shape": "rectangular", "width": 15, "depth": 12, "floors": 2},
        "components": [
            {
                "type": "canopy",
                "host": "door_front_01",
                "size": {"depth": 1.5, "thickness": 0.2, "width_offset": 0.4},
                "form": {"slope": 0.15},
                "material_role": "roof",
            },
        ],
    }
    
    normalized = normalize_architecture_plan(plan, "带雨篷的建筑")
    result = compile_design(normalized, user_message="带雨篷的建筑")
    
    # 雨篷依赖门的存在，可能需要先有门才能编译
    assert result.blueprint is not None


def test_light_instance_compilation():
    """灯具实例能被正确编译。"""
    
    plan = {
        "massing": {"shape": "rectangular", "width": 15, "depth": 12, "floors": 2},
        "components": [
            {
                "type": "light",
                "host": "wall_front_1",
                "size": {"radius": 0.2},
                "form": {"lightType": "wall", "intensity": 1.2},
                "material_role": "frame",
            },
        ],
    }
    
    normalized = normalize_architecture_plan(plan, "带灯具的建筑")
    result = compile_design(normalized, user_message="带灯具的建筑")
    
    assert result.ok
    # 显式实例**顶替**了派生的那一条（而不是整类取代，也不是并存）。
    assert result.stats["instance_overrides"]["replaced"].get("light") == 1

    components = result.blueprint.get("geometry", {}).get("components", [])
    lights = [c for c in components if c.get("type") == "light"]

    # 🔴 引擎的 light 只有 position / fixtureType / initiallyOn。
    # `lightType` 是**闭集**（point / spot），写 "wall" 会让整份蓝图 schema_invalid ——
    # 旧断言把这个错误固化下来了，所以这里改成钉住真正合法的字段。
    explicit = [light for light in lights if light.get("id") == "light_01"]
    assert len(explicit) == 1
    assert len(explicit[0]["position"]) == 3
    assert explicit[0]["fixtureType"] == "bulb"
    # 其余立面的派生灯**没被整类换掉**（否则配额下限会被跌破，`ok` 变 False）。
    assert len(lights) >= 2


def test_host_resolution_supports_multiple_formats():
    """host解析支持多种格式。"""
    
    plan = {
        "massing": {"shape": "rectangular", "width": 20, "depth": 15, "floors": 3},
        "components": [
            {
                "type": "window",
                "host": "wall_front_1",  # 直接墙id
                "size": {"width": 1.2, "height": 1.4},
            },
            {
                "type": "window",
                "host": "slot_back_02",  # 槽位id
                "size": {"width": 1.0, "height": 1.2},
            },
            {
                "type": "balcony",
                "host": "volume_primary_L2_south",  # 体量面id
                "size": {"width": 2.4, "depth": 1.2},
            },
        ],
    }
    
    normalized = normalize_architecture_plan(plan, "多格式host测试")
    result = compile_design(normalized, user_message="多格式host测试")
    
    # 应该能成功编译，不因host格式问题失败
    assert result.blueprint is not None


def test_slot_geometry_wins_over_instance_size():
    """有批准槽位时几何以槽位为准：实例的 size 不落进产物（§3.4）。

    旧实现里实例的 width/height 会盖掉派生槽位，``validate_design_brief_constraints``
    随即报"未落实批准槽位"——几何被两处夹取就是会分叉。重构后实例的 size 只在
    **追加**（该墙没有同类型派生结果）时才是尺寸来源。
    """

    plan = {
        "massing": {"shape": "rectangular", "width": 20, "depth": 15, "floors": 3},
        "components": [
            {
                "type": "door",
                "host": "wall_front_1",
                # 离谱的尺寸：若被采纳，槽位校验必炸。模板存在时必须被忽略。
                "size": {"width": 3.0, "height": 2.5},
                "form": {"mode": "slide"},
            },
        ],
    }

    normalized = normalize_architecture_plan(plan, "尺寸由槽位定")
    result = compile_design(normalized, user_message="尺寸由槽位定")

    assert result.ok
    doors = [
        item
        for item in result.blueprint["geometry"]["components"]
        if item.get("type") == "door" and item.get("id") == "door_01"
    ]
    assert len(doors) == 1
    door = doors[0]
    # 几何与派生模板一致（槽位说了算），不是实例写的 3.0 / 2.5。
    assert door["width"] != 3.0
    assert door["height"] != 2.5
    # 形态表态仍然生效。
    assert door["interaction"]["mode"] == "slide"


def test_unknown_form_keys_are_dropped_not_passed():
    """白名单外的 form 键被丢弃并记入 stats，而不是透传进蓝图。

    透传任意键会让整份蓝图 ``schema_invalid``（引擎字段闭集）；丢键 + 记账
    才是对齐编译器"认不出就降级"的既有口径。
    """

    plan = {
        "massing": {"shape": "rectangular", "width": 15, "depth": 12, "floors": 2},
        "components": [
            {
                "type": "window",
                "host": "wall_front_1",
                "form": {"verticalMullions": 2, "slope": 0.3, "intensity": 1.5},
            },
        ],
    }

    normalized = normalize_architecture_plan(plan, "非法形态键测试")
    result = compile_design(normalized, user_message="非法形态键测试")

    assert result.ok
    windows = [
        item
        for item in result.blueprint["geometry"]["components"]
        if item.get("type") == "window" and item.get("id") == "window_01"
    ]
    assert len(windows) == 1
    window = windows[0]
    assert window["verticalMullions"] == 2
    assert "slope" not in window
    assert "intensity" not in window
    ignored = result.stats["instance_overrides"]["form_ignored"].get("window", [])
    assert "slope" in ignored
    assert "intensity" in ignored


def test_occurrence_suffix_selects_nth_derived_template():
    """``host="wall_front_1:2"`` 命中同墙第 2 条派生结果。

    旧实现两个实例会配对到同一条模板：第二条替换空转，该删的那条还删不掉。
    """

    plan = {
        "massing": {"shape": "rectangular", "width": 20, "depth": 15, "floors": 3},
        # 灯具是派生型：没有配额下限派生链就不产灯，实例无模板可顶替。
        # max 只是参考值（上限剔除已删除），这里只钉"出现序配对"，
        # 不让配额语义和实例配对互相污染。
        "component_quota": {"light": {"min": 2, "max": 8}},
        "components": [
            {
                "type": "light",
                "host": "wall_front_1",
                "form": {"fixtureType": "table_lamp"},
            },
            {
                "type": "light",
                "host": "wall_front_1:2",
                "form": {"fixtureType": "table_lamp"},
            },
        ],
    }

    normalized = normalize_architecture_plan(plan, "出现序配对测试")
    result = compile_design(normalized, user_message="出现序配对测试")

    assert result.ok
    assert result.stats["instance_overrides"]["replaced"].get("light") == 2
    lights = [
        item
        for item in result.blueprint["geometry"]["components"]
        if item.get("type") == "light"
    ]
    explicit = [item for item in lights if item.get("id") in {"light_01", "light_02"}]
    assert len(explicit) == 2
    # 两条实例顶替的是**不同**的派生结果（位置不同），且各自带上形态表态。
    assert explicit[0]["position"] != explicit[1]["position"]
    assert all(item["fixtureType"] == "table_lamp" for item in explicit)
    # 其余派生灯照留（覆盖层不是替换层）。
    assert len(lights) > 2


def test_form_parameters_applied_correctly():
    """form参数被正确应用到构件上。"""
    
    plan = {
        "massing": {"shape": "rectangular", "width": 15, "depth": 12, "floors": 2},
        "components": [
            {
                "type": "door",
                "host": "wall_front_1",
                "size": {"width": 1.2, "height": 2.1},
                "form": {
                    "mode": "slide",
                    "frameWidth": 0.08,
                    "leafDepth": 0.05,
                },
            },
        ],
    }
    
    normalized = normalize_architecture_plan(plan, "形态参数测试")
    result = compile_design(normalized, user_message="形态参数测试")
    
    assert result.ok
    components = result.blueprint.get("geometry", {}).get("components", [])
    doors = [c for c in components if c.get("type") == "door"]
    
    if doors:
        door = doors[0]
        interaction = door.get("interaction", {})
        assert interaction.get("mode") == "slide"
        assert door.get("frameWidth") == 0.08
        assert door.get("leafDepth") == 0.05


def test_interaction_form_value_is_checked_on_the_layer_the_engine_reads():
    """`hingeSide` / `openAngle` 落在 `interaction` 里，校验的必须是**那一层**。

    两件事一起钉：(a) 部分表态（只给 `hingeSide`、不给 `mode`）**不许**被
    `openingInteractionSpec.required=['mode']` 误判 —— 那是把一次合法表态变成假拒绝；
    (b) 值本身越界时不落、记证据，且**不覆盖**派生模板里已有的值。
    """

    plan = {
        "massing": {"shape": "rectangular", "width": 15, "depth": 12, "floors": 2},
        "components": [{
            "type": "door",
            "host": "wall_front_1",
            "form": {"hingeSide": "left", "openAngle": 200},
        }],
    }

    normalized = normalize_architecture_plan(plan, "门窗交互形态")
    result = compile_design(normalized, user_message="门窗交互形态")

    assert result.ok
    overrides = result.stats["instance_overrides"]
    assert "hingeSide" in overrides["form_applied"]["door"]
    assert "openAngle" in overrides["form_ignored"]["door"]
    assert "180" in overrides["form_rejections"]["door"]["openAngle"]

    door = next(
        item for item in result.blueprint["geometry"]["components"]
        if item.get("id") == "door_01"
    )
    assert door["interaction"]["hingeSide"] == "left"
    assert door["interaction"].get("openAngle") != 200


# ── 屋顶宿主解析（2026-10-08 事故：`host='main_L2_roof'`）──


def _two_wing_plan(components: list[dict]) -> dict:
    """两个顶层体量 + 平屋面 ⇒ `roof_slots` 非空，屋面 id 是 `roof_planned_01/02`。

    这是能**证明**宿主解析生效的最小配置：两块屋面各自派生檐口，
    写左边的体量必须配到 `roof_planned_01`、写右边的必须配到 `roof_planned_02`；
    若解析没生效（退到"第 1 条派生结果"），两次都会配到 `roof_planned_01`。
    """

    return {
        "massing": {"shape": "rectangular", "width": 12, "depth": 10, "floors": 2},
        "roof": {"type": "flat"},
        "volumes": [
            {
                "id": "left_wing", "x": 0, "z": 0, "width": 6, "depth": 10,
                "start_floor": 1, "end_floor": 2,
            },
            {
                "id": "right_wing", "x": 6, "z": 0, "width": 6, "depth": 10,
                "start_floor": 1, "end_floor": 2,
            },
        ],
        "component_quota": {"cornice": {"min": 1, "max": 1}},
        "components": components,
    }


def _explicit(results, component_id: str) -> list[dict]:
    return [
        item
        for item in results.blueprint["geometry"]["components"]
        if item.get("id") == component_id
    ]


def test_roof_hosted_cornice_resolves_volume_id_to_its_own_roof():
    """檐口挂在体量 id 上 ⇒ 配到的是**那个体量**的屋面，不是兜底的第 1 条派生结果。

    旧实现 `parentRoof == host` 全等匹配对体量写法一律落空，静默退到
    `_template_for(..., occurrence)` —— 檐口会挂到别的体量屋面，且不报任何东西
    （正是 `_host_lookup` 文档里警告的"比报错更难发现"）。
    """

    for volume_id, expected_roof in (
        ("left_wing", "roof_planned_01"),
        ("right_wing", "roof_planned_02"),
    ):
        plan = _two_wing_plan(
            [{"type": "cornice", "host": volume_id, "size": {"height": 0.45, "depth": 0.25}}]
        )
        normalized = normalize_architecture_plan(plan, "双翼平屋面")
        result = compile_design(normalized, user_message="双翼平屋面")

        explicit = _explicit(result, "cornice_01")
        assert len(explicit) == 1, (volume_id, result.summary())
        assert explicit[0]["parentRoof"] == expected_roof
        # 按宿主配到了 ⇒ 不算兜底。
        assert result.summary()["instance_host_fallback"] == []


def test_roof_hosted_cornice_accepts_top_floor_roof_alias():
    """`<volume_id>_L<顶层>_roof`（模型现场写的 `main_L2_roof` 那种类推写法）同样解析。

    单一体量（default profile 的 `main`）走 `_single_roof`，屋面 id 是 `roof_01`。
    """

    plan = {
        "massing": {"shape": "rectangular", "width": 12, "depth": 10, "floors": 2},
        "roof": {"type": "flat"},
        "component_quota": {"cornice": {"min": 1, "max": 1}},
        "components": [
            {"type": "cornice", "host": "main_L2_roof", "size": {"height": 0.45, "depth": 0.25}}
        ],
    }

    normalized = normalize_architecture_plan(plan, "单体积平屋面")
    result = compile_design(normalized, user_message="单体积平屋面")

    explicit = _explicit(result, "cornice_01")
    assert len(explicit) == 1, result.summary()
    assert explicit[0]["parentRoof"] == "roof_01"
    assert result.summary()["instance_host_fallback"] == []


def test_unresolvable_roof_host_falls_back_but_is_recorded():
    """宿主完全解析不到时仍兜底产出，但**必须记账**——静默错位比报错更难查。"""

    plan = {
        "massing": {"shape": "rectangular", "width": 12, "depth": 10, "floors": 2},
        "roof": {"type": "flat"},
        "component_quota": {"cornice": {"min": 1, "max": 1}},
        "components": [
            {"type": "cornice", "host": "attic_roof_xyz", "size": {"height": 0.45}}
        ],
    }

    normalized = normalize_architecture_plan(plan, "宿主不可解析")
    result = compile_design(normalized, user_message="宿主不可解析")

    # 兜底仍然产出一条（不是丢弃），但那一笔要能看到。
    assert len(_explicit(result, "cornice_01")) == 1
    assert result.summary()["instance_host_fallback"] == ["cornice:attic_roof_xyz"]
    assert result.stats["instance_overrides"]["host_fallback"] == ["cornice:attic_roof_xyz"]
    assert result.summary()["instance_dropped"] == []


def test_unresolvable_opening_host_is_dropped_and_reaches_the_gap_summary():
    """宿主解析不到、又无从追加的门窗/阳台实例整条丢弃 —— 且必须报得出来。

    契约层已不再拦宿主引用（`contracts._validate_component_instances`），
    `compile_report.instance_dropped` 就是"写是写了、没落地"的**唯一**通道：
    `plan.expand.compile_gap_summary` 把它注入到该类型的生成条目参数里。
    """

    from app.agent.plan.expand import compile_gap_summary

    plan = {
        "massing": {"shape": "rectangular", "width": 12, "depth": 10, "floors": 2},
        "components": [
            {"type": "balcony", "host": "nowhere_L9_front", "size": {"width": 3.0}}
        ],
    }

    normalized = normalize_architecture_plan(plan, "悬空宿主")
    result = compile_design(normalized, user_message="悬空宿主")

    assert result.summary()["instance_dropped"] == ["balcony:nowhere_L9_front"]
    assert _explicit(result, "balcony_01") == []

    gaps = compile_gap_summary({"compile_report": result.summary()})
    assert gaps["instance_dropped"] == ["balcony:nowhere_L9_front"]


# ── 形态值收口（2026-10-08 现场：檐口 profile 写了一个预设名） ──


def _cornice_plan(form: dict) -> dict:
    """能派生檐口的图纸：gable 屋面 + cornice 配额下限 2，再叠一条显式实例。"""

    return {
        "massing": {"shape": "rectangular", "width": 16, "depth": 11, "floors": 2},
        "roof": {"type": "gable", "ridge_axis": "x", "overhang": 0.6},
        "component_quota": {"cornice": {"min": 2, "max": 4}},
        "components": [{"type": "cornice", "host": "volume_primary", "form": form}],
    }


def test_invalid_form_value_is_rejected_instead_of_landing():
    """回归（2026-10-08）：`form.profile = "rectangular_80x60"`（预设名）不再落进蓝图。

    旧行为的代价是**两端都坏**：值原样落下 ⇒ `validate_cornice_placement` 把
    **类型错误**报成"退化为直线"；修复环的确定性修复用 `len(profile) < 3` 当判据，
    19 个字符的字符串让它认为"无需修复" ⇒ recheck 原样失败 ⇒ 派模型 ⇒
    `patch_entity(profile=…)` 又不在 `repair._PATCH_FIELDS` 里 ⇒ 错误活到最终交付。
    现在：值不落、派生模板的合法截面留着、并且**留下字段级证据**。
    """

    normalized = normalize_architecture_plan(_cornice_plan({"profile": "rectangular_80x60"}), "檐口截面")
    result = compile_design(normalized, user_message="檐口截面")

    assert result.ok
    explicit = _explicit(result, "cornice_01")
    assert len(explicit) == 1
    profile = explicit[0]["profile"]
    assert isinstance(profile, list) and len(profile) >= 3
    assert all(isinstance(point, (list, tuple)) and len(point) == 2 for point in profile)

    overrides = result.stats["instance_overrides"]
    assert overrides["form_ignored"]["cornice"] == ["profile"]
    reason = overrides["form_rejections"]["cornice"]["profile"]
    assert "profile" in reason and "array" in reason
    assert result.summary()["instance_form_rejected"] == [f"cornice.profile: {reason}"]


def test_valid_form_profile_still_lands():
    """合法的二维点数组照旧落地 —— 收口只拦"值不合法"，不收回能力。"""

    points = [[-0.16, -0.14], [0.16, -0.14], [0.16, 0.08], [-0.16, 0.08]]
    normalized = normalize_architecture_plan(_cornice_plan({"profile": points}), "檐口截面")
    result = compile_design(normalized, user_message="檐口截面")

    assert result.ok
    explicit = _explicit(result, "cornice_01")
    assert [[float(x), float(y)] for x, y in explicit[0]["profile"]] == points
    overrides = result.stats["instance_overrides"]
    assert overrides["form_rejections"] == {}
    assert "profile" in overrides["form_applied"]["cornice"]


def test_every_form_key_lands_on_an_engine_field():
    """🔴 形态白名单里的**每个**键都必须在引擎 schema 里找得到落点。

    键名对、落点不存在 = 静默失效：值落进了蓝图，引擎不读、校验器也看不见。
    现场（2026-10-08）：`roof.ridge_axis` / `roof.overhang` 在白名单里、屋顶元素
    schema 里没有（`ridgeAxis` 同样不存在）—— 这条用例当时就会红，是"白名单 ⊆
    引擎字段闭集"这条不变量的守卫。
    """

    missing: list[str] = []
    for component_type, keys in sorted(_INSTANCE_FORM_FIELDS.items()):
        for key in sorted(keys):
            route, target = _INSTANCE_FORM_ROUTES.get(key, ("field", key))
            if route == "interaction_fn":
                continue  # `mode` 由 `_apply_opening_form` 收口，不走字段落点
            container = "interaction" if route == "interaction" else None
            if _form_target_schema(component_type, container or target) is None:
                missing.append(f"{component_type}.{key} -> {container or target}")

    assert not missing, f"形态键落不到引擎字段上（静默失效）：{missing}"


def test_form_key_absent_from_engine_schema_is_recorded_as_unverified(monkeypatch):
    """落点不在引擎闭集里时：**照旧落下**（不阻断），但必须留证据。

    白名单已收干净，所以只能**造**一次漂移：把落点 schema 缓存强制置空。
    这条钉的是"证据通道"存在，而不是"某个键应该存在"。
    """

    monkeypatch.setitem(_FORM_TARGET_SCHEMA_CACHE, ("roof", "roofType"), None)

    plan = {
        "massing": {"shape": "rectangular", "width": 12, "depth": 10, "floors": 2},
        "components": [{
            "type": "roof",
            "host": "volume_primary",
            "form": {"roofType": "gable"},
        }],
    }

    normalized = normalize_architecture_plan(plan, "坡屋顶")
    result = compile_design(normalized, user_message="坡屋顶")

    assert result.ok, "静默失效不是错误，不许阻断"
    assert result.summary()["instance_form_unverified"] == ["roof.roofType"]
    overrides = result.stats["instance_overrides"]
    assert overrides["form_applied"]["roof"] == ["roofType"], "认得的值照旧落下"
    assert overrides["form_rejections"] == {}, "闭集外 ≠ 值不合格，两者必须分开记"
