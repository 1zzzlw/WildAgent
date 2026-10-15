"""Agent 生成结果统一出口的回归测试。"""

import json
from unittest.mock import patch

import pytest

from app.services.agent_delivery import (
    ArtifactSaveError,
    GenerationRejectedError,
    WARNING_GATE_MAX,
    commit_generation_result,
    final_validation_results,
    prepare_blueprint_delivery,
    retain_generation_blueprint,
    summarize_validation,
)
from app.utils.blueprint_parser import compact_blueprint_title


def _result(name: str, *, error: bool = False, warning: bool = False) -> dict:
    return {
        "step": 1,
        "name": name,
        "output": "result",
        "has_error": error,
        "has_warning": warning,
    }


def _blueprint() -> dict:
    return {
        "meta": {"name": "测试/建筑"},
        "geometry": {"elements": [{"id": "floor"}], "components": [{"id": "door"}]},
    }


def test_recheck_overwrites_initial_validation_error():
    results = [
        _result("validate_opening_fit", error=True),
        _result("validate_opening_fit [recheck]"),
        _result("validate_collision", warning=True),
    ]

    final = final_validation_results(results)
    summary = summarize_validation(results)

    assert [result["name"] for result in final] == [
        "validate_opening_fit [recheck]",
        "validate_collision",
    ]
    assert summary.total == 2
    assert summary.passed == 1
    assert summary.warnings == 1
    assert summary.errors == 0


@pytest.mark.parametrize("status", ["failed", "partial"])
def test_failed_validation_keeps_existing_blueprint_and_error_report(status):
    with patch("app.services.agent_delivery.save_blueprint_file_as") as save:
        error = _result("validate_design_brief", error=True)
        error["output"] = "建筑方案要求 2 层，但没有 stair 构件"
        delivery = prepare_blueprint_delivery(
            _blueprint(), "session_failed", [error], status=status,
        )

    save.assert_called_once()
    assert not delivery.validation_passed
    assert delivery.validation.errors == 1
    assert "校验未通过" in delivery.reply
    assert error["output"] in delivery.reply


def test_failed_snapshot_can_save_actual_file_without_changing_invalid_geometry(tmp_path, monkeypatch):
    from app.agent.validation.diagnostics import VALIDATOR_VERSION, blueprint_fingerprint
    blueprint = _blueprint()
    blueprint["geometry"]["elements"] = [{"id": "bad_box", "type": "primitive", "shape": "box",
                                          "position": [0, 0, 0], "dimensions": [-1, 1, 1]}]
    results = [_result("validate_element_dimensions", error=True)]
    results[0]["output"] = "bad_box 的尺寸必须为正数"
    snapshot = {"blueprint_fingerprint": blueprint_fingerprint(blueprint),
                "validator_version": VALIDATOR_VERSION, "status": "failed",
                "results": results, "error_count": 1}
    monkeypatch.setattr("app.services.agent_delivery.SCENES_DIR", tmp_path)
    delivery = commit_generation_result("session_failed", "req_failed", blueprint, results,
        status="failed", validation_snapshot=snapshot)

    saved = json.loads((tmp_path / delivery.filename).read_text(encoding="utf-8"))
    assert saved == blueprint
    assert not delivery.validation_passed
    assert "bad_box" in delivery.reply


@pytest.mark.parametrize("blueprint", [
    {}, {"meta": {}, "geometry": {}}, {"meta": {}, "geometry": {"elements": [], "components": []}},
    {"meta": None, "geometry": {"elements": None, "components": {"broken": True}}},
])
def test_incomplete_blueprint_is_saved_without_discarding_source(blueprint):
    with patch("app.services.agent_delivery.save_blueprint_file_as") as save:
        delivery = prepare_blueprint_delivery(blueprint, "incomplete", [], status="failed")
    save.assert_called_once()
    assert save.call_args.args[0] == blueprint
    assert not delivery.validation_passed
    assert delivery.elements_count == delivery.components_count == 0


@pytest.mark.parametrize("value", [None, [], "not a blueprint"])
def test_no_blueprint_object_cannot_be_saved(value):
    with patch("app.services.agent_delivery.save_blueprint_file_as") as save:
        with pytest.raises(GenerationRejectedError, match="没有可保存"):
            prepare_blueprint_delivery(value, "absent", [], status="failed")
    save.assert_not_called()


def test_recovery_keeps_fragments_failed_body_and_resources_without_inventing_geometry():
    from copy import deepcopy
    state = {"skeleton_blueprint": {"meta": {"name": "draft"},
                                    "geometry": {"elements": [], "components": []}},
             "component_fragments": {"windows": [{"id": "window"}]},
             "component_diagnostics": {"windows": {"components": ["window"], "materials": {"glass": {}}},
                 "body": {"failed_implementations": {"building_body": {
                     "geometry": {"elements": [{"id": "wall", "thickness": -0.2}]},
                     "materials": {"stone": {"color": "bad"}}}}}}}
    before = deepcopy(state)
    recovered = retain_generation_blueprint(state)
    assert recovered["geometry"] == {"elements": [{"id": "wall", "thickness": -0.2}],
                                     "components": [{"id": "window"}]}
    assert recovered["materials"] == {"glass": {}, "stone": {"color": "bad"}}
    assert state == before


