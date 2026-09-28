"""立面开口的「类型 + 形态」（设计文档 §3.3）。

三件事必须钉住：

1. **文法只有一处**（`app.design.openings`）——契约层、归一化、立面编译、resolver 都从那里读；
2. 🔴 **非法形态只丢形态、不丢开口**（红线：能力缺失只标记、不阻断），而**非法类型要当场退回**；
3. **形态最终落到蓝图的 `interaction.mode`**，`fixed` 是"不写 interaction"的哨兵。
"""

from collections import Counter

import pytest
from pydantic import ValidationError

from app.agent.compiler import MODE_FINAL, compile_design
from app.agent.generation.architecture import normalize_architecture_plan
from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
from app.agent.generation.architecture.design_workflow import check_block_contract
from app.agent.generation.architecture.facade import _apply_opening_form
from app.design.contracts import FacadeDecision
from app.design.openings import (
    FIXED_FORM,
    FORMS_BY_KIND,
    INTERACTION_FORMS,
    OPENING_KINDS,
    opening_kind,
    opening_token,
    split_opening,
)
from app.utils.blueprint_normalizer import load_schema

MESSAGE = "三层矩形别墅，白色外墙，坡屋顶"
FACADE_BLOCK = BLOCK_BY_NAME["facade"]


# ── 1. 文法（唯一事实源） ──


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("window", ("window", None)),
        ("door:slide", ("door", "slide")),
        ("  WINDOW : FIXED  ", ("window", "fixed")),
        ("empty", ("empty", None)),
        ("window:", ("window", None)),
        # 形态名不认识 ⇒ **保留开口**、只丢形态（绝不能降级成 empty）
        ("window:casement", ("window", None)),
        ("door:fixed", ("door", None)),  # 门必须能开
        ("window:lift", ("window", None)),  # 窗没有"提升"
        # 类型不认识 ⇒ 空槽位
        ("garage", ("empty", None)),
        ("", ("empty", None)),
        ("empty:x", ("empty", None)),
        (None, ("empty", None)),
        ({"kind": "window"}, ("empty", None)),  # 对象形态是 §3.4 的事，本层不认
        # 形态段有杂字 ⇒ 按"形态名不认识"处理：开口照留，只是没形态
        ("door:slide:extra", ("door", None)),
    ],
)
def test_split_opening_grammar(token, expected):
    assert split_opening(token) == expected


@pytest.mark.parametrize("kind", OPENING_KINDS)
@pytest.mark.parametrize("form", [None, "swing", "slide", "lift", "fixed", "不存在的形态"])
def test_opening_token_round_trips(kind, form):
    """`opening_token` 的产物必须能被 `split_opening` 原样读回（两函数不允许分叉）。"""

    assert opening_token(*split_opening(opening_token(kind, form))) == opening_token(kind, form)


def test_forms_match_the_engine_interaction_enum():
    """🔴 漂移守卫（"能派生的别写死"）。

    `INTERACTION_FORMS` 是硬编码的；引擎往 `openingInteractionSpec.mode` 里加了新值它就过期。
    这条用**后端真正加载的那份** schema（知识库副本）来钉，而不是另抄一份。
    """

    schema = load_schema()
    assert schema, "读不到知识库 schema.json"
    mode_enum = schema["$defs"]["openingInteractionSpec"]["properties"]["mode"]["enum"]
    assert sorted(INTERACTION_FORMS) == sorted(mode_enum)
    assert FIXED_FORM not in mode_enum, "fixed 不是引擎枚举值——它是'不写 interaction'的哨兵"


def test_every_buildable_kind_has_a_form_set():
    assert set(FORMS_BY_KIND) == set(OPENING_KINDS) - {"empty"}
    assert FIXED_FORM not in FORMS_BY_KIND["door"]  # 门构件 interaction 必填 ⇒ 门不能"不可开启"
    assert "lift" not in FORMS_BY_KIND["window"]
    for kind, forms in FORMS_BY_KIND.items():
        assert forms - {FIXED_FORM} <= set(INTERACTION_FORMS), kind


# ── 2. 契约层 ──


def test_contract_accepts_form_tokens():
    facade = FacadeDecision(
        bays=2,
        ground_pattern=["window:swing", "door:slide"],
        upper_pattern=["window:fixed", "empty"],
    )
    assert facade.ground_pattern == ["window:swing", "door:slide"]


@pytest.mark.parametrize("bad", ["garage", "", "empty:x"])
def test_contract_rejects_unknown_kinds(bad):
    with pytest.raises(ValidationError):
        FacadeDecision(bays=1, ground_pattern=[bad], upper_pattern=["empty"])


def test_contract_tolerates_an_unknown_form_name_without_rewriting_it():
    """形态名写错**不在契约层拒**：原样留着，由归一化降级——不在这里静默改写文档。"""

    facade = FacadeDecision(bays=1, ground_pattern=["window:casement"], upper_pattern=["window"])
    assert facade.ground_pattern == ["window:casement"]
    assert opening_kind(facade.ground_pattern[0]) == "window"


@pytest.mark.parametrize("token", ["door", "door:slide"])
def test_upper_pattern_never_allows_a_door(token):
    with pytest.raises(ValidationError):
        FacadeDecision(bays=1, ground_pattern=["empty"], upper_pattern=[token])


