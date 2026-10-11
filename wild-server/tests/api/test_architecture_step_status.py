"""执行真实节点完成分支，确保图纸失败不会记录成完整图纸成功。"""
import ast
from pathlib import Path

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("output,stage", [
    ({"status": "failed", "error": "建筑图纸未通过检查"}, "error"),
    ({"architecture_plan": {"massing": {"width": 12, "depth": 10, "floors": 2},
                            "roof": {"type": "gable"}}}, "done"),
])
async def test_architecture_completion_reports_actual_outcome(output, stage):
    path = Path(__file__).parents[2] / "app" / "api" / "ws_agent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and isinstance(node.test, ast.Compare)
                  and isinstance(node.test.left, ast.Name) and node.test.left.id == "node_name"
                  and any(isinstance(value, ast.Constant) and value.value == "architecture"
                          for value in node.test.comparators))
    function = ast.parse("async def complete():\n    pass\n").body[0]
    function.body = branch.body
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    steps, debug = [], []
    async def send_step(*args):
        steps.append(args)
    async def send_debug(_event, payload):
        debug.append(payload)
    context = {"node_output": output, "node_name": "architecture", "label": "建筑图纸",
               "diag": {"settled": stage == "done"}, "send_step": send_step, "send_debug": send_debug}
    exec(compile(module, str(path), "exec"), context)
    await context["complete"]()
    assert steps[0][2] == stage
    assert debug[0]["stage"] == stage
    assert ("完整图纸" in steps[0][4]) == (stage == "done")
    if stage == "error":
        assert output["error"] in steps[0][4]


@pytest.mark.asyncio
async def test_execute_completion_closes_each_item_step():
    path = Path(__file__).parents[2] / "app" / "api" / "ws_agent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and isinstance(node.test, ast.Compare)
                  and isinstance(node.test.left, ast.Name) and node.test.left.id == "node_name"
                  and any(isinstance(value, ast.Constant) and value.value == "execute"
                          for value in node.test.comparators))
    function = ast.parse("async def complete():\n    pass\n").body[0]
    function.body = branch.body
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    steps = []
    async def send_step(*args):
        steps.append(args)
    async def send_debug(*args):
        pass
    results = [{"item_id": "generate_1", "kind": "window", "label": "窗",
                "run_state": "succeeded", "evidence": "落实 2"},
               {"item_id": "generate_2", "kind": "roof", "label": "屋顶",
                "run_state": "failed", "evidence": "检查失败"}]
    context = {"node_output": {"execute_diag": {"item_results": results}},
               "node_name": "execute", "label": "执行计划条目", "send_step": send_step, "send_debug": send_debug}
    exec(compile(module, str(path), "exec"), context)
    await context["complete"]()
    assert steps[:2] == [("generating", "plan:generate_1", "done", "窗", "落实 2"),
                         ("generating", "plan:generate_2", "error", "屋顶", "检查失败")]
