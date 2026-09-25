"""物件方案的归一化与确定性兜底。

与建筑链的 `architecture/planning.py` 同构，但**不产出体量、立面与屋顶**：
归一化只负责"让方案合法"，不负责"让方案好看"——好看是模型的活。

归一化的四件事（全部确定性、可单测）：
1. 闭集：`kind` 只能取 `OBJECT_COMPONENT_KINDS`（furniture / primitive / body）；
   `furniture` 的 `subtype` 只能取 `FURNITURE_SUBTYPES` 的 key；
2. 钳制：尺寸落在 schema 允许的 (0, 50]、height 落在该子类型的合理区间、
   primitive 零件的 shape 与几何参数合法；
3. 去重：同 `(kind, subtype, name)` 只保留一条，数量用 `count` 表达；
4. **如实**：一条都归一化不出来时不再用预设顶替，而是返回"点名了但表达不了"
   （`unsupported_objects`），让下游标记而不是骗人。
"""

from __future__ import annotations

import re
from typing import Any

from .subtypes import (
    BODY_KIND,
    FURNITURE_SUBTYPES,
    GENERIC_KIND,
    OBJECT_COMPONENT_KINDS,
    PRESET_KIND,
    closest_axis,
    default_size,
    keyword_spans,
    long_axis,
    match_subtype,
    matched_subtypes,
)

#: schema 的硬边界（见 `design/contracts.py::ComponentObject`）。
_MAX_SIZE = 50.0
_MIN_SIZE = 0.05
_MAX_COUNT = 16
_MAX_OBJECTS = 24

#: `primitive` 零件的合法 shape（与 schema.json::$defs/primitive 的 oneOf 一致）。
PRIMITIVE_SHAPES: tuple[str, ...] = ("box", "sphere", "cylinder", "profile_sweep")

#: 单个物件最多几个零件。上限不是"够用即可"，而是防止模型把一次方案写成
#: 上千个体素球——那是 `dense_brick` 该干的事，用 primitive 硬堆只会拖垮编译。
_MAX_PARTS = 64

#: `body` 的枚举参数（KB《构件参数》§十）。
BODY_BUILDS: tuple[str, ...] = ("lean", "athletic", "stout")
BODY_HEAD_SHAPES: tuple[str, ...] = ("round", "oval", "angular")

_NUMBER = r"(\d+(?:\.\d+)?)"


def _clamp(value: object, low: float, high: float, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float("inf"), float("-inf")):
        return fallback
    return round(max(low, min(high, number)), 3)


def _clamp_count(value: object) -> int:
    if isinstance(value, bool):
        return 1
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
    return max(1, min(_MAX_COUNT, number))


_CN_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_NUM_CHARS = "".join(_CN_DIGITS)
#: 阿拉伯数字或中文数词。中文只支持口语里会说的那一档（一~九十九，
#: 如"两米""十二米"），不试图覆盖"壹佰贰拾"这类书面数字。
_NUM_TOKEN = rf"(?:\d+(?:\.\d+)?|[{_CN_NUM_CHARS}十]+)"
#: "一米八" → "1.8"，统一交给数字解析；末尾不接数字才算，避免"一米八个"误伤。
_CN_DECIMAL_METRE = re.compile(
    rf"([{_CN_NUM_CHARS}])米([{_CN_NUM_CHARS}])(?![\d{_CN_NUM_CHARS}十])"
)
_AXIS_CHARS = "长宽高"
#: 量词表：数量短语里允许出现在数词与名词之间的字。
_CLASSIFIERS = "个把张件条盏块套只口台面座"
#: 正向："长1.8米" / "宽度约2m"。
_FORWARD_DIM = re.compile(
    rf"([{_AXIS_CHARS}])(?:度)?\s*(?:约|大约)?\s*({_NUM_TOKEN})\s*(?:米|m|M)?"
)
#: 反向："1.8米长" / "两米宽"。必须在正向之后跑，且不能吃掉已被正向消费的数字——
#: 否则"长1.8宽0.9"里的"1.8宽"会把 1.8 记到宽度上。
_REVERSED_DIM = re.compile(
    rf"({_NUM_TOKEN})\s*(?:米|m|M)?\s*([{_AXIS_CHARS}])"
)
#: 裸尺寸："一张1.8米的桌子"——带单位但**不带轴名**。
#: 必须带单位（米/m）才认，否则"四把椅子"的 4 会被当成尺寸。
_BARE_DIM = re.compile(rf"({_NUM_TOKEN})\s*(?:米|m|M)")
_AXIS_NAMES = {"长": "length", "宽": "width", "高": "height"}


