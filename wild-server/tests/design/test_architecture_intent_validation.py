"""2026-10-10：分项设计意图应保留内容，并统一为现有文本契约。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.design.contracts import ArchitectureIntent, DesignDocument
from app.design.resolver import architecture_plan_from_document, build_design_document


STRATEGIES = ("spatial_strategy", "composition", "material_strategy")
LOG_INTENTS = [
    {
        "spatial_strategy": {"access": "Primary entrance through north-facing courtyard with direct connection to living areas",
            "circulation": "Central open staircase connecting all levels with minimal corridors",
            "exterior": "Terraced garden sequence creating outdoor rooms at different elevations"},
        "composition": {"massing": "Single main volume with 15% setback creating a covered outdoor entry",
            "roof": "Sloped roof with 25° pitch extending 1.5m over living areas for shade",
            "facade": "Vertical wood slats (50mm spacing) regulating sun exposure and privacy"},
        "material_strategy": {"primary": "Weathered cedar cladding with vertical grain pattern",
            "secondary": "Limestone base course for durability and thermal mass",
            "layers": "Cedar → Insulation → Moisture barrier → Metal flashing"},
    },
    {
        "spatial_strategy": {"access": "北向庭院作为主要入口过渡区，设置双层挑空门厅衔接室内外空间",
            "circulation": "中央开放式楼梯串联各功能区，无走廊设计保证空间连续性",
            "exterior": "阶梯式露台系统形成不同高差的户外活动空间，与自然景观形成层次互动"},
        "composition": {"massing": "单一体量为主，西侧局部退台15%形成悬浮露台",
            "roof": "25°斜坡屋面，檐口延伸1.5m形成遮阳带",
            "facade": "垂直木格栅（50mm间距）与石材基座组合，实现光影调控与隐私保护"},
        "material_strategy": {"primary": "耐候木（Cedar）表层，呈现自然风化纹理",
            "secondary": "天然石材基座，提供基础稳定与热惰性",
            "layers": "木表层→XPS保温层→防水膜→金属屋面"},
    },
    {
        "spatial_strategy": {"access": "Primary entrance through a south-facing courtyard with direct connection to living areas",
            "circulation": "Central open staircase connecting all levels with minimal corridors",
            "exterior": "Terraced garden sequence creating outdoor rooms at different elevations"},
        "composition": {"massing": "Single main volume with 10% setback creating a covered outdoor entry",
            "roof": "Sloped roof with 25° pitch extending 1.5m over living areas for shade",
            "facade": "Vertical wood slats (50mm spacing) regulating sun exposure and privacy"},
        "material_strategy": {"primary": "Weathered cedar cladding with vertical grain pattern",
            "secondary": "Limestone base course for durability and thermal mass",
            "layers": ["Cedar → Insulation → Moisture barrier → Metal flashing"]},
    },
]


@pytest.mark.parametrize("raw", LOG_INTENTS)
def test_logged_strategies_survive_validation_and_review(raw):
    original = deepcopy(raw)
    intent = ArchitectureIntent.model_validate(raw)
    fixture = Path(__file__).parents[1] / "fixtures/design_trace_baseline.json"
    plan = json.loads(fixture.read_text(encoding="utf-8"))["normalized_plan"]
    plan["design_intent"] = raw
    document = build_design_document(plan, session_id="sectioned-intent", source_request="生成一个别墅")
    saved = DesignDocument.model_validate_json(document.model_dump_json())
    output = architecture_plan_from_document(saved)["design_intent"]
    for field in STRATEGIES:
        assert isinstance(getattr(intent, field), str)
        assert json.loads(output[field]) == raw[field]
    assert raw == original


@pytest.mark.parametrize("field", STRATEGIES)
def test_existing_text_is_not_rewritten(field):
    text = "入口组织：庭院过渡；交通组织：中央楼梯。\n材料保持原文。"
    assert getattr(ArchitectureIntent.model_validate({field: text}), field) == text


@pytest.mark.parametrize("field", STRATEGIES)
@pytest.mark.parametrize("value", [42, True, None, ["未声明为数组的策略"]])
def test_unrelated_invalid_types_are_still_rejected(field, value):
    with pytest.raises(ValidationError) as error:
        ArchitectureIntent.model_validate({field: value})
    assert error.value.errors()[0]["type"] == "string_type"


@pytest.mark.parametrize("field", STRATEGIES)
def test_sectioned_content_is_not_silently_truncated(field):
    with pytest.raises(ValidationError) as error:
        ArchitectureIntent.model_validate({field: {"description": "木" * 801}})
    assert error.value.errors()[0]["type"] == "string_too_long"


def test_public_schema_keeps_text_fields_and_rejects_unknown_keys():
    schema = ArchitectureIntent.model_json_schema()
    assert all(schema["properties"][field]["type"] == "string" for field in STRATEGIES)
    with pytest.raises(ValidationError):
        ArchitectureIntent.model_validate({"unrecognized_strategy": "不能绕过字段契约"})
