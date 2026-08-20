"""Agent 生成结果统一出口的回归测试。"""

from unittest.mock import patch

import pytest

from app.services.agent_delivery import (
    ArtifactSaveError,
    GenerationRejectedError,
    final_validation_results,
    prepare_blueprint_delivery,
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


def test_rejected_blueprint_is_never_saved():
    with patch("app.services.agent_delivery.save_blueprint_file_as") as save:
        with pytest.raises(GenerationRejectedError):
            prepare_blueprint_delivery(
                _blueprint(),
                "session_rejected",
                [_result("validate_schema", error=True)],
                status="partial",
            )

    save.assert_not_called()


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
