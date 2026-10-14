"""任务结束与设计落实分开，并阻止相同失败几何消耗后续修订。"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.agent.plan import implementation as impl
from app.agent.plan.reconcile import reconcile
from app.agent.plan.store import new_plan, record_result, terminal_stats
from app.agent.plan.contracts import PlanItem
from app.agent.validation.issues import repeated_failed_candidate, validation_issues_from_results
from app.design.markers import implementation_records
from tests.plan.test_drawing_implementation import empty_state, patch_services, reply, run, task
from tests.plan.test_drawing_fragment_retries import slab


@pytest.mark.parametrize("statuses,expected", [
    (["implemented", "implemented"], "done"),
    (["implemented", "abandoned"], "abandoned"),
    (["abandoned", "abandoned"], "abandoned"),
])
def test_ended_marker_task_is_successful_only_when_every_marker_lands(statuses, expected):
    ids = ["first", "second"]
    item = PlanItem(id="item", op="generate", params={"design_markers": True}, target={"marker_ids": ids})
    plan = new_plan([item, PlanItem(id="next", op="generate", depends_on=["item"])])
    plan = record_result(plan, "item", state="failed" if "abandoned" in statuses else "succeeded")
    state = {"resolved_design": {"component_markers": [{"id": i} for i in ids]},
             "component_diagnostics": {"item": {"implementations": {i: {"status": s} for i, s in zip(ids, statuses)}}}}
    updated, _ = reconcile(plan, state)
    assert updated.item("item").status == expected
    assert updated.item("next").status == "ready"
    assert terminal_stats(updated)["done"] == (1 if expected == "done" else 0)
    assert "舍弃 " + str(statuses.count("abandoned")) in updated.item("item").run.evidence


@pytest.mark.parametrize("rename", [False, True])
def test_repeated_failed_geometry_stops_before_third_call_even_when_renamed(monkeypatch, rename):
    state = empty_state()
    bad = slab(valid=False)
    retry = {**bad, "id": "renamed_slab"} if rename else bad
    second = reply("lattice", [retry])
    payload = json.loads(second.content)
    payload["implementations"][0]["explanation"] = "不同说明不会修复楼板面积"
    second.content = json.dumps(payload)
    events = patch_services(monkeypatch, [reply("lattice", [bad]), second])
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state)))
    record = implementation_records(updates)["lattice"]
    assert status == "failed" and ids == []
    assert record["status"] == "abandoned" and record["stop_reason"] == "repeated_failed_candidate"
    assert repeated_failed_candidate(record)
    assert record["attempted_stages"] == ["generate", "repair_1"]
    assert events == ["rag", "model", "model"]
    assert sum(t.get("model_calls", 0) for t in trace) == 2


def test_changed_failed_geometry_can_use_remaining_attempt_to_pass(monkeypatch):
    state = empty_state()
    events = patch_services(monkeypatch, [reply("lattice", [slab(valid=False)]),
        reply("lattice", [slab(offset=4, valid=False)]), reply("lattice", [slab()])])
    updates, status, _, _, _ = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded"
    assert implementation_records(updates)["lattice"]["attempted_stages"] == ["generate", "repair_1", "repair_2"]
    assert events == ["rag", "model", "model", "model"]


def test_no_progress_claim_requires_matching_geometry_issues_and_dependency_context():
    evidence = {"candidate_fingerprint": "geometry", "context_fingerprint": "host",
                "issues_fingerprint": "error", "issues": ["error"]}
    attempt = {"stage": "generate", "marker_ids": ["m"], "failed_candidates": {"m": evidence}}
    record = {"marker_id": "m", "stop_reason": "repeated_failed_candidate", "attempts": [attempt, deepcopy(attempt)]}
    assert repeated_failed_candidate(record, context_fingerprint="host")
    assert not repeated_failed_candidate(record, context_fingerprint="new_host")
    record["attempts"][-1]["failed_candidates"]["m"]["issues_fingerprint"] = "new_error"
    assert not repeated_failed_candidate(record)


def test_structured_issue_ownership_is_preserved_without_parsing_display_text():
    result = SimpleNamespace(name="validate_stair_alignment", has_error=True, output="面向用户的说明",
        issues=[{"code": "stair_platform_misaligned", "marker_id": "stairs", "design_path": "/components/0",
                 "entity_ids": ["flight_a", "flight_b"], "expected": 0, "actual": 1.2}])
    issues = validation_issues_from_results([result], {"geometry": {"elements": [], "components": []}})
    assert issues[0]["marker_id"] == "stairs"
    assert issues[0]["entity_ids"] == ["flight_a", "flight_b"]
    assert issues[0]["expected"] == 0 and issues[0]["actual"] == 1.2


def test_legacy_multi_entity_issue_keeps_both_owners():
    result = SimpleNamespace(name="validate_stair_alignment", has_error=True,
                             output="❌ [flight_a, flight_b] 相邻梯段平台错开 1.2m")
    blueprint = {"geometry": {"elements": [{"id": i, "type": "stair"} for i in ("flight_a", "flight_b")], "components": []}}
    issue = validation_issues_from_results([result], blueprint)[0]
    assert issue["entity_ids"] == ["flight_a", "flight_b"]
    assert issue["entity_id"] == "flight_a" and issue["related_entity_ids"] == ["flight_b"]


def test_opening_overlap_does_not_assign_fault_to_context_wall():
    result = SimpleNamespace(name="validate_collision", has_error=True,
        output="❌ [component:window_a] 与 ❌ [component:door_b] 在父墙 [wall_front] 上重叠 (0.20m × 1.80m)")
    blueprint = {"geometry": {"elements": [{"id": "wall_front", "type": "wall"}],
        "components": [{"id": "window_a", "type": "window", "parentWall": "wall_front"},
                       {"id": "door_b", "type": "door", "parentWall": "wall_front"}]}}
    issue = validation_issues_from_results([result], blueprint)[0]
    assert issue["entity_ids"] == ["window_a", "door_b"]
    assert issue["related_entity_ids"] == ["door_b"]
    assert issue["entity_id"] == "window_a"


def test_unattributed_assembly_issue_never_reopens_building_body(monkeypatch):
    from app.agent.design_flow import compile as compilation
    from tests.plan.test_drawing_stair_assembly import state_with_stair
    state, _ = state_with_stair()
    source_fragments = deepcopy(state["component_fragments"])
    def evaluation(*args, **kwargs):
        return {"errors": [SimpleNamespace(output="无法定位的全局错误")],
                "issues": [{"code": "UNKNOWN", "message": "无法定位的全局错误"}]}
    monkeypatch.setattr("app.agent.validation.candidate.evaluate_candidate", evaluation)
    result = run(compilation.compile_node(state))
    assert result["compile_report"]["ok"] is False
    assert not result["compile_report"].get("retry_implementation")
    assert result["compile_report"]["unattributed_issues"][0]["code"] == "UNKNOWN"
    assert result["component_fragments"] == source_fragments
    assert all("assembly_feedback" not in i["params"] for i in result["plan"]["items"])