def test_empty_retry_state_does_not_erase_retained_geometry():
    retained = _blueprint()
    state = {"merged_blueprint": {"meta": {}, "geometry": {"elements": [], "components": []}}}
    assert retain_generation_blueprint(state, retained) == retained
    assert retain_generation_blueprint({"current_blueprint": retained}) == retained
    assert retain_generation_blueprint({}) is None


def test_malformed_saved_blueprint_remains_visible_in_session_and_scene_lists(tmp_path, monkeypatch):
    from app.api import scenes, sessions
    blueprint = {"meta": None, "geometry": {"elements": None, "components": "bad"}}
    monkeypatch.setattr("app.services.agent_delivery.SCENES_DIR", tmp_path)
    monkeypatch.setattr(scenes, "SCENES_DIR", tmp_path)
    monkeypatch.setattr(sessions, "SCENES_DIR", tmp_path)
    delivery = prepare_blueprint_delivery(blueprint, "session_broken", [], status="failed")
    saved_path = tmp_path / delivery.filename
    assert json.loads(saved_path.read_text(encoding="utf-8")) == blueprint
    assert scenes._scene_summary(saved_path)["filename"] == delivery.filename
    assert sessions._find_blueprint_for_session("session_broken")["filename"] == delivery.filename


def test_many_warnings_do_not_block_saving_existing_entities():
    results = [_result(f"warning_{index}", warning=True) for index in range(WARNING_GATE_MAX + 1)]
    with patch("app.services.agent_delivery.save_blueprint_file_as") as save:
        delivery = prepare_blueprint_delivery(_blueprint(), "warnings", results, status="complete")
    save.assert_called_once()
    assert not delivery.validation_passed
    assert delivery.validation.warnings == WARNING_GATE_MAX + 1


def test_validation_exception_still_saves_existing_entities_with_failure_report():
    result = _result("validate_delivery", error=True)
    result["output"] = "交付内容复检失败"
    with patch("app.services.agent_delivery.save_blueprint_file_as") as save:
        delivery = commit_generation_result("session_interrupted", "req_interrupted", _blueprint(), [result],
                                            status="failed", validation_snapshot=None)
    save.assert_called_once()
    assert not delivery.validation_passed
    assert result["output"] in delivery.reply


def test_failed_snapshot_is_not_reported_as_passed_when_no_errors_were_collected():
    from app.agent.validation.diagnostics import VALIDATOR_VERSION, blueprint_fingerprint
    blueprint = _blueprint()
    snapshot = {"blueprint_fingerprint": blueprint_fingerprint(blueprint),
                "validator_version": VALIDATOR_VERSION, "status": "failed", "results": [], "error_count": 0}
    with patch("app.services.agent_delivery.save_blueprint_file_as"):
        delivery = prepare_blueprint_delivery(blueprint, "failed", [], status="complete",
                                              validation_snapshot=snapshot)
    assert not delivery.validation_passed
    assert "校验未通过" in delivery.reply


def test_successful_delivery_uses_uniform_file_reference_and_reply():
    with patch("app.services.agent_delivery.save_blueprint_file_as") as save:
        delivery = prepare_blueprint_delivery(
            _blueprint(),
            "session_delivery",
            [_result("validate_schema")],
            status="complete",
        )

    assert delivery.filename.endswith("/session_delivery_测试_建筑.wild")
    assert delivery.file_url == f"/api/scenes/{delivery.filename}"
    assert delivery.elements_count == 1
    assert delivery.components_count == 1
    assert "校验 1✓ 0⚠" in delivery.reply
    save.assert_called_once()


def test_valid_file_with_abandoned_design_items_reports_incomplete_design():
    fulfillment = {"total": 3, "satisfied": 2, "open": 1, "gaps": [],
                   "implementation_summary": {"implemented": 2, "abandoned": 1, "design_complete": False}}
    with patch("app.services.agent_delivery.save_blueprint_file_as"):
        delivery = prepare_blueprint_delivery(_blueprint(), "incomplete", [_result("validate_schema")],
                                              status="complete", fulfillment=fulfillment)
    assert "图纸落实 2 项、舍弃 1 项" in delivery.reply
    assert "设计尚未完整实现" in delivery.reply


def test_long_descriptive_blueprint_name_uses_short_session_title_and_filename():
    blueprint = _blueprint()
    blueprint["meta"]["name"] = (
        "退台新中式别墅：一层矩形基座，二层U形退台，两翼端部各设悬挑阳台"
    )

    with patch("app.services.agent_delivery.save_blueprint_file_as"):
        delivery = prepare_blueprint_delivery(
            blueprint,
            "session_short_title",
            [_result("validate_schema")],
            status="complete",
        )

    assert compact_blueprint_title(blueprint["meta"]["name"]) == "退台新中式别墅"
    assert delivery.name == "退台新中式别墅"
    assert delivery.filename.endswith("/session_short_title_退台新中式别墅.wild")


def test_save_failure_has_dedicated_exception():
    with patch(
        "app.services.agent_delivery.save_blueprint_file_as",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(ArtifactSaveError, match="disk full"):
            prepare_blueprint_delivery(
                _blueprint(),
                "session_save_error",
                [_result("validate_schema")],
                status="complete",
            )
