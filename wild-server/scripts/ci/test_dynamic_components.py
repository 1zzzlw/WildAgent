"""设备类型从需求、计划词表到执行注册表可达，未调用模型。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.agent.generation.architecture.profile import _default_detail_packages
from app.agent.generation.component.registry import COMPONENT_REGISTRY
from app.agent.generation.skeleton.output import parse_components_from_reply


def test_requested_devices_reach_component_registry():
    assert set(_default_detail_packages("两层别墅，电梯和吊扇", 2)) >= {"elevator", "fan"}
    assert "fan" in _default_detail_packages("单层客厅要吊扇", 1)
    assert "elevator" not in _default_detail_packages("单层电梯", 1)
    assert parse_components_from_reply("_components: elevator, fan") == ["elevator", "fan"]
    assert "controlPosition" in COMPONENT_REGISTRY["fan"].required_fields
    assert "landingWalls" in COMPONENT_REGISTRY["elevator"].optional_fields
