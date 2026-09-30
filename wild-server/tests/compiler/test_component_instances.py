"""测试§3.4构件实例清单的编译。"""

from app.agent.compiler import compile_design
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
