"""交付对象类型判定：这次请求要的是建筑，还是单个物件。

判据是**单侧的**：只有"命中了建筑类型闭集"这一个条件判 ``architecture``，
其余一律 ``object``。反过来做（先枚举物件名、没命中就当建筑）是错的——

- 建筑类型是有限闭集，"不是建筑" ⟹ "是物件" 这个推理成立；
- 物件名是开放集，"不是已知物件" ⟹ "是建筑" 这个推理不成立，
  它只会把每个没被列举到的新物件名（小人、花瓶、路灯）都变成一栋房子。

代价是不再"建筑优先"：像"带家具的别墅"这种同时含物件词的说法，靠的仍是
闭集里的"别墅"命中，结论不变；而"生成一个书包"这类建筑词一个都没有的句子，
现在会正确地进物件链，而不是被兜底成住宅。

闭集本体（``_ARCHITECTURE_TYPE_KEYWORDS``）与唯一规则判据
（:func:`is_architecture_request`）都在 :mod:`.profile`；本模块只负责把
"intent 不参与分叉"这条策略叠在那个判据之上。
"""
from __future__ import annotations

from app.agent.state import TargetKind

from .profile import is_architecture_request


def detect_target_kind(message: str, intent: str = "generate") -> TargetKind:
    """按 intent + 建筑类型闭集判定交付对象类型。

    ``intent != "generate"`` 不做分叉：编辑/问答的对象永远是既有场景，
    下游按 ``architecture`` 走，避免"改桌子"被当成物件链。
    """

    if intent != "generate":
        return "architecture"
    return "architecture" if is_architecture_request(message) else "object"


__all__ = ["TargetKind", "detect_target_kind"]
