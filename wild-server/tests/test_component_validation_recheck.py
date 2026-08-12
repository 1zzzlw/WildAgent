import asyncio

from app.agent.component_registry import COMPONENT_REGISTRY, ComponentConfig
from app.agent.nodes.base_component_node import (
    create_component_validator,
    _validate_and_fix_with_tools,
    _validate_fragments,
    _validation_has_error,
)


def _skeleton() -> dict:
    return {
        "meta": {"version": "1.1", "type": "building", "name": "recheck"},
        "geometry": {
            "elements": [
                {
                    "id": "wall_front",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [8, 3, 0],
                    "thickness": 0.24,
                }
            ],
            "components": [],
        },
        "materials": {},
    }


def test_component_fix_is_revalidated_and_passes() -> None:
    fragments = [{
        "id": "door_front",
        "type": "door",
        "parentWall": "wall_front",
        "from": [2, 0, 6],
        "width": 1,
        "height": 2.2,
    }]

    fixed_fragments, repair_applied, validation_passed = _validate_and_fix_with_tools(
        fragments,
        "door",
        _skeleton(),
        False,
    )

    assert repair_applied is True
    assert validation_passed is True
    assert fixed_fragments[0]["from"][2] == 0


def test_component_fix_does_not_claim_success_when_recheck_still_fails() -> None:
    fragments = [{
        "id": "oversized_door",
        "type": "door",
        "parentWall": "wall_front",
        "from": [1, 0, 0],
        "width": 20,
        "height": 2.2,
    }]

    _, repair_applied, validation_passed = _validate_and_fix_with_tools(
        fragments,
        "door",
        _skeleton(),
        False,
    )

    assert repair_applied is True
    assert validation_passed is False


def test_required_boolean_false_is_not_treated_as_missing() -> None:
    config = ComponentConfig(
        component_type="light",
        label="灯具",
        entity_type="light",
        required_fields=["type", "id", "position", "initiallyOn"],
    )
    fragment = {
        "type": "light",
        "id": "light_off",
        "position": [1, 2, 3],
        "initiallyOn": False,
    }

    assert _validate_fragments([fragment], config) == [fragment]


def test_structured_validation_result_is_supported() -> None:
    assert _validation_has_error({"has_error": True, "errors": ["bad"]}) is True
    assert _validation_has_error({"has_error": False, "errors": []}) is False


def test_ground_level_balcony_is_relocated_to_upper_wall() -> None:
    skeleton = _skeleton()
    skeleton["geometry"]["elements"].extend([
        {
            "id": "wall_upper_front",
            "type": "wall",
            "from": [0, 3.2, 0],
            "to": [8, 6.4, 0],
            "thickness": 0.24,
        },
        {
            "id": "wall_upper_back",
            "type": "wall",
            "from": [8, 3.2, 6],
            "to": [0, 6.4, 6],
            "thickness": 0.24,
        },
    ])
    fragments = [{
        "id": "balcony_ground",
        "type": "balcony",
        "parentWall": "wall_front",
        "from": [3, 0, 0],
        "width": 2.4,
        "depth": 1.2,
        "slabThickness": 0.18,
    }]

    fixed, repair_applied, validation_passed = _validate_and_fix_with_tools(
        fragments,
        "balcony",
        skeleton,
        False,
    )

    assert repair_applied is True
    assert validation_passed is True
    assert fixed[0]["parentWall"].startswith("wall_upper_")
    assert fixed[0]["from"][1] == 3.2


def test_horizontally_overflowing_balcony_is_relocated() -> None:
    skeleton = _skeleton()
    skeleton["geometry"]["elements"][0] = {
        "id": "wall_short",
        "type": "wall",
        "from": [0, 0, 0],
        "to": [1, 3.2, 0],
        "thickness": 0.24,
    }
    skeleton["geometry"]["elements"].append({
        "id": "wall_long",
        "type": "wall",
        "from": [0, 0, 6],
        "to": [8, 3.2, 6],
        "thickness": 0.24,
    })
    fragments = [{
        "id": "balcony_overflow",
        "type": "balcony",
        "parentWall": "wall_short",
        "from": [0, 1.8, 0],
        "width": 1.5,
        "depth": 1.2,
        "slabThickness": 0.18,
    }]

    fixed, repair_applied, validation_passed = _validate_and_fix_with_tools(
        fragments,
        "balcony",
        skeleton,
        False,
    )

    assert repair_applied is True
    assert validation_passed is True
    assert fixed[0]["parentWall"] == "wall_long"
    assert fixed[0]["from"][0] + fixed[0]["width"] <= 8


def test_two_full_width_balconies_use_distinct_upper_front_walls() -> None:
    skeleton = _skeleton()
    skeleton["geometry"]["elements"].extend([
        {
            "id": "wall_front_2_left", "type": "wall",
            "from": [0, 3.2, 0], "to": [1.5, 6.4, 0], "thickness": 0.24,
        },
        {
            "id": "wall_front_2_right", "type": "wall",
            "from": [3.5, 3.2, 0], "to": [5, 6.4, 0], "thickness": 0.24,
        },
    ])
    fragments = [
        {
            "id": f"balcony_{index}", "type": "balcony",
            "parentWall": "wall_front", "from": [0, 0, 0],
            "width": 1.5, "depth": 1.5, "slabThickness": 0.18,
        }
        for index in (1, 2)
    ]

    fixed, repair_applied, validation_passed = _validate_and_fix_with_tools(
        fragments, "balcony", skeleton, False,
    )

    assert repair_applied is True
    assert validation_passed is True
    assert {item["parentWall"] for item in fixed} == {
        "wall_front_2_left", "wall_front_2_right",
    }
    assert all(item["from"] == [0.0, 3.2, 0.0] for item in fixed)


def test_failed_component_recheck_is_not_forwarded_to_merge() -> None:
    validator = create_component_validator(COMPONENT_REGISTRY["door"])
    invalid = {
        "id": "oversized_door",
        "type": "door",
        "parentWall": "wall_front",
        "from": [1, 0, 0],
        "width": 20,
        "height": 2.2,
    }

    result = asyncio.run(validator({
        "skeleton_blueprint": _skeleton(),
        "component_fragments": {"door": [invalid]},
    }))

    assert result["door_fragments"] == []
    assert result["component_fragments"]["door"] == []
    assert result["door_val_diag"]["validation_passed"] is False
    assert result["door_val_diag"]["rejected_fragment_count"] == 1