def _to_metres(token: str) -> float | None:
    """阿拉伯数字与中文数词统一转 float；不认识返回 None。"""

    token = (token or "").strip()
    if not token:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return float(token)
    if token == "十":
        return 10.0
    if "十" in token:
        left, _, right = token.partition("十")
        if left and left not in _CN_DIGITS:
            return None
        if right and right not in _CN_DIGITS:
            return None
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return float(tens * 10 + ones)
    if len(token) == 1 and token in _CN_DIGITS:
        return float(_CN_DIGITS[token])
    return None


def _dimension_hits(text: str) -> list[tuple[int, str, float]]:
    """找出原话里显式写出的尺寸，返回 `(位置, 轴, 数值)`。

    轴 ∈ `{"length", "width", "height"}`——这是**口语轴的语义**，不是 WILD 字段名：
    "长"到底落 `width` 还是 `depth` 由子类型决定（见 `_requested_size`）。
    "位置"取匹配的**右端**，用于把尺寸归属给最近的前置子类型。

    正向写法（"长1.8"）先行并占位，反向写法（"1.8长"）只在不撞已占区间时才采纳，
    裸写法（"1.8米"）最后兜。这是为了"长1.8宽0.9高0.75"这种紧凑连写：正向三个都命中，
    反向的"1.8宽""0.9高"全部落在已消费区间里被丢弃，不会把数字串位。

    裸写法返回轴名 `"bare"`——它没有轴信息，落哪条轴要由子类型决定
    （见 `_requested_size` 与 `subtypes.closest_axis`）。
    """

    text = _CN_DECIMAL_METRE.sub(
        lambda m: f"{_CN_DIGITS[m.group(1)]}.{_CN_DIGITS[m.group(2)]}", str(text or "")
    )
    if not text:
        return []

    consumed: list[tuple[int, int]] = []
    per_axis: dict[str, tuple[int, float]] = {}

    def _record(start: int, end: int, axis: str, token: str) -> None:
        value = _to_metres(token)
        if value is None or axis is None:
            return
        consumed.append((start, end))
        current = per_axis.get(axis)
        if current is None or end < current[0]:
            per_axis[axis] = (end, value)

    def _occupied(start: int, end: int) -> bool:
        return any(not (end <= c_start or start >= c_end) for c_start, c_end in consumed)

    for match in _FORWARD_DIM.finditer(text):
        _record(match.start(), match.end(), _AXIS_NAMES.get(match.group(1)), match.group(2))

    for match in _REVERSED_DIM.finditer(text):
        start, end = match.start(), match.end()
        if _occupied(start, end):
            continue
        _record(start, end, _AXIS_NAMES.get(match.group(2)), match.group(1))

    for match in _BARE_DIM.finditer(text):
        if _occupied(match.start(), match.end()):
            continue
        _record(match.start(), match.end(), "bare", match.group(1))

    return sorted((end, axis, value) for axis, (end, value) in per_axis.items())


