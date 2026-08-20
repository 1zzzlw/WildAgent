from app.agent.facade_recipe import (
    _build_parameters,
    _parse_parameters,
    load_curtain_wall_parameters,
)


def test_load_curtain_wall_parameters_from_knowledge_base() -> None:
    """幕墙确定性参数应从知识库配方 JSON 读取，而非写死在代码里。"""
    params = load_curtain_wall_parameters()
    assert params.pane_module == 1.4
    assert params.mullion_gap == 0.2
    assert params.min_window_width == 0.75
    assert params.sill_height == 0.5
    assert params.sill_ratio == 0.13
    assert params.top_clearance == 0.25


def test_parse_parameters_ignores_minimal_example_json() -> None:
    """配方里的最小示例 JSON（无 pane_module）不应被当作参数块。"""
    text = (
        '```json\n{"meta": {"version": "1.1"}}\n```\n'
        '```json\n{"pane_module": 1.2}\n```'
    )
    assert _parse_parameters(text) == {"pane_module": 1.2}


def test_parse_parameters_only_extracts_known_keys() -> None:
    """只提取已知参数键，忽略 JSON 中的无关字段。"""
    text = '```json\n{"pane_module": 1.6, "unknown_field": 42}\n```'
    assert _parse_parameters(text) == {"pane_module": 1.6}


def test_build_parameters_clamps_out_of_range_values() -> None:
    """越界参数被夹回合理区间，避免配方手误破坏生成。"""
    params = _build_parameters({"pane_module": 999.0, "mullion_gap": 0.001})
    assert params.pane_module == 4.0
    assert params.mullion_gap == 0.05
