"""P3–P7 审查发现的跨阶段回归；由用户运行。"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

from app.design.fulfillment import _instance_check
from app.design.resolver import build_design_document, architecture_plan_from_document, attach_material_plan
from app.design.contracts import DesignDocument
from app.agent.vision.revision import build_vision_evidence, candidate_verdict, pick_best
from app.agent.vision.report import summarize
from app.agent.vision.evaluation import validated_review


def test_instance_mapping_cannot_hide_final_type_host_or_deletion():
    mapping = [{"index": 0, "entity_id": "d", "entity_type": "door",
                "declared_host": "front", "entity_host_field": "parentWall",
                "entity_host": "w1", "host_intent": "resolved"}]
    blueprint = {"geometry": {"elements": [{"id": "w1", "type": "wall"}, {"id": "w2", "type": "wall"}],
                              "components": [{"id": "d", "type": "window", "parentWall": "w2"}]}}
    assert _instance_check(blueprint, ["decisions", "components", "0", "type"], "door", "equals", mapping)[0] == "open"
    assert _instance_check(blueprint, ["decisions", "components", "0", "host"], "front", "equals", mapping)[0] == "open"
    blueprint["geometry"]["components"] = []
    assert _instance_check(blueprint, ["decisions", "components", "0", "type"], "door", "equals", mapping)[0] == "open"


def test_region_survives_design_and_material_node_round_trip():
    plan = json.loads((Path(__file__).parents[1] / "fixtures/design_trace_baseline.json").read_text(encoding="utf-8"))["normalized_plan"]
    plan["materials"] = {"regions": [{"role": "roof", "type": "roof"}]}
    document = build_design_document(plan, session_id="audit", source_request="两层住宅")
    assert architecture_plan_from_document(document)["materials"]["regions"] == plan["materials"]["regions"]
    from app.agent.generation.material.plan import resolve_material_plan
    materials = resolve_material_plan(None, [], architecture_plan=plan)
    updated = attach_material_plan(document, materials)
    assert updated.decisions.materials.regions == document.decisions.materials.regions


def test_only_versioned_legacy_documents_migrate_empty_to_open():
    plan = json.loads((Path(__file__).parents[1] / "fixtures/design_trace_baseline.json").read_text(encoding="utf-8"))["normalized_plan"]
    doc = build_design_document(plan, session_id="audit", source_request="两层住宅")
    raw = doc.model_dump(mode="json")
    face = raw["decisions"]["facades"]["back"]
    face["ground_pattern"] = ["empty"] * face["bays"]
    new = DesignDocument.model_validate(raw)
    assert new.decisions.facades["back"].ground_pattern == face["ground_pattern"]
    old = deepcopy(raw)
    old["schema_version"] = "design/1.0"
    migrated = DesignDocument.model_validate(old)
    assert migrated.schema_version == "design/1.1"
    assert set(migrated.decisions.facades["back"].ground_pattern) == {"open"}
    assert DesignDocument.model_validate(migrated.model_dump(mode="json")) == migrated


def test_proxy_never_authorizes_visual_revision():
    evaluation = {"source": "proxy", "complete": True, "items": [{
        "criterion": "facade_rhythm", "status": "needs_review", "confidence": "high",
        "evidence": {"relatedFields": ["decisions.facades"], "views": ["front"]}}]}
    assert build_vision_evidence(evaluation) == []


def test_best_selection_cannot_resurrect_rejected_candidate():
    baseline = {"items": [{"status": "needs_review"}]}
    rejected = {"items": [], "accepted": False, "compileErrors": 1}
    assert pick_best([("baseline", {}, baseline), ("rejected", {}, rejected)]) == "baseline"


def test_fulfillment_regression_uses_goal_identity_not_visual_count():
    verdict = candidate_verdict(
        result=SimpleNamespace(defects=[]),
        fulfillment=SimpleNamespace(design_gaps=[SimpleNamespace(id="door", status="open")]),
        evaluation={"source": "human", "complete": True, "items": []},
        baseline_fulfillment={"door": "satisfied"}, baseline_issues=10,
    )
    assert not verdict.accepted


def test_empty_review_and_empty_report_never_claim_completion():
    assert not validated_review({"source": "human", "complete": True}, {})["complete"]
    report = summarize([])
    assert not report["complete"]
    assert all(item["runs"] == 0 and item["geometryValidRate"] is None for item in report["groups"])
