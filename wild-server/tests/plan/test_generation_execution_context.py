"""执行条目必须将真实宿主传入组件校验，不能仅携带模型可读摘要。"""

import asyncio
from copy import deepcopy
from unittest.mock import patch

import pytest

from app.agent.plan.contracts import PlanItem
from app.agent.plan.handlers import run_generate
from app.agent.generation.component_processing import validate_and_fix_with_tools


@pytest.mark.parametrize("count", [1, 15, 38])
def test_generate_validates_openings_against_actual_skeleton(count):
    wall = {"id": "host", "type": "wall", "from": [0, 0, 0], "to": [count * 2 + 1, 3, 0], "thickness": 0.24}
    skeleton = {"geometry": {"elements": [wall], "components": []}, "materials": {}}
    windows = [{"id": f"w{i}", "type": "window", "parentWall": "host", "from": [i * 2 + 0.3, 1, 0],
                "width": 1.2, "height": 1.2} for i in range(count)]

    async def generator(context):
        return {"component_fragments": {"window": windows}, "component_diagnostics": {}}

    original = deepcopy(skeleton)
    item = PlanItem(id="generate_window_01", op="generate", kind="window")
    with patch("app.agent.plan.handlers._generator_for", return_value=generator):
        updates, status, _, _, _ = asyncio.run(run_generate({"skeleton_blueprint": skeleton}, item))
    assert status == "succeeded"
    assert len(updates["component_fragments"]["window"]) == count
    assert updates["component_diagnostics"]["window_val"]["validation_passed"] is True
    assert skeleton == original


def test_failed_validation_keeps_specific_evidence_and_original_input():
    fragments = [{"id": "w", "type": "window", "parentWall": "missing", "from": [0, 1, 0], "width": 1, "height": 1}]
    original = deepcopy(fragments)
    details = {}
    _, _, passed = validate_and_fix_with_tools(fragments, "window", {}, False, diagnostics=details)
    assert passed is False
    assert "missing" in details["initial"]
    assert "missing" in details["recheck"]
    assert fragments == original
