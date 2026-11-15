"""`rotation` 的**单位迁移**：把模型写出的"度数标量 / 度数数组"收敛成契约要求的三元弧度数组。

为什么需要它：`rotation` 的契约是**弧度制 vec3**（KB《家具》与 `prompts` 都这么写），
但模型经常写成 `180`（度数标量）或 `[0, 90, 0]`（度数数组）。
校验器 `spatial_tools.validate_element_required_fields` 会如实报
"rotation 必须是弧度制三维数组" —— 报得没错，**但一次单位滑档不该让整批生成作废**：
实测家具批量 2 件产出 8 个片段全被判死、条目重试、最终 0 件家具落地。
这正是《动态节点设计规划》"归一化不是类型过滤器"要处理的情形 ——
**同一语义、不同单位 ⇒ 迁移；语义本身不合法 ⇒ 才交给校验器报错**。

判据（故意保守，避免把合法的弧度值改坏）：

| 输入 | 处置 | 理由 |
|---|---|---|
| `180`、`"90"`、`"90deg"`、`"90度"` | → `[0, π, 0]` | 标量只可能是**绕 Y 的度数**，与校验器自己的提示一致（"朝向写 [0, 弧度, 0]"） |
| `[0, 90, 0]` | → `[0, π/2, 0]` | 有分量 >2π、且非零分量都是 15 的整数倍 ⇒ 只可能是度数 |
| `[0, 1.5708, 0]` | 原样 | 全部分量落在 ±2π 内 ⇒ 就是弧度 |
| `[0, 7.0, 0]` | `None`（交回校验器） | 7.0 不是 15 的整数倍、又超出 2π ⇒ 认不出，不猜 |
| `[0, 1]`、`true`、`{"y": 90}` | `None` | 形态就不对 |

`2π` 是分界线：角度的有效域就是一圈，超出它按弧度读没有意义。
"""

from __future__ import annotations

import math
from typing import Any

TWO_PI = 2 * math.pi

#: 度数一般取 15 的整数倍（0/15/30/45/60/75/90/…/270/360），用来区分"度数数组"。
_DEGREE_STEP = 15.0
_DEGREE_SUFFIXES = ("degrees", "degree", "deg", "°", "度")


def _as_float(value: Any) -> float | None:
    """把标量/数字字符串（可带度数后缀）收敛成有限浮点；其余返回 None。"""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip().lower()
        for suffix in _DEGREE_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                break
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _is_degree_multiple(value: float) -> bool:
    remainder = abs(value) % _DEGREE_STEP
    return remainder < 1e-6 or abs(remainder - _DEGREE_STEP) < 1e-6


def coerce_rotation(value: Any) -> list[float] | None:
    """把 `rotation` 迁移成三元弧度数组；认不出的形态返回 `None`（不猜）。"""

    scalar = _as_float(value)
    if scalar is not None:
        return [0.0, math.radians(scalar), 0.0]

    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    numbers = [_as_float(item) for item in value]
    if any(number is None for number in numbers):
        return None
    resolved = [float(number) for number in numbers]  # type: ignore[arg-type]

    if all(abs(number) <= TWO_PI for number in resolved):
        return resolved
    if all(_is_degree_multiple(number) for number in resolved if number):
        return [math.radians(number) for number in resolved]
    return None


def coerce_element_rotation(element: dict) -> list[float] | None:
    """就地迁移 `element["rotation"]`；**没有改动**时返回 `None`（方便调用方记日志）。

    只在字段确实存在时动手：缺字段是"用默认朝向"，不是错，不该被补上一个值来掩盖。
    已经是合法弧度数组的直接返回 `None`，避免无谓的精度改写。
    """

    if not isinstance(element, dict) or "rotation" not in element:
        return None
    raw = element["rotation"]
    if isinstance(raw, (list, tuple)) and len(raw) == 3:
        numbers = [_as_float(item) for item in raw]
        if all(number is not None and abs(number) <= TWO_PI for number in numbers):
            return None
    coerced = coerce_rotation(raw)
    if coerced is None:
        return None
    element["rotation"] = [round(value, 6) for value in coerced]
    return element["rotation"]
