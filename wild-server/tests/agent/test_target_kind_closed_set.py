"""目标类型判定必须建在**建筑类型闭集**上，不能建在物件名词表上。

背景（2026-09-23，"生成一个小人"测试用例）：`detect_target_kind` 曾用一张
家具名词表判"是不是物件"，没命中就兜底成建筑。物件名是开放集，于是每一个
没被列举到的名字（小人、花瓶、路灯、机器人）都会变成一栋房子 —— 用户拿到
一个他没要的住宅。

这组测试锁住两条不变量：

1. **判据单侧**：只有"命中建筑类型闭集"才判 architecture，其余一律 object；
2. **闭集自洽**：`_PROFILE_TYPE_WORDS` 里每个选档词都必须被
   `is_architecture_request` 认成建筑，否则会出现"选了档却说不是建筑"。
"""

from __future__ import annotations

import pytest

from app.agent.generation.architecture import (
    is_architecture_request,
    match_architecture_profile_id,
)
from app.agent.generation.architecture import profile as profile_module
from app.agent.routing import detect_target_kind


#: 任意命名物件：**不能**因为"名字没被列举过"就被判成建筑。
OBJECT_CASES = [
    "生成一个桌子",
    "生成一个小人",
    "生成一个花瓶",
    "生成一个路灯",
    "生成一个机器人",
    "生成一个雕塑",
    "生成一个盆栽",
    "生成一张沙发",
    "生成一个书包",
]

#: 建筑类型闭集内的说法：命中即 architecture。
ARCHITECTURE_CASES = [
    "生成一个欧式别墅",
    "帮我设计一个小木屋",
    "生成一个两层的住宅",
    "生成一栋写字楼",
    "生成一个学校",
    "生成一个地铁站",
    "生成一个厂房",
    "生成一个凉亭",
    "生成一座教堂",
    "生成一个体育馆",
    "生成一栋房子",
    "带家具的别墅",
]


@pytest.mark.parametrize("message", OBJECT_CASES)
def test_unknown_object_names_are_not_architecture(message):
    assert is_architecture_request(message) is False
    assert detect_target_kind(message, "generate") == "object"


@pytest.mark.parametrize("message", ARCHITECTURE_CASES)
def test_architecture_type_words_are_architecture(message):
    assert is_architecture_request(message) is True
    assert detect_target_kind(message, "generate") == "architecture"


@pytest.mark.parametrize("profile_id, words", sorted(profile_module._PROFILE_TYPE_WORDS.items()))
def test_every_profile_type_word_is_recognized_as_architecture(profile_id, words):
    """选了档就必须也认成建筑：两个判据共用一份闭集，不能各说各话。"""

    for word in words:
        assert is_architecture_request(f"生成一个{word}") is True, (
            f"{profile_id} 的类型词 {word!r} 没被 is_architecture_request 认成建筑"
        )
        assert match_architecture_profile_id(f"生成一个{word}") is not None


def test_architecture_closed_set_covers_profile_words_by_construction():
    closed = set(profile_module._ARCHITECTURE_TYPE_WORDS)
    for words in profile_module._PROFILE_TYPE_WORDS.values():
        assert set(words) <= closed


@pytest.mark.parametrize("intent", ["edit", "chat"])
def test_non_generate_intent_never_becomes_object(intent):
    """edit/chat 不做目标分叉（下游按 architecture 走），避免"改桌子"被当成物件链。"""

    assert detect_target_kind("生成一个小人", intent) == "architecture"


def test_object_name_keyword_table_is_gone():
    """防回归：开放集的物件名词表不能再出现在路由模块里。

    它一回来，"没命中→建筑"的兜底就会跟着回来，而那正是"要桌子给房子"的成因。
    """

    from app.agent import routing

    assert not hasattr(routing, "OBJECT_TARGET_KEYWORDS")
    assert not hasattr(routing, "ARCHITECTURE_TARGET_KEYWORDS")


def test_empty_message_is_not_architecture():
    assert is_architecture_request("") is False
    assert is_architecture_request(None) is False
