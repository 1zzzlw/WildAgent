"""能力缺口判定（《动态节点设计规划》§8.1）。

政策只有一条：**能力缺失只标记、不阻断**。无知识分片、无执行路径、宿主不可用的
要求一律转成 ``unsupported`` 条目——它们不派发、不进循环，但会进交付清单，让用户
看见"这件事系统现在做不到"。把一份本来能出图的请求判死，用户拿到的是一张图都没有。

这份表是**数据**：新增一个"暂时做不到的能力"只加一条记录，不改判定逻辑，也不新增
``op``。它与 §2.4 的能力清单是同一枚硬币的两面——清单里有的才派发，这里列的是
已知做不了、必须说明的。

注意区分两种"做不了"：

- **能力缺失**（本模块）：主链根本不设计室内平面、不处理场地语义。
  标记为 ``unsupported``，附带用户可读的说明。
- **发散需求**（调度层面）：用户想加的东西系统支持，只是这次计划里没有——
  那由 ``replanner`` 追加条目解决，不是能力缺失。

⚠️ 2026-09-23 移除 `furniture` 条目：它当时写着"引擎没有家具构件"，但引擎有
（`wild-core/src/primitive/geometry/furniture.ts` 十个子类型）、schema 合法、
`spatial_tools` 有专门校验，缺的只是生成侧注册。这是一条**误判**，
已被 `audit_capability_parity.py` 的 ⑥ 项抓出。旧的错误声明比没有更糟：
模型会拿它当硬约束，于是"生成一个桌子"被改写成"给你一个住宅当替代"。

同一次改动把"**房间里**放点家具"这类需求归到 `floor_plan`：它缺的不是家具，
而是"哪一间房"——家具能单独生成，房间划分不能。原先挂在 `furniture` 名下会把
一条室内缺陷写成一件构件不存在，用户照着提示也找不出真正的原因。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.plan.contracts import ItemRun, PlanItem


@dataclass(frozen=True)
class CapabilityGap:
    """一类已知做不到的能力：触发词 + 面向用户的说明。"""

    id: str
    label: str
    #: 命中任一触发词即判定该能力被要求（中文按子串、英文按 casefold 子串）。
    terms: tuple[str, ...]
    #: 说明"缺的是什么、现在能给什么"，直接进交付清单，所以必须对用户可读。
    notice: str
    #: 该能力对应的目标（知道自己在说什么，便于后续按 kind 接入真正实现）。
    target: str = ""
    #: 命中后额外写入交付清单的替代路径提示（可选）。
    fallback: str = ""


#: 主链当前的能力缺口。判定准则是"系统真的做不到"，不是"表述不规范"。
CAPABILITY_GAPS: tuple[CapabilityGap, ...] = (
    CapabilityGap(
        id="floor_plan",
        label="室内房间平面",
        # "房间里/房间内/室内"是**室内语义**的触发词，不是房间数量词：用户要求把东西
        # 放进房间，就需要房间划分，而主链只有墙和楼板、没有房间。
        # 这不是"家具做不到"——家具能做（见文件头 2026-09-23 的说明），
        # 缺的是"哪一间房"这件事。
        terms=(
            "房间位置", "房间布局", "功能分区平面", "内部隔墙", "房间分隔", "户型图",
            "房间里", "房间内", "室内",
        ),
        target="architecture.floor_plan",
        notice="当前不设计室内房间位置、房间布局与内部隔墙，本次不会给出房间平面。",
        fallback="体量、外轮廓、门窗洞口与立面尺寸照常生成。",
    ),
    CapabilityGap(
        id="site_semantics",
        label="场地语义",
        terms=("车库", "后院", "花园", "garage", "backyard", "garden"),
        target="architecture.semantic_space",
        notice="当前不处理场地语义（车库、后院、花园等室外空间划分）。",
        fallback="建筑主体照常生成，场地关系需要后续能力支持。",
    ),
)

#: 交付媒介与系统产物不一致：不产出二维平面图，但体量与立面会以图纸 SVG 呈现。
#: 这类表述**不算能力缺失**（图的语义都在），只记一条提示，不阻断、不判死。
PRESENTATION_MEDIUM_TERMS: tuple[str, ...] = (
    "平面草图", "平面图", "二维平面", "2d 平面", "2d平面", "剖面图",
)


def _hit(text: str, terms: tuple[str, ...]) -> str | None:
    folded = text.casefold()
    for term in terms:
        if term.casefold() in folded:
            return term
    return None


def detect_capability_gaps(user_message: str) -> list[CapabilityGap]:
    """按用户原话判定命中的能力缺口，顺序与声明顺序一致（确定性）。"""

    text = str(user_message or "")
    if not text:
        return []
    return [gap for gap in CAPABILITY_GAPS if _hit(text, gap.terms)]


def requested_presentation_medium(user_message: str) -> str:
    """命中的交付媒介词（空串表示没提）。只用于提示，不参与判定。"""

    return _hit(str(user_message or ""), PRESENTATION_MEDIUM_TERMS) or ""


def capability_gap_items(user_message: str) -> list[PlanItem]:
    """把命中的能力缺口转成 ``unsupported`` 条目。

    这些条目**必须**是终态：``poll_runnable`` 只取 ``ready``，所以它们不会被派发，
    也不会让循环多转一圈；它们唯一的作用是出现在 ``terminal_stats`` 与交付清单里。
    """

    items: list[PlanItem] = []
    for gap in detect_capability_gaps(user_message):
        notice = gap.notice + (f"（{gap.fallback}）" if gap.fallback else "")
        items.append(
            PlanItem(
                id=f"unsupported_{gap.id}_01",
                op="validate",  # 借 validate 的语义：这是"判定结论"，不是一件待做的工作
                kind=gap.id,
                label=f"能力缺失：{gap.label}",
                target={"capability": gap.target or gap.id, "matched": True},
                params={"notice": notice, "unsupported": True},
                status="unsupported",
                run=ItemRun(max_attempts=1, evidence=notice),
            )
        )
    return items


def capability_notes(user_message: str) -> list[dict[str, Any]]:
    """给 state/前端用的能力缺口说明（与条目同源，避免两处各写一份话术）。"""

    return [
        {"id": gap.id, "label": gap.label, "notice": gap.notice, "fallback": gap.fallback}
        for gap in detect_capability_gaps(user_message)
    ]


def object_gap_items(plan: dict | None) -> list[PlanItem]:
    """物件方案里"点名了但表达不出来"的物件 → ``unsupported`` 条目。

    与 `capability_gap_items` 同一口径（§8.1：能力缺失只标记、不阻断），
    区别是这里的缺口来自**本轮方案**而不是静态能力表：模型既没命中图鉴预设、
    也没给出可用的通用几何零件，于是方案如实记下"做不了"。

    🔴 为什么要专门留这条通道：物件名是开放集，模型总有认不出的时候。
    以前的兜底是**用品类相近的预设顶替**（认不出就做一张桌子），
    用户拿到自己没要的东西还以为系统理解对了。现在改成如实标记：
    场景可以是空的，但清单里必须说明白"哪一件没做成、为什么"。

    这些条目和 `capability_gap_items` 一样是**终态**：``status="unsupported"``
    不会被 `poll_runnable` 取走，只进 `terminal_stats` 与交付清单。
    """

    if not isinstance(plan, dict):
        return []
    raw = plan.get("unsupported_objects")
    if not isinstance(raw, list):
        return []

    items: list[PlanItem] = []
    for index, entry in enumerate(raw[:24], start=1):
        name = str(entry).strip()[:60]
        if not name:
            continue
        notice = (
            f"本次点名了「{name}」，但它既没有命中可用的物件预设，也没有给出可生成的"
            "几何组合；系统未用品类相近的物件顶替，因此本件没有产出。"
        )
        items.append(
            PlanItem(
                id=f"unsupported_object_{index:02d}",
                op="validate",  # 与能力缺口同处理：这是"判定结论"，不是一件待做的工作
                kind="object_expression",
                label=f"未能表达：{name}",
                target={"capability": "object.expression", "request": name},
                params={"notice": notice, "unsupported": True},
                status="unsupported",
                run=ItemRun(max_attempts=1, evidence=notice),
            )
        )
    return items


__all__ = [
    "CAPABILITY_GAPS",
    "PRESENTATION_MEDIUM_TERMS",
    "CapabilityGap",
    "capability_gap_items",
    "capability_notes",
    "detect_capability_gaps",
    "object_gap_items",
    "requested_presentation_medium",
]
