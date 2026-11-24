"""物件（非建筑）生成链。

目录边界很清楚：**只有"方案"这一层是物件专有**。
材质确定后的计划、执行、合并、校验复用建筑链的同一套节点——
因为它们的输入是 `DesignDocument` 与 `design_brief`，与"物件还是建筑"无关。

    objects/subtypes.py  子类型闭集（关键词、缺省尺寸、height 语义）+ 两条表达通道
    objects/planning.py  方案归一化与确定性兜底
    objects/skeleton.py  空几何骨架 + 物件设计清单
    app/agent/workflows/design/objects.py  方案节点（LLM + 兜底）

任意命名物件走的是同一条链的两个出口：命中图鉴预设 → `furniture`（精确几何）；
没命中 → `primitive` 通用几何组合（开放集出口）。见 `subtypes.OBJECT_COMPONENT_KINDS`。
"""

from agent.utils.design.objects.planning import fallback_object_plan
from agent.utils.design.objects.planning import normalize_object_plan
from agent.utils.design.objects.skeleton import OBJECT_MATERIALS
from agent.utils.design.objects.skeleton import build_object_skeleton
from agent.utils.design.objects.skeleton import object_design_brief
from agent.utils.design.objects.subtypes import BODY_KIND
from agent.utils.design.objects.subtypes import FURNITURE_SUBTYPES
from agent.utils.design.objects.subtypes import GENERIC_KIND
from agent.utils.design.objects.subtypes import OBJECT_COMPONENT_KINDS
from agent.utils.design.objects.subtypes import PRESET_KIND

__all__ = [
    "BODY_KIND",
    "FURNITURE_SUBTYPES",
    "GENERIC_KIND",
    "OBJECT_COMPONENT_KINDS",
    "OBJECT_MATERIALS",
    "PRESET_KIND",
    "build_object_skeleton",
    "fallback_object_plan",
    "normalize_object_plan",
    "object_design_brief",
]
