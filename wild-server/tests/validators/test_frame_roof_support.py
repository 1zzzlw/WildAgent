"""柱梁屋面的承托与实体台基应使用同一套实际几何事实。"""
from copy import deepcopy

import pytest

from app.tools.spatial_tools import get_roof_support_bounds, validate_roof_coverage


def frame_roof(offset=(0, 0), scale=1):
    x, z = offset
    point = lambda a, y, b: [x+a*scale, y*scale, z+b*scale]
    columns = [{"id": f"column_{i}", "type": "column", "base": point(a, 0.5, b),
                "height": 3*scale, "bottomRadius": 0.125*scale, "topRadius": 0.125*scale}
               for i, (a, b) in enumerate(((0.75, 0.75), (4.25, 0.75), (4.25, 4.25), (0.75, 4.25)))]
    beams = [{"id": f"beam_{i}", "type": "beam", "from": point(a, 3.65, b),
              "to": point(c, 3.65, d), "crossSection": "rect", "width": 0.2*scale, "height": 0.3*scale}
             for i, (a, b, c, d) in enumerate(((0.75, 0.75, 4.25, 0.75),
                 (4.25, 0.75, 4.25, 4.25), (4.25, 4.25, 0.75, 4.25), (0.75, 4.25, 0.75, 0.75)))]
    platform = {"id": "platform", "type": "primitive", "shape": "box", "position": point(2.5, 0.25, 2.5),
                "dimensions": [6*scale, 0.5*scale, 6*scale]}
    floor = {"id": "floor", "type": "floor", "from": point(0.75, 0.4, 0.75),
             "to": point(4.25, 0.4, 4.25), "thickness": 0.1*scale}
    roof = {"id": "cover", "type": "roof", "roofType": "hip", "span": 6.6*scale,
            "depth": 6.6*scale, "height": 1.85*scale, "thickness": 0.12*scale,
            "position": point(2.5, 3.8, 2.5)}
    return {"geometry": {"elements": [*columns, *beams, platform, floor, roof], "components": []}}


@pytest.mark.parametrize("offset", [(0, 0), (-12, 21)])
@pytest.mark.parametrize("scale", [0.75, 1, 1.4])
def test_roof_on_beams_above_columns_and_solid_platform_is_not_floating(offset, scale):
    blueprint = frame_roof(offset, scale)
    original = deepcopy(blueprint)
    assert "❌" not in validate_roof_coverage.func(blueprint)
    elements = blueprint["geometry"]["elements"]
    roof = elements[-1]
    bounds = get_roof_support_bounds([], roof,
        columns=[e for e in elements if e["type"] == "column"],
        beams=[e for e in elements if e["type"] == "beam"])
    assert bounds["support_y"] == pytest.approx(3.8*scale)
    assert bounds["support_kind"] == "beam"
    assert blueprint == original


@pytest.mark.parametrize("defect", ["missing_beams", "raised_roof", "distant_platform"])
def test_real_support_or_coverage_defects_are_still_rejected(defect):
    blueprint = frame_roof()
    elements = blueprint["geometry"]["elements"]
    if defect == "missing_beams":
        elements[:] = [e for e in elements if e["type"] != "beam"]
    elif defect == "raised_roof":
        elements[-1]["position"][1] += 0.5
    else:
        next(e for e in elements if e["id"] == "platform")["position"][0] += 20
    assert "❌" in validate_roof_coverage.func(blueprint)


@pytest.mark.parametrize("offset", [0, -17])
@pytest.mark.parametrize("reverse", [False, True])
def test_beam_overlap_uses_the_actual_3d_axis(offset, reverse):
    from app.tools.spatial_tools import validate_collision

    def beam(name, start, end):
        return {"id": name, "type": "beam", "from": [v+offset for v in start],
                "to": [v+offset for v in end], "width": 0.16, "height": 0.16, "crossSection": "rect"}
    first = beam("eave", [0, 3, 0], [4, 3, 0])
    diagonal = beam("rafter", [0, 3, 0], [2, 4.4, 2])
    if reverse:
        diagonal["from"], diagonal["to"] = diagonal["to"], diagonal["from"]
    blueprint = {"geometry": {"elements": [first, diagonal], "components": []}}
    assert "同轴重叠" not in validate_collision.func(blueprint)
    duplicate = beam("overlap", [1, 3, 0], [3, 3, 0])
    if reverse:
        duplicate["from"], duplicate["to"] = duplicate["to"], duplicate["from"]
    blueprint["geometry"]["elements"] = [first, duplicate]
    assert "同轴重叠" in validate_collision.func(blueprint)
    blueprint["geometry"]["elements"] = [diagonal, {**diagonal, "id": "diagonal_duplicate"}]
    assert "同轴重叠" in validate_collision.func(blueprint)


@pytest.mark.parametrize("offset", [0, -17])
@pytest.mark.parametrize("depth", [4.8, 6.8])
@pytest.mark.parametrize("reverse", [False, True])
def test_hip_roof_checks_beam_section_instead_of_only_its_centerline(offset, depth, reverse):
    from app.tools.spatial_tools import _hip_roof_beam_penetrations

    roof = {"id": "cover", "type": "roof", "roofType": "hip", "position": [offset, 3.04, offset],
            "span": 4.8, "depth": depth, "height": 1.4, "thickness": 0.12}
    beam = {"id": "member", "type": "beam", "crossSection": "rect", "width": 0.16, "height": 0.16,
            "from": [offset-1.8, 3.04, offset-1.8], "to": [offset-0.2, 4.28, offset-0.2]}
    if reverse:
        beam["from"], beam["to"] = beam["to"], beam["from"]
    before = deepcopy([roof, beam])
    assert "截面穿出" in _hip_roof_beam_penetrations([roof, beam])[0]
    assert [roof, beam] == before
    for point in (beam["from"], beam["to"]):
        point[1] -= 0.12
    assert _hip_roof_beam_penetrations([roof, beam]) == []
    for point in (beam["from"], beam["to"]):
        point[1] += 3
    assert _hip_roof_beam_penetrations([roof, beam]) == []
