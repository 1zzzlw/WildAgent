"""失败证据与定向修订回放；模型响应固定，不访问模型或检索服务。"""
from copy import deepcopy
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.agent.validation import issues
from app.agent.plan import implementation
from app.agent.design_flow import compile as compilation


def blueprint():
    return {"meta": {"version": "1.0", "type": "building", "name": "反馈回归"},
            "geometry": {"elements": [
                {"id": "shape_main", "type": "primitive", "shape": "sphere", "radius": .5,
                 "position": [0, .5, 0], "material": "stone"},
                {"id": "other_main", "type": "primitive", "shape": "sphere", "radius": .5,
                 "position": [3, .5, 0], "material": "stone"},
            ], "components": []}, "materials": {"stone": {"baseColor": [.8, .8, .8]}}, "assets": {}}


def marker():
    return {"id": "shape", "type": "primitive", "host": "", "design_path": "/decisions/components/0",
            "design": {"size": {"width": 1, "height": 1, "depth": 1},
                       "placement": {"position": [0, .5, 0]}, "form": {}}}


def failure():
    return {"code": "DESIGN_COMPONENT_GEOMETRY", "validator": "design_component_geometry",
            "entity_ids": ["shape_main"], "message": "构件宽度不符合图纸", "severity": "error"}


def test_structured_issue_cannot_move_to_another_entity_and_count_as_progress():
    before = [failure(), {**failure(), "code": "SECOND_PROBLEM", "message": "另一个问题"}]
    after = [{**failure(), "entity_ids": ["other_main"]}]
    assert issues.compare_issue_sets(before, after)["accepted"] is False


def test_deduplicating_errors_is_not_repair_progress():
    assert issues.compare_issue_sets([failure(), failure()], [failure()])["accepted"] is False


def test_feedback_binds_design_owner_expected_and_actual_without_mutation():
    bp, item = blueprint(), marker()
    original = deepcopy((bp, item))
    feedback = issues.repair_feedback([failure()], bp, markers=[item],
        records={"shape": {"entity_ids": ["shape_main"]}}, design_hash="approved", source="compile")
    assert feedback["entity_ids"] == ["shape_main"]
    assert feedback["marker_ids"] == ["shape"]
    assert feedback["issues"][0]["expected"]["shape"]["size"]["width"] == 1
    assert feedback["issues"][0]["actual"]["entities"][0]["radius"] == .5
    assert feedback["blueprint_fingerprint"] and feedback["design_hash"] == "approved"
    assert (bp, item) == original


def test_design_conflict_is_explicitly_returned_for_design_revision():
    issue = {**failure(), "recommended_repair_level": "design_revision"}
    feedback = issues.repair_feedback([issue], blueprint(), source="compile")
    assert feedback["requires_design_revision"] is True


def test_rejected_fragment_retains_validator_evidence():
    bp = blueprint()
    bp["geometry"]["elements"] = bp["geometry"]["elements"][1:]
    bad = {"id": "shape", "geometry": {"elements": [
        {"id": "shape_main", "type": "primitive", "shape": "sphere", "radius": -.2,
         "position": [0, .5, 0], "material": "stone"}], "components": []}}
    before = deepcopy(bp)
    _, _, rejected, _ = implementation._accept_fragment(bp, bad, marker())
    assert rejected and rejected["issues"]
    assert any(issue["validator"] == "validate_wild_schema" for issue in rejected["issues"])
    assert any("shape_main" in issue.get("entity_ids", []) for issue in rejected["issues"])
    assert bp == before


def test_local_and_final_validation_share_schema_evidence():
    from app.agent.validation.candidate import evaluate_candidate

    bp = blueprint()
    bp["geometry"]["elements"][0]["radius"] = -.2
    before = deepcopy(bp)
    local = next(i for i in implementation.implementation_issues(bp) if i["validator"] == "validate_wild_schema")
    final = next(i for i in evaluate_candidate(bp)["issues"] if i["validator"] == "validate_wild_schema")
    assert local == final
    assert final["entity_ids"] == ["shape_main"]
    assert final["field_path"] == "/geometry/elements/0"
    assert final["actual"]["radius"] == -.2
    assert bp == before


