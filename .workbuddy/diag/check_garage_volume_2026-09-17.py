"""实证：引擎能否建出"两层主楼 + 一层车库体量、L 形连接、各自屋顶与楼板"。

用户在 Agent 模式被拦下的四条验收条件，全部只因为句中含"车库"二字。
本脚本绕开闸门直接喂一份等价方案，验证下游是否真的做不到。

**判据说明（2026-09-17 修正）**：附属体量不是靠"墙 id 里含 garage"表达的。
骨架在**墙环上开缺口**：一层环被切成多段（wall_right_1_1 / wall_right_1_2 …），
车库只到一层，所以二层环恢复成 4 面不切；车库还各有自己的地板与层高处顶板
（floor_1_garage / floor_2_garage）。旧版判据用"含 garage 的墙段"导致误判为"建不出"。

用法（在 wild-server 目录下）：
    ./.venv/Scripts/python.exe ../.workbuddy/diag/check_garage_volume_2026-09-17.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_DIR))

from app.agent.generation.architecture import normalize_architecture_plan  # noqa: E402
from app.agent.generation.architecture.skeleton import (  # noqa: E402
    build_deterministic_skeleton,
)
from app.design.resolver import build_design_document  # noqa: E402

# wall_<face>_<level>[_<segment>]：segment 存在即说明该层墙环被切开了
_WALL_ID = re.compile(r"^wall_[a-z]+_(?P<level>\d+)(?:_(?P<segment>\d+))?$")

MESSAGE = "生成一座两层住宅，带一个一层车库体量，两个体量呈 L 形连接"

# 模型本该给出的方案：主体两层、车库一层，靠 x 偏移形成 L 形相连（共享边不重叠）。
RAW = {
    "massing": {"shape": "L", "floors": 2},
    "volumes": [
        {
            "id": "main", "role": "primary",
            "x": 0, "z": 0, "width": 10, "depth": 12,
            "start_floor": 1, "end_floor": 2,
        },
        {
            "id": "garage", "role": "secondary",
            "x": 10, "z": 0, "width": 6, "depth": 6,
            "start_floor": 1, "end_floor": 1,
        },
    ],
    "roof": {"type": "hip"},
}


def _run(label: str, raw: dict, message: str) -> bool:
    print(f"\n{'=' * 66}\n{label}\n{'=' * 66}")
    plan = normalize_architecture_plan(raw, message)
    volumes = plan.get("volumes") or []
    print("--- 归一化后的体量 ---")
    for volume in volumes:
        print(
            f"  {volume['id']:<10} role={volume['role']:<9} "
            f"x={volume['x']:<5} z={volume['z']:<5} "
            f"{volume['width']}x{volume['depth']} "
            f"floors={volume['start_floor']}..{volume['end_floor']}"
        )
    print(f"  massing: {plan['massing']}")
    print(f"  roof:    {plan.get('roof')}")

    print("--- DesignDocument 契约 ---")
    try:
        document = build_design_document(plan, session_id="diag", source_request=message)
    except Exception as exc:  # noqa: BLE001
        print(f"  拒绝：{' '.join(str(exc).split())[:200]}")
        return False
    print(f"  通过：{len(document.decisions.volumes)} 个体量")

    print("--- 确定性骨架（真实几何，无模型） ---")
    skeleton = build_deterministic_skeleton(plan, message)
    elements = (skeleton.get("geometry") or {}).get("elements") or []
    by_type: dict[str, int] = {}
    for element in elements:
        by_type[str(element.get("type"))] = by_type.get(str(element.get("type")), 0) + 1
    print(f"  元素总数 {len(elements)}：{json.dumps(by_type, ensure_ascii=False)}")

    # 判据一：车库有自己的地板与层高处顶板
    garage_floors = [
        e for e in elements
        if str(e.get("id") or "") in {"floor_1_garage", "floor_2_garage"}
    ]
    # 判据二：一层墙环被切分（有缺口 = 附属体量与主体相连），二层墙环不切（车库未延伸到二层）
    level_walls: dict[int, list[str]] = {}
    for element in elements:
        if element.get("type") != "wall":
            continue
        match = _WALL_ID.match(str(element.get("id") or ""))
        if match:
            level_walls.setdefault(int(match.group("level")), []).append(
                str(element.get("id"))
            )
    level_1 = level_walls.get(1, [])
    level_2 = level_walls.get(2, [])
    print(f"  车库专用楼板 {len(garage_floors)} 块：{sorted(str(e.get('id')) for e in garage_floors)}")
    print(f"  一层墙环 {len(level_1)} 段（>4 即存在缺口）：{sorted(level_1)}")
    print(f"  二层墙环 {len(level_2)} 段（4 即车库未延伸到二层）：{sorted(level_2)}")

    ok = bool(garage_floors) and len(level_1) > 4 and len(level_2) == 4
    print("  判定：" + ("能建出车库体量" if ok else "建不出车库体量"))
    return ok


def main() -> int:
    # 变体 A：照字面理解——主体 10x12、车库紧贴其右侧，总轮廓仍是 10x12。
    variant_a = {
        "massing": {"shape": "L", "floors": 2},
        "volumes": [
            {"id": "main", "role": "primary", "x": 0, "z": 0,
             "width": 10, "depth": 12, "start_floor": 1, "end_floor": 2},
            {"id": "garage", "role": "secondary", "x": 10, "z": 0,
             "width": 6, "depth": 6, "start_floor": 1, "end_floor": 1},
        ],
        "roof": {"type": "hip"},
    }
    # 变体 B：把总轮廓扩到能同时容纳两个体量（16x12），主体与车库仍然各是 10x12 / 6x6。
    variant_b = {
        "massing": {"shape": "L", "floors": 2, "width": 16, "depth": 12},
        "volumes": [
            {"id": "main", "role": "primary", "x": 0, "z": 0,
             "width": 10, "depth": 12, "start_floor": 1, "end_floor": 2},
            {"id": "garage", "role": "secondary", "x": 10, "z": 0,
             "width": 6, "depth": 6, "start_floor": 1, "end_floor": 1},
        ],
        "roof": {"type": "hip"},
    }

    results = [
        _run("变体 A：总轮廓 = 主体尺寸（主体 10x12 + 车库贴边）", variant_a, MESSAGE),
        _run("变体 B：总轮廓放大到 16x12（主体 10x12 + 车库 6x6）", variant_b, MESSAGE),
    ]
    print("\n" + "=" * 66)
    print(f"变体 A 可建：{results[0]}    变体 B 可建：{results[1]}")
    return 0 if any(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