def _owner_subtype(position: int, spans: list[tuple[int, int, str]]) -> str | None:
    """尺寸短语归属于**距离最近**的子类型关键词，两侧都看。

    不能只找前置：中文定语在名词之前，裸尺寸几乎总是**先于**名词出现
    （"一张1.8米的桌子"），只看前置会让它落到上一句的"椅子"头上。
    同距时取**后随**的那个——这正是"定语在前"的语序造成的平局。
    短语离所有关键词都很远时（"生成餐桌和椅子，长1.8米"），
    仍然落到离它最近的那个，这是该情形下唯一不猜的答案。
    """

    best: tuple[tuple[int, int], str] | None = None
    for start, end, subtype in spans:
        if end <= position:
            key = (position - end, 1)      # 在前：同距时让位于后随者
        elif start >= position:
            key = (start - position, 0)
        else:
            key = (0, 0)                   # 区间本身覆盖该位置
        if best is None or key < best[0]:
            best = (key, subtype)
    if best is not None:
        return best[1]
    return spans[0][2] if spans else None


def _requested_size(user_message: str, subtype: str = "") -> dict[str, float]:
    """从用户原话里取**该子类型**明确写出的长/宽/高（米）。

    只认"长 1.8 米""宽1.2m""高0.75"这类显式写法，不推断。
    取不到就返回空字典，让缺省尺寸生效——猜尺寸比给缺省值更糟。

    水平面的四条规则（本函数唯一需要判断的地方）：
    - **归属**：一个尺寸短语只给离它最近的那个子类型（两侧都算，见 `_owner_subtype`）。
      否则"餐桌椅，餐桌长1.8米"会把 1.8 也算到椅子头上。
    - **"长"落在该子类型的长边**，而不是死认 `width`。餐桌长边是 `width`（1.4 > 0.8），
      床的长边却是 `depth`（2.0 > 1.5）；见 `subtypes.long_axis`。
    - **"宽"**：同句已给出"长"时落在另一条水平边（长/宽配对，对应"1.8×1.2"的写法）；
      只给"宽"时落在 `width`——中文家具口语里单独说的"宽"指正面宽度，
      衣柜"宽 1.8"必须落在 `width` 才符合直觉。
    - **裸尺寸**（"1.8米"，没有轴名）按缺省尺度落轴，见 `subtypes.closest_axis`。
      它优先级最低：写了轴名的尺寸总能覆盖它。
    """

    text = str(user_message or "")
    hits = _dimension_hits(text)
    if subtype:
        spans = keyword_spans(text)
        if spans:
            hits = [hit for hit in hits if _owner_subtype(hit[0], spans) == subtype]

    primary = long_axis(subtype) if subtype else "width"
    short_axis = "depth" if primary == "width" else "width"

    found: dict[str, float] = {}
    for _, axis, value in hits:
        if axis == "bare":
            # 没有子类型上下文时落不了轴，只能按 `width` 处理。
            found[closest_axis(subtype, value) if subtype else "width"] = value
    length = next((value for _, axis, value in hits if axis == "length"), None)
    width = next((value for _, axis, value in hits if axis == "width"), None)
    height = next((value for _, axis, value in hits if axis == "height"), None)

    if length is not None:
        found[primary] = length
    if width is not None:
        found[short_axis if length is not None else "width"] = width
    if height is not None:
        found["height"] = height

    return found


def _count_for(user_message: str, subtype: str) -> int:
    """用户点名数量时按原话取；否则 1。

    只在该子类型确实被点名时才有意义——"生成四把椅子"里 4 属于椅子。
    数量必须**紧贴**关键词（中间只允许一个量词），所以"长1.8米高0.75的桌子"
    里的 1.8/0.75 不会被当成张数：它们和"桌"之间隔着"的"。
    """

    text = str(user_message or "")
    keywords = FURNITURE_SUBTYPES.get(subtype, {}).get("keywords", ())
    for keyword in keywords:
        # 阿拉伯数字与中文数词都认；上限由 `_clamp_count` 统一收口。
        match = re.search(
            rf"({_NUM_TOKEN})\s*[{_CLASSIFIERS}]?\s*{re.escape(keyword)}", text
        )
        if match:
            value = _to_metres(match.group(1))
            if value is not None:
                return _clamp_count(int(value))
    match = re.search(rf"(?:总共|一共|共)\s*{_NUMBER}\s*[{_CLASSIFIERS}]", text)
    if match:
        return _clamp_count(float(match.group(1)))
    return 1


