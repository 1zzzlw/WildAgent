"""设计意图贯穿审核与执行；几何有效不等于设计落实。"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.design.completeness import evaluate_design
from app.design.contracts import DesignDocument
from app.design.normalization import semantic_design_fingerprint
from app.design.resolver import architecture_plan_from_document, build_design_document, _stable_hash
from app.agent.prompts import build_component_prompt, build_material_plan_prompt, build_plan_strategy_prompt


def plan():
    result = json.loads((Path(__file__).parents[1] / "fixtures/design_trace_baseline.json").read_text(encoding="utf-8"))["normalized_plan"]
    result["design_intent"] = {
        "goals": ["组织清晰的入口与主次体量"], "assumptions": ["场地朝向未指定"],
        "spatial_strategy": "从入口到竖向交通连续到达", "composition": "主次体量与屋面协调",
        "material_strategy": "浅石墙配深色金属框", "selected_systems": ["gable", "canopy"],
    }
    return result


def document(raw=None):
    return build_design_document(raw or plan(), session_id="intent-chain", source_request="生成一个别墅")


def test_intent_survives_save_review_and_plan_roundtrip():
    raw = plan()
    original = deepcopy(raw)
    doc = DesignDocument.model_validate_json(document(raw).model_dump_json()).model_copy(update={"status": "approved"})
    assert doc.schema_version == "design/1.3"
    assert architecture_plan_from_document(doc)["design_intent"] == raw["design_intent"]
    assert raw == original


def test_design_basis_is_not_silently_cut_to_five_items_at_review():
    raw = plan()
    raw["design_rationale"] = [f"方案关系 {index}" for index in range(8)]
    reviewed = architecture_plan_from_document(document(raw))
    assert len(reviewed["design_rationale"]) == 9
    assert "方案关系 7" in reviewed["design_rationale"][-1]


@pytest.mark.parametrize("version", ["design/1.1", "design/1.2"])
def test_historical_document_without_intent_remains_readable(version):
    data = document().model_dump(mode="json")
    data["schema_version"] = version
    data["decisions"].pop("design_intent")
    assert DesignDocument.model_validate(data).decisions.design_intent is None


def test_review_hash_binds_intent_but_geometry_fingerprint_ignores_prose():
    first = document()
    second = first.model_copy(deep=True)
    second.decisions.design_intent.material_strategy = "原木墙配深色金属框"
    assert _stable_hash(first) != _stable_hash(second)
    assert semantic_design_fingerprint(first) == semantic_design_fingerprint(second)


@pytest.mark.parametrize("target,expected,status", [
    ("/decisions/volumes", 1, "needs_review"),
    ("/decisions/facades/front/entrance_bay", 0, "needs_review"),
    ("/decisions/roof/type", "invented_roof", "unsupported"),
])
def test_impossible_targets_do_not_trigger_futile_design_rewriting(target, expected, status):
    raw = plan()
    raw["design_constraints"] = [{"id": "target", "kind": "preference", "source": "architecture_draft",
        "target": target, "expected": expected, "check": "equals", "expression": "待核对的设计选择"}]
    doc = document(raw)
    gap = next(g for g in evaluate_design(doc, _stable_hash(doc)) if g.constraint_id == "target")
    assert gap.status == status


def test_invalid_normalization_target_is_reviewable_without_restoring_zero_index():
    raw = plan()
    raw["normalization_changes"] = [{"path": "/decisions/facades/front/entrance_bay",
        "before": 0, "after": raw["facades"]["front"]["entrance_bay"], "before_exists": True,
        "after_exists": True, "category": "semantic_change", "semantic_change": True,
        "reason": "入口索引从 1 开始", "source": "model"}]
    doc = document(raw)
    gaps = [g for g in evaluate_design(doc, _stable_hash(doc)) if g.id.startswith("gap.normalization.")]
    assert gaps and all(g.status == "needs_review" for g in gaps)


def test_material_plan_uses_design_direction_instead_of_classifier_hint():
    prompt = build_material_plan_prompt(plan(), [], style_preference=["classifier-only-style"])
    assert "浅石墙配深色金属框" in prompt
    assert "classifier-only-style" not in prompt


def test_execution_strategy_keeps_intent_when_geometry_summary_is_long():
    raw = plan()
    raw["massing"]["unused_description"] = "very long geometry " * 400
    prompt = build_plan_strategy_prompt(capability_catalog=[], design_brief={}, skeleton_summary="",
        detail_level="standard", architecture_plan=raw)
    assert "浅石墙配深色金属框" in prompt


def test_component_prompt_receives_intent_without_changing_slot_coordinates():
    prompt = build_component_prompt("", "window", "wall-real", design_brief={
        "design_intent": plan()["design_intent"], "design_notes": ["开口配合入口组织"],
    })
    assert "浅石墙配深色金属框" in prompt
    assert "开口配合入口组织" in prompt
    assert "不重新做方案选择" in prompt


def test_compile_reports_dropped_roof_attachment_before_review():
    from app.agent.compiler import compile_design
    from app.agent.generation.architecture.planning import normalize_architecture_plan
    raw = plan()
    raw["roof"] = {"type": "chinese_curved", "ridge_axis": "x", "overhang": 0.5}
    raw["components"] = [{"id": "eave", "type": "cornice", "host": "unresolved-roof",
        "size": {}, "form": {"profile": [[0, 0], [0.1, 0], [0.1, 0.1]]}, "material_role": "roof"}]
    result = compile_design(normalize_architecture_plan(raw), user_message="生成一个别墅")
    defect = next(d for d in result.defects if d.code == "design_instance_uncompiled")
    assert defect.target == "eave"
    assert defect.design_field == "decisions.components[0]"


@pytest.mark.parametrize("code,field", [
    ("design_instance_uncompiled", "decisions.components[0]"),
    ("material_region_unapplied", "decisions.materials.regions"),
])
def test_design_implementation_warnings_create_preapproval_tasks(code, field):
    from app.agent.generation.architecture.completion import plan_design_tasks
    defect = SimpleNamespace(severity="warn", code=code, design_field=field, target="eave", evidence="未落实")
    tasks = plan_design_tasks(document(), SimpleNamespace(defects=[defect]),
        SimpleNamespace(design_gaps=[]), round_index=0)
    assert [t["block"] for t in tasks] == ["components"]
