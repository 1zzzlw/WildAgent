"""P3 regression cases; execution is left to the project owner."""
from copy import deepcopy

import pytest

from app.agent.generation.architecture.planning import normalize_architecture_plan
from app.design.normalization import approved_compilation_changes, field_changes
from app.design.resolver import build_design_document, _stable_hash
from app.design.completeness import evaluate_design


def normalize(raw):
    changes = []
    plan = normalize_architecture_plan(raw, normalization_changes=changes, input_source="model")
    return plan, changes


@pytest.mark.parametrize("value,category", [(None, "default"), (-5, "semantic_change"), (15.1234, None)])
def test_missing_invalid_and_explicit_dimensions_are_distinct(value, category):
    raw, _ = normalize({})
    if value is None:
        del raw["massing"]["width"]
    else:
        raw["massing"]["width"] = value
    result, changes = normalize(raw)
    entries = [c for c in changes if c["path"] == "/decisions/massing/width"]
    if category is None:
        assert result["massing"]["width"] == value
        assert not entries
    else:
        assert entries[0]["category"] == category
        assert entries[0]["before_exists"] == (value is not None)
        assert entries[0]["after"] == result["massing"]["width"]


def test_legal_dimensions_and_tiers_survive_unrelated_invalid_field():
    raw, _ = normalize({})
    raw["massing"].update(width=350.1234, floor_height=-1, tiers=[
        {"floors": raw["massing"]["floors"], "width_ratio": 0.8, "depth_ratio": 1},
    ])
    result, changes = normalize(raw)
    assert result["massing"]["width"] == 350.1234
    assert result["massing"]["tiers"] == raw["massing"]["tiers"]
    assert any(c["path"] == "/decisions/massing/floor_height" for c in changes)


@pytest.mark.parametrize("count", [1, 2])
def test_roof_array_migration_is_only_lossless_for_single_roof(count):
    raw, _ = normalize({})
    raw["roof"] = [{"type": "flat", "ridge_axis": "x", "overhang": 0.1234}] * count
    result, changes = normalize(raw)
    change = next(c for c in changes if c["path"] == "/decisions/roof")
    assert change["semantic_change"] == (count > 1)
    if count == 1:
        assert result["roof"] == raw["roof"][0]
        assert change["category"] == "protocol"
    else:
        assert change["before"] == raw["roof"]


def test_valid_explicit_facade_is_not_replaced_by_entrance_or_curtain_defaults():
    raw, _ = normalize({})
    raw["curtain_wall"] = True
    raw["facades"]["front"] = {"bays": 12, "ground_pattern": ["window"] * 12,
                                "upper_pattern": ["empty"] * 12, "entrance_bay": 3}
    result, _ = normalize(raw)
    assert result["facades"]["front"] == raw["facades"]["front"]


def test_overlapping_volumes_are_not_silently_moved_or_deleted():
    raw, _ = normalize({})
    first = deepcopy(raw["volumes"][0])
    first.update(id="main", x=0, z=0, width=6, depth=6)
    second = {**first, "id": "wing", "role": "secondary", "x": 3}
    raw["volumes"] = [first, second]
    result, _ = normalize(raw)
    assert result["volumes"] == raw["volumes"]


def test_repeated_normalization_does_not_keep_rewriting_decisions():
    first, _ = normalize({})
    second, changes = normalize(first)
    third, _ = normalize(second)
    assert second == third
    assert not any(c["semantic_change"] for c in changes)


