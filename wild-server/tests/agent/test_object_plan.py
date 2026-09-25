"""物件方案的确定性部分：子类型识别、尺寸归属与落轴、数量、兜底。

这一层的价值全在"模型不可用/说错时用户仍拿到他点名的那件东西"，
所以每条断言都对应一个真实会被用户看见的错误结果，例如：
把"一张1.8米的桌子"做成 1.4 米、把"两把椅子"做成 1 把。
"""

import pytest

from app.agent.generation.objects.planning import (
    fallback_object_plan,
    normalize_object_plan,
)
from app.agent.generation.objects.subtypes import (
    FURNITURE_SUBTYPES,
    closest_axis,
    long_axis,
    matched_subtypes,
)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("生成一个桌子", ["table"]),
        ("生成一个床头柜", ["nightstand"]),
        ("生成一张双人床", ["bed"]),
        # 中文复合词：长词先占位，"桌"不再单独成项，但"椅"必须成项。
        ("生成一套餐桌椅", ["table", "chair"]),
        ("生成一个书柜", ["bookshelf"]),
    ],
)
def test_subtype_matching_keeps_compound_words_intact(message, expected):
    assert matched_subtypes(message) == expected


@pytest.mark.parametrize(
    "subtype,value,axis",
    [
        # 长边未必是 width：床的长边是 depth。
        ("table", 1.8, "width"),
        ("bed", 2.0, "depth"),
        ("sofa", 1.9, "width"),
        # 尺度差得远时靠缺省值就能定轴：落地灯 1.6 米只可能是高。
        ("lamp", 1.6, "height"),
        ("wardrobe", 2.2, "height"),
    ],
)
def test_bare_dimension_lands_on_the_axis_closest_in_scale(subtype, value, axis):
    assert closest_axis(subtype, value) == axis


@pytest.mark.parametrize(
    "subtype,axis",
    [("table", "width"), ("bed", "depth"), ("chair", "depth"), ("lamp", "width")],
)
def test_long_axis_compares_defaults_rather_than_names(subtype, axis):
    assert long_axis(subtype) == axis


@pytest.mark.parametrize(
    "message,expected",
    [
        # (子类型, 数量, 宽, 深, 高)
        ("生成一个桌子", [("table", 1, 1.4, 0.8, 0.75)]),
        ("生成四把椅子", [("chair", 4, 0.45, 0.5, 0.9)]),
        ("生成十把椅子", [("chair", 10, 0.45, 0.5, 0.9)]),
        # "长"落在餐桌的 width 上，而不是塞进 depth 做出"深大于宽"的畸形比例。
        ("生成一张长1.8米的餐桌", [("table", 1, 1.8, 0.8, 0.75)]),
        ("生成一张1.8米的桌子", [("table", 1, 1.8, 0.8, 0.75)]),
        ("生成一米八长的桌子", [("table", 1, 1.8, 0.8, 0.75)]),
        # 紧凑连写不能让数字串位："1.8宽"必须被丢弃，"宽0.9"必须生效。
        ("生成一张长1.8宽0.9高0.75的桌子", [("table", 1, 1.8, 0.9, 0.75)]),
        # "长"落在床的 depth 上（2.0 > 1.5）。
        ("生成一张两米长的床", [("bed", 1, 1.5, 2.0, 1.0)]),
        # 只给"宽"时落 width：家具口语里"宽"指正面宽度。
        ("生成一个宽1.8米的衣柜", [("wardrobe", 1, 1.8, 0.6, 2.2)]),
        ("生成一个地毯，长2米", [("tile", 1, 2.0, 1.0, 0.03)]),
        # 裸尺寸按缺省尺度落轴：1.6 米对落地灯是总高。
        ("生成一个1.6米的落地灯", [("lamp", 1, 0.36, 0.36, 1.6)]),
        ("生成一个2.2米的衣柜", [("wardrobe", 1, 1.8, 0.6, 2.2)]),
        # 尺寸只归属离它最近的子类型：椅子不该跟着餐桌一起被拉长。
        (
            "生成一套餐桌椅，餐桌长1.8米",
            [("table", 1, 1.8, 0.8, 0.75), ("chair", 1, 0.45, 0.5, 0.9)],
        ),
        (
            "生成两把椅子和一张1.8米的桌子",
            [("chair", 2, 0.45, 0.5, 0.9), ("table", 1, 1.8, 0.8, 0.75)],
        ),
    ],
)
def test_fallback_plan_is_exactly_what_the_user_named(message, expected):
    items = fallback_object_plan(message)["objects"]

    assert [
        (i["subtype"], i["count"], i["width"], i["depth"], i["height"]) for i in items
    ] == expected


def test_fallback_plan_without_any_named_subtype_reports_the_gap_instead_of_substituting():
    """没命中任何预设时**不许**用具名预设顶替，必须如实报缺口。

    旧行为是 `match_subtype(text) or DEFAULT_SUBTYPE` —— 认不出就做一张桌子。
    那与"要桌子给房子"是同一个模式：用户拿到自己没要的东西，还以为系统理解对了。
    现在改成 `objects=[]` + `unsupported_objects=[原文]`，
    由计划阶段转成 unsupported 条目进交付清单（能力缺失只标记、不阻断）。
    """

    plan = fallback_object_plan("生成一个家具")

    assert plan["objects"] == []
    assert plan["unsupported_objects"] == ["生成一个家具"]
    assert plan["design_rationale"]


def test_fallback_plan_keeps_preset_items_and_carries_no_gap():
    plan = fallback_object_plan("生成一个桌子")

    assert [item["subtype"] for item in plan["objects"]] == ["table"]
    assert plan["unsupported_objects"] == []


def test_model_output_is_clamped_and_deduplicated():
    plan = normalize_object_plan(
        {
            "concept": "办公桌椅",
            "objects": [
                {"subtype": "chair", "count": 2, "width": 0.5, "depth": 0.5, "height": 9},
                {"subtype": "chair", "count": 3, "width": 0.4, "depth": 0.4, "height": 0.9},
            ],
            "design_rationale": ["按会议桌配套"],
        },
        "生成五把椅子",
    )

    objects = plan["objects"]
    assert len(objects) == 1
    assert objects[0]["count"] == 5           # 同子类型合并，数量相加
    assert objects[0]["width"] == 0.5         # 尺寸取较大者
    # height 被钳到 chair 的合理区间 (0.75, 1.05]
    assert objects[0]["height"] == pytest.approx(1.05)


def test_unknown_subtype_from_model_falls_back_to_the_named_subtype():
    """模型给了引擎没有的子类型时必须回落到用户原话，而不是照抄。"""

    plan = normalize_object_plan(
        {"objects": [{"subtype": "悬浮滑板", "count": 1}]},
        "生成一个桌子",
    )

    assert [item["subtype"] for item in plan["objects"]] == ["table"]


def test_every_normalized_subtype_belongs_to_the_closed_set():
    plan = normalize_object_plan(
        {"objects": [{"subtype": name, "count": 1} for name in FURNITURE_SUBTYPES]},
        "生成全套家具",
    )

    assert {item["subtype"] for item in plan["objects"]} == set(FURNITURE_SUBTYPES)
