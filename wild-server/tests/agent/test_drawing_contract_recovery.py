"""真实失败输出的契约回归；模型和检索使用替身，不验证建筑渲染。"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.generation.architecture import normalize_architecture_plan
from app.agent.generation.architecture.design_workflow import draft_design


ATTEMPTS = json.loads((Path(__file__).parents[1] / "fixtures" /
                       "architecture_drawing_rejected_outputs.json").read_text(encoding="utf-8"))














@pytest.mark.parametrize("component_type,count", [("balcony", 1), ("canopy", 2), ("cornice", 3)])
def test_optional_counts_are_derived_without_deleting_explicit_markers(component_type, count):
    raw = normalize_architecture_plan({"massing": {"floors": 2}}, user_message="建筑")
    raw.pop("component_quota")
    raw.pop("required_components")
    raw["components"] = [{"id": f"part_{i}", "type": component_type, "host": "main_L2_front"}
                         for i in range(count)]
    changes = []
    result = normalize_architecture_plan(raw, normalization_changes=changes, input_source="model")
    assert result["components"] == raw["components"]
    assert result["component_quota"][component_type]["min"] == count
    assert result["component_quota"][component_type]["max"] == count
    assert component_type in result["required_components"]
    assert not [c for c in changes if c["semantic_change"] and "component_quota" in c["path"]]


@pytest.mark.parametrize("quota", [1, None, [], {"balcony": 1}, {"canopy": 1}, {"cornice": 1}])
def test_legacy_invalid_quota_has_actionable_error_instead_of_silent_drop(quota):
    with pytest.raises(ValueError, match="component_quota.*对象"):
        normalize_architecture_plan({"component_quota": quota})


def test_derived_balcony_count_preserves_explicit_user_access_requirement():
    plan = normalize_architecture_plan({"massing": {"floors": 2}, "components": [
        {"id": "balcony_a", "type": "balcony", "host": "main_L2_front"}]},
        user_message="两个阳台直接通向室内")
    assert plan["balcony_access_count"] == 2
    assert plan["component_quota"]["balcony"]["min"] == 2
