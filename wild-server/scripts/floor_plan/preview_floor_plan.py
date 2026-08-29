r"""离线生成 FloorPlanIR v2 的 SVG 预览。

启动方式（在 wild-server 目录运行）：
    .\.venv\Scripts\python.exe scripts\floor_plan\preview_floor_plan.py

读取自己的 JSON：
    .\.venv\Scripts\python.exe scripts\floor_plan\preview_floor_plan.py --input scripts\floor_plan\sample_floor_plan.json --output storage\sessions\my_floor_plan.svg

输入 JSON 需要包含 ``massing`` 和 ``spatial_plan``。脚本会先走与 Agent
相同的归一化和确定性校验，再输出 SVG；无效细分会明确回退为单一主要空间。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.agent.spatial_plan import (  # noqa: E402
    architecture_plan_to_svgs,
    normalize_spatial_plan,
    spatial_plan_summary,
    spatial_plan_to_svg,
)


SAMPLE_INPUT = {
    "massing": {
        "shape": "rectangle",
        "width": 12,
        "depth": 9,
        "floor_height": 3.2,
        "modeled_floors": 1,
    },
    "spatial_plan": {
        "review_rules": {
            "enabled": ["egress", "opening_corner"],
            "max_egress_distance": 30,
            "min_opening_corner_clearance": 0.3,
        },
        "levels": [{
            "level": 1,
            "entrance_space_id": "living",
            "spaces": [
                {"id": "living", "name": "起居室", "space_type": "living", "bounds": [0, 0, 7, 9]},
                {"id": "service", "name": "服务空间", "space_type": "service", "bounds": [7, 0, 12, 9]},
            ],
            "walls": [
                {"id": "partition", "from": [7, 0], "to": [7, 9], "thickness": 0.12},
            ],
            "openings": [{
                "id": "door_connection",
                "type": "door",
                "host_wall_id": "partition",
                "offset": 3.8,
                "width": 0.9,
                "height": 2.1,
                "sill_height": 0,
                "connects": ["living", "service"],
            }],
        }],
    },
    "facades": {
        "front": {"bays": 3, "ground_pattern": ["window", "door", "window"], "upper_pattern": ["window", "empty", "window"]},
        "back": {"bays": 2, "ground_pattern": ["window", "window"], "upper_pattern": ["window", "window"]},
        "left": {"bays": 2, "ground_pattern": ["empty", "window"], "upper_pattern": ["empty", "window"]},
        "right": {"bays": 2, "ground_pattern": ["window", "empty"], "upper_pattern": ["window", "empty"]},
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="生成并检查 FloorPlanIR v2 SVG 预览")
    parser.add_argument("--input", type=Path, help="包含 massing + spatial_plan 的 UTF-8 JSON")
    parser.add_argument(
        "--output",
        type=Path,
        default=SERVER_ROOT / "storage" / "sessions" / "floor_plan_preview.svg",
        help="SVG 输出路径",
    )
    parser.add_argument("--level", type=int, default=1, help="要预览的楼层，默认 1")
    parser.add_argument("--all-levels", action="store_true", help="为全部显式楼层分别输出 SVG")
    args = parser.parse_args()

    payload = SAMPLE_INPUT
    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    massing = payload.get("massing")
    if not isinstance(massing, dict):
        raise SystemExit("输入错误：缺少对象 massing")

    volumes = payload.get("volumes") if isinstance(payload.get("volumes"), list) else None
    plan = normalize_spatial_plan(payload.get("spatial_plan"), massing, volumes)
    facades = payload.get("facades") if isinstance(payload.get("facades"), dict) else {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.all_levels:
        svgs = architecture_plan_to_svgs({"spatial_plan": plan, "facades": facades})
        outputs = []
        for level, svg in svgs.items():
            output = args.output.with_name(f"{args.output.stem}_L{level}{args.output.suffix}")
            output.write_text(svg, encoding="utf-8")
            outputs.append(output)
    else:
        svg = spatial_plan_to_svg(plan, level_number=args.level, facades=facades)
        args.output.write_text(svg, encoding="utf-8")
        outputs = [args.output]

    summary = spatial_plan_summary(plan)
    print(f"平面来源: {summary['source']}")
    print(f"楼层/空间/内墙/洞口: {summary['level_count']}/{summary['space_count']}/{summary['interior_wall_count']}/{summary['opening_count']}")
    print(f"跨层洞口/垂直交通: {summary['void_count']}/{summary['vertical_circulation_count']}")
    rule_review = summary["rule_review"]
    print(f"工程预审: {'通过' if rule_review['passed'] else '未通过'}（{len(rule_review['findings'])} 项，法定审图={rule_review['legal_review']}）")
    for finding in rule_review["findings"]:
        print(f"  {'通过' if finding['passed'] else '未通过'} [{finding['gate']}] {finding['message']}")
    if summary["fallback_reason"]:
        print(f"回退原因: {summary['fallback_reason']}")
    for output in outputs:
        print(f"SVG 已保存: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
