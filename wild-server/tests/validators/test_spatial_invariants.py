from app.agent.spatial_invariants import build_spatial_invariants
from app.tools.spatial_tools import compute_wall_bounding_box


def _blueprint() -> dict:
    return {
        "geometry": {
            "elements": [
                {"id": "wall_front", "type": "wall", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.24},
                {"id": "wall_right", "type": "wall", "from": [10, 0, 0], "to": [10, 3, 8], "thickness": 0.24},
                {"id": "floor_ground", "type": "floor", "from": [0, 0, 0], "to": [10, 0, 8]},
            ]
        }
    }


def test_wall_bounding_box_is_machine_readable() -> None:
    result = compute_wall_bounding_box(_blueprint())

    assert result == {
        "min": [0.0, 0.0, 0.0],
        "max": [10.0, 3.0, 8.0],
        "center": [5.0, 1.5, 4.0],
        "size": [10.0, 3.0, 8.0],
        "wall_count": 2,
    }


def test_spatial_invariants_preserve_wall_frames_and_floor_elevation() -> None:
    blueprint = _blueprint()
    result = build_spatial_invariants(blueprint, compute_wall_bounding_box(blueprint))

    assert result["coordinate_system"] == "Y-up, metres"
    assert result["walls"][0]["length_xz"] == 10.0
    assert result["walls"][0]["direction_xz"] == [1.0, 0.0, 0.0]
    assert result["walls"][0]["normal_xz"] == [-0.0, 0.0, 1.0]
    assert result["floors"] == [
        {
            "id": "floor_ground",
            "from": [0.0, 0.0, 0.0],
            "to": [10.0, 0.0, 8.0],
            "elevation": 0.0,
        }
    ]
