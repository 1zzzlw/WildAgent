import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.design.contracts import DesignDocument, DesignPatch
from app.design.repository import DesignConflictError, DesignRepository
from app.design.resolver import (
    architecture_plan_from_document,
    attach_material_plan,
    build_design_document,
    render_design_svg,
    resolve_design,
)


def sample_plan(*, curtain_wall: bool = False) -> dict:
    return {
        "schema_version": "1.1",
        "profile": "ordinary_public",
        "concept": "通透办公建筑",
        "massing": {
            "shape": "rectangle",
            "width": 20,
            "depth": 12,
            "floors": 3,
            "modeled_floors": 3,
            "representation_mode": "full",
            "floor_height": 4,
            "symmetry": True,
        },
        "complexity": {
            "level": "standard",
            "min_volumes": 1,
            "min_detail_packages": 0,
            "target_structural_elements": 10,
            "grid_bays": [2, 2],
            "reason": "test",
        },
        "volumes": [{
            "id": "main",
            "role": "primary",
            "x": 0,
            "z": 0,
            "width": 20,
            "depth": 12,
            "start_floor": 1,
            "end_floor": 3,
        }],
        "structural_grid": {"system": "frame", "x_bays": 4, "z_bays": 3},
        "detail_packages": [],
        "facades": {
            "front": {"bays": 4, "entrance_bay": 2, "ground_pattern": ["window", "door", "window", "window"], "upper_pattern": ["window"] * 4},
            "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
            "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
            "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
        },
        "roof": {"type": "flat", "ridge_axis": "x", "overhang": 0},
        "component_quota": {
            "door": {"min": 1, "max": 1},
            "window": {"min": 41, "max": 41},
            "roof": {"min": 1, "max": 1, "type": "flat"},
        },
        "curtain_wall": curtain_wall,
        "balcony_access_count": 0,
        "balcony_width": None,
        "required_components": ["door", "window", "roof"],
        "unsupported_component_types": [],
        "design_rationale": ["入口与轴网协调"],
    }


def make_document(*, curtain_wall: bool = False) -> DesignDocument:
    return build_design_document(
        sample_plan(curtain_wall=curtain_wall),
        session_id="session_design_test",
        source_request="生成三层玻璃幕墙写字楼",
        building_type="office",
    )


def test_design_document_round_trip_and_resolution():
    document = make_document(curtain_wall=True)
    resolved = resolve_design(document)
    plan = architecture_plan_from_document(document)

    assert document.schema_version == "design/1.0"
    assert document.decisions.envelope.system == "curtain_wall"
    assert resolved.design_revision == document.revision
    assert resolved.design_hash.startswith("sha256:")
    assert resolved.component_quantities["door"] == 1
    assert plan["curtain_wall"] is True
    assert plan["massing"]["width"] == 20
    assert plan["circulation"]["vertical_strategy"] == "stair"


def test_svg_is_derived_and_keeps_json_paths():
    document = make_document()
    svg = render_design_svg(document)

    assert svg.startswith("<svg")
    assert 'data-design-path="/decisions/volumes/0"' in svg
    assert 'data-design-path="/decisions/facades/front"' in svg
    assert "DesignDocument r1" in svg


def test_material_plan_is_part_of_reviewed_design_without_new_revision():
    document = make_document()
    updated = attach_material_plan(document, {
        "concept": "银灰金属框与物理玻璃",
        "palette": ["silver", "blue glass"],
        "roles": [],
        "resolvedAssets": {},
    })

    assert updated.revision == document.revision
    assert updated.decisions.materials.keywords == [
        "银灰金属框与物理玻璃", "silver", "blue glass",
    ]
    assert updated.decisions.materials.resolved_plan is not None
    assert updated.decisions.materials.resolved_plan.concept == "银灰金属框与物理玻璃"


def test_material_plan_rejects_unknown_roles_and_fields():
    data = make_document().model_dump(mode="json")
    data["decisions"]["materials"]["resolved_plan"] = {
        "concept": "invalid",
        "roles": [{
            "role": "wall_everything",
            "materialId": "wall",
            "material": {},
            "untyped": True,
        }],
    }

    with pytest.raises(ValidationError):
        DesignDocument.model_validate(data)