def test_degradation_evidence_reaches_current_design_gaps_and_keeps_constraint_id():
    raw, _ = normalize({})
    raw["roof"]["type"] = "unsupported_roof"
    raw["design_constraints"] = [{"id": "roof.choice", "kind": "preference",
        "target": "/decisions/roof/type", "expression": "roof choice", "source": "architecture_draft",
        "check": "equals", "expected": "unsupported_roof"}]
    plan, changes = normalize(raw)
    plan["normalization_changes"] = changes
    doc = build_design_document(plan, session_id="p3", source_request="建筑")
    trace = next(t for t in doc.rule_trace if t.changes)
    change = next(c for c in trace.changes if c["path"] == "/decisions/roof/type")
    assert change["constraint_ids"] == ["roof.choice"]
    gaps = evaluate_design(doc, _stable_hash(doc))
    assert any(g.id.startswith("gap.normalization.") and g.status == "open" for g in gaps)
    assert any(g.constraint_id == "roof.choice" and g.status == "unsupported" for g in gaps)
    assert doc.decisions.design_rationale[0].startswith("[决策事实]")


def test_blueprint_evidence_is_per_entity_and_field():
    before = {"geometry": {"components": [{"id": "window_1", "width": 1.2}]}}
    after = deepcopy(before)
    after["geometry"]["components"][0]["width"] = 1.1
    changes = field_changes(before, after, rule="delivery")
    assert changes[0]["path"] == "/geometry/components/window_1/width"
    assert (changes[0]["before"], changes[0]["after"]) == (1.2, 1.1)


@pytest.mark.parametrize("change", ["size", "delete", "material"])
def test_approved_entity_changes_are_detected(change):
    expected = {"geometry": {"elements": [{"id": "wall_1", "width": 2}], "components": []},
                "materials": {"stone": {"color": "#cccccc"}}}
    actual = deepcopy(expected)
    if change == "size":
        actual["geometry"]["elements"][0]["width"] = 3
    elif change == "delete":
        actual["geometry"]["elements"] = []
    else:
        actual["materials"]["stone"]["color"] = "#ffffff"
    assert approved_compilation_changes(expected, actual)


def test_added_execution_entities_and_numeric_noise_are_not_design_mutation():
    expected = {"geometry": {"elements": [{"id": "wall_1", "width": 2}]}}
    actual = deepcopy(expected)
    actual["geometry"]["elements"][0].update(width=2.0001, computed=True)
    actual["geometry"]["elements"].append({"id": "light_1", "type": "light"})
    assert approved_compilation_changes(expected, actual) == []


def test_document_compilation_skips_request_reinterpretation(monkeypatch):
    from app.design.compilation import compile_document
    raw, _ = normalize({})
    doc = build_design_document(raw, session_id="p3", source_request="宽100米的建筑")
    captured = {}
    def compile_stub(plan, **kwargs):
        captured.update(plan=plan, **kwargs)
        return object()
    monkeypatch.setattr("app.agent.compiler.compile_design", compile_stub)
    compile_document(doc)
    assert captured["normalized_input"] is True
    assert captured["plan"]["massing"]["width"] == doc.decisions.massing.width


@pytest.mark.parametrize("roof", [{"type": "unknown"}, [{"type": "flat"}, {"type": "gable"}]])
def test_invalid_explicit_roof_is_returned_to_existing_block_retry(roof):
    from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
    from app.agent.generation.architecture.design_workflow import check_block_contract
    error = check_block_contract(BLOCK_BY_NAME["roof"], {"roof": roof}, {})
    assert "roof" in error and "显式值" in error


def test_unsupported_instance_size_is_visible_in_review():
    from types import SimpleNamespace
    from app.design.compilation import project_compilation
    raw, _ = normalize({})
    doc = build_design_document(raw, session_id="p3", source_request="建筑")
    change = {"path": "/decisions/components/0/size/width", "target": "door_01",
              "before": 3.7, "after": 1.1, "reason": "实例尺寸未落实"}
    result = SimpleNamespace(blueprint={"geometry": {}}, design_brief={}, defects=[],
                             stats={"instance_overrides": {"size_changes": [change]}})
    resolved = project_compilation(doc, result)
    gap = next(g for g in resolved.design_gaps if g.layer == "implementation")
    assert gap.status == "unsupported"
    assert (gap.expected, gap.actual) == (3.7, 1.1)
    assert any("实例尺寸未落实" in warning for warning in resolved.warnings)
