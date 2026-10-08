"""目标类型判定必须建在**建筑类型闭集**上，不能建在物件名词表上。

背景（2026-09-23，"生成一个小人"测试用例）：`detect_target_kind` 曾用一张
家具名词表判"是不是物件"，没命中就兜底成建筑。物件名是开放集，于是每一个
没被列举到的名字（小人、花瓶、路灯、机器人）都会变成一栋房子 —— 用户拿到
一个他没要的住宅。

这组测试锁住两条不变量：

1. **判据单侧**：只有"命中建筑类型闭集"才判 architecture，其余一律 object；
2. **闭集自洽**：`_ARCHITECTURE_TYPE_KEYWORDS` 里每个类型词都必须被
   `is_architecture_request` 认成建筑。

历史注记：这份词表曾经还承担"关键词选档"职责（住宅/公建/厂房…八档），
2026-09-29 已删除（用户决策：选档白名单限制模型表达、且无法维护）——
类型词现在**只**服务路由闭集，不再表达任何设计先验。
"""

from __future__ import annotations

import pytest

from app.agent.generation.architecture import (
    detect_target_kind,
    is_architecture_request,
)
from app.agent.generation.architecture import profile as profile_module


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


@pytest.mark.parametrize("word", profile_module._ARCHITECTURE_TYPE_KEYWORDS)
def test_every_type_word_is_recognized_as_architecture(word):
    """闭集里的每个类型词都必须被认成建筑，路由判据不能自相矛盾。"""

    assert is_architecture_request(f"生成一个{word}") is True, (
        f"类型词 {word!r} 没被 is_architecture_request 认成建筑"
    )


def test_architecture_closed_set_covers_type_words_by_construction():
    closed = set(profile_module._ARCHITECTURE_TYPE_WORDS)
    assert set(profile_module._ARCHITECTURE_TYPE_KEYWORDS) <= closed


def test_profile_selection_is_deleted_and_custom_is_the_only_profile():
    """防回归：关键词选档已删除，档案表只剩 custom（物理边界，不做设计锚定）。"""

    assert set(profile_module._ARCHITECTURE_PROFILES) == {"custom"}
    profile = profile_module.detect_architecture_profile("欧式古典柱廊殿宇")
    assert profile["id"] == "custom"
    # custom 不做设计锚定：shapes / base_components 必须是全集语义（宽边界）。
    assert "courtyard" in profile["shapes"]
    assert "pavilion" in profile["shapes"]


@pytest.mark.parametrize("intent", ["edit", "chat"])
def test_non_generate_intent_never_becomes_object(intent):
    """edit/chat 不做目标分叉（下游按 architecture 走），避免"改桌子"被当成物件链。"""

    assert detect_target_kind("生成一个小人", intent) == "architecture"


def test_object_name_keyword_table_is_gone():
    """防回归：开放集的物件名词表不能再出现在路由模块里。

    它一回来，"没命中→建筑"的兜底就会跟着回来，而那正是"要桌子给房子"的成因。
    """

    from app.agent.generation.architecture import target_kind as target_kind_module
    from app.agent.intent import rules as rules_module

    # 判定的新家（architecture）与降级规则的新家（intent）都必须干净：
    # 物件名词表出现在任何一处，"没命中→建筑"的兜底就会跟着回来。
    for module in (target_kind_module, rules_module):
        assert not hasattr(module, "OBJECT_TARGET_KEYWORDS")
        assert not hasattr(module, "ARCHITECTURE_TARGET_KEYWORDS")


def test_empty_message_is_not_architecture():
    assert is_architecture_request("") is False
    assert is_architecture_request(None) is False
