"""设计表达协议回归；不导入图运行时，也不依赖模型服务。"""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.design.contracts import DesignConstraint, FacadeDecision
from app.design.coordinates import volume_conflicts


@pytest.mark.parametrize("adoption", ["adopted", "proposed", "superseded"])
def test_adoption_status_keeps_its_distinct_protocol_value(adoption):
    value = DesignConstraint(id="choice", kind="preference", target="/decisions/massing",
                             expression="体量选择", adoption=adoption)
    assert value.adoption == adoption


def test_translated_adoption_is_rejected_instead_of_becoming_adopted():
    with pytest.raises(ValidationError, match="adoption"):
        DesignConstraint(id="choice", kind="preference", target="/decisions/massing",
                         expression="体量选择", adoption="已采纳")


@pytest.mark.parametrize("pattern", [[{"door": "swing"}, "window"]])
def test_invalid_facade_expression_is_rejected_without_changing_the_design(pattern):
    original = deepcopy(pattern)
    with pytest.raises(ValidationError):
        FacadeDecision(bays=2, ground_pattern=pattern, upper_pattern=["window", "empty"])
    assert pattern == original


@pytest.mark.parametrize("pattern", [["door:swing", "window:fixed"], ["open", "open"], ["open", "window"], ["open", "empty"], ["empty", "empty"]])
def test_explicit_opening_expression_is_preserved(pattern):
    facade = FacadeDecision(bays=2, ground_pattern=pattern, upper_pattern=["window", "empty"])
    assert facade.ground_pattern == pattern


@pytest.mark.parametrize("offset", [(0, 0), (-30, -40), (70, 90)])
def test_logged_three_volumes_conflict_is_translation_invariant_and_not_silently_fixed(offset):
    volumes = [{"id": name, "x": x + offset[0], "z": z + offset[1], "width": 8, "depth": 10,
                "end_floor": 2}
               for name, x, z in (("main", 0, 0), ("east_wing", 0, 10), ("west_wing", 8, 0))]
    original = deepcopy(volumes)
    conflicts = volume_conflicts(volumes, {"width": 15, "depth": 12, "modeled_floors": 2})
    assert [(c["conflict_path"], c["actual_extent"]) for c in conflicts] == [
        ("/decisions/massing/width", 16), ("/decisions/massing/depth", 20),
    ]
    assert volume_conflicts(volumes, {"width": 16, "depth": 20, "modeled_floors": 2}) == []
    assert volumes == original
