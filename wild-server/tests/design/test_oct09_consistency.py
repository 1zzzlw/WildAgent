"""O1/O2/O4/O6：原产物、完整门禁和最终关系的参数化回归。由用户运行。"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.agent.generation.architecture.planning import normalize_architecture_plan
from app.agent.validation.candidate import evaluate_candidate
from app.agent.validation.diagnostics import ValidationSnapshot, blueprint_fingerprint
from app.agent.validation.workflow import validate_node
from app.agent.compiler.pipeline_defects import pipeline_defect_messages
from app.design.compilation import compile_document
from app.design.contracts import DesignGap
from app.design.coordinates import DesignCoordinateConflict
from app.design.fulfillment import evaluate_fulfillment, fulfillment_line, fulfillment_summary
from app.design.relations import canopy_support_point, entity_index, evaluate_support
from app.design.resolver import build_design_document, _stable_hash
from app.agent.plan.contracts import PlanItem
from app.agent.plan.store import new_plan
from app.agent.plan.reconcile import reconcile, ensure_artifact_consistency
from app.services.agent_delivery import GenerationRejectedError, commit_generation_result


FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures/oct09_consistency.json").read_text(encoding="utf-8"))


def design(raw=None):
    plan = normalize_architecture_plan(deepcopy(raw or FIXTURE["base_plan"]))
    return build_design_document(plan, session_id="oct09", source_request="生成一个别墅")


@pytest.mark.parametrize("origin", [(0, 0), (10, 7.5), (-13, -8)])
@pytest.mark.parametrize("dimensions", [(12, 9), (20, 15), (9, 12)])
@pytest.mark.parametrize("floors", [2, 3])
@pytest.mark.parametrize("axis,overhang", [("x", 0), ("z", 0.6)])
def test_roof_and_walls_share_translated_volume(origin, dimensions, floors, axis, overhang):
    raw = deepcopy(FIXTURE["base_plan"])
    width, depth = dimensions
    x, z = origin
    raw["massing"].update(width=width, depth=depth, floors=floors, modeled_floors=floors)
    raw["volumes"][0].update(x=x, z=z, width=width, depth=depth, end_floor=floors)
    raw["roof"].update(ridge_axis=axis, overhang=overhang)
    doc = design(raw)
    result = compile_document(doc)
    points = [p for e in result.blueprint["geometry"]["elements"] if e["type"] == "wall" for p in (e["from"], e["to"])]
    assert [min(p[0] for p in points), max(p[0] for p in points)] == pytest.approx([x, x+width])
    assert [min(p[2] for p in points), max(p[2] for p in points)] == pytest.approx([z, z+depth])
    roof = next(e for e in result.blueprint["geometry"]["elements"] if e["type"] == "roof")
    assert roof["position"] == pytest.approx([x+width/2, floors*3, z+depth/2])
    assert [roof["span"], roof["depth"]] == pytest.approx([width+2*overhang, depth+2*overhang])
    assert roof["ridgeAxis"] == axis
    assert doc.decisions.volumes[0].width == width


def test_observed_origin_is_not_guessed_as_a_center_or_clipped():
    raw = deepcopy(FIXTURE["base_plan"])
    raw.update(massing=FIXTURE["observed_massing"], volumes=[FIXTURE["observed_volume"]])
    doc = design(raw)
    assert doc.decisions.volumes[0].model_dump(mode="json") == FIXTURE["observed_volume"]


@pytest.mark.parametrize("mutation", ["too_wide", "too_deep", "floor_gap"])
def test_coordinate_conflict_preserves_input_and_names_fields(mutation):
    raw = deepcopy(FIXTURE["base_plan"])
    if mutation == "floor_gap":
        raw["volumes"][0]["end_floor"] = 1
    else:
        raw["volumes"][0]["width" if mutation == "too_wide" else "depth"] += 1
    before = deepcopy(raw)
    with pytest.raises(DesignCoordinateConflict) as error:
        normalize_architecture_plan(raw)
    assert raw == before
    assert error.value.conflicts
    assert all(c["path"].startswith("/decisions/volumes") for c in error.value.conflicts)


@pytest.mark.parametrize("partial", [False, True])
def test_stacked_volumes_expose_supported_roof_or_explicit_blocker(partial):
    raw = deepcopy(FIXTURE["base_plan"])
    lower = {**raw["volumes"][0], "end_floor": 1}
    upper = {**lower, "id": "upper", "role": "secondary", "start_floor": 2, "end_floor": 2}
    if partial:
        upper.update(width=8, depth=6)
    raw["volumes"] = [lower, upper]
    result = compile_document(design(raw))
    blockers = [d.code for d in result.defects if d.severity == "error"]
    if partial:
        assert "roof_partial_coverage" in blockers
    else:
        assert "roof_layout_unsupported" not in blockers
        roofs = [e for e in result.blueprint["geometry"]["elements"] if e["type"] == "roof"]
        assert len(roofs) == 1
        assert roofs[0]["position"][1] == 6


def test_original_bad_roof_is_not_repaired_by_compile_diagnostics():
    blueprint = deepcopy(compile_document(design()).blueprint)
    roof = next(e for e in blueprint["geometry"]["elements"] if e["type"] == "roof")
    roof.update(span=4, depth=3, position=[100, 6, 100])
    original = deepcopy(blueprint)
    defects = pipeline_defect_messages(blueprint)
    assert blueprint == original
    assert any("roof" in name for name, _ in defects)


def test_final_gate_identifies_the_same_approved_mutation():
    doc = design()
    blueprint = deepcopy(compile_document(doc).blueprint)
    roof = next(e for e in blueprint["geometry"]["elements"] if e["type"] == "roof")
    roof["height"] += 0.2
    before = deepcopy(blueprint)
    evaluated = evaluate_candidate(blueprint, design_document=doc.model_dump(mode="json"), source="callback")
    final = asyncio.run(validate_node({"merged_blueprint": blueprint, "design_document": doc.model_dump(mode="json")}))
    assert blueprint == before
    assert evaluated["approved_design_changes"]
    assert any(r.name == "approved_design_mutation" and r.has_error for r in evaluated["errors"])
    assert final["status"] == "partial"
    assert final["validation_snapshot"]["blueprint_fingerprint"] == blueprint_fingerprint(blueprint)
    assert final["validation_snapshot"]["design_hash"] == _stable_hash(doc)


def test_snapshot_requires_current_design_context():
    blueprint = {"geometry": {"elements": [], "components": []}}
    snapshot = ValidationSnapshot(blueprint_fingerprint=blueprint_fingerprint(blueprint),
        design_hash="design-a", design_revision=1, design_brief_fingerprint=blueprint_fingerprint({"roof": 1}))
    assert snapshot.matches(blueprint, design_hash="design-a", design_revision=1, design_brief={"roof": 1})
    assert not snapshot.matches(blueprint)
    assert not snapshot.matches(blueprint, design_hash="design-a", design_revision=2, design_brief={"roof": 1})
    assert not snapshot.matches(blueprint, design_hash="design-b", design_revision=1, design_brief={"roof": 1})


def support_scene():
    return {"geometry": {"elements": [
        {"type": "wall", "id": "front", "from": [10, 0, 7], "to": [22, 3, 7], "thickness": 0.24},
        {"type": "wall", "id": "back", "from": [10, 0, 16], "to": [22, 3, 16], "thickness": 0.24},
        {"type": "column", "id": "support", "base": [12, 0, 5.88], "height": 2.7}],
        "components": [{"type": "canopy", "id": "entry", "parentWall": "front", "from": [1, 2.8, 0],
                        "width": 4, "depth": 2, "thickness": 0.2}]} }


RELATION = {"kind": "supports", "target": "entry", "along_ratio": 0.25, "depth_ratio": 0.5}


@pytest.mark.parametrize("change", [None, "rear_column", "short_column", "missing_canopy", "duplicate_column", "negative_height"])
def test_relation_rechecks_final_entities_not_column_count(change):
    bp = support_scene()
    if change == "rear_column":
        bp["geometry"]["elements"][-1]["base"][2] = 16
    elif change == "short_column":
        bp["geometry"]["elements"][-1]["height"] -= 0.3
    elif change == "missing_canopy":
        bp["geometry"]["components"] = []
    elif change == "duplicate_column":
        bp["geometry"]["elements"].append(deepcopy(bp["geometry"]["elements"][-1]))
    elif change == "negative_height":
        bp["geometry"]["elements"][-1].update(base=[12, 2.7, 5.88], height=-2.7)
    assert evaluate_support(bp, "support", RELATION)["status"] == ("satisfied" if change is None else "open")
    item = PlanItem(id="supports_entry", op="generate", kind="column", target={"entity_requirements": [
        {"entity_id": "support", "relation": RELATION}]})
    updated, _ = reconcile(new_plan([item]), {"merged_blueprint": bp})
    assert (updated.item(item.id).status == "done") == (change is None)
    if change is None:
        bp["geometry"]["elements"][-1]["base"][2] += 1
        assert ensure_artifact_consistency(updated, {"merged_blueprint": bp}).item(item.id).status != "done"


@pytest.mark.parametrize("reverse", [False, True])
def test_relation_is_translation_and_wall_direction_aware(reverse):
    bp = support_scene()
    if reverse:
        wall = bp["geometry"]["elements"][0]
        wall["from"], wall["to"] = [22, 0, 7], [10, 3, 7]
    point, bottom = canopy_support_point(bp, RELATION)
    assert point[2] < 7
    bp["geometry"]["elements"][-1].update(base=[point[0], bottom, point[2]], height=point[1]-bottom)
    assert evaluate_support(bp, "support", RELATION)["status"] == "satisfied"


def test_side_entry_and_second_canopy_need_their_own_support():
    bp = support_scene()
    bp["geometry"]["elements"].append({"type": "wall", "id": "side", "from": [22, 0, 7],
                                        "to": [22, 3, 16], "thickness": 0.24})
    side = {**deepcopy(bp["geometry"]["components"][0]), "id": "side_entry", "parentWall": "side"}
    bp["geometry"]["components"].append(side)
    relation = {**RELATION, "target": "side_entry"}
    assert evaluate_support(bp, "support", relation)["status"] == "open"
    point, bottom = canopy_support_point(bp, relation)
    assert point[0] > 22
    bp["geometry"]["elements"].append({"type": "column", "id": "side_support",
        "base": [point[0], bottom, point[2]], "height": point[1]-bottom})
    assert evaluate_support(bp, "side_support", relation)["status"] == "satisfied"
    assert evaluate_support(bp, "side_support", RELATION)["status"] == "open"


def test_declared_support_is_compiled_and_array_fulfillment_tracks_it():
    raw = deepcopy(FIXTURE["base_plan"])
    raw["components"] = [
        {"id": "entry", "type": "canopy", "host": "main_L1_front", "size": {"depth": 2}},
        {"id": "support", "type": "column", "host": "entry", "relation": RELATION},
    ]
    expected = {"id": "support", "type": "column", "relation": RELATION, "form": {}}
    raw["design_constraints"] = [{"id": "entry_support", "kind": "preference", "source": "architecture_draft",
        "target": "/decisions/components", "expression": "入口雨棚支撑",
        "expected": [{"id": "entry", "type": "canopy"}, expected], "check": "equals"}]
    doc = design(raw)
    compiled = compile_document(doc)
    blueprint = deepcopy(compiled.blueprint)
    assert evaluate_support(blueprint, "support", RELATION)["status"] == "satisfied"
    mappings = compiled.stats["instance_overrides"]["instance_entities"]
    def gap():
        return next(g for g in evaluate_fulfillment(doc, blueprint, _stable_hash(doc), mappings)
                    if g.constraint_id == "entry_support")
    assert gap().status == "satisfied"
    constraint = next(c for c in doc.constraints if c.id == "entry_support")
    constraint.expected[1]["form"] = {"future_shape": True}
    assert gap().status == "needs_review"
    constraint.expected[1]["form"] = {}
    entity_index(blueprint)["support"]["height"] -= 0.3
    assert gap().status == "open"


def test_fifteen_requirements_do_not_report_sixty_percent_overall():
    statuses = ["satisfied"]*3 + ["open"]*2 + ["needs_review"] + ["unsupported"]*9
    gaps = [DesignGap(id=f"g{i}", constraint_id=f"c{i}", design_hash="d", target="/decisions/x",
                      status=s, evidence="synthetic") for i, s in enumerate(statuses)]
    summary = fulfillment_summary(gaps, design_hash="d")
    assert summary["total"] == 15 and summary["satisfied"] == 3
    assert summary["satisfied_ratio"] == 0.6 and summary["decidable_coverage"] == 0.333
    assert all(text in fulfillment_line(summary) for text in ("3/15", "3/5", "5/15"))
    unknown = fulfillment_summary(gaps[-9:], design_hash="d")
    assert unknown["satisfied_ratio"] is None
    assert "无可判定项" in fulfillment_line(unknown)


@pytest.mark.parametrize("tamper", ["blueprint", "results", "version", "missing", "design_revision"])
def test_save_rejects_stale_or_missing_evidence(monkeypatch, tamper):
    from app.agent.validation.diagnostics import VALIDATOR_VERSION
    bp = {"meta": {"designHash": "d", "designRevision": 1}, "geometry": {"elements": [], "components": []}}
    snapshot = {"blueprint_fingerprint": blueprint_fingerprint(bp), "validator_version": VALIDATOR_VERSION,
                "design_hash": "d", "design_revision": 1, "status": "complete", "results": [], "error_count": 0}
    if tamper == "blueprint":
        bp["geometry"]["components"].append({"type": "light", "id": "extra"})
    elif tamper == "results":
        snapshot["results"] = [{"name": "missing"}]
    elif tamper == "version":
        snapshot["validator_version"] = "old"
    elif tamper == "design_revision":
        snapshot["design_revision"] = 2
    else:
        snapshot = None
    saved = []
    monkeypatch.setattr("app.services.agent_delivery.save_blueprint_file_as", lambda *a: saved.append(a))
    with pytest.raises(GenerationRejectedError):
        commit_generation_result("s", "r", bp, [], status="complete", validation_snapshot=snapshot)
    assert not saved


def test_legal_single_volume_can_pass_full_gate_and_save(monkeypatch):
    raw = deepcopy(FIXTURE["base_plan"])
    raw["massing"].update(floors=1, modeled_floors=1)
    raw["volumes"][0]["end_floor"] = 1
    raw["roof"].update(type="flat", overhang=0)
    doc = design(raw)
    compiled = compile_document(doc)
    blueprint = deepcopy(compiled.blueprint)
    blueprint.setdefault("meta", {}).update(designHash=_stable_hash(doc), designRevision=doc.revision)
    evaluated = evaluate_candidate(blueprint, design_document=doc.model_dump(mode="json"), design_brief=compiled.design_brief)
    assert not evaluated["errors"], [r.output for r in evaluated["errors"]]
    saved = []
    monkeypatch.setattr("app.services.agent_delivery.save_blueprint_file_as", lambda *a: saved.append(a))
    delivery = commit_generation_result("s", "r", blueprint, evaluated["snapshot"]["results"],
        status="complete", fulfillment=evaluated["fulfillment"], validation_snapshot=evaluated["snapshot"])
    assert len(saved) == 1
    assert delivery.elements_count > 0


def test_proxy_measurements_are_not_completed_visual_review():
    from app.agent.vision.evaluation import proxy_evaluate
    result = proxy_evaluate(compile_document(design()).blueprint)
    assert result["complete"] is False
    assert "截图" in result["okMeaning"]


def test_backend_and_core_agree_on_optional_ridge_axis_contract():
    server = Path(__file__).parents[2]
    backend = json.loads((server / "storage/knowledge_base/schema.json").read_text(encoding="utf-8"))
    core = json.loads((server.parent / "wild-core/schema.json").read_text(encoding="utf-8"))
    assert backend["$defs"]["roof"] == core["$defs"]["roof"]
    assert "ridgeAxis" not in backend["$defs"]["roof"]["required"]


def test_warning_gate_is_part_of_the_same_readonly_evaluation(monkeypatch):
    from app.services.agent_service import PipelineStepResult
    from app.services.agent_delivery import WARNING_GATE_MAX
    bp = deepcopy(compile_document(design()).blueprint)
    original = deepcopy(bp)
    rows = [PipelineStepResult(step=i, name=f"warning_{i}", output="⚠️ synthetic", has_error=False, has_warning=True)
            for i in range(WARNING_GATE_MAX+1)]
    monkeypatch.setattr("app.services.agent_service.run_validation_pipeline", lambda *a, **kw: deepcopy(rows))
    result = evaluate_candidate(bp)
    assert bp == original
    assert result["snapshot"]["status"] == "partial"
    assert any(row.name == "validate_delivery_warning_gate" for row in result["errors"])
