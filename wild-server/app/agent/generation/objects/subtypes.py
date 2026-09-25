"""家具子类型的受控词表 —— 物件方案、确定性兜底与提示词共用的**唯一事实源**。

数据来自知识库文档 `storage/knowledge_base/knowledge/components/furniture.md`
（后者又来自 `wild-core/src/primitive/geometry/furniture.ts` 中 `build*` 函数的真实几何）。

为什么代码里还要有一份：这里只承担两件确定性工作——
**关键词识别**（"餐桌" → `table`）与**缺省尺寸**（用户没说多大时给多少米）。
字段语义、朝向约定、编译后产出仍然只在 KB 里，生成提示词的 C 段以 RAG 检索结果为准。
两者若冲突，以 KB 为准，并同步修本表。

⚠️ 本表是闭集：`ObjectDecisions.subtype` 只能取这里的 key。物件方案不引入
引擎没有的子类型——那正是"方案批了却没人能生成"的来源。
"""

from __future__ import annotations

from typing import Any

#: 子类型 → 契约。字段含义：
#:   keywords       命中即认为用户要这个子类型（按声明顺序取第一个命中）
#:   width/depth/height  缺省尺寸（米）；height 的语义见 height_meaning
#:   height_range   该子类型 height 的合理区间（米），归一化时按此钳制
#:   height_meaning 写进提示词，告诉模型 height 指什么
FURNITURE_SUBTYPES: dict[str, dict[str, Any]] = {
    "table": {
        "keywords": ("餐桌", "长桌", "圆桌", "桌子", "桌", "table"),
        "width": 1.4, "depth": 0.8, "height": 0.75,
        "height_range": (0.68, 0.82),
        "height_meaning": "台面顶高",
    },
    "chair": {
        # 裸 "椅" 必须在：中文惯用复合词是"餐桌椅"（= 餐桌 + 椅），
        # 若只收 "椅子" 就会在 "餐桌椅" 里被 "餐桌" 的长词占位挤掉，用户拿不到椅子。
        "keywords": ("椅子", "餐椅", "座椅", "凳子", "凳", "椅", "chair"),
        "width": 0.45, "depth": 0.5, "height": 0.9,
        "height_range": (0.75, 1.05),
        "height_meaning": "含靠背的总高",
    },
    "sofa": {
        "keywords": ("沙发", "长凳", "卡座", "sofa"),
        "width": 1.9, "depth": 0.85, "height": 0.8,
        "height_range": (0.7, 0.95),
        "height_meaning": "含靠背的总高",
    },
    "bed": {
        "keywords": ("双人床", "单人床", "床", "床铺", "bed"),
        "width": 1.5, "depth": 2.0, "height": 1.0,
        "height_range": (0.85, 1.15),
        "height_meaning": "床头板高",
    },
    "wardrobe": {
        "keywords": ("衣柜", "大衣柜", "衣橱", "wardrobe"),
        "width": 1.8, "depth": 0.6, "height": 2.2,
        "height_range": (1.8, 2.5),
        "height_meaning": "柜体总高",
    },
    "bookshelf": {
        "keywords": ("书架", "书柜", "置物架", "储物架", "shelf", "bookshelf"),
        "width": 0.9, "depth": 0.32, "height": 2.0,
        "height_range": (1.5, 2.4),
        "height_meaning": "总高",
    },
    "nightstand": {
        "keywords": ("床头柜", "床边柜", "nightstand"),
        "width": 0.5, "depth": 0.42, "height": 0.55,
        "height_range": (0.45, 0.65),
        "height_meaning": "台面顶高",
    },
    "tv_cabinet": {
        "keywords": ("电视柜", "视听柜", "tv cabinet", "media console"),
        "width": 1.8, "depth": 0.42, "height": 0.5,
        "height_range": (0.4, 0.65),
        "height_meaning": "台面顶高",
    },
    "lamp": {
        "keywords": ("落地灯", "台灯", "地灯", "灯具", "灯", "lamp"),
        "width": 0.36, "depth": 0.36, "height": 1.6,
        "height_range": (0.3, 2.0),
        "height_meaning": "总高（width/depth 是灯罩直径；本子类型不发光，要真实照明请用 light 组件）",
    },
    "tile": {
        "keywords": ("地毯", "垫板", "地毯板", "tile"),
        "width": 1.6, "depth": 1.0, "height": 0.03,
        "height_range": (0.01, 0.08),
        "height_meaning": "板厚",
    },
}

