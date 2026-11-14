"""图纸完成后自动继续；真实图路由与 checkpoint，模型和几何阶段使用固定替身。"""
import asyncio
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.mark.parametrize("kind", ["architecture", "object"])
def test_generation_finishes_without_review_interrupt(monkeypatch, kind):
    from langgraph.checkpoint.memory import InMemorySaver
    from app.agent import graph as workflow

    async def classifier(_state):
        return {"intent": "generate", "intent_target_kind": kind}
    async def design(_state):
        return {"design_document": {"decisions": {"kind": kind}, "status": "draft"}}
    async def material(state):
        return {"design_document": {**state["design_document"], "status": "approved"}}
    async def skeleton(_state):
        return {"skeleton_blueprint": {"geometry": {"elements": [], "components": []}}}
    async def plan(_state):
        return {"plan": {"items": []}}
    async def compile_result(_state):
        return {"merged_blueprint": {"geometry": {"elements": []}}}
    async def validate(_state):
        return {"status": "complete"}
    for name, function in {"classifier_node": classifier, "architecture_planner": design,
        "object_planner": design, "material_planner": material, "skeleton_generator": skeleton,
        "plan_node": plan, "compile_node": compile_result, "validate_node": validate}.items():
        monkeypatch.setattr(workflow, name, function)

    async def run():
        graph = workflow.build_generation_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "auto-"+kind}}
        events = [event async for event in graph.astream({"user_message": "生成场景"}, config, stream_mode="updates")]
        nodes = [node for event in events for node in event]
        expected = ["classifier", "architecture" if kind == "architecture" else "object_design", "material_plan"]
        if kind == "object":
            expected.append("skeleton")
        expected.append("plan")
        if kind == "architecture":
            expected.append("compile")
        assert nodes == [*expected, "final_validate"]
        snapshot = await graph.aget_state(config)
        assert snapshot.next == ()
        assert snapshot.values["status"] == "complete"
    asyncio.run(run())


def test_design_version_mismatch_stops_without_clearing_fragments():
    from app.agent.plan.workflow import plan_node
    from test_surface_presets import architecture_document

    state = {"design_document": architecture_document().model_dump(mode="json"),
             "resolved_design": {"design_hash": "outdated"}, "component_fragments": {"kept": [{"id": "wall"}]}}
    result = asyncio.run(plan_node(state))
    assert result["status"] == "failed"
    assert "版本" in result["error"]
    assert "component_fragments" not in result
    assert state["component_fragments"]["kept"] == [{"id": "wall"}]
