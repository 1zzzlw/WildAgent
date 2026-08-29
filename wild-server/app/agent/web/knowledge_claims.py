"""网络知识整理：结构化声明 + WILD 能力映射。

网页事实必须先经过能力映射才能进入上下文：只有当前 engine 支持的组件/字段
可以原样保留；不支持的术语必须降级到现有表达；无法降级的一律丢弃。绝不允许
把网页术语直接变成不存在的 WILD 类型。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger

# 引擎支持的类型 = 组件（component_registry）+ 基础元素（geometry.elements）。
# wall/floor/stair/column/beam 是 elements 不是 components，必须一并纳入能力白名单。
_BASE_ELEMENT_TYPES = {"wall", "floor", "stair", "column", "beam", "roof", "opening", "furniture"}


def _supported_component_types() -> set[str]:
    try:
        from app.agent.component_registry import get_implemented_components
        components = {cfg.component_type for cfg in get_implemented_components()}
    except Exception:
        components = {"door", "window", "roof", "railing", "canopy", "balcony",
                      "ramp", "bay_window", "cornice", "chimney", "light"}
    return components | _BASE_ELEMENT_TYPES


# 降级映射：网页术语 → 当前支持的表达（来自 capability 边界文档）。
_KNOWN_DEGRADATIONS: dict[str, str] = {
    "mullion": "wall + window + primitive.box（竖梃/横梃用几何表达，无原生类型）",
    "竖梃": "wall + window + primitive.box（无原生类型，用几何表达）",
    "横梃": "wall + window + primitive.box（无原生类型，用几何表达）",
    "龙骨": "wall + primitive.box（幕墙龙骨用几何表达，无原生类型）",
    "curtain wall panel": "wall（壳）+ window 窗带 + primitive.box（龙骨）",
    "elevator shaft": "wall（井道围合）+ floor（各层楼板）",
    "core wall": "wall（核心筒墙体围合）",
    "glass facade": "wall + window（玻璃幕墙壳）",
    "balustrade": "railing 组件",
    "eaves": "cornice 组件或 roof 出檐",
    "parapet": "wall（矮墙）",
    "hipped roof": "roof roofType=hip",
    "gable roof": "roof roofType=gable",
    "flat roof": "roof roofType=flat",
    "dome roof": "roof roofType=dome",
    "chinese curved roof": "roof roofType=chinese_curved",
    "pagoda roof": "roof roofType=chinese_pagoda",
}


@dataclass
class KnowledgeClaim:
    """一条结构化网络知识声明。"""

    claim: str
    topic: str
    applicable_building_types: list[str] = field(default_factory=list)
    region: str = ""              # 适用地区（如 "中国"）
    year: str = ""                # 规范年份/来源年份
    norm_code: str = ""           # 规范号（如 GB50016-2014）
    source_url: str = ""
    source_org: str = ""
    confidence: str = "unknown"   # high/medium/low/unknown
    # 能力映射结果：
    mapped_supported: list[str] = field(default_factory=list)   # 命中的支持组件
    degraded_to: list[str] = field(default_factory=list)        # 降级映射
    unmapped_terms: list[str] = field(default_factory=list)     # 无法映射，丢弃
    usable: bool = False          # 是否可用于本次上下文（有 supported 或 degraded）

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 中文构件词 → 引擎支持组件（用于中文声明的能力映射）。
_CN_COMPONENT_ALIASES: dict[str, str] = {
    "墙体": "wall", "墙": "wall", "隔墙": "wall", "幕墙": "wall",
    "楼板": "floor", "地板": "floor", "楼梯": "stair", "台阶": "stair",
    "柱子": "column", "柱": "column", "梁": "beam",
    "门": "door", "窗": "window", "窗户": "window", "屋顶": "roof",
    "栏杆": "railing", "扶手": "railing",
    "雨棚": "canopy", "雨篷": "canopy", "阳台": "balcony", "露台": "balcony",
    "坡道": "ramp", "凸窗": "bay_window", "飘窗": "bay_window",
    "檐口": "cornice", "飞檐": "cornice", "烟囱": "chimney", "灯具": "light",
}


def _extract_terms(claim: str) -> list[str]:
    """从声明文本粗提取候选术语（英文小写 + 中文词 + 中文构件别名）。"""
    import re
    english = re.findall(r"[a-zA-Z][a-zA-Z ]{2,30}", claim.lower())
    chinese = re.findall(r"[一-鿿]{2,12}", claim)
    terms: list[str] = []
    for term in english + chinese:
        cleaned = " ".join(term.split())
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    # 中文构件别名 → 引擎支持组件（追加到术语列表，让后续映射命中）。
    for cn, engine_term in _CN_COMPONENT_ALIASES.items():
        if cn in claim and engine_term not in terms:
            terms.append(engine_term)
    return terms


def map_claim_to_capability(claim: KnowledgeClaim) -> KnowledgeClaim:
    """把声明对照引擎支持组件 + 降级映射做能力映射。

    匹配到支持的组件类型 → mapped_supported；
    匹配到降级映射 → degraded_to；
    其余英文术语无法映射 → unmapped_terms（声明仍可能可用，只要前者任一非空）。
    """
    supported = _supported_component_types()
    terms = _extract_terms(claim.claim)
    mapped: list[str] = []
    degraded: list[str] = []
    unmapped: list[str] = []
    for term in terms:
        matched_supported = term in supported
        if matched_supported:
            mapped.append(term)
            continue
        degradation = _KNOWN_DEGRADATIONS.get(term)
        if degradation:
            degraded.append(f"{term} → {degradation}")
            continue
        # 只把明显是构件/术语的英文词记为 unmapped，避免中文常见词误报。
        if term.isascii() and len(term) > 3:
            unmapped.append(term)

    # 降级映射额外对原始声明做子串匹配：中文术语（竖梃/横梃/龙骨）常被
    # 中文分词切进长词里，单靠切分后的 term 匹配不到。
    for phrase, degradation in _KNOWN_DEGRADATIONS.items():
        if phrase in claim.claim and phrase not in terms:
            degraded.append(f"{phrase} → {degradation}")
    claim.mapped_supported = sorted(set(mapped))
    claim.degraded_to = sorted(set(degraded))
    claim.unmapped_terms = sorted(set(unmapped))
    claim.usable = bool(claim.mapped_supported or claim.degraded_to)
    return claim


def filter_usable_claims(claims: list[KnowledgeClaim]) -> tuple[list[KnowledgeClaim], list[KnowledgeClaim]]:
    """把声明分为可用/丢弃两组。可用 = 有 supported 或 degraded 映射。

    丢弃组仍保留在诊断里（供审核），但不进入临时上下文。
    """
    usable = [c for c in claims if c.usable]
    dropped = [c for c in claims if not c.usable]
    return usable, dropped
