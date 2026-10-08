"""Approval must use the completed draft, including after checkpoint replay."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.design.resolver import build_design_document, _stable_hash


def document():
    plan=json.loads((Path(__file__).parents[1]/"fixtures/design_trace_baseline.json").read_text(encoding="utf-8"))["normalized_plan"]
    return build_design_document(plan,session_id="review_version",source_request="生成一个别墅")


@pytest.mark.parametrize("stored_newer", [False,True])
def test_review_persists_completion_but_preserves_newer_user_patch(monkeypatch,stored_newer):
    from app.agent.design_flow import review as node
    doc=document().model_copy(update={"revision":2})
    stored=doc.model_copy(update={"revision":3 if stored_newer else 1})
    saved=[]
    monkeypatch.setattr(node,"design_repository",SimpleNamespace(get=lambda _:stored,
        save=lambda d:(saved.append(d) or d,{})))
    monkeypatch.setattr(node,"resolve_design",lambda d:SimpleNamespace(model_dump=lambda **kw:{}))
    class Paused(Exception): pass
    def interrupt(payload):
        assert payload["document"]["revision"] == (3 if stored_newer else 2)
        raise Paused()
    monkeypatch.setattr(node,"interrupt",interrupt)
    with pytest.raises(Paused):
        node.design_review({"design_document":doc.model_dump(mode="json")})
    assert len(saved)==(0 if stored_newer else 1)


def test_legacy_approval_returns_to_review(monkeypatch):
    from app.agent.nodes.compile_node import compile_node
    from app.design import compilation, resolver
    doc=document().model_copy(update={"status":"approved"})
    monkeypatch.setattr(compilation,"compile_document",lambda d:SimpleNamespace())
    monkeypatch.setattr(compilation,"project_compilation",lambda d,r:SimpleNamespace(design_hash=_stable_hash(d)))
    monkeypatch.setattr(resolver,"resolve_design",lambda d:SimpleNamespace(model_dump=lambda **kw:{"design_revision":d.revision}))
    result=asyncio.run(compile_node({"design_document":doc.model_dump(mode="json"),"resolved_design":{}}))
    assert result["design_review_status"]=="pending"
    assert result["design_document"]["revision"]==doc.revision+1
    assert "skeleton_blueprint" not in result
