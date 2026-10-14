from copy import deepcopy

import pytest

from app.design.contracts import FloorConnection
from app.design.coordinates import design_relation_checks, floor_connection_targets, stair_span_conflicts


def design():
    return {"massing": {"floors": 3, "floor_height": 3, "representation_mode": "full"},
            "floor_layouts": [{"floor": i, "level": y} for i, y in ((1, 0.45), (2, 3.45), (3, 7.15))],
            "volumes": [{"id": "main"}], "circulation": {"vertical_strategy": "stair"}}


def marker(connections):
    return {"id": "stairs", "type": "stair", "host": "main", "design_path": "/decisions/components/0",
            "design": {"floor_connections": connections}}


def test_partial_stair_uses_its_declared_nonuniform_floor_span():
    raw = design()
    component = {"type": "stair", "size": {"height": 3.7},
                 "floor_connections": [{"from_floor": 2, "to_floor": 3}]}
    targets, issues = floor_connection_targets(raw, component)
    assert not issues and targets[0]["from_y"] == 3.45
    assert targets[0]["to_y"] == 7.15 and targets[0]["rise"] == pytest.approx(3.7)
    raw["components"] = [component]
    assert stair_span_conflicts(raw) == []


def test_roof_access_is_explicit_and_bad_floor_reference_is_structured():
    targets, issues = floor_connection_targets(design(), {"floor_connections": [{"from_floor": 3, "to_floor": "roof"}]})
    assert targets[0]["to_y"] == pytest.approx(10.15) and not issues
    _, issues = floor_connection_targets(design(), {"floor_connections": [{"from_floor": 3, "to_floor": 4}]})
    assert issues[0]["code"] == "floor_connection_reference"
    with pytest.raises(ValueError):
        FloorConnection.model_validate({"from_floor": 1, "to_floor": 0})


def test_explicit_stair_only_strategy_cannot_omit_a_floor():
    stairs = marker([{"from_floor": 1, "to_floor": 2}])
    errors, reviews = design_relation_checks(design(), [stairs], {})
    assert errors[0]["code"] == "stair_floor_unreachable"
    assert errors[0]["actual"] == {"unreachable_floors": [3]}
    assert not reviews


def test_unspecified_connections_and_alternative_transport_remain_for_review():
    raw = design()
    errors, reviews = design_relation_checks(raw, [marker([])], {})
    assert not errors and reviews[0]["marker_id"] == "stairs"
    raw["circulation"]["vertical_strategy"] = "elevator_and_stair"
    errors, reviews = design_relation_checks(raw, [marker([{"from_floor": 1, "to_floor": 2}])], {})
    assert not errors and reviews[0]["code"] == "stair_floor_unreachable"


def test_unknown_form_is_allowed_but_an_undeclared_host_is_reported():
    raw = design()
    component = {"id": "new_shape", "type": "unregistered_shape", "host": "main",
                 "design_path": "/decisions/components/0", "design": {"form": {"shape": "new"}}}
    assert design_relation_checks(raw, [component], {}) == ([], [])
    broken = deepcopy(component)
    broken["host"] = "typo_host"
    errors, _ = design_relation_checks(raw, [broken], {})
    assert errors[0]["path"] == "/decisions/components/0/host"
    assert errors[0]["actual"] == "typo_host"