def test_schematic_preview_spreads_representative_levels_over_full_height():
    plan = sample_plan()
    plan["massing"].update({
        "floors": 30,
        "modeled_floors": 10,
        "representation_mode": "schematic",
    })
    plan["volumes"][0]["end_floor"] = 10
    plan["component_quota"]["window"] = {"min": 139, "max": 139}
    document = build_design_document(
        plan,
        session_id="session_schematic_test",
        source_request="生成三十层示意办公塔楼",
    )
    resolved = resolve_design(document)

    assert resolved.bounds["height"] == 120
    assert len(resolved.levels) == 10
    assert resolved.levels[-1].index == 30


def test_repository_patch_increments_revision_and_invalidates_approval(tmp_path: Path):
    repository = DesignRepository(tmp_path)
    document, _ = repository.save(make_document())
    approved, _ = repository.approve(document.session_id, document.revision)
    patch = DesignPatch.model_validate({
        "type": "design_patch",
        "patch_id": "patch_width",
        "base_revision": approved.revision,
        "source": "user",
        "operations": [{
            "op": "replace",
            "path": "/decisions/massing/width",
            "value": 24,
        }],
    })

    changed, resolved = repository.apply_patch(document.session_id, patch)

    assert changed.revision == 2
    assert changed.status == "draft"
    assert changed.approved_at is None
    assert resolved["bounds"]["width"] == 24
    assert (tmp_path / "history" / document.session_id / "revision_2.json").exists()


def test_repository_rejects_stale_or_locked_patch(tmp_path: Path):
    repository = DesignRepository(tmp_path)
    data = make_document().model_dump(mode="json")
    data["locks"] = ["/decisions/massing/floors"]
    document, _ = repository.save(DesignDocument.model_validate(data))
    locked = {
        "type": "design_patch",
        "patch_id": "patch_locked",
        "base_revision": document.revision,
        "source": "user",
        "operations": [{"op": "replace", "path": "/decisions/massing/floors", "value": 4}],
    }
    with pytest.raises(DesignConflictError, match="已锁定"):
        repository.apply_patch(document.session_id, locked)

    parent_replace = json.loads(json.dumps(locked, ensure_ascii=False))
    parent_replace["operations"][0] = {
        "op": "replace",
        "path": "/decisions/massing",
        "value": document.decisions.massing.model_dump(mode="json"),
    }
    with pytest.raises(DesignConflictError, match="已锁定"):
        repository.apply_patch(document.session_id, parent_replace)

    stale = json.loads(json.dumps(locked, ensure_ascii=False))
    stale["operations"][0]["path"] = "/decisions/massing/width"
    stale["base_revision"] = 99
    with pytest.raises(DesignConflictError, match="版本冲突"):
        repository.apply_patch(document.session_id, stale)


def test_repository_rejects_unsupported_component_patch(tmp_path: Path):
    repository = DesignRepository(tmp_path)
    repository.save(make_document())
    patch = DesignPatch.model_validate({
        "patch_id": "patch_unsupported",
        "base_revision": 1,
        "operations": [{
            "op": "add",
            "path": "/decisions/required_components/-",
            "value": "sunshade",
        }],
    })

    with pytest.raises(ValueError, match="未实现的构件: sunshade"):
        repository.apply_patch("session_design_test", patch)


def test_repository_marks_only_matching_approved_design_as_compiled(tmp_path: Path):
    repository = DesignRepository(tmp_path)
    draft, resolved = repository.save(make_document())
    with pytest.raises(DesignConflictError, match="已批准"):
        repository.mark_compiled(
            draft.session_id,
            revision=draft.revision,
            design_hash=resolved["design_hash"],
        )

    approved, approved_resolved = repository.approve(draft.session_id, draft.revision)
    compiled, compiled_resolved = repository.mark_compiled(
        approved.session_id,
        revision=approved.revision,
        design_hash=approved_resolved["design_hash"],
    )

    assert compiled.status == "compiled"
    assert compiled_resolved["design_hash"] == approved_resolved["design_hash"]

    repository.delete(compiled.session_id)
    assert repository.get(compiled.session_id) is None
    assert not (tmp_path / "history" / compiled.session_id).exists()


def test_invalid_facade_pattern_is_rejected():
    data = make_document().model_dump(mode="json")
    data["decisions"]["facades"]["front"]["ground_pattern"] = ["door"]

    with pytest.raises(ValidationError, match="pattern 长度"):
        DesignDocument.model_validate(data)


def test_multistorey_design_requires_vertical_circulation():
    data = make_document().model_dump(mode="json")
    data["decisions"]["circulation"]["vertical_strategy"] = "none"

    with pytest.raises(ValidationError, match="竖向交通"):
        DesignDocument.model_validate(data)
