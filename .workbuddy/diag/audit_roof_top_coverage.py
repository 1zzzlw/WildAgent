"""顶层墙 - 屋顶覆盖审计：反向检查"每块体量的顶被屋顶盖住了吗"。

为什么需要它：`spatial_tools.validate_roof_coverage` 是**单向**的（roof → wall）——
它只问"这块屋顶相对它下面那些墙合不合理"，从不问"这些顶层墙上面有没有屋顶"。
于是"漏掉一块体量的屋顶"这个错误能一路通过全部 10 个校验器。

2026-09-17 实测：一份 L 形别墅（主楼 10×8 + 侧翼 6×4，只给主楼生成了一块 gable 屋顶）
在 `verify_wild_blueprint.py` 上 10/10 全绿 —— 本文具就是为了把这类错误变成机器可判定的。

判据：把**顶层墙段**按环分组，沿每段墙的中线采样，统计有多少比例落在所有屋顶 footprint 之外。
允许的出檐容差由 `--tolerance` 控制（默认 0.05m，即墙中线必须真的在屋顶投影里）。

用法：
    ./.venv/Scripts/python.exe ../.workbuddy/diag/audit_roof_top_coverage.py <蓝图...>
退出码 0 = 每个顶层墙环都被屋顶完整覆盖。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_ROOT))

from app.tools.spatial_tools import _wall_vertical_range  # noqa: E402

SAMPLE_STEP = 0.25


def roof_footprints(elements: list[dict]) -> list[tuple[float, float, float, float, str]]:
    out = []
    for el in elements:
        if el.get("type") != "roof":
            continue
        pos = el.get("position")
        span, depth = el.get("span"), el.get("depth")
        if not (isinstance(pos, list) and len(pos) >= 3):
            continue
        if not (isinstance(span, (int, float)) and isinstance(depth, (int, float))):
            continue
        out.append((
            float(pos[0]) - float(span) / 2,
            float(pos[0]) + float(span) / 2,
            float(pos[2]) - float(depth) / 2,
            float(pos[2]) + float(depth) / 2,
            str(el.get("id")),
        ))
    return out


def point_covered(x: float, z: float, rects, tol: float) -> bool:
    for x0, x1, z0, z1, _ in rects:
        if x0 - tol <= x <= x1 + tol and z0 - tol <= z <= z1 + tol:
            return True
    return False


def sample_wall(wall: dict, rects, tol: float) -> tuple[float, float]:
    """返回 (总长, 被覆盖长度)。"""
    f, t = wall.get("from", [0, 0, 0]), wall.get("to", [0, 0, 0])
    length = math.hypot(float(t[0]) - float(f[0]), float(t[2]) - float(f[2]))
    if length <= 1e-6:
        return 0.0, 0.0
    n = max(2, int(length / SAMPLE_STEP) + 1)
    covered = 0
    for i in range(n):
        u = i / (n - 1)
        x = float(f[0]) + (float(t[0]) - float(f[0])) * u
        z = float(f[2]) + (float(t[2]) - float(f[2])) * u
        if point_covered(x, z, rects, tol):
            covered += 1
    return length, length * covered / n


def group_rings(walls: list[dict]) -> list[list[dict]]:
    """按端点共享关系把墙段串成环（容差 0.01m，与引擎一致）。"""
    key = lambda v: (round(float(v[0]), 2), round(float(v[2]), 2))
    remaining = list(walls)
    rings: list[list[dict]] = []
    while remaining:
        ring = [remaining.pop(0)]
        grown = True
        while grown:
            grown = False
            ends = {key(ring[0]["from"]), key(ring[-1]["to"])}
            for i, w in enumerate(remaining):
                if key(w["from"]) in ends or key(w["to"]) in ends:
                    ring.append(remaining.pop(i))
                    grown = True
                    break
        rings.append(ring)
    return rings


def check(path: Path, tol: float) -> int:
    print("=" * 78)
    print(path.name)
    print("=" * 78)
    bp = json.loads(path.read_text(encoding="utf-8"))
    elements = bp.get("geometry", {}).get("elements", []) or []
    walls = [e for e in elements if e.get("type") == "wall"]
    rects = roof_footprints(elements)

    if not walls:
        print("  ⚠️  没有墙，跳过。")
        return 0
    if not rects:
        print(f"  ❌ 有 {len(walls)} 面墙但**一块屋顶都没有** —— 建筑顶部完全裸露。")
        return 1

    tops = [_wall_vertical_range(w)[1] for w in walls]
    max_top = max(tops)
    top_walls = [w for w, top in zip(walls, tops) if abs(top - max_top) <= 0.05]

    print(f"  顶层墙顶标高 = {max_top:.2f}m，顶层墙段 {len(top_walls)} 面")
    for x0, x1, z0, z1, rid in rects:
        print(f"  屋顶 [{rid}] footprint X[{x0:.2f}, {x1:.2f}] Z[{z0:.2f}, {z1:.2f}]"
              f"  ({x1 - x0:.2f} × {z1 - z0:.2f} m)")

    rings = group_rings(top_walls)
    failures = 0
    print(f"  ── 按环统计（顶层墙被串成 {len(rings)} 个环 ⇒ 体量数）")
    for idx, ring in enumerate(rings, 1):
        total = covered = 0.0
        uncovered_ids = []
        for w in ring:
            length, cov = sample_wall(w, rects, tol)
            total += length
            covered += cov
            if cov < length - 1e-6:
                uncovered_ids.append(f"{w.get('id')}({(1 - cov / length) * 100:.0f}% 裸露)")
        ratio = covered / total if total else 0.0
        x0 = min(min(float(w["from"][0]), float(w["to"][0])) for w in ring)
        x1 = max(max(float(w["from"][0]), float(w["to"][0])) for w in ring)
        z0 = min(min(float(w["from"][2]), float(w["to"][2])) for w in ring)
        z1 = max(max(float(w["from"][2]), float(w["to"][2])) for w in ring)
        flag = "✅" if ratio >= 1 - 1e-6 else "❌"
        if ratio < 1 - 1e-6:
            failures += 1
        print(f"   {flag} 环{idx}  X[{x0:.1f}, {x1:.1f}] Z[{z0:.1f}, {z1:.1f}]"
              f"  墙长 {total:.1f}m  屋顶覆盖 {covered:.1f}m ({ratio:.0%})")
        for item in uncovered_ids:
            print(f"        未覆盖：{item}")

    if failures:
        print(f"  — 结果：{failures} 个体量的屋顶缺失/不足（validate_roof_coverage 不会报这个）")
        return 1
    print("  — 结果：PASS（所有顶层墙均被屋顶覆盖）")
    return 0


def main(argv: list[str]) -> int:
    tol = 0.05
    targets = []
    for a in argv[1:]:
        if a.startswith("--tolerance="):
            tol = float(a.split("=", 1)[1])
        else:
            targets.append(Path(a))
    if not targets:
        print(__doc__)
        return 2
    return max(check(p, tol) for p in targets)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
