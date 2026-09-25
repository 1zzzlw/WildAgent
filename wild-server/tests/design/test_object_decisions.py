"""物件场景的设计契约与解析。

核心断言只有一句：**物件场景在结构上产不出房子**。
所以这里既查正例（物件文档能建、能解析、能回编译成生成侧方案），
也查反例（往物件文档里塞 massing/volumes 必须被拒）。
"""

import pytest
from pydantic import ValidationError

from app.design.contracts import DesignDocument
from app.design.repository import DesignRepository
from app.design.resolver import (
    architecture_plan_from_document,
    build_design_document,
    render_design_svg,
    resolve_design,
)


def object_plan(**overrides) -> dict:
    plan = {
        "target_kind": "object",
        "concept": "胡桃木长餐桌单件场景",
        "objects": [
            {
                "kind": "furniture",
                "subtype": "table",
                "count": 1,
                "width": 1.8,
                "depth": 0.9,
                "height": 0.75,
                "placement": "居中，桌腿落地",
                "material": "walnut",
                "rationale": "用户点名要一张餐桌",
            },
            {
                "kind": "furniture",
                "subtype": "chair",
                "count": 4,
                "width": 0.45,
                "depth": 0.5,
                "height": 0.9,
                "placement": "沿长边两侧两两相对，面向桌面",
                "material": "walnut",
                "rationale": "与餐桌配套",
            },
        ],
        "design_rationale": ["只交付家具，不引入墙体与屋顶"],
    }
    plan.update(overrides)
    return plan


def make_document(**overrides) -> DesignDocument:
    return build_design_document(
        object_plan(**overrides),
        session_id="session_object_test",
        source_request="生成一张餐桌配四把椅子",
    )


def test_object_plan_produces_object_decisions_instead_of_massing():
    document = make_document()

    assert document.decisions.kind == "object"
    assert document.decisions.concept.startswith("胡桃木")
    assert [item.subtype for item in document.decisions.objects] == ["table", "chair"]
    # 建筑支路的字段一个都不能出现——这是"结构上产不出房子"的判据。
    assert not hasattr(document.decisions, "massing")
    assert not hasattr(document.decisions, "volumes")
    assert not hasattr(document.decisions, "facades")


def test_resolution_has_no_levels_volumes_or_facade_slots():
    resolved = resolve_design(make_document())

    assert resolved.levels == []
    assert resolved.volumes == []
    assert resolved.facade_slots == []
    assert resolved.component_quantities == {"furniture": 5}
    # 外廓是审核图的取景估算（沿 X 排开、间距 0.3m），不是真实摆位。
    assert resolved.bounds["width"] == pytest.approx(1.8 + 0.3 + 0.45)
    assert resolved.bounds["depth"] == pytest.approx(0.9)
    assert resolved.bounds["height"] == pytest.approx(0.9)


def test_review_svg_is_an_object_sheet_not_a_floor_plan():
    svg = render_design_svg(make_document())

    assert svg.startswith("<svg")
    # 物件审图不能出现建筑支路的分面/体量锚点。
    assert 'data-design-path="/decisions/facades/front"' not in svg
    assert "/decisions/volumes/0" not in svg


def test_object_document_round_trips_into_generation_plan():
    plan = architecture_plan_from_document(make_document())

    assert plan["target_kind"] == "object"
    assert plan["required_components"] == ["furniture"]
    # 配额是折总量：桌椅同属 furniture，所以 min=max=1+4。
    assert plan["component_quota"]["furniture"] == {
        "min": 5,
        "max": 5,
        "note": "居中，桌腿落地",
    }
    # 逐件规格必须原样留在方案里——生成节点靠它拿回"1.8 米"这类逐件信息，
    # 配额里的 note 只有一行，承载不了两件家具各自的尺寸与摆位。
    assert [item["subtype"] for item in plan["objects"]] == ["table", "chair"]
    assert [item["width"] for item in plan["objects"]] == [1.8, 0.45]
    assert "massing" not in plan