@pytest.mark.parametrize("change", ["other-entity", "shared-material", "shared-asset", "unrelated-addition"])
def test_compile_repair_rejects_changes_outside_failed_scope(change):
    original = blueprint()
    original["assets"]["texture"] = {"assetId": "texture", "name": "original"}
    original["materials"]["stone"]["textureSet"] = "texture"
    candidate = deepcopy(original)
    if change == "other-entity":
        candidate["geometry"]["elements"][1]["radius"] = .7
    elif change == "shared-material":
        candidate["materials"]["stone"]["baseColor"] = [1, 0, 0]
    elif change == "shared-asset":
        candidate["assets"]["texture"]["name"] = "changed"
    else:
        candidate["geometry"]["elements"].append({"id": "unrelated", "type": "primitive"})
    feedback = {"entity_ids": ["shape_main"], "marker_ids": ["shape"]}
    assert compilation._repair_scope_errors(original, candidate, feedback)


def test_compile_repair_accepts_local_changes():
    original = blueprint()
    candidate = deepcopy(original)
    candidate["geometry"]["elements"][0]["radius"] = .4
    assert compilation._repair_scope_errors(original, candidate,
        {"entity_ids": ["shape_main"], "marker_ids": ["shape"]}) == []


def test_display_text_does_not_become_a_material_reference():
    original = blueprint()
    original["geometry"]["elements"][0]["material"] = "private"
    original["geometry"]["elements"][1]["label"] = {"text": "private"}
    original["materials"]["private"] = {"baseColor": [.5, .5, .5]}
    candidate = deepcopy(original)
    candidate["materials"]["private"]["baseColor"] = [1, 0, 0]
    assert compilation._repair_scope_errors(original, candidate,
        {"entity_ids": ["shape_main"], "marker_ids": ["shape"]}) == []


@pytest.mark.parametrize("responses, expected", [([-.2, .5], "succeeded"), ([-.2, -.2], "failed"),
                                                ([None, .5], "succeeded")])
def test_marker_failure_revision_and_revalidation(monkeypatch, responses, expected):
    from app.agent.plan.contracts import PlanItem
    from app.agent.plan import knowledge_tool
    from app.llm import client, invocation
    from app.llm.invocation import LlmResult

    bp = blueprint()
    bp["geometry"]["elements"] = bp["geometry"]["elements"][1:]
    state = {"skeleton_blueprint": bp, "resolved_design": {"design_hash": "approved", "component_markers": [marker()]},
             "design_document": {"decisions": {"massing": {"shape": "rect", "width": 4, "depth": 4, "floors": 1,
                 "modeled_floors": 1, "floor_height": 3}, "volumes": [{"id": "main", "x": 0, "z": 0,
                 "width": 4, "depth": 4, "start_floor": 1, "end_floor": 1}], "complexity": {"level": "simple"}}}}
    state["thinking_mode"] = True
    before = deepcopy(state)
    messages, model_settings = [], []
    async def reply(_model, request, **_kwargs):
        messages.append(json.loads(request[-1]["content"]))
        radius = responses[len(messages)-1]
        if radius is None:
            return LlmResult(content="{invalid json")
        entity = {**blueprint()["geometry"]["elements"][0], "radius": radius}
        return LlmResult(content=json.dumps({"implementations": [
            {"id": "shape", "geometry": {"elements": [entity], "components": []}}]}))
    monkeypatch.setattr(client, "create_llm", lambda **kwargs: model_settings.append(kwargs) or object())
    monkeypatch.setattr(invocation, "invoke_llm", reply)
    monkeypatch.setattr(knowledge_tool, "search_knowledge_result", lambda *_args, **_kwargs:
        {"text": "sphere", "has_shape_reference": True, "chunk_ids": []})
    item = PlanItem(id="generate_shape", op="generate", kind="primitive", target={"marker_ids": ["shape"]},
                    params={"design_markers": True, "design_hash": "approved"})
    updates, outcome, _, _, _ = asyncio.run(implementation.run_marker_generate(state, item))
    assert outcome == expected
    assert len(messages) == 2
    assert all(settings["enable_thinking"] is False for settings in model_settings)
    evidence = messages[1]["failure_evidence"]["shape"]
    assert evidence["design_hash"] == "approved" and evidence["issues"]
    assert evidence["marker_ids"] == ["shape"]
    diag = updates["component_diagnostics"][item.id]
    calls = [entry for entry in diag["trace"] if entry.get("tool") == "generate_wild"]
    assert calls[1]["feedback_used"]["shape"] == evidence
    if expected == "succeeded":
        assert diag["implementations"]["shape"]["status"] == "implemented"
        assert diag["failure_evidence"] == {}
    else:
        assert diag["implementations"]["shape"]["stop_reason"] == "repeated_failed_candidate"
        assert diag["failure_evidence"]["shape"]["issues"]
    assert state == before


