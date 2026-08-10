from app.agent.nodes.base_component_node import _validate_and_fix_with_tools


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
