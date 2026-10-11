"""图纸显式实例的尺寸、位置、宿主与依赖回归；不调用模型。"""
from copy import deepcopy

import pytest

from app.agent.compiler.compile import _compile_from_instances
from app.agent.generation.architecture import normalize_architecture_plan
from app.design.compilation import compile_document
from app.design.markers import component_markers
from app.design.relations import evaluate_support
from app.design.resolver import build_design_document


def scene(dx=0, dz=0, level=2):
    walls = [
        {"type": "wall", "id": "front", "from": [dx, 0, dz], "to": [dx+12, 3, dz], "thickness": .24},
        {"type": "wall", "id": "back", "from": [dx+12, 0, dz+8], "to": [dx, 3, dz+8], "thickness": .24},
        {"type": "wall", "id": "upper", "from": [dx, (level-1)*3, dz], "to": [dx+12, level*3, dz], "thickness": .24},
    ]
    components = [
        {"type": "door", "id": "entrance", "parentWall": "front", "from": [4, 0, 0], "width": 1.2, "height": 2.1},
        {"type": "balcony", "id": "derived_balcony", "parentWall": "upper", "from": [4, (level-1)*3, 0],
         "width": 3.1, "depth": 1.2, "slabThickness": .15, "railingHeight": 1.05, "postSpacing": 1,
         "material": "metal", "railingMaterial": "metal"},
        {"type": "light", "id": "light_1", "position": [dx+4.6, 1.8, dz-.35], "fixtureType": "bulb"},
        {"type": "light", "id": "light_2", "position": [dx+6, 1.8, dz+8.35], "fixtureType": "bulb"},
    ]
    blueprint = {"geometry": {"elements": walls, "components": components}, "materials": {"metal": {}, "roof": {}}}
    return blueprint, {"light_hosts": {"light_1": "front", "light_2": "back"}}


def compile_instances(instances, blueprint=None, brief=None):
    default_blueprint, default_brief = scene()
    return _compile_from_instances(instances, blueprint or default_blueprint,
                                   (blueprint or default_blueprint)["materials"], {},
                                   brief if brief is not None else default_brief)


@pytest.mark.parametrize("hosts", [("front", "back"), ("back", "front"), ("column_left", "column_right")])
def test_lights_do_not_reuse_first_template(hosts):
    blueprint, brief = scene()
    # 现场柱挂灯不支持，但不得再被错误归因为两个实例都占了第一个模板。
    if hosts[0].startswith("column"):
        brief["light_hosts"] = {}
    instances = [{"id": f"lamp_{i}", "type": "light", "host": host} for i, host in enumerate(hosts)]
    components, replaced, stats = compile_instances(instances, blueprint, brief)
    assert len(replaced) == 2 and replaced[0] is not replaced[1]
    assert components[0]["position"] != components[1]["position"]
    assert bool(stats["host_fallback"]) == hosts[0].startswith("column")


@pytest.mark.parametrize("dx,dz", [(0, 0), (17, -9)])
def test_two_wall_lights_keep_distinct_explicit_positions(dx, dz):
    blueprint, brief = scene(dx, dz)
    instances = [{"id": f"lamp_{offset}", "type": "light", "host": "front",
                  "placement": {"offset": offset, "sill_height": 2.5}} for offset in (3, 7)]
    components, replaced, stats = compile_instances(instances, blueprint, brief)
    assert len(replaced) == 1
    assert [c["position"] for c in components] == [[dx+3, 2.5, dz-.47], [dx+7, 2.5, dz-.47]]
    assert not stats["host_fallback"]
    assert all("from" not in c and "parentWall" not in c for c in components)


def test_actual_duplicate_light_position_is_still_rejected():
    instances = [{"id": name, "type": "light", "host": "front",
                  "placement": {"offset": 3, "sill_height": 2.5}} for name in ("left", "right")]
    with pytest.raises(ValueError, match="同一设计位置"):
        compile_instances(instances)


@pytest.mark.parametrize("placement", [{"offset": 13, "sill_height": 2}, {"offset": 3, "sill_height": 4}])
def test_wall_light_outside_its_declared_host_is_rejected(placement):
    with pytest.raises(ValueError, match="超出宿主墙范围"):
        compile_instances([{"id": "lamp", "type": "light", "host": "front", "placement": placement}])