@pytest.mark.parametrize("mode", ["local", "outside", "no-change", "design-conflict", "addition"])
def test_compile_repair_feedback_scope_and_revalidation(monkeypatch, mode):
    from app.agent.validation import candidate
    from app.design.contracts import DesignDocument
    from app.design import resolver
    from app.llm import client, invocation
    from app.llm.invocation import LlmResult
    from app.agent.validation.diagnostics import blueprint_fingerprint

    bp = blueprint()
    bp["geometry"]["elements"][0]["radius"] = .8
    records = {name: {"status": "implemented", "entity_ids": [entity["id"]],
        "entity_fingerprint": blueprint_fingerprint([entity])}
        for name, entity in zip(["shape", "other"], bp["geometry"]["elements"])}
    state = {"design_document": {}, "skeleton_blueprint": bp,
             "resolved_design": {"component_markers": [marker()]}, "plan": {"llm_calls": 2}}
    before = deepcopy(state)
    document = SimpleNamespace(decisions=SimpleNamespace(massing=SimpleNamespace(model_dump=lambda **_kwargs: {})))
    monkeypatch.setattr(DesignDocument, "model_validate", classmethod(lambda *_args, **_kwargs: document))
    monkeypatch.setattr(resolver, "_stable_hash", lambda *_args: "approved")
    monkeypatch.setattr(compilation, "_assemble_with_relations", lambda *_args: (deepcopy(bp), [], deepcopy(records)))
    evaluations, messages = [], []
    def evaluate(value, **_kwargs):
        evaluations.append(deepcopy(value))
        failed = value["geometry"]["elements"][0]["radius"] != .5
        issue = {**failure(), "validator": "approved_design_invalid"} if mode == "design-conflict" else failure()
        return {"issues": [issue] if failed else [], "errors": [SimpleNamespace(output=issue["message"])] if failed else [],
                "snapshot": {"design_hash": "approved"}, "fulfillment": {"satisfied_ids": ["other"]}}
    async def reply(_model, request, **_kwargs):
        messages.append(json.loads(request[-1]["content"].split("\n", 1)[1]))
        patch = [{"op": "update_element", "id": "shape_main", "changes": {"radius": .8 if mode == "no-change" else .5}}]
        if mode == "outside":
            patch.append({"op": "update_element", "id": "other_main", "changes": {"radius": .7}})
        if mode == "addition":
            patch.append({"op": "add_element", "element": {**bp["geometry"]["elements"][0], "id": "shape_detail"}})
        return LlmResult(content=json.dumps({"operations": patch}))
    monkeypatch.setattr(candidate, "evaluate_candidate", evaluate)
    monkeypatch.setattr(client, "create_llm", lambda **_kwargs: object())
    monkeypatch.setattr(invocation, "invoke_llm", reply)
    result = asyncio.run(compilation.compile_node(state))
    repair = result["compile_report"]["repair"]
    if mode == "design-conflict":
        assert messages == [] and repair["stop_reason"] == "design_revision_required"
        assert result["plan"]["llm_calls"] == 2
    else:
        assert len(messages) == 1 and result["plan"]["llm_calls"] == 3
        assert messages[0]["repair_feedback"]["entity_ids"] == ["shape_main"]
        assert messages[0]["repair_feedback"]["marker_ids"] == ["shape"]
        assert repair["accepted"] is (mode in {"local", "addition"})
        assert len(evaluations) == (1 if mode == "outside" else 2)
    assert result["merged_blueprint"]["geometry"]["elements"][1] == bp["geometry"]["elements"][1]
    if mode in {"outside", "no-change", "design-conflict"}:
        assert result["merged_blueprint"] == bp
    if mode == "addition":
        adopted = result["design_brief"]["implementation"]["records"]["shape"]
        assert adopted["entity_ids"] == ["shape_main", "shape_detail"]
    assert state == before