#: 物件方案可以使用的构件类型（`ObjectDecisions.objects[].kind` 的闭集）。
#:
#: 两条**表达通道**，不是为某个名字写的规则：
#:
#: - ``furniture``：图鉴预设（`FURNITURE_SUBTYPES`，闭集）。命中预设时几何最精确，
#:   引擎有逐子类型的原生 builder；
#: - ``primitive``：通用几何组合（box/sphere/cylinder/profile_sweep）。**开放集出口**——
#:   预设命中不了的名字（小人、花瓶、路灯、机器人）都能用它表达，
#:   因为"几何方式"是闭集，而"物件名"是开放集；
#: - ``body``：引擎的简化人物元素（KB《构件参数》§十，status=partial）。
#:
#: 判据的落点在这里而不是在名字表里：**先看名字能不能落进闭集预设，落不进就走通用几何**。
#: 这样"生成一个桌子"与"生成一个小人"走的是同一条链的不同出口，
#: 不需要为"小人"单独写任何规则。
OBJECT_COMPONENT_KINDS: tuple[str, ...] = ("furniture", "primitive", "body")

#: 图鉴预设的表达通道名（= `OBJECT_COMPONENT_KINDS` 的第一项，单独取名便于阅读）。
PRESET_KIND = "furniture"

#: 通用几何通道名。
GENERIC_KIND = "primitive"

#: 引擎简化人物通道名。
BODY_KIND = "body"

#: 🔴 用于**尺度参照**的子类型：`default_size` / `long_axis` / `closest_axis` 在
#: 传入未注册子类型时要有一个可读的参照，取 `table`（尺寸容差最大）。
#:
#: ⚠️ 它**不是**兜底替身：这几个函数只处理"已知子类型下的缺省尺寸"，
#: 不会把用户点名的物件换成桌子。曾经这里叫 `DEFAULT_SUBTYPE` 并被
#: `fallback_object_plan` 用来"用户没点名就做一张桌子"——
#: 那个用法已删除，理由见 `planning.fallback_object_plan`。
_SCALE_REFERENCE_SUBTYPE = "table"


def subtype_catalog() -> list[dict[str, Any]]:
    """给提示词用的紧凑子类型表：只给模型真正需要的字段。"""

    return [
        {
            "subtype": subtype,
            "height_meaning": spec["height_meaning"],
            "default_size_m": [spec["width"], spec["depth"], spec["height"]],
            "height_range_m": list(spec["height_range"]),
        }
        for subtype, spec in FURNITURE_SUBTYPES.items()
    ]


def keyword_spans(text: str) -> list[tuple[int, int, str]]:
    """返回**互不重叠**的 `(起点, 终点, 子类型)`，按起点升序。

    与 `find_matches` 同一套占位算法（关键词长度降序贪婪），区别只在于
    这里**不按子类型去重**——同一个子类型出现两次就返回两条。
    需要按"谁离尺寸短语最近"来归属尺寸时，必须看到全部出现位置，
    只留第一次会漏掉"生成餐桌椅，餐桌长1.8米"里第二个"餐桌"。
    """

    haystack = str(text or "")
    if not haystack:
        return []

    occurrences: list[tuple[int, int, int, str]] = []
    for subtype, spec in FURNITURE_SUBTYPES.items():
        for keyword in spec["keywords"]:
            start = haystack.find(keyword)
            while start >= 0:
                occurrences.append((start, start + len(keyword), len(keyword), subtype))
                start = haystack.find(keyword, start + 1)

    # 长度降序优先占位；同长时按起点、再按子类型名保证确定性。
    occurrences.sort(key=lambda item: (-item[2], item[0], item[3]))
    taken: list[tuple[int, int]] = []
    spans: list[tuple[int, int, str]] = []
    for start, end, _, subtype in occurrences:
        if any(not (end <= taken_start or start >= taken_end) for taken_start, taken_end in taken):
            continue
        taken.append((start, end))
        spans.append((start, end, subtype))
    spans.sort(key=lambda item: item[0])
    return spans


