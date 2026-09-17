"""复核 validate_roof_top_coverage 的每条 ⚠️ 是真阳性还是误报。

对每个被点名的蓝图，打印：
  - 每块 roof 的 roofType / position / span / depth / eaveOutset
  - 被点名的墙：竖向范围、厚度、是否 curve
  - 该墙采样点上方是否有楼板 / 上层墙

用法：
    cd wild-server
    ./.venv/Scripts/python.exe ../.workbuddy/diag/probe_roof_warnings_2026-09-17.py [蓝图名片段...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_ROOT))

from app.tools.spatial_tools import (  # noqa: E402
    _floor_regions_by_level,
    _highest_wall_bounds,
    _is_structural_wall,
    _roof_footprint_entries,
    _sample_wall_centerline,
    _wall_vertical_range,
    validate_roof_top_coverage,
)

TARGETS: list[str] = []


def describe_elements(elements: list[dict]) -> None:
    walls = [
        el for el in elements
        if el.get("type") == "wall" and _is_structural_wall(el)
    ]
    roofs = [el for el in elements if el.get("type") == "roof"]
    print(f"  结构性墙 {len(walls)} / 全部墙 "
          f"{len([el for el in elements if el.get('type') == 'wall'])}，"
          f"屋顶 {len(roofs)}，楼板层 {len(_floor_regions_by_level(elements))}")

    bounds = _highest_wall_bounds(walls)
    if bounds:
        x0, x1, z0, z1, top = bounds
        print(f"  承托墙包围盒 X[{x0:.1f},{x1:.1f}] Z[{z0:.1f},{z1:.1f}] 最高墙顶 {top:.2f}")

    for roof in roofs:
        parts = [
            f"roofType={roof.get('roofType')}",
            f"position={roof.get('position')}",
            f"span={roof.get('span')}",
            f"depth={roof.get('depth')}",
        ]
        if roof.get("eaveOutset") is not None:
            parts.append(f"eaveOutset={roof.get('eaveOutset')}")
        if roof.get("tiers") is not None:
            parts.append(f"tiers={roof.get('tiers')}")
        print(f"    [{roof.get('id')}] " + " ".join(parts))

    entries = _roof_footprint_entries(elements, walls)
    for x0, x1, z0, z1, base_y, rid in entries:
        print(f"    ⇒ 生效 footprint [{rid}] X[{x0:.2f},{x1:.2f}] "
              f"Z[{z0:.2f},{z1:.2f}] baseY={base_y:.2f}")

    # 顶层墙（墙顶最高的一批）
    if walls:
        tops = [(_wall_vertical_range(w)[1], w) for w in walls]
        highest = max(top for top, _ in tops)
        top_walls = [w for top, w in tops if abs(top - highest) <= 0.05]
        print(f"  ── 顶层墙（墙顶≈{highest:.2f}，共 {len(top_walls)} 面）")
        for wall in top_walls:
            bottom, top = _wall_vertical_range(wall)
            length, _ = _sample_wall_centerline(wall)
            curve = "曲线" if wall.get("curve") else "直墙"
            print(f"    [{wall.get('id')}] Y[{bottom:.2f},{top:.2f}] "
                  f"长{length:.1f}m 厚{wall.get('thickness')} {curve}")


def main(argv: list[str]) -> int:
    patterns = argv[1:] or TARGETS
    files = sorted(set((SERVER_ROOT.parent / "wild-web").rglob("*.wild"))) + sorted(
        set((SERVER_ROOT / "storage").rglob("*.wild"))
    )
    files = [p for p in files if "node_modules" not in str(p)]

    shown = 0
    for path in files:
        if patterns and not any(pat in path.name for pat in patterns):
            continue
        try:
            blueprint = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001
            print(f"[跳过] {path.name}: {error}")
            continue
        message = validate_roof_top_coverage.invoke({"blueprint": blueprint})
        if not message.startswith("⚠️"):
            continue
        shown += 1
        print("=" * 78)
        print(path.name)
        print("=" * 78)
        elements = blueprint.get("geometry", {}).get("elements", []) or []
        describe_elements(elements)
        print("  --- 校验器输出 ---")
        for line in message.splitlines():
            print("  " + line)
        print()
    print(f"共复核 {shown} 份")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