# ── 通用几何通道（primitive / body）的归一化 ──


def _finite(value: object) -> float | None:
    """有限数才收；bool / 字符串 / NaN / inf 一律 None。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _vec3(value: object) -> list[float] | None:
    if not (isinstance(value, list) and len(value) == 3):
        return None
    out: list[float] = []
    for item in value:
        number = _finite(item)
        if number is None:
            return None
        out.append(round(number, 3))
    return out


def _positive(value: object) -> float | None:
    number = _finite(value)
    if number is None or number <= 0:
        return None
    return round(number, 3)


def _bounded(value: object, low: float, high: float, fallback: float) -> float:
    number = _finite(value)
    if number is None:
        return fallback
    return round(max(low, min(high, number)), 3)


def normalize_primitive_part(raw: object) -> dict[str, Any] | None:
    """把一个通用几何零件归一化为合法参数；不合法的返回 None。

    ⚠️ 这里**不做几何推断**：不替模型补 shape 的必填参数、不纠正零件之间的穿插、
    也不把零件吸附到某个网格上。零件表本身就是本次要交付的几何 ——
    猜出来的零件和用户点名的那个东西没有关系，那正是要避免的静默替换。
    本函数只做**取值域内的收口**：shape 白名单、正数、有限数、Vec3 形状。
    """

    if not isinstance(raw, dict):
        return None
    shape = str(raw.get("shape") or "").strip().lower()
    if shape not in PRIMITIVE_SHAPES:
        return None

    part: dict[str, Any] = {"shape": shape}
    for field in ("position", "rotation", "scale"):
        vector = _vec3(raw.get(field))
        if vector is None and field == "rotation":
            # `rotation` 允许"度数标量/度数数组"的写法：走与生成链同一个单位迁移
            # 规则，而不是因为形态不对就静默丢掉朝向（丢掉 = 悄悄换了交付结果）。
            from app.utils.rotation import coerce_rotation

            coerced = coerce_rotation(raw.get(field))
            vector = [round(value, 6) for value in coerced] if coerced else None
        if vector is not None:
            part[field] = vector
    material = str(raw.get("material") or "").strip()[:80]
    if material:
        part["material"] = material

    if shape == "box":
        dimensions = _vec3(raw.get("dimensions"))
        if dimensions is None or any(side <= 0 for side in dimensions):
            return None
        part["dimensions"] = dimensions
    elif shape == "sphere":
        radius = _positive(raw.get("radius"))
        if radius is None:
            return None
        part["radius"] = radius
    elif shape == "cylinder":
        height = _positive(raw.get("height"))
        if height is None:
            return None
        part["height"] = height
        radius = _positive(raw.get("radius"))
        if radius is not None:
            part["radius"] = radius
        else:
            # 锥台写法：上下半径必须成对出现（schema 的 oneOf 只认这两种组合）。
            top = _positive(raw.get("radiusTop"))
            bottom = _positive(raw.get("radiusBottom"))
            if top is None or bottom is None:
                return None
            part["radiusTop"] = top
            part["radiusBottom"] = bottom
    else:  # profile_sweep
        path = raw.get("path")
        if not (isinstance(path, list) and len(path) >= 2):
            return None
        points = [_vec3(point) for point in path]
        if any(point is None for point in points):
            return None
        part["path"] = points
        profile = raw.get("profile")
        if isinstance(profile, list) and len(profile) >= 2:
            pairs: list[list[float]] = []
            for pair in profile:
                if not (isinstance(pair, list) and len(pair) == 2):
                    return None
                x, y = _finite(pair[0]), _finite(pair[1])
                if x is None or y is None:
                    return None
                pairs.append([round(x, 4), round(y, 4)])
            part["profile"] = pairs

    for field, low, high in (("segments", 3, 128), ("heightSegments", 2, 64)):
        value = raw.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            part[field] = max(low, min(high, value))
    if isinstance(raw.get("closedProfile"), bool):
        part["closedProfile"] = raw["closedProfile"]
    return part


def _part_extents(part: dict[str, Any]) -> tuple[list[float], list[float]]:
    """单个零件的 (最小角, 最大角) 世界坐标近似包围盒。"""

    center = part.get("position") if isinstance(part.get("position"), list) else [0.0, 0.0, 0.0]
    shape = part.get("shape")
    if shape == "box" and isinstance(part.get("dimensions"), list):
        half = [float(side) / 2.0 for side in part["dimensions"]]
    elif shape == "sphere":
        radius = float(part.get("radius") or 0.0)
        half = [radius, radius, radius]
    elif shape == "cylinder":
        radius = float(
            part.get("radius")
            or part.get("radiusBottom")
            or part.get("radiusTop")
            or 0.0
        )
        half = [radius, float(part.get("height") or 0.0) / 2.0, radius]
    elif shape == "profile_sweep" and isinstance(part.get("path"), list) and part["path"]:
        points = part["path"]
        low = [min(float(point[axis]) for point in points) for axis in range(3)]
        high = [max(float(point[axis]) for point in points) for axis in range(3)]
        return ([low[axis] + center[axis] for axis in range(3)],
                [high[axis] + center[axis] for axis in range(3)])
    else:
        half = [0.0, 0.0, 0.0]
    return (
        [center[axis] - half[axis] for axis in range(3)],
        [center[axis] + half[axis] for axis in range(3)],
    )


def parts_bounds(parts: list[dict[str, Any]]) -> tuple[float, float, float]:
    """零件表的整体包围盒 `(width, depth, height)`（近似，米）。

    用途只有一个：`ComponentObject` 要求每件物件给出整体尺寸，而模型的零件表未必
    附了它 —— 这时从零件反算比留空或编一个数诚实。近似之处：

    - 不处理 `rotation` 与 `scale`（旋转后的 AABB 需要完整矩阵运算），
      所以带旋转的零件会算出偏小的包围盒；
    - `profile_sweep` 只按 `path` 的范围算，忽略截面自身厚度。

    这两条都只会让包围盒**偏小**，而它只用于尺度合理性显示，不参与任何判定。
    """

    if not parts:
        return 0.0, 0.0, 0.0
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for part in parts:
        low, high = _part_extents(part)
        for axis in range(3):
            lows[axis] = min(lows[axis], low[axis])
            highs[axis] = max(highs[axis], high[axis])
    return (
        max(0.0, highs[0] - lows[0]),   # width  = X
        max(0.0, highs[2] - lows[2]),   # depth  = Z
        max(0.0, highs[1] - lows[1]),   # height = Y
    )


def _object_base(
    raw: dict[str, Any],
    *,
    kind: str,
    name: str,
    message: str,
) -> dict[str, Any]:
    """物件条目的公共字段。尺寸取模型给的值，缺失时由调用方补算。"""

    return {
        "kind": kind,
        "subtype": "",
        "name": name[:60],
        "count": _clamp_count(raw.get("count")),
        "placement": str(raw.get("placement") or "").strip()[:300],
        "material": str(raw.get("material") or "").strip()[:80],
        "rationale": str(raw.get("rationale") or "").strip()[:300],
    }


def _normalize_furniture_item(raw: dict[str, Any], user_message: str) -> dict[str, Any] | None:
    """图鉴预设通道：`kind=furniture` + 闭集 `subtype`。

    命中预设时不做任何近似 —— 这是"名字能落进闭集，就用引擎原生 builder"的那条路。
    子类型认不出来时返回 None（**不挑一个最像的顶上**），由调用方改走通用几何通道
    或如实报告做不了。
    """

    subtype = str(raw.get("subtype") or "").strip().lower()
    if subtype not in FURNITURE_SUBTYPES:
        # 模型把子类型写进 name 位置是常见抖动，按原话再认一次。
        subtype = ""
    if not subtype:
        subtype = match_subtype(str(raw.get("name") or "")) or ""
    if not subtype:
        return None

    spec = FURNITURE_SUBTYPES[subtype]
    fallback_w, fallback_d, fallback_h = default_size(subtype)
    requested = _requested_size(user_message, subtype)
    low_h, high_h = spec["height_range"]

    width = _clamp(raw.get("width"), _MIN_SIZE, _MAX_SIZE, requested.get("width", fallback_w))
    depth = _clamp(raw.get("depth"), _MIN_SIZE, _MAX_SIZE, requested.get("depth", fallback_d))
    height = _clamp(raw.get("height"), low_h, high_h, requested.get("height", fallback_h))

    count = _clamp_count(raw.get("count"))
    if count == 1:
        count = _count_for(user_message, subtype)

    return {
        "kind": PRESET_KIND,
        "subtype": subtype,
        "name": str(raw.get("name") or "").strip()[:60],
        "count": count,
        "width": width,
        "depth": depth,
        "height": height,
        "placement": str(raw.get("placement") or "").strip()[:300],
        "material": str(raw.get("material") or "").strip()[:80],
        "rationale": str(raw.get("rationale") or "").strip()[:300],
    }


def _normalize_generic_item(raw: dict[str, Any], user_message: str) -> dict[str, Any] | None:
    """通用几何通道：`kind=primitive` + 零件表。

    这是**开放集出口**：任何名字（小人、花瓶、路灯、机器人）都从这里产出，
    因为"几何方式"只有四种（闭集），而"物件名"列不完。零件表就是本次的几何，
    一个零件都收不下时返回 None（不做近似形体）。
    """

    parts = raw.get("parts")
    candidates: list[object]
    if isinstance(parts, list):
        candidates = list(parts)
    elif raw.get("shape"):
        # 单形体写法：顶层直接就是一份 primitive 参数。
        candidates = [raw]
    else:
        return None

    normalized = [
        part for part in (normalize_primitive_part(item) for item in candidates[:_MAX_PARTS])
        if part is not None
    ]
    if not normalized:
        return None

    item = _object_base(
        raw,
        kind=GENERIC_KIND,
        name=str(raw.get("name") or "").strip(),
        message=user_message,
    )
    bounds_w, bounds_d, bounds_h = parts_bounds(normalized)
    item["parts"] = normalized
    item["width"] = _clamp(raw.get("width"), _MIN_SIZE, _MAX_SIZE, bounds_w or 0.2)
    item["depth"] = _clamp(raw.get("depth"), _MIN_SIZE, _MAX_SIZE, bounds_d or 0.2)
    item["height"] = _clamp(raw.get("height"), _MIN_SIZE, _MAX_SIZE, bounds_h or 0.2)
    return item


def _normalize_body_item(raw: dict[str, Any], user_message: str) -> dict[str, Any] | None:
    """简化人物通道：`kind=body`，参数据 KB《构件参数》§十。

    缺失参数给**中性缺省**（身高 1.7m、体型 athletic、圆头、四肢比例 1.0），
    因为这几个字段是枚举或比例，缺省不会改变"这是一个人"这个判断；
    而形状类字段（primitive 的 dimensions / path）缺省就会变成另一个东西，
    所以那里坚决不补。
    """

    height = _bounded(raw.get("height"), 0.5, 2.5, 1.7)
    build = str(raw.get("build") or "").strip().lower()
    head_shape = str(raw.get("headShape") or "").strip().lower()
    item = _object_base(
        raw,
        kind=BODY_KIND,
        name=str(raw.get("name") or "").strip(),
        message=user_message,
    )
    item["params"] = {
        "height": height,
        "build": build if build in BODY_BUILDS else "athletic",
        "headShape": head_shape if head_shape in BODY_HEAD_SHAPES else "round",
        "armLength": _bounded(raw.get("armLength"), 0.5, 1.5, 1.0),
        "legLength": _bounded(raw.get("legLength"), 0.5, 1.5, 1.0),
        "cloakLength": _bounded(raw.get("cloakLength"), 0.3, 1.5, 0.6),
        "hoodUp": bool(raw.get("hoodUp")),
    }
    # 人物包围盒只用于尺度显示：肩宽随身高线性变化，0.45 是引擎骨架的实际比例。
    item["width"] = _bounded(raw.get("width"), _MIN_SIZE, _MAX_SIZE, round(height * 0.45, 3))
    item["depth"] = _bounded(raw.get("depth"), _MIN_SIZE, _MAX_SIZE, round(height * 0.45, 3))
    item["height"] = height
    return item


def normalize_object_item(raw: dict[str, Any], user_message: str = "") -> dict[str, Any] | None:
    """把一条模型输出的物件归一化为合法条目；不可用时返回 None。

    分发只按 `kind` 与**已给的表达**走，不按物件名走：

    - `kind` 是三个通道之一 → 走对应通道；
    - 没给 `kind` 但给了 `parts`/`shape` → 通用几何通道（模型常见简写）；
    - 其余 → 图鉴预设通道（认不出子类型则返回 None）。
    """

    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip().lower()
    if kind and kind not in OBJECT_COMPONENT_KINDS:
        # 未知 kind 不猜语义（模型爱写 "couch"、"ornament" 这类业务名）：
        # 当作"没给 kind"，由下面的"已给的表达"来决定走哪条通道。
        kind = ""
    if kind == GENERIC_KIND or (not kind and (raw.get("parts") or raw.get("shape"))):
        return _normalize_generic_item(raw, user_message)
    if kind == BODY_KIND:
        return _normalize_body_item(raw, user_message)
    return _normalize_furniture_item(raw, user_message)


def _object_key(item: dict[str, Any]) -> tuple[str, str, str]:
    """去重键：`(kind, subtype, name)`。

    只用 `(kind, subtype)` 是不够的 —— 通用几何与人物通道的 `subtype` 是空串，
    于是"花瓶"和"路灯"会被折成同一条，用户拿到两件东西里的一件。
    预设通道靠 `subtype` 区分，其余通道靠 `name` 区分。
    """

    return (str(item.get("kind") or ""), str(item.get("subtype") or ""), str(item.get("name") or ""))


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同 `(kind, subtype, name)` 合并为一条：数量相加，摆位与理由保留先到者。"""

    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for item in items:
        key = _object_key(item)
        if key not in merged:
            merged[key] = dict(item)
            order.append(key)
            continue
        existing = merged[key]
        existing["count"] = _clamp_count(existing["count"] + item["count"])
        for field in ("placement", "material", "rationale"):
            if not existing.get(field) and item.get(field):
                existing[field] = item[field]
        # 尺寸取较大者：多条目描述同一件物件时，"大"的一版更容易一眼认出来，
        # 而偏小的一版容易被误读成零件缺失。
        for field in ("width", "depth", "height"):
            existing[field] = max(float(existing[field]), float(item[field]))
    return [merged[key] for key in order]