def find_matches(text: str) -> list[tuple[int, str]]:
    """返回 `(起点, 子类型)`，按起点升序；**重叠的关键词只保留最长的那个**。

    为什么不能简单做"子串并集"：中文里短词常被长词包含——"床头柜"含"床"、
    "双人床"含"床"、"餐桌椅"含"餐桌"。直接取并集会把"生成一个床头柜"
    识别成"床 + 床头柜"两件东西，用户会拿到一张多余的床。

    做法是按关键词长度**降序贪婪占位**：长词先占区间，被它覆盖的短词不再单独成项；
    互不重叠的短词照常各自成项（这正是"餐桌椅"能同时给出 table 与 chair 的原因）。
    """

    # 同一子类型多次命中只留第一次：数量由 `count` 表达，不由重复条目表达。
    seen: set[str] = set()
    ordered: list[tuple[int, str]] = []
    for start, _, subtype in keyword_spans(text):
        if subtype in seen:
            continue
        seen.add(subtype)
        ordered.append((start, subtype))
    return ordered


def match_subtype(text: str) -> str | None:
    """用户点名的**第一个**子类型；没有命中返回 None。

    只有一个命中时它就是答案；多个命中时取最靠前的那个（中文习惯上先说的更主要）。
    语义推断仍是模型的活，这里只做模型不可用时的兜底。
    """

    matched = find_matches(text)
    return matched[0][1] if matched else None


def matched_subtypes(text: str) -> list[str]:
    """用户提到的所有子类型，按出现位置排序、已去重。

    "生成一套餐桌椅"会给出 `["table", "chair"]`——两个词都在，正是需求的全貌。
    """

    return [subtype for _, subtype in find_matches(text)]


def default_size(subtype: str) -> tuple[float, float, float]:
    spec = FURNITURE_SUBTYPES.get(subtype) or FURNITURE_SUBTYPES[_SCALE_REFERENCE_SUBTYPE]
    return float(spec["width"]), float(spec["depth"]), float(spec["height"])


def long_axis(subtype: str) -> str:
    """该子类型**水平长边**对应的字段名（`"width"` 或 `"depth"`）。

    用户说"长 1.8 米"时，指的是家具最长的水平边——但它未必是 `width`：
    餐桌的长边是 `width`（1.4 > 0.8），床的长边却是 `depth`（2.0 > 1.5）。
    把这条判断放在目录旁边，`planning._requested_size` 才不会把床的"长"塞进 width。
    等长时取 `width`：此时两者等价，取哪个都不改变形状。
    """

    spec = FURNITURE_SUBTYPES.get(subtype) or FURNITURE_SUBTYPES[_SCALE_REFERENCE_SUBTYPE]
    return "depth" if float(spec["depth"]) > float(spec["width"]) else "width"


def closest_axis(subtype: str, value: float) -> str:
    """用户只给一个**不带轴名**的尺寸（"一张1.8米的桌子"）时，落到哪条轴。

    依据是**缺省值的尺度**而不是语序：1.6 米对落地灯只能是 `height`（灯罩才 0.36），
    对餐桌只能是 `width`（1.4），2.2 米对衣柜只能是 `height`（柜高 2.2）。
    比的是相对偏差 `|v - default| / default`——用相对值才能让"0.5 米的床头柜"
    在 0.5/0.42/0.55 之间选对，而不是被绝对差拽向数值大的那条轴。
    """

    spec = FURNITURE_SUBTYPES.get(subtype) or FURNITURE_SUBTYPES[_SCALE_REFERENCE_SUBTYPE]
    candidates = {
        "width": float(spec["width"]),
        "depth": float(spec["depth"]),
        "height": float(spec["height"]),
    }
    return min(candidates, key=lambda axis: abs(value - candidates[axis]) / candidates[axis])


__all__ = [
    "BODY_KIND",
    "FURNITURE_SUBTYPES",
    "GENERIC_KIND",
    "OBJECT_COMPONENT_KINDS",
    "PRESET_KIND",
    "closest_axis",
    "default_size",
    "find_matches",
    "keyword_spans",
    "long_axis",
    "match_subtype",
    "matched_subtypes",
    "subtype_catalog",
]
