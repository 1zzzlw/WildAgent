"""空间工具域：二维几何、骨架空间不变量与楼梯洞口。

全部是纯函数工具，无模型调用、无 IO，包初始化无副作用。被
``generation.architecture`` 与 ``app.tools.spatial_tools`` 共用。
"""
from __future__ import annotations

from .geometry import (
    curve_points,
    path_length,
    shared_footprint,
    shared_stair_layout,
    snap_to_grid,
)
from .invariants import build_spatial_invariants
from .stair_openings import cut_stair_openings, stair_opening_issues

__all__ = [
    "build_spatial_invariants",
    "curve_points",
    "cut_stair_openings",
    "path_length",
    "shared_footprint",
    "shared_stair_layout",
    "snap_to_grid",
    "stair_opening_issues",
]
