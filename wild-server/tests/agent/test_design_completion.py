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
        model_dump=lambda **kw: {"id":"gap.floors","expected":3})])
    tasks=completion.plan_design_tasks(doc,SimpleNamespace(defects=[]),resolved,round_index=0)
    assert tasks[0]["block"]=="massing"
    assert {t["block"] for t in tasks} >= {"structure","facade","roof","components"}
    assert all(t["base_hash"]==_stable_hash(doc) for t in tasks)