def fallback_object_plan(user_message: str) -> dict[str, Any]:
    """模型不可用或输出不可解析时的确定性兜底方案。

    兜底只做**确定性做得到**的事：把用户点名的**图鉴预设**翻译成家具条目
    （预设里有缺省尺寸，是确切的知识）。预设命中不了的名字（小人、花瓶、路灯）
    在这里**算不出几何** —— 那就如实报"本次表达不了"，而不是挑一张桌子顶上。

    🔴 这里曾经是 `subtypes = [match_subtype(text) or DEFAULT_SUBTYPE]`：
    没命中任何预设就做一张桌子。静默替换比失败更糟 ——
    用户拿到自己没要的东西，还以为系统理解对了（"要桌子给房子"就是这个模式）。
    现在改成 `unsupported_objects`：与《动态节点设计规划》§8.1 的
    "能力缺失只标记、不阻断"同一条口径。
    """

    text = str(user_message or "")
    subtypes = matched_subtypes(text)

    items: list[dict[str, Any]] = []
    for subtype in subtypes:
        # "长"落在哪条轴依子类型而定（餐桌是 width、床是 depth），
        # 且尺寸短语只归属最近的前置子类型，所以必须按子类型各算一次。
        requested = _requested_size(text, subtype)
        fallback_w, fallback_d, fallback_h = default_size(subtype)
        spec = FURNITURE_SUBTYPES[subtype]
        low_h, high_h = spec["height_range"]
        items.append({
            "kind": PRESET_KIND,
            "subtype": subtype,
            "name": "",
            "count": _count_for(text, subtype),
            "width": _clamp(requested.get("width"), _MIN_SIZE, _MAX_SIZE, fallback_w),
            "depth": _clamp(requested.get("depth"), _MIN_SIZE, _MAX_SIZE, fallback_d),
            "height": _clamp(requested.get("height"), low_h, high_h, fallback_h),
            "placement": "",
            "material": "",
            "rationale": "根据用户点名的物件类型确定性生成（模型方案不可用）",
        })

    if not items:
        return {
            "target_kind": "object",
            "concept": f"{text.strip()[:40] or '物件'} 单件场景",
            "objects": [],
            "unsupported_objects": [text.strip()[:60] or "未识别物件"],
            "design_rationale": [
                "模型未给出可用物件方案，且用户点名的物件不在图鉴预设内；"
                "确定性兜底不猜测几何，也不用品类相近的预设顶替。",
            ],
        }

    return {
        "target_kind": "object",
        "concept": f"{'、'.join(subtypes)} 单件场景",
        "objects": items[:_MAX_OBJECTS],
        "unsupported_objects": [],
        "design_rationale": ["按用户点名的物件类型与尺寸生成，不含建筑体量"],
    }


