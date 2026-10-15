"""公共生成选项的归一化约定。"""

import pytest

from app.contracts.generation_options import DETAIL_LEVEL_GUIDANCE, normalize_detail_level


@pytest.mark.parametrize("level", list(DETAIL_LEVEL_GUIDANCE))
def test_supported_detail_level_is_preserved(level):
    assert normalize_detail_level(level) == level


@pytest.mark.parametrize("value", [None, "", "unknown", [], {}, 0])
def test_invalid_detail_level_defaults_to_minimal(value):
    assert normalize_detail_level(value) == "minimal"


def test_default_detail_level_is_minimal():
    assert normalize_detail_level() == "minimal"
