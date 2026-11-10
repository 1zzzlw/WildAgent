"""粒度不自动开启思考；只有显式打开开关才启用。"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.agent.plan.contracts import PlanItem
from app.agent.plan.handlers import build_execution_context


@pytest.mark.parametrize("level", ["minimal", "simple", "standard", "detailed"])
@pytest.mark.parametrize("choice", [None, False, True])
def test_component_thinking_requires_explicit_choice(level, choice):
    state = {"detail_level": level}
    if choice is not None:
        state["thinking_mode"] = choice
    context = build_execution_context(state, PlanItem(id="generate_test", op="generate"))
    assert context["thinking_mode"] is (choice is True and level != "minimal")
