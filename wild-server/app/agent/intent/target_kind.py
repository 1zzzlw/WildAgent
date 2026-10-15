"""生成目标类型识别；关键词只用于目标类型兜底，不参与建筑设计。"""

from __future__ import annotations

from app.agent.state import TargetKind


_ARCHITECTURE_TYPE_KEYWORDS: tuple[str, ...] = (
    "地铁",
    "地下车站",
    "站台层",
    "地下站",
    "隧道",
    "超高层",
    "高层",
    "摩天",
    "塔楼",
    "体育场",
    "体育馆",
    "游泳馆",
    "航站楼",
    "高铁站",
    "火车站",
    "客运站",
    "剧院",
    "音乐厅",
    "会展",
    "大会堂",
    "工厂",
    "厂房",
    "仓库",
    "车间",
    "物流中心",
    "机库",
    "温室",
    "粮仓",
    "园林",
    "水榭",
    "凉亭",
    "亭子",
    "游廊",
    "佛寺",
    "寺庙",
    "道观",
    "清真寺",
    "教堂",
    "礼拜殿",
    "办公",
    "写字楼",
    "学校",
    "幼儿园",
    "教学楼",
    "博物馆",
    "图书馆",
    "医院",
    "商场",
    "超市",
    "酒店",
    "法院",
    "养老院",
    "别墅",
    "住宅",
    "民居",
    "民房",
    "公寓",
    "洋房",
    "排屋",
    "联排",
    "独栋",
    "自建房",
    "木屋",
    "小屋",
    "房子",
    "房屋",
    "house",
    "villa",
    "cottage",
    "cabin",
)

_GENERIC_ARCHITECTURE_WORDS: tuple[str, ...] = (
    "建筑",
    "构筑物",
    "场地",
    "大厦",
    "商厦",
    "楼",
    "屋",
    "房",
    "塔",
    "阁",
    "苑",
    "站",
    "厂",
)

_ARCHITECTURE_TYPE_WORDS: tuple[str, ...] = (
    tuple(dict.fromkeys(_ARCHITECTURE_TYPE_KEYWORDS)) + _GENERIC_ARCHITECTURE_WORDS
)


def is_architecture_request(user_message: str) -> bool:
    """检查用户原话是否包含建筑类型词。"""
    message = str(user_message or "").lower()
    if not message:
        return False
    return any(word in message for word in _ARCHITECTURE_TYPE_WORDS)


def detect_target_kind(message: str, intent: str = "generate") -> TargetKind:
    """生成请求区分建筑和物件；其他请求使用统一默认值。"""
    if intent != "generate":
        return "architecture"
    return "architecture" if is_architecture_request(message) else "object"
