"""Loop policy uses controlled model responses; geometry parity is tested separately."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.generation.architecture import completion
from app.design.completeness import evaluate_design
from app.design.resolver import build_design_document, _stable_hash


def document():
    plan = json.loads((Path(__file__).parents[1]/"fixtures/design_trace_baseline.json").read_text(encoding="utf-8"))["normalized_plan"]
    plan["design_constraints"] = [dict(id="user.roof", kind="user_hard", target="/decisions/roof/type",
        expression="平屋顶", source="user_request", source_quote="平屋顶", check="equals", expected="flat")]
    return build_design_document(plan, session_id="completion", source_request="平屋顶别墅")


@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setattr(completion, "compile_document", lambda doc: SimpleNamespace(defects=[]))
    monkeypatch.setattr(completion, "project_compilation", lambda doc,result: SimpleNamespace(
        design_hash=_stable_hash(doc), design_gaps=evaluate_design(doc,_stable_hash(doc))))
    # Keep the loop test independent of normalization policy; integration tests use real compiler.
    monkeypatch.setattr("app.agent.generation.architecture.planning.normalize_architecture_plan", lambda plan,**kw: deepcopy(plan))


def run(doc, **kw):
    return asyncio.run(completion.complete_design(document=doc.model_dump(mode="json"),
        user_message=doc.requirements.source_request, complexity_profile=None, architecture_profile=None,
        thinking_mode=False, max_rounds=3, max_no_progress=2, **kw))


def test_missing_design_is_completed_and_evidence_rechecked(monkeypatch, isolated):
    calls=[]
    async def draft(**kw):
        calls.append(kw)
        return {"roof": {**kw["current_plan"]["roof"],"type":"flat"}}, {"unsettled_blocks":[]}
    monkeypatch.setattr(completion,"draft_design_blocks",draft)
    doc=document()
    result=run(doc)
    assert result.changed
    assert result.document["revision"] == doc.revision+1
    assert result.diag["stop_reason"] == "satisfied"
    assert calls[0]["only_blocks"] == ["roof"]
    assert calls[0]["max_attempts"] == 1
    assert calls[0]["allow_probe"] is False
    assert result.diag["tasks"][0]["closed_gap_ids"] == ["gap.user.roof"]


@pytest.mark.parametrize("patch", [{"massing":{}}, {"design_constraints":[]}])
def test_out_of_scope_or_goal_erasing_patch_is_rejected(monkeypatch, isolated, patch):
    async def draft(**kw): return deepcopy(patch), {"unsettled_blocks":[]}
    monkeypatch.setattr(completion,"draft_design_blocks",draft)
    doc=document()
    result=run(doc)
    assert not result.changed
    assert result.diag["stop_reason"] == "no_progress"
    assert result.diag["design_gaps"]
    assert result.diag["budget"]["reserved_model_calls"] <= 9


def test_model_failure_keeps_last_valid_document(monkeypatch, isolated):
    async def draft(**kw): raise RuntimeError("provider unavailable")
    monkeypatch.setattr(completion,"draft_design_blocks",draft)
    doc=document()
    result=run(doc)
    assert result.document == doc.model_dump(mode="json")
    assert result.diag["stop_reason"] == "model_error"
    assert len(result.diag["rounds"]) == 1


def test_approved_design_never_enters_completion(monkeypatch, isolated):
    async def draft(**kw): raise AssertionError("must not call model")
    monkeypatch.setattr(completion,"draft_design_blocks",draft)
    result=run(document().model_copy(update={"status":"approved"}))
    assert result.diag["stop_reason"] == "approval_boundary"
    assert not result.changed


def test_massing_gap_adds_dependent_block_tasks(isolated):
    doc=document()
    resolved=SimpleNamespace(design_gaps=[SimpleNamespace(status="open",target="/decisions/massing/floors",
        model_dump=lambda **kw: {"id":"gap.floors","target":"/decisions/massing/floors","expected":3})])
    tasks=completion.plan_design_tasks(doc,SimpleNamespace(defects=[]),resolved,round_index=0)
    assert tasks[0]["block"]=="massing"
    assert {t["block"] for t in tasks} >= {"structure","facade","roof","components"}
    assert all(t["base_hash"]==_stable_hash(doc) for t in tasks)


@pytest.mark.parametrize("remaining", [4, 5])
def test_budget_does_not_split_an_atomic_five_block_group(remaining):
    tasks = [{"id": str(i), "depends_on": [str(i-1)] if i else []} for i in range(5)]
    selected, pending = completion.select_task_group(tasks, remaining)
    assert len(selected) == (5 if remaining == 5 else 0)
    assert len(pending) == (0 if remaining == 5 else 5)


def test_remaining_four_calls_can_close_an_independent_one_call_group():
    tasks = [{"id": str(i), "depends_on": [str(i-1)] if i else []} for i in range(5)]
    tasks.append({"id": "independent", "depends_on": []})
    selected, pending = completion.select_task_group(tasks, 4)
    assert [task["id"] for task in selected] == ["independent"]
    assert len(pending) == 5


@pytest.mark.parametrize("field", ["decisions.volumes", "/decisions/massing/width"])
def test_geometry_compile_defects_keep_dependencies_and_respect_scope(isolated, field):
    defect = SimpleNamespace(severity="error", design_field=field, code="coverage", target="roof", evidence="gap")
    resolved = SimpleNamespace(design_gaps=[])
    tasks = completion.plan_design_tasks(document(), SimpleNamespace(defects=[defect]), resolved, round_index=0)
    assert {t["block"] for t in tasks} == {"massing", "structure", "facade", "roof", "components"}
    limited = completion.plan_design_tasks(document(), SimpleNamespace(defects=[defect]), resolved,
                                         round_index=0, only_blocks=["massing"])
    assert limited == []


def test_concept_gap_does_not_invalidate_geometry_blocks(isolated):
    gap = SimpleNamespace(status="open", target="/decisions/concept",
        model_dump=lambda **kw: {"id": "gap.title", "target": "/decisions/concept"})
    tasks = completion.plan_design_tasks(document(), SimpleNamespace(defects=[]),
                                        SimpleNamespace(design_gaps=[gap]), round_index=0)
    assert [t["block"] for t in tasks] == ["intent"]


def test_unchanged_candidate_is_not_applied(monkeypatch, isolated):
    async def draft(**kw):
        kw["call_accounting"]["model_calls"] += 1
        return {"roof": deepcopy(kw["current_plan"]["roof"])}, {"model_calls": 1, "unsettled_blocks": []}
    monkeypatch.setattr(completion, "draft_design_blocks", draft)
    doc = document()
    result = run(doc)
    assert not result.changed
    assert result.diag["stop_reason"] == "no_progress"
    assert result.diag["budget"]["actual_model_calls"] == len(result.diag["rounds"])
    assert all(not row["accepted"] for row in result.diag["rounds"])


def test_failed_model_attempts_are_counted_separately_from_reservations(monkeypatch, isolated):
    async def draft(**kw):
        kw["call_accounting"]["model_calls"] += 1
        raise TimeoutError("controlled timeout")
    monkeypatch.setattr(completion, "draft_design_blocks", draft)
    result = run(document())
    assert result.diag["stop_reason"] == "model_error"
    assert result.diag["budget"]["actual_model_calls"] == 1
    assert result.diag["budget"]["remaining_model_calls"] == 8


def test_semantic_fingerprint_ignores_descriptions_but_preserves_ordered_patterns():
    from app.design.contracts import DesignDocument
    from app.design.normalization import semantic_design_fingerprint
    doc = document()
    payload = doc.model_dump(mode="json")
    payload["decisions"]["concept"] = "另一段说明"
    payload["decisions"]["required_components"].reverse()
    equivalent = DesignDocument.model_validate(payload)
    assert semantic_design_fingerprint(equivalent) == semantic_design_fingerprint(doc)
    pattern = payload["decisions"]["facades"]["front"]["ground_pattern"]
    assert len(set(pattern)) > 1
    pattern.append(pattern.pop(0))
    assert semantic_design_fingerprint(DesignDocument.model_validate(payload)) != semantic_design_fingerprint(doc)


def test_indexed_component_reference_keeps_array_order_in_fingerprint():
    from app.design.contracts import DesignDocument, DesignConstraint
    from app.design.normalization import semantic_design_fingerprint
    payload = document().model_dump(mode="json")
    payload["decisions"]["components"] = [
        {"id": "first", "type": "canopy", "host": "main_L1_front"},
        {"id": "second", "type": "canopy", "host": "main_L1_back"},
    ]
    payload["constraints"].append(DesignConstraint(id="indexed", kind="preference", source="architecture_draft",
        target="/decisions/components/0/id", expression="首个实例", expected="first", check="equals").model_dump(mode="json"))
    doc = DesignDocument.model_validate(payload)
    payload["decisions"]["components"].reverse()
    assert semantic_design_fingerprint(DesignDocument.model_validate(payload)) != semantic_design_fingerprint(doc)
