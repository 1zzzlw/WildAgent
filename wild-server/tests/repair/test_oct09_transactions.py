"""O3：失败候选不写回；上下文与正例提交保留完整场景。由用户运行。"""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.agent.repair import workflow
from app.agent.validation.diagnostics import VALIDATOR_VERSION, blueprint_fingerprint
from app.agent.plan.contracts import PlanItem
from app.agent.plan import handlers
from app.services.agent_service import agent_service


def state():
    blueprint = {"meta": {"version": "1.1", "type": "building"}, "geometry": {
        "elements": [{"type": "wall", "id": "wall", "from": [0, 0, 0], "to": [6, 3, 0], "thickness": 0.2}],
        "components": [
            {"type": "door", "id": "door", "parentWall": "wall", "from": [2, 0, 0], "width": 1, "height": 2.2},
            {"type": "canopy", "id": "canopy", "parentWall": "wall", "from": [1.8, 2.5, 0],
             "width": 1.4, "depth": 1, "thickness": 0.1} ]}, "materials": {}}
    return {"merged_blueprint": blueprint, "skeleton_blueprint": deepcopy(blueprint),
            "component_fragments": {"door": [deepcopy(blueprint["geometry"]["components"][0])]},
            "failed_components": [{"component_id": "door", "component_type": "door",
                                   "errors": ["overlap"], "current_params": deepcopy(blueprint["geometry"]["components"][0])}],
            "retry_count": 0, "max_retries": 3, "thinking_mode": False}


def evidence(bp, codes=(), satisfied=("kept",), approved_errors=()):
    issues = [{"code": code, "entity_id": "door", "message": code} for code in codes]
    return {"issues": issues, "errors": issues, "results": [], "approved_design_errors": list(approved_errors),
            "fulfillment": {"satisfied_ids": list(satisfied)},
            "snapshot": {"blueprint_fingerprint": blueprint_fingerprint(bp), "validator_version": VALIDATOR_VERSION,
                         "status": "partial" if codes else "complete", "results": [],
                         "error_count": len(codes), "warning_count": 0}}


@pytest.mark.parametrize("outcome", ["complete", "partial", "approved_mutation", "regressed_fulfillment", "same_candidate", "timeout", "no_actions"])
def test_callback_is_atomic_and_uses_real_scene_context(monkeypatch, outcome):
    original = state()
    preserved = deepcopy(original)
    calls, contexts = [], []

    def gate(bp, **kw):
        if kw.get("source") == "callback_before":
            return evidence(bp, ["overlap", "geometry"])
        codes = ["geometry"] if outcome == "partial" else ["approved_design_mutation"] if outcome == "approved_mutation" else []
        return evidence(bp, codes, satisfied=[] if outcome == "regressed_fulfillment" else ["kept"])

    async def invoke(*a, **kw):
        calls.append(1)
        if outcome == "timeout":
            raise TimeoutError("controlled timeout")
        along = 2 if outcome == "same_candidate" else 0.5
        content = "[]" if outcome == "no_actions" else (
            '[{"tool":"move_opening","arguments":{"entity_id":"door","along":'+str(along)+'}}]')
        return SimpleNamespace(content=content, reasoning="")

    def component_context(kind, bp):
        contexts.append(deepcopy(bp))
        return "real host context"

    monkeypatch.setattr(workflow, "evaluate_candidate", gate)
    monkeypatch.setattr(workflow, "create_llm", lambda **kw: object())
    monkeypatch.setattr(workflow, "invoke_llm", invoke)
    monkeypatch.setattr(workflow, "get_reasoning_callback", lambda: None)
    monkeypatch.setattr(agent_service, "spec_loader", SimpleNamespace(load_many=lambda *a, **kw: ""))
    monkeypatch.setattr("app.tools.component_tools.validate_component", component_context)
    result = asyncio.run(workflow.callback_node(original))
    assert original == preserved
    assert contexts[0]["geometry"] == original["merged_blueprint"]["geometry"]
    assert len(calls) == 1
    assert result["repair_audit"]["accepted"] == (outcome == "complete")
    if outcome == "complete":
        assert result["merged_blueprint"]["geometry"]["components"][0]["from"][0] == 0.5
        assert result["component_fragments"]["door"][0]["from"][0] == 0.5
        assert result["validation_snapshot"]["blueprint_fingerprint"] == blueprint_fingerprint(result["merged_blueprint"])
    else:
        assert "merged_blueprint" not in result
        assert "skeleton_blueprint" not in result
        assert "component_fragments" not in result
    if outcome in {"partial", "approved_mutation", "regressed_fulfillment", "same_candidate", "no_actions"}:
        repeated = asyncio.run(workflow.callback_node({**original, **result}))
        assert repeated["repair_audit"]["stop_reason"] == "repeated_candidate"
        assert len(calls) == 1


def test_invalid_approved_design_stops_before_model(monkeypatch):
    original = state()
    monkeypatch.setattr(workflow, "evaluate_candidate", lambda bp, **kw: evidence(bp, ["geometry"], approved_errors=[{"code": "coverage"}]))
    def unexpected(**kw):
        raise AssertionError("must request a design revision before model repair")
    monkeypatch.setattr(workflow, "create_llm", unexpected)
    result = asyncio.run(workflow.callback_node(original))
    assert result["repair_audit"]["stop_reason"] == "design_revision_required"
    assert "merged_blueprint" not in result


def test_plan_repair_preserves_the_accepted_callback_candidate(monkeypatch):
    original = state()
    candidate = deepcopy(original["merged_blueprint"])
    candidate["geometry"]["components"][0]["from"][0] = 0.5
    monkeypatch.setattr(handlers, "run_fix", lambda *a: ({}, "failed", [], "no deterministic fix", []))
    async def validate(*a):
        return {"status": "partial", "final_blueprint": original["merged_blueprint"]}
    async def callback(*a):
        return {"merged_blueprint": candidate, "final_blueprint": candidate, "repair_audit": {"accepted": True}}
    monkeypatch.setattr("app.agent.validation.workflow.validate_node", validate)
    monkeypatch.setattr(workflow, "callback_node", callback)
    updates, result, *_ = asyncio.run(handlers.run_repair(original, PlanItem(id="repair", op="repair")))
    assert result == "succeeded"
    assert updates["merged_blueprint"] == candidate
    assert updates["final_blueprint"] == candidate