# ── 3. 归一化 ──


def _plan(ground: list[str], upper: list[str]) -> dict:
    raw = {"facades": {"front": {"bays": len(ground), "ground_pattern": ground, "upper_pattern": upper}}}
    return normalize_architecture_plan(raw, user_message=MESSAGE)


def test_normalize_keeps_forms_and_degrades_only_the_unknown_ones():
    plan = _plan(
        ["window:swing", "door:slide", "window:casement"],
        ["window:fixed", "window", "empty"],
    )
    front = plan["facades"]["front"]
    assert front["ground_pattern"] == ["window:swing", "door:slide", "window"]  # 第三个只丢形态
    assert front["upper_pattern"] == ["window:fixed", "window", "empty"]


def test_no_form_at_all_is_byte_identical_to_the_old_behaviour():
    front = _plan(["window", "door", "window"], ["window", "window", "window"])["facades"]["front"]
    assert front["ground_pattern"] == ["window", "door", "window"]
    assert front["upper_pattern"] == ["window", "window", "window"]


def test_forms_do_not_change_the_component_counts():
    """形态是形容词，不该动配额——否则 `defaulted`/配额对账全会漂。"""

    plain = _plan(["window", "door", "window"], ["window", "window", "window"])
    formed = _plan(["window:swing", "door:slide", "window:fixed"], ["window:fixed", "window", "window"])
    for kind in ("door", "window"):
        assert formed["component_quota"][kind]["min"] == plain["component_quota"][kind]["min"]
        assert formed["component_quota"][kind]["max"] == plain["component_quota"][kind]["max"]


# ── 4. 块契约：类型写错让模型重写，形态写错不打扰它 ──


def _facade_pick(ground: list[str], upper: list[str]) -> dict:
    return {
        "facades": {
            "front": {"bays": len(ground), "ground_pattern": ground, "upper_pattern": upper}
        }
    }


def test_block_contract_flags_an_illegal_kind():
    issue = check_block_contract(
        FACADE_BLOCK, _facade_pick(["garage", "window", "window"], ["window"] * 3), {}
    )
    assert "garage" in issue and "door" in issue


@pytest.mark.parametrize("token", ["door", "door:slide"])
def test_block_contract_flags_a_door_in_the_upper_pattern(token):
    issue = check_block_contract(
        FACADE_BLOCK, _facade_pick(["empty"] * 3, ["window", "window", token]), {}
    )
    assert "upper_pattern" in issue and "door" in issue


def test_block_contract_leaves_an_unknown_form_alone():
    """形态名写错**不该**罚模型重写整块——归一化只丢个形容词。"""

    assert (
        check_block_contract(FACADE_BLOCK, _facade_pick(["window:casement"] * 3, ["window"] * 3), "")
        == ""
    )


# ── 5. 规则函数：只覆写 mode ──


def test_apply_form_fixed_removes_the_interaction():
    item = {"type": "window", "interaction": {"mode": "swing"}}
    _apply_opening_form(item, FIXED_FORM, "seed")
    assert "interaction" not in item


def test_apply_form_slide_drops_the_swing_only_keys():
    item = {"interaction": {"mode": "swing", "hingeSide": "right", "openAngle": 90}}
    _apply_opening_form(item, "slide", "seed")
    assert item["interaction"] == {"mode": "slide"}


def test_apply_form_swing_keeps_a_hinge_side_the_model_already_chose():
    item = {"interaction": {"mode": "swing", "hingeSide": "right"}}
    _apply_opening_form(item, "swing", "seed")
    assert item["interaction"]["mode"] == "swing"
    assert item["interaction"]["hingeSide"] == "right"  # 已经对的细节不许丢
    assert item["interaction"]["openAngle"] == 90  # 缺的补默认


def test_apply_form_ignores_an_unknown_form():
    item = {"interaction": {"mode": "swing"}}
    _apply_opening_form(item, "casement", "seed")
    assert item["interaction"] == {"mode": "swing"}


# ── 6. 端到端：形态落到蓝图 ──


def test_the_design_form_reaches_the_blueprint_interaction():
    plan = _plan(
        ["window:swing", "door:slide", "window:fixed"],
        ["window:fixed", "window", "empty"],
    )
    result = compile_design(plan, mode=MODE_FINAL, user_message=MESSAGE)
    assert result.ok, [defect.to_dict() for defect in result.defects]
    modes = Counter(
        (component["type"], (component.get("interaction") or {}).get("mode", "<无>"))
        for component in result.blueprint["geometry"]["components"]
        if component.get("type") in {"door", "window"}
    )
    assert modes[("door", "slide")] == 1, modes
    assert modes[("window", "swing")] >= 1, modes
    assert modes[("window", "<无>")] >= 1, modes  # 至少那个 fixed 窗


def test_no_window_ever_carries_fixed_as_a_mode():
    """`fixed` 是哨兵，不是引擎枚举值——绝不许出现在产物里。"""

    plan = _plan(["window:fixed"] * 3, ["window:fixed", "window", "empty"])
    result = compile_design(plan, mode=MODE_FINAL, user_message=MESSAGE)
    modes = {
        (component.get("interaction") or {}).get("mode")
        for component in result.blueprint["geometry"]["components"]
    }
    assert FIXED_FORM not in modes
