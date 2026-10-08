"""檐口校验/修复的判据一致性（2026-10-08 事故：`profile` 写了一个预设名）。

两侧必须是**同一条判据**：校验器报什么，确定性修复就得修什么。旧实现里
校验器把**类型错误**报成"退化为直线"，修复器又用 ``len(profile) < 3`` 判"要不要修" ——
``"rectangular_80x60"`` 有 19 个字符，于是修复器认为"无需修复"、recheck 原样失败，
错误被留到最终交付（而 ``classify_validation_issue`` 还把这一步声明成
``deterministic_fix``，声明与实现不符）。
"""

from app.tools.component_tools import (
    fix_cornice_placement,
    validate_cornice_placement,
)

_PATH = [[-8.0, 0.0, -5.5], [-8.0, 0.0, 5.5]]


def _blueprint(profile, path=None) -> dict:
    return {
        "geometry": {
            "elements": [],
            "components": [{
                "type": "cornice",
                "id": "cornice_01",
                "path": _PATH if path is None else path,
                "profile": profile,
            }],
        },
    }


def _reference_profile() -> list[list[float]]:
    from app.agent.compiler.compile import _CORNICE_PROFILE

    return [[float(x), float(y)] for x, y in _CORNICE_PROFILE]


def test_string_profile_is_reported_as_a_type_error_not_a_degeneracy():
    """字符串截面必须报**类型**，不能报"退化为直线"——否则修复被引到错误病因上。"""

    message = validate_cornice_placement(_blueprint("rectangular_80x60"))

    assert "rectangular_80x60" in message
    assert "二维数字点" in message
    assert "退化" not in message


def test_collinear_profile_is_still_reported_as_degenerate():
    """真正的退化（共线、面积为零）仍按退化报，不被类型文案吃掉。"""

    assert "退化" in validate_cornice_placement(_blueprint([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]))


def test_string_path_is_reported_as_a_type_error_not_a_length_problem():
    """path 同理：字符串 path 有长度，别报成"总长度过短"。"""

    message = validate_cornice_placement(_blueprint(_reference_profile(), path="abc"))

    assert "path 必须是" in message
    assert "过短" not in message


def test_fix_repairs_whatever_the_validator_rejected():
    """回归：校验器拒的，确定性修复必须能修好（声明 deterministic_fix 就要做到）。"""

    for broken in ("rectangular_80x60", [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]], None):
        blueprint = _blueprint(broken)
        fix_cornice_placement(blueprint)
        assert validate_cornice_placement(blueprint) == "✅ 檐口校验通过 (1 个檐口)"


def test_fix_falls_back_to_the_compiler_reference_section():
    """回落的是编译器派生檐口用的**同一份**参考截面（单一事实源，不另抄一份）。"""

    blueprint = _blueprint("rectangular_80x60")
    fix_cornice_placement(blueprint)

    assert blueprint["geometry"]["components"][0]["profile"] == _reference_profile()


def test_valid_cornice_needs_no_fix():
    """已经合格的檐口不许被"修复"改形状。"""

    blueprint = _blueprint(_reference_profile())
    message = fix_cornice_placement(blueprint)

    assert "无需修复" in message
    assert blueprint["geometry"]["components"][0]["profile"] == _reference_profile()
