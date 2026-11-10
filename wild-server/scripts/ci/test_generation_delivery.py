"""生成失败时只保留实际实体，不能把空脚手架当成交付建筑。"""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services import agent_delivery as delivery


@pytest.mark.parametrize("geometry", [{}, {"elements": [], "components": []}, {"elements": None}])
def test_empty_scaffold_is_not_a_retained_building(geometry):
    empty = {"meta": {"name": "未命名建筑"}, "geometry": geometry, "materials": {}}
    assert delivery.retain_generation_blueprint({
        "final_blueprint": empty, "skeleton_blueprint": empty, "current_blueprint": empty,
    }, empty) is None


def test_empty_delivery_is_rejected_before_save(monkeypatch):
    def unexpected_save(*args):
        pytest.fail("空建筑不能写入场景文件")
    monkeypatch.setattr(delivery, "save_blueprint_file_as", unexpected_save)
    with pytest.raises(delivery.GenerationRejectedError, match="实体"):
        delivery.prepare_blueprint_delivery({"geometry": {"elements": [], "components": []}},
                                            "empty_generation", [], status="failed")


def test_failed_fragments_remain_editable_and_are_not_mutated():
    state = {"skeleton_blueprint": {"meta": {}, "geometry": {"elements": [], "components": []}},
             "component_diagnostics": {"body": {"failed_implementations": {"building_body": {
                 "geometry": {"elements": [{"id": "wall", "type": "wall"}], "components": []},
                 "materials": {"plaster": {"baseColor": [0.8, 0.8, 0.8]}},
             }}}}}
    before = deepcopy(state)
    retained = delivery.retain_generation_blueprint(state)
    assert retained["geometry"]["elements"] == [{"id": "wall", "type": "wall"}]
    assert "plaster" in retained["materials"]
    retained["geometry"]["elements"][0]["id"] = "changed"
    assert state == before


def test_partial_components_are_saved_with_failure_report(monkeypatch):
    blueprint = {"meta": {"name": "保留组件"}, "geometry": {
        "elements": [], "components": [{"id": "window", "type": "window"}]}}
    saved = []
    monkeypatch.setattr(delivery, "save_blueprint_file_as", lambda value, *_: saved.append(deepcopy(value)))
    retained = delivery.retain_generation_blueprint({"merged_blueprint": blueprint})
    result = delivery.prepare_blueprint_delivery(retained, "partial_generation", [
        {"name": "implementation_incomplete", "has_error": True, "output": "主体尚未完成"},
    ], status="failed")
    assert saved == [blueprint]
    assert result.components_count == 1
    assert result.validation_passed is False
    assert "主体尚未完成" in result.reply
