"""变异测试：把每条修复「改回旧行为」，确认对应回归用例真的会红。

用例钉不住修复 = 假保护。跑法：
    cd wild-server
    ./.venv/Scripts/python.exe ../.workbuddy/diag/mutate_roof_top_coverage.py
"""
from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_ROOT))

import app.tools.spatial_tools as st  # noqa: E402

tests = importlib.import_module("tests.validators.test_roof_top_coverage")


def outcome(test_fn) -> str:
    try:
        test_fn()
    except AssertionError:
        return "已钉住 ✓"
    except Exception as error:  # noqa: BLE001
        return f"异常 {type(error).__name__}: {error}"
    return "未钉住 ✗（用例假绿）"


def run(label: str, test_fn, mutate, restore) -> bool:
    mutate()
    try:
        result = outcome(test_fn)
    finally:
        restore()
    print(f"{label:44s} {result}")
    return "已钉住" in result


# ── 变异 1：曲线墙退回 from→to 直线采样（天坛的 from/to XZ 同点）
def straight_points(wall: dict) -> list[tuple[float, float]]:
    start, end = wall["from"], wall["to"]
    return [(float(start[0]), float(start[2])), (float(end[0]), float(end[2]))]


# ── 变异 2：半宽忽略 eaveOutset（重檐底层檐口 span/2 + eaveOutset）
def extents_without_outset(roof, fallback_half_w, fallback_half_d, expand_to_fallback):
    stripped = {key: value for key, value in roof.items() if key != "eaveOutset"}
    return _ORIG_EXTENTS(
        stripped, fallback_half_w, fallback_half_d, expand_to_fallback,
    )


# ── 变异 3：跳过缺 position 的屋顶（旧实现直接 continue）
def entries_requiring_position(elements, walls):
    return [
        entry for entry in _ORIG_ENTRIES(elements, walls)
        if any(
            element.get("type") == "roof"
            and str(element.get("id", "?")) == entry[5]
            and isinstance(element.get("position"), list)
            for element in elements
        )
    ]


# ── 变异 4：不过滤栏杆（矮、薄的墙也参与判定）
def all_walls_structural(wall) -> bool:  # noqa: ARG001
    return True


# ── 变异 5：采样退回端点采样（4cm 贴边被放大成半格）
def endpoint_sampling(wall, step=st.TOP_COVERAGE_SAMPLE_STEP):
    points = _ORIG_POINTS(wall)
    if len(points) < 2:
        return 0.0, []
    cumulative = [0.0]
    for start, end in zip(points, points[1:]):
        cumulative.append(
            cumulative[-1] + math.hypot(end[0] - start[0], end[1] - start[1])
        )
    total = cumulative[-1]
    if total <= 1e-6:
        return 0.0, []
    count = max(2, int(total / step) + 1)
    samples: list[tuple[float, float]] = []
    segment = 0
    for index in range(count):
        target = total * index / (count - 1)
        while segment + 2 < len(cumulative) and cumulative[segment + 1] < target:
            segment += 1
        span = cumulative[segment + 1] - cumulative[segment]
        ratio = 0.0 if span <= 1e-9 else (target - cumulative[segment]) / span
        ax, az = points[segment]
        bx, bz = points[segment + 1]
        samples.append((ax + (bx - ax) * ratio, az + (bz - az) * ratio))
    return total, samples


_ORIG_POINTS = st._wall_centerline_points
_ORIG_EXTENTS = st._roof_half_extents
_ORIG_ENTRIES = st._roof_footprint_entries
_ORIG_STRUCTURAL = st._is_structural_wall
_ORIG_SAMPLE = st._sample_wall_centerline

MUTATIONS = [
    ("曲线墙退回直线采样", tests.test_curved_wall_is_sampled_along_its_curve,
     lambda: setattr(st, "_wall_centerline_points", straight_points),
     lambda: setattr(st, "_wall_centerline_points", _ORIG_POINTS)),
    ("半宽忽略 eaveOutset", tests.test_pagoda_eave_outset_extends_coverage,
     lambda: setattr(st, "_roof_half_extents", extents_without_outset),
     lambda: setattr(st, "_roof_half_extents", _ORIG_EXTENTS)),
    ("跳过缺 position 的屋顶", tests.test_roof_without_position_is_inferred_from_support_walls,
     lambda: setattr(st, "_roof_footprint_entries", entries_requiring_position),
     lambda: setattr(st, "_roof_footprint_entries", _ORIG_ENTRIES)),
    ("不过滤栏杆", tests.test_railing_walls_are_ignored,
     lambda: setattr(st, "_is_structural_wall", all_walls_structural),
     lambda: setattr(st, "_is_structural_wall", _ORIG_STRUCTURAL)),
    ("采样退回端点采样", tests.test_endpoint_sliver_below_threshold_is_not_reported,
     lambda: setattr(st, "_sample_wall_centerline", endpoint_sampling),
     lambda: setattr(st, "_sample_wall_centerline", _ORIG_SAMPLE)),
]


def main() -> int:
    failures = 0
    for label, test_fn, mutate, restore in MUTATIONS:
        if not run(label, test_fn, mutate, restore):
            failures += 1
    print(f"\n{len(MUTATIONS) - failures}/{len(MUTATIONS)} 条修复被用例钉住")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
