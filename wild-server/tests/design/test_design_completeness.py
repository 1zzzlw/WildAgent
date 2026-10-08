"""Design evidence must not silently rewrite user goals."""
import json
from pathlib import Path

from app.design.contracts import DesignConstraint
from app.design.completeness import evaluate_design, merge_design_constraints
from app.design.resolver import build_design_document, _stable_hash


def document(constraints=()):
    plan = json.loads((Path(__file__).parents[1]/"fixtures/design_trace_baseline.json").read_text(encoding="utf-8"))["normalized_plan"]
    plan["design_constraints"] = list(constraints)
    return build_design_document(plan, session_id="intent", source_request="两层别墅，平屋顶")


def requirement(**updates):
    return dict(id="user.roof", kind="user_hard", target="/decisions/roof/type",
                expression="平屋顶", source="user_request", source_quote="平屋顶",
                check="equals", expected="flat", **updates)


def test_legal_design_can_have_an_unfulfilled_requirement():
    doc = document([requirement()])
    gap = next(g for g in evaluate_design(doc, _stable_hash(doc)) if g.constraint_id=="user.roof")
    assert gap.status == "open"
    assert gap.expected == "flat"
    assert gap.actual == "gable"
    assert gap.design_hash == _stable_hash(doc)


def test_missing_history_is_not_reported_as_full_satisfaction():
    doc = document()
    assert any(g.status=="needs_review" for g in evaluate_design(doc,_stable_hash(doc)))


def test_cannot_erase_or_weaken_adopted_goal():
    old = DesignConstraint.model_validate(requirement())
    changed = {**requirement(), "expected":"gable"}
    assert merge_design_constraints([old], [changed], "平屋顶")[0].expected == "flat"
    assert merge_design_constraints([old], [], "平屋顶") == [old]


def test_user_revision_supersedes_but_model_revision_cannot():
    old = DesignConstraint.model_validate(requirement())
    new = {**requirement(), "id":"user.roof.v2", "supersedes":old.id,
           "expected":"gable", "source_quote":"改成坡屋顶"}
    denied = merge_design_constraints([old],[new],"平屋顶")
    assert denied[0].adoption == "adopted"
    assert denied[1].adoption == "proposed"
    approved = merge_design_constraints([old],[new],"平屋顶","改成坡屋顶")
    assert approved[0].adoption == "superseded"
    assert approved[1].source == "user_revision"


def test_unsupported_field_and_enum_are_not_satisfied():
    constraints = [{**requirement(), "target":"/decisions/roof/per_volume"},
                   {**requirement(), "id":"user.roof.form", "expected":"unsupported-shape"}]
    doc = document(constraints)
    assert all(g.status=="unsupported" for g in evaluate_design(doc,_stable_hash(doc)) if g.constraint_id.startswith("user.roof"))


def test_model_choice_does_not_override_explicit_user_goal():
    choice = {**requirement(), "id":"choice.roof", "kind":"preference", "source":"architecture_draft", "expected":"gable"}
    doc = document([requirement(), choice])
    assert next(c for c in doc.constraints if c.id=="choice.roof").adoption == "superseded"
