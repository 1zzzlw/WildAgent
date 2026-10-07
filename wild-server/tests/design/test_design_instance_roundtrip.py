"""构件设计必须跨过文档/审核边界，并影响真实编译产物。"""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.design.contracts import DesignDocument
from app.design.resolver import architecture_plan_from_document, build_design_document


def instance_plan() -> dict:
    fixture = Path(__file__).parents[1] / "fixtures" / "design_trace_baseline.json"
    plan = json.loads(fixture.read_text(encoding="utf-8"))["normalized_plan"]
    plan["components"] = [{
        "type": "window",
        "host": "left_wing_L1_left",
        "size": {"width": 1.25, "height": 1.4},
        "form": {"frameWidth": 0.11},
        "material_role": "frame",
    }]
    return plan


@pytest.mark.parametrize("count", [0, 1, 2])
def test_instances_survive_document_roundtrip(count):
    plan = instance_plan()
    plan["components"] = [deepcopy(plan["components"][0]) for _ in range(count)]
    if count == 2:
        plan["components"][1]["host"] += ":2"
    original = deepcopy(plan)
    document = build_design_document(plan, session_id="roundtrip", source_request="生成一个别墅")
    saved = DesignDocument.model_validate_json(document.model_dump_json())
    approved = saved.model_copy(update={"status": "approved"})

    assert architecture_plan_from_document(approved)["components"] == plan["components"]
    assert plan == original


def test_legacy_document_has_empty_instances():
    plan = instance_plan()
    del plan["components"]
    document = build_design_document(plan, session_id="legacy", source_request="生成一个别墅")
    assert architecture_plan_from_document(document)["components"] == []


def test_approved_instance_form_reaches_compiler_and_merge_alignment():
    from app.agent.compiler import compile_design
    from app.agent.generation.architecture import conform_openings_to_slots
    from app.design.repository import DesignRepository
    from tempfile import TemporaryDirectory

    plan = instance_plan()
    document = build_design_document(plan, session_id="compiled", source_request="生成一个别墅")
    with TemporaryDirectory() as directory:
        repository = DesignRepository(Path(directory))
        repository.save(document)
        approved, _ = repository.approve(document.session_id, document.revision)
    result = compile_design(architecture_plan_from_document(approved), user_message="生成一个别墅")
    geometry = result.blueprint["geometry"]
    aligned, _ = conform_openings_to_slots(
        geometry["components"], result.design_brief, result.blueprint["materials"]
    )
    windows = [item for item in aligned if item["type"] == "window" and item.get("frameWidth") == 0.11]
    assert len(windows) == 1
    assert windows[0]["parentWall"] == "wall_left_1_1"
    original = next(item for item in geometry["components"] if item["type"] == "window" and item.get("frameWidth") == 0.11)
    assert windows[0]["from"] == original["from"]