def test_parts_decomposed_object_keeps_no_element_upper_bound():
    """通用几何通道：`count` 是物件数，元素数由零件数决定 ⇒ 配额不能设上限。

    回归背景：配额曾被无条件写成 `max = count`，而 `assembly.enforce_element_quota`
    拿它去钳**元素**数 ⇒ "一个花瓶 = 4 个零件"被读成"4 个花瓶、超过上限 1"，
    收尾归一在 `_finalize_merge` 里把花瓶削成一块底座圆盘（0.16 × 0.04 × 0.16 m），
    而 `design_constraints` 随后仍然判通过 —— 只剩一块底座，没有任何地方会报。

    同一份配额被两个消费点当"元素数"用，所以单位必须在**这里**对齐：
    能分解成零件的物件只留下限（每件至少落地一块几何），不设上限。
    """

    objects = [
        {
            "kind": "primitive", "name": "花瓶", "count": 1,
            "width": 0.16, "depth": 0.16, "height": 0.4,
            "parts": [
                {"shape": "cylinder"}, {"shape": "cylinder"},
                {"shape": "sphere"}, {"shape": "box"},
            ],
        },
        {
            "kind": "furniture", "subtype": "table", "name": "餐桌", "count": 2,
            "width": 1.4, "depth": 0.8, "height": 0.75,
        },
        {
            "kind": "body", "name": "小人", "count": 1,
            "width": 0.5, "depth": 0.3, "height": 1.72,
        },
    ]
    plan = architecture_plan_from_document(make_document(objects=objects))
    quota = plan["component_quota"]

    # 缺 `max` 键 = 不设上限（两个消费点都走 `.get("max")`）。
    assert quota["primitive"] == {"min": 1, "note": ""}
    # 一个物件 = 一个元素的通道照旧收紧上限，别把这条修复扩大化。
    assert quota["furniture"]["max"] == 2
    assert quota["body"]["max"] == 1

    # 直接锁住失败模式：4 个零件必须一个都不被削掉。
    from loguru import logger

    from app.agent.generation.assembly import enforce_element_quota

    elements = [{"type": "primitive", "id": f"primitive_{index:02d}"} for index in range(4)]
    kept, pruned = enforce_element_quota(elements, quota, logger)

    assert pruned == 0
    assert len(kept) == 4


def test_repository_saves_object_document(tmp_path):
    repository = DesignRepository(tmp_path)
    saved, _ = repository.save(make_document())

    assert saved.status == "draft"
    assert saved.revision == 1


def test_object_document_rejects_building_fields():
    data = make_document().model_dump(mode="json")
    # 带标签联合按 kind 解析，物件支路没有 massing 字段，塞进去必须被拒。
    data["decisions"]["massing"] = {"width": 20, "depth": 12}

    with pytest.raises(ValidationError):
        DesignDocument.model_validate(data)


def test_empty_object_list_is_rejected():
    data = make_document().model_dump(mode="json")
    data["decisions"]["objects"] = []

    with pytest.raises(ValidationError):
        DesignDocument.model_validate(data)


def test_architecture_document_still_parses_without_kind_field():
    """2026-09-23 之前存档的文档没有 `kind`，必须仍解析成建筑支路。"""

    legacy = {
        "schema_version": "design/1.0",
        "design_id": "design_legacy",
        "session_id": "session_legacy",
        "revision": 1,
        "status": "draft",
        "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-09-01T00:00:00Z",
        "approved_at": None,
        "requirements": {
            "source_request": "生成一栋两层别墅",
            "building_type": "villa",
            "profile": "residential_lowrise",
            "style_intent": [],
        },
        "decisions": {
            "concept": "两层坡屋顶别墅",
            "massing": {
                "shape": "rectangle",
                "width": 12,
                "depth": 9,
                "floors": 2,
                "modeled_floors": 2,
                "representation_mode": "full",
                "floor_height": 3,
                "symmetry": True,
            },
            "complexity": {
                "level": "simple",
                "min_volumes": 1,
                "min_detail_packages": 0,
                "target_structural_elements": 8,
                "grid_bays": [2, 2],
                "reason": "住宅",
            },
            "volumes": [
                {
                    "id": "main",
                    "role": "primary",
                    "x": 0,
                    "z": 0,
                    "width": 12,
                    "depth": 9,
                    "start_floor": 1,
                    "end_floor": 2,
                }
            ],
            "structural_grid": {"system": "wall_bearing", "x_bays": 2, "z_bays": 2},
            "envelope": {"system": "solid_wall", "curtain_wall": None},
            "facades": {
                "front": {
                    "bays": 2,
                    "entrance_bay": 1,
                    "ground_pattern": ["door", "window"],
                    "upper_pattern": ["window", "window"],
                },
                "back": {
                    "bays": 2,
                    "ground_pattern": ["window", "window"],
                    "upper_pattern": ["window", "window"],
                },
                "left": {
                    "bays": 2,
                    "ground_pattern": ["window", "window"],
                    "upper_pattern": ["window", "window"],
                },
                "right": {
                    "bays": 2,
                    "ground_pattern": ["window", "window"],
                    "upper_pattern": ["window", "window"],
                },
            },
            "roof": {"type": "gable", "ridge_axis": "x", "overhang": 0.5},
            "circulation": {"vertical_strategy": "stair"},
            "materials": {"keywords": [], "resolved_plan": None},
            "detail_packages": [],
            "component_quota": {},
            "balcony_access_count": 0,
            "balcony_width": None,
            "required_components": [],
            "unsupported_component_types": [],
            "design_rationale": [],
        },
        "constraints": [],
        "locks": [],
        "rule_trace": [],
    }

    document = DesignDocument.model_validate(legacy)

    assert document.decisions.kind == "architecture"
    assert document.decisions.massing.floors == 2
