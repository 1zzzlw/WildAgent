"""§2.5 的验收：交付流水线与编译期缺陷必须是**同一口径的一处实现**。

设计文档 §2.5 的原话是"全部由 ``compile_design(validate=True)`` 统一产出
``defects``，这样'能否编译'和'图纸是否合格'是同一个函数的两半"。

这一层钉的就是那句话——**不是**"编译器另有一套校验"：

1. 同蓝图下，流水线最终 error 步骤的 ``❌`` 行**逐条**出现在编译缺陷里（source of truth）
2. 编译期跑流水线**不改动**它的入参（``compile_design`` 自称纯函数）
3. 缺口本身（ID 重复）被 schema 收口挡住——它是流水线 Step 1 抓不到的那一类
4. 编译产物不但"过既有校验器"，还**一条缺陷都不报**（收口后仍绿）

⚠️ 第 1 条是本次重构的反面教训：只要编译期"手挑几个校验器调一遍"，
交付侧加一个新校验器、编译侧不跟——两处就分叉，而且**不会红**（谁也不报错，
只是收敛环少看到一类缺陷）。所以判据必须是"同源"，不是"都跑过"。
"""

from __future__ import annotations

from copy import deepcopy

from app.agent.compiler import compile_design
from app.agent.compiler.compile import _schema_defects, _validator_defects
from app.agent.compiler.pipeline_defects import pipeline_defect_messages

_MESSAGE = "生成一个三层别墅"

_RECT: dict = {
    "massing": {
        "shape": "rect",
        "width": 12,
        "depth": 9,
        "floors": 3,
        "modeled_floors": 3,
        "floor_height": 3.2,
    },
    "facades": {
        "front": {
            "bays": 4,
            "entrance_bay": 2,
            "ground_pattern": ["window", "door", "window", "empty"],
            "upper_pattern": ["window", "window", "window", "empty"],
        },
        "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
        "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
        "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
    },
    "roof": {"type": "gable", "ridge_axis": "x", "overhang": 0.6},
    "circulation": {"vertical_strategy": "stair"},
}


def _compiled() -> dict:
    result = compile_design(deepcopy(_RECT), user_message=_MESSAGE)
    assert result.blueprint, [item.to_dict() for item in result.defects]
    return result.blueprint


# ── 一、同源：编译缺陷就是流水线的 error 步骤 ──


def test_compile_defects_are_exactly_the_pipeline_error_lines() -> None:
    """编译期报出的流水线缺陷，与交付路径报出的**逐字相同**。

    这是"同一口径一处实现"的可验证形式。若哪天有人在编译期又手挑一个校验器，
    这条会红——因为它算出来的集合不再等于 ``pipeline_defect_messages``。
    """

    blueprint = _compiled()
    brief = {"component_quota": {}}
    compile_evidence = {
        item.evidence
        for item in _validator_defects(blueprint, brief)
        if item.code != "design_constraint"
    }
    assert compile_evidence == {message for _name, message in pipeline_defect_messages(blueprint)}


def test_pipeline_defects_do_not_touch_the_input() -> None:
    """在副本上跑：流水线里的 ``fix_*`` 会就地改蓝图，编译期只要诊断。

    ``compile_design`` 自称纯函数（``MEMORY.md``：编译器 = 解释器），
    如果这里直接吃到入参，dry_run 会**静默修好**图纸，而外面拿到的还是原样——
    同一份图纸两次编译结果不同，回归与门禁全部失效。
    """

    blueprint = _compiled()
    before = deepcopy(blueprint)

    # 造一个会被 fix_element_dimensions 改掉的越界尺寸，确认修复真的发生了。
    wall = next(
        element
        for element in blueprint["geometry"]["elements"]
        if element.get("type") == "wall"
    )
    wall["thickness"] = 99.0
    before_patched = deepcopy(blueprint)

    pipeline_defect_messages(blueprint)

    assert blueprint == before_patched, "入参被就地修改了"
    assert blueprint != before, "夹具本身没改动，用例失去意义"


def test_pipeline_defects_are_structured_and_carry_evidence() -> None:
    """缺陷带 ``design_field`` 与原文证据——收敛环靠前者定位，人工审核靠后者。

    流水线 Step 1（顶层结构）不过就短路，这条同时钉住了"短路**不算**编译错误"：
    编译永远有结果，只是缺陷清单更短。
    """

    broken = {"geometry": {"elements": [], "components": []}}  # 缺 meta / materials
    found = pipeline_defect_messages(broken)
    assert found, "顶层结构缺失必须被报出"
    assert all("❌" in message for _name, message in found)

    defects = _validator_defects(broken, {})
    assert defects
    assert all(item.severity == "error" for item in defects)
    assert all(item.target == "blueprint" for item in defects)


# ── 二、schema 收口：skeleton 的预检搬进编译器后仍有效 ──


def test_schema_defects_catch_duplicate_ids() -> None:
    """ID 重复是流水线 Step 1 **抓不到**的一类坏蓝图。

    §2.5 要把散在三处的校验收进编译器；如果只复用流水线，这一类就漏了——
    ``validate_blueprint_structure`` 只看顶层字段存在性，不看 id 唯一性。
    所以两条规则都要留，这条钉住"schema 收口没有被流水线取代"。
    """

    blueprint = _compiled()
    assert _schema_defects(blueprint) == [], "编译产物必须 schema 合法"

    elements = blueprint["geometry"]["elements"]
    elements.append(deepcopy(elements[0]))
    duplicated = _schema_defects(blueprint)
    assert duplicated, "重复 id 必须被 schema 收口挡住"
    assert all(item.severity == "error" for item in duplicated)
    assert any("重复" in item.evidence and "ID" in item.evidence for item in duplicated), (
        [item.evidence for item in duplicated]
    )


def test_compiled_blueprint_reports_no_defect_at_all() -> None:
    """收口之后编译产物仍然零缺陷——加校验**不是**为了把产物判红。"""

    result = compile_design(deepcopy(_RECT), user_message=_MESSAGE)
    assert result.defects == [], [item.to_dict() for item in result.defects]
    assert result.ok
