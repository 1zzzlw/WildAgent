"""物品零件的构造助手。

坐标约定（与 `wild-core/src/primitive/geometry/furniture.ts` 一致，改前先看那份注释）：

- 物品局部原点是**底面中心**：X 向右，+Z 是正面，Y=0 是地面；
- `primitive` 的 `position` 是**形体中心**，不是角点 —— 写 `at=(0, h/2, 0)` 才是"从地面立起 h 高"；
- `cylinder` 沿 **+Y**；要横放（沿 Z）就传 `rot=(pi/2, 0, 0)`；
- `rotation` 单位是**弧度**（引擎按欧拉 XYZ 叠加）。

这些零件最终是一个 `.wild` asset 的 `geometry.elements`，因此只能使用引擎
`registry.ts` 里已注册的 statement 类型：`primitive`（box/sphere/cylinder/profile_sweep）
与 `solid`（extrude/revolve/loft/sweep/boolean 等）。**不要新增类型** ——
新增物品的意义就是不再改引擎。
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

PI = math.pi


def _v(at: Sequence[float]) -> list[float]:
    return [round(float(value), 4) for value in at]


def _rot(rot: Sequence[float] | None) -> list[float] | None:
    return None if rot is None else [round(float(value), 6) for value in rot]


def box(
    pid: str,
    size: Sequence[float],
    at: Sequence[float] = (0, 0, 0),
    material: str = "default",
    rot: Sequence[float] | None = None,
) -> dict:
    """长方体。`size` = (宽 X, 高 Y, 深 Z)，`at` 是**几何中心**。"""

    width, height, depth = (max(float(value), 0.001) for value in size)
    element: dict = {
        "type": "primitive",
        "id": pid,
        "shape": "box",
        "dimensions": [round(width, 4), round(height, 4), round(depth, 4)],
        "position": _v(at),
        "material": material,
    }
    rotation = _rot(rot)
    if rotation:
        element["rotation"] = rotation
    return element


def cyl(
    pid: str,
    radius: float,
    height: float,
    at: Sequence[float] = (0, 0, 0),
    material: str = "default",
    radius_top: float | None = None,
    segments: int = 24,
    rot: Sequence[float] | None = None,
) -> dict:
    """圆柱 / 圆台。`at` 是**几何中心**，沿 +Y 生长。"""

    element: dict = {
        "type": "primitive",
        "id": pid,
        "shape": "cylinder",
        "height": round(max(float(height), 0.001), 4),
        "segments": max(3, min(96, int(segments))),
        "position": _v(at),
        "material": material,
    }
    if radius_top is None:
        element["radius"] = round(max(float(radius), 0.001), 4)
    else:
        element["radiusBottom"] = round(max(float(radius), 0.001), 4)
        element["radiusTop"] = round(max(float(radius_top), 0.001), 4)
    rotation = _rot(rot)
    if rotation:
        element["rotation"] = rotation
    return element


def sphere(
    pid: str,
    radius: float,
    at: Sequence[float] = (0, 0, 0),
    material: str = "default",
    segments: int = 20,
) -> dict:
    return {
        "type": "primitive",
        "id": pid,
        "shape": "sphere",
        "radius": round(max(float(radius), 0.001), 4),
        "segments": max(8, min(96, int(segments))),
        "position": _v(at),
        "material": material,
    }


def sweep(
    pid: str,
    profile: Sequence[Sequence[float]],
    path: Sequence[Sequence[float]],
    material: str = "default",
    closed: bool = True,
    caps: bool = True,
) -> dict:
    """截面沿路径扫掠。`profile` 是 (u, v) 点列，`path` 是 (x, y, z) 点列。

    用途：管件、转角扶手、桌腿弯撑。比堆 box 省零件且轮廓连续。
    """

    return {
        "type": "primitive",
        "id": pid,
        "shape": "profile_sweep",
        "profile": [[round(float(u), 4), round(float(v), 4)] for u, v in profile],
        "path": [_v(point) for point in path],
        "closedProfile": bool(closed),
        "caps": bool(caps),
        "material": material,
    }


def ring_profile(radius: float, segments: int = 12) -> list[list[float]]:
    """圆形截面点列（用于 `sweep`）。"""

    count = max(3, int(segments))
    return [
        [round(radius * math.cos(2 * PI * index / count), 4), round(radius * math.sin(2 * PI * index / count), 4)]
        for index in range(count)
    ]


def rect_profile(width: float, height: float) -> list[list[float]]:
    half_w, half_h = width / 2, height / 2
    return [[-half_w, -half_h], [half_w, -half_h], [half_w, half_h], [-half_w, half_h]]


def legs4(
    prefix: str,
    width: float,
    depth: float,
    height: float,
    inset: float = 0.06,
    radius: float = 0.025,
    material: str = "wood",
    segments: int = 12,
) -> list[dict]:
    """四角立腿，返回 4 个圆柱。`height` 是腿高，腿底在 Y=0。"""

    half_w = max(width / 2 - inset, 0.01)
    half_d = max(depth / 2 - inset, 0.01)
    out: list[dict] = []
    for index, (sx, sz) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        out.append(
            cyl(
                f"{prefix}_{index}",
                radius,
                height,
                (sx * half_w, height / 2, sz * half_d),
                material,
                segments=segments,
            )
        )
    return out


def row(
    prefix: str,
    count: int,
    builder,
    start: float,
    step: float,
    axis: str = "x",
    cross: float = 0.0,
    y: float = 0.0,
) -> list[dict]:
    """沿一条轴等距复制零件。`builder(id, at)` 返回一个零件。"""

    out: list[dict] = []
    for index in range(max(1, int(count))):
        offset = start + index * step
        at = (offset, y, cross) if axis == "x" else (cross, y, offset)
        out.append(builder(f"{prefix}_{index}", at))
    return out


def merge(*groups: Iterable[dict]) -> list[dict]:
    out: list[dict] = []
    for group in groups:
        out.extend(group)
    return out


def _rotate_point(point: Sequence[float], rotation: Sequence[float]) -> list[float]:
    """欧拉 XYZ 旋转，与 `furniture.ts::rotateEulerXYZ` 同一顺序。"""

    x, y, z = point
    rx, ry, rz = rotation
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        cy * cz * x - cy * sz * y + sy * z,
        (sx * sy * cz + cx * sz) * x + (-sx * sy * sz + cx * cz) * y - sx * cy * z,
        (-cx * sy * cz + sx * sz) * x + (cx * sy * sz + sx * cz) * y + cx * cy * z,
    ]


def bbox_of(parts: Sequence[dict]) -> tuple[list[float], list[float]]:
    """零件表的世界包围盒（物品局部坐标）。

    只覆盖 `primitive` 的三种规则形体；`profile_sweep` 与 `solid` 按路径/矢量
    近似取端点 —— 这里只用于补全 footprint 缺省值，不做精确几何求交。
    """

    lows = [math.inf, math.inf, math.inf]
    highs = [-math.inf, -math.inf, -math.inf]

    def push(point: Sequence[float]) -> None:
        for axis in range(3):
            lows[axis] = min(lows[axis], float(point[axis]))
            highs[axis] = max(highs[axis], float(point[axis]))

    for part in parts:
        center = part.get("position") or [0, 0, 0]
        shape = part.get("shape")
        rotation = part.get("rotation") or [0, 0, 0]
        turned = any(abs(float(value)) > 1e-6 for value in rotation)
        if part.get("type") == "primitive":
            if shape == "box":
                width, height, depth = part.get("dimensions") or [0, 0, 0]
            elif shape == "sphere":
                diameter = 2 * float(part.get("radius") or 0)
                width = height = depth = diameter
            elif shape == "cylinder":
                diameter = 2 * float(part.get("radius") or part.get("radiusBottom") or 0)
                width = depth = diameter
                height = float(part.get("height") or 0)
            elif shape == "profile_sweep":
                for point in part.get("path") or []:
                    push(point)
                continue
            else:
                continue
            if turned:
                # 旋转件必须按旋转后的 8 个角点求 AABB。用"半对角线当尺寸"会把
                # 横放的杆算成一个更大的立方体，归一化随之把整件物品顶离地面。
                half = [width / 2, height / 2, depth / 2]
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        for sz in (-1, 1):
                            local = _rotate_point([sx * half[0], sy * half[1], sz * half[2]], rotation)
                            push([center[0] + local[0], center[1] + local[1], center[2] + local[2]])
                continue
            push([center[0] - width / 2, center[1] - height / 2, center[2] - depth / 2])
            push([center[0] + width / 2, center[1] + height / 2, center[2] + depth / 2])
        else:
            # solid：按 position 落在原点求值，保守地以原点为中心留 0.2m
            push([center[0] - 0.1, center[1] - 0.1, center[2] - 0.1])
            push([center[0] + 0.1, center[1] + 0.1, center[2] + 0.1])

    if not math.isfinite(lows[0]):
        return [0, 0, 0], [0, 0, 0]
    return [round(value, 3) for value in lows], [round(value, 3) for value in highs]