def normalize_object_plan(raw: Any, user_message: str = "") -> dict[str, Any]:
    """把模型输出归一化为可交付的物件方案（模型不可用时可安全传入 None）。

    `objects` 允许为空 —— 但**只有**在同时给出了 `unsupported_objects`
    （点名了、却表达不出来）时才成立，这条不变量在 `contracts.ObjectDecisions`
    上强制。空方案不是"没做完"，而是"这次确实做不了"的如实记录。
    """

    payload = raw if isinstance(raw, dict) else {}
    raw_objects = payload.get("objects")
    items: list[dict[str, Any]] = []
    if isinstance(raw_objects, list):
        for entry in raw_objects:
            normalized = normalize_object_item(entry, user_message)
            if normalized is not None:
                items.append(normalized)

    unsupported = [
        str(entry).strip()[:60]
        for entry in (payload.get("unsupported_objects") or [])
        if str(entry).strip()
    ][:_MAX_OBJECTS]

    if not items and not unsupported:
        # 模型一个可用条目都没给：走确定性兜底（预设命中则出条目，否则如实报缺口）。
        return fallback_object_plan(user_message)

    items = _deduplicate(items)[:_MAX_OBJECTS]
    rationale = [
        str(item)[:300]
        for item in (payload.get("design_rationale") or [])
        if str(item).strip()
    ][:12]
    if not rationale:
        rationale = ["按用户需求确定物件种类、尺寸与摆位"]
    if unsupported and items:
        rationale.append(
            "另有 " + "、".join(unsupported) + " 无法表达为可生成几何，已如实标记而未顶替。"
        )
    return {
        "target_kind": "object",
        "concept": str(payload.get("concept") or "").strip()[:240],
        "objects": items,
        "unsupported_objects": unsupported,
        "design_rationale": rationale,
    }


__all__ = [
    "BODY_BUILDS",
    "BODY_HEAD_SHAPES",
    "PRIMITIVE_SHAPES",
    "fallback_object_plan",
    "normalize_object_item",
    "normalize_object_plan",
    "normalize_primitive_part",
    "parts_bounds",
]