def test_balcony_railing_switch_matches_both_schemas_and_rejects_non_boolean():
    import json
    from pathlib import Path
    import jsonschema
    from app.utils.blueprint_normalizer import get_schema
    schema = get_schema()
    frontend = json.loads((Path(__file__).parents[3] / "wild-core/schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["balconyComponent"] == frontend["$defs"]["balconyComponent"]
    validator = jsonschema.Draft202012Validator({"$ref": "#/$defs/balconyComponent", "$defs": schema["$defs"]})
    balcony = scene()[0]["geometry"]["components"][1]
    for flag in (True, False):
        assert not list(validator.iter_errors({**balcony, "railingEnabled": flag}))
    assert list(validator.iter_errors({**balcony, "railingEnabled": 0}))
    from app.agent.validation.design_constraints import design_quota_shortfalls
    assert design_quota_shortfalls({"geometry": {"components": [{**balcony, "railingEnabled": False}]}},
                                   {"component_quota": {"railing": {"min": 1}}}) == ["railing 数量 0 少于设计下限 1"]


@pytest.mark.parametrize("dx,dz,level", [(0, 0, 2), (17, -9, 3)])
def test_balcony_size_and_dependent_railing_follow_actual_geometry(dx, dz, level):
    blueprint, brief = scene(dx, dz, level)
    instances = [
        {"id": "guard", "type": "railing", "host": "terrace", "size": {"height": 1.1}},
        {"id": "terrace", "type": "balcony", "host": "upper", "size": {"width": 3, "depth": 1.5, "height": .3},
         "placement": {"offset": 6, "sill_height": 0}},
    ]
    components, _, stats = compile_instances(instances, blueprint, brief)
    balcony, railing = components
    y = (level-1)*3
    assert balcony["width"] == 3 and balcony["slabThickness"] == .3
    assert balcony["railingEnabled"] is False
    assert railing["height"] == 1.1
    assert railing["path"] == [[dx+6, y, dz-.12], [dx+6, y, dz-1.62],
                                [dx+9, y, dz-1.62], [dx+9, y, dz-.12]]
    assert not stats["dropped"] and not stats["size_changes"]
    assert [e["entity_id"] for e in stats["instance_entities"]] == ["guard", "terrace"]
    from app.agent.generation.assembly.merge import deduplicate_balcony_representations
    context = {**blueprint, "geometry": {**blueprint["geometry"], "components": components}}
    railing["id"] = "balcony_guard"
    assert deduplicate_balcony_representations(context)["removed_railing_count"] == 0
    assert railing in context["geometry"]["components"]


@pytest.mark.parametrize("dx,dz", [(0, 0), (17, -9)])
def test_canopy_position_thickness_and_column_radii_are_realized(dx, dz):
    blueprint, brief = scene(dx, dz)
    instances = [
        {"id": "support", "type": "column", "host": "front",
         "relation": {"kind": "supports", "target": "cover", "along_ratio": 0, "depth_ratio": .5},
         "size": {"bottomRadius": .15, "topRadius": .12, "height": 2.7}},
        {"id": "cover", "type": "canopy", "host": "entrance",
         "size": {"width": 2.4, "depth": 1.8, "height": .2},
         "placement": {"offset": 6.3, "sill_height": 2.8}},
    ]
    components, _, stats = compile_instances(instances, blueprint, brief)
    canopy, column = components
    assert canopy["from"] == [6.3, 2.8, 0] and canopy["thickness"] == .2
    assert column["base"] == [dx+6.3, 0, dz-1.02]
    assert column["height"] == 2.7 and column["bottomRadius"] == .15 and column["topRadius"] == .12
    context = {**blueprint, "geometry": {**blueprint["geometry"], "components": components}}
    assert evaluate_support(context, "support", instances[0]["relation"])["status"] == "satisfied"
    assert not stats["size_changes"]
    instances[0]["size"]["height"] = 3
    with pytest.raises(ValueError, match="显式柱高.*冲突"):
        compile_instances(instances, blueprint, deepcopy(brief))






