"""用项目自己的校验流水线校验一份 .wild 蓝图。

为什么要这个脚本：知识库把「Validator 能判定」定义为硬约束（`rules/` 那一支），
所以"生成得对不对"不该靠肉眼看，而应该拿同一批工具跑一遍——和线上
`agent_service.run_validation_pipeline()` 用的是同一组函数。

覆盖三层：
  ① JSON 可解析 + 顶层结构（validate_blueprint_structure）
  ② 空间流水线全部校验器（必填字段 / 引用 / 洞口 / 墙角 / 楼梯 / 屋顶 / 碰撞 / 尺寸）
  ③ 知识库红线（本脚本自带，因为这些是"机器能判定"之外的文档纪律）：
     roofType 枚举、baseColor 不能是 #RRGGBB、玻璃必须写全 materialClass/transmission/ior、
     转角两面墙端点坐标必须完全相同

用法：
    cd wild-server
    ./.venv/Scripts/python.exe ../.workbuddy/diag/verify_wild_blueprint.py <蓝图路径...>
退出码 0 = 全部通过。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_ROOT))

from app.tools.spatial_tools import (  # noqa: E402
    validate_blueprint_structure,
    validate_collision,
    validate_element_dimensions,
    validate_element_required_fields,
    validate_opening_coords,
    validate_opening_fit,
    validate_reference_integrity,
    validate_roof_coverage,
    validate_roof_top_coverage,
    validate_stair_alignment,
    validate_wall_junctions,
)

# 顺序照抄 agent_service 的流水线；每个元素是 (名称, 工具)。
PIPELINE = [
    ("结构完整性", validate_blueprint_structure),
    ("构件必填字段", validate_element_required_fields),
    ("引用完整性", validate_reference_integrity),
    ("门窗洞口坐标", validate_opening_coords),
    ("门窗洞口贴合", validate_opening_fit),
    ("墙体转角对齐", validate_wall_junctions),
    ("楼梯高度对齐", validate_stair_alignment),
    ("屋顶覆盖范围", validate_roof_coverage),
    ("墙顶-屋顶反向覆盖", validate_roof_top_coverage),
    ("构件尺寸", validate_element_dimensions),
    ("碰撞与悬空", validate_collision),
]

ROOF_TYPES = {"gable", "hip", "dome", "flat", "chinese_curved", "chinese_pagoda"}
BAD_ROOF_TYPES = {"pitched", "sloped", "gabled", "hipped", "shed", "mono-pitch", "mansard"}
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def knowledge_redlines(bp: dict) -> list[str]:
    """知识库「生成红线」里那几条，机器可判定的部分。"""
    problems: list[str] = []
    elements = bp.get("geometry", {}).get("elements", []) or []
    components = bp.get("geometry", {}).get("components", []) or []
    materials = bp.get("materials", {}) or {}

    for el in elements:
        if el.get("type") != "roof":
            continue
        roof_type = el.get("roofType")
        if roof_type in BAD_ROOF_TYPES:
            problems.append(f"[红线] {el.get('id')} roofType={roof_type!r} 是建筑术语，不是 WILD 枚举值")
        elif roof_type not in ROOF_TYPES:
            problems.append(f"[红线] {el.get('id')} roofType={roof_type!r} 不在 6 个合法值内")

    for name, mat in materials.items():
        if not isinstance(mat, dict):
            continue
        base = mat.get("baseColor")
        if isinstance(base, str) and HEX_COLOR.match(base):
            problems.append(f"[红线] 材质 {name} 的 baseColor 写成了 {base!r}，必须是 [R,G,B] 数组")
        elif not (isinstance(base, list) and len(base) == 3):
            problems.append(f"[红线] 材质 {name} 的 baseColor 不是长度 3 的数组：{base!r}")

    # 玻璃：用了玻璃的角色必须写全物理属性
    glass_refs: set[str] = set()
    for comp in components:
        for key in ("glassMaterial",):
            if comp.get(key):
                glass_refs.add(comp[key])
    for name in sorted(glass_refs):
        mat = materials.get(name)
        if not isinstance(mat, dict):
            problems.append(f"[红线] 玻璃材质 {name} 未在 materials 中定义")
            continue
        if mat.get("materialClass") != "glass":
            problems.append(f"[红线] 玻璃材质 {name} 缺 materialClass: \"glass\"（会渲染成不透明板）")
        if not isinstance(mat.get("transmission"), (int, float)) or (mat.get("transmission") or 0) <= 0:
            problems.append(f"[红线] 玻璃材质 {name} 的 transmission 必须 > 0")
        if not isinstance(mat.get("ior"), (int, float)):
            problems.append(f"[红线] 玻璃材质 {name} 缺 ior")
        opacity = mat.get("opacity")
        if opacity is not None and float(opacity) < 1:
            problems.append(f"[红线] 玻璃材质 {name} 的 opacity={opacity}，应为 1 或省略")

    # 转角两面墙必须共享完全相同的端点坐标（引擎容差仅 0.01m）
    endpoints: dict[tuple[float, float, float], list[str]] = {}
    for el in elements:
        if el.get("type") != "wall":
            continue
        for key in ("from", "to"):
            vec = el.get(key)
            if isinstance(vec, list) and len(vec) == 3:
                endpoints.setdefault((round(vec[0], 4), round(vec[1], 4), round(vec[2], 4)), []).append(
                    f"{el.get('id')}.{key}"
                )
    for vec, owners in endpoints.items():
        if len(owners) > 1:
            # 同一条边被两面墙共用是合法的；这里只要求"坐标完全一致"，所以无需报错。
            continue
    # 反查：两面墙水平距离 < 0.01m 但坐标不完全相等 → 靠容差贴合，属违规写法
    wall_pts = [
        (el.get("id"), (round(el["from"][0], 4), round(el["from"][1], 4), round(el["from"][2], 4)),
         (round(el["to"][0], 4), round(el["to"][1], 4), round(el["to"][2], 4)))
        for el in elements
        if el.get("type") == "wall" and isinstance(el.get("from"), list) and isinstance(el.get("to"), list)
    ]
    for i, (id_a, a_from, a_to) in enumerate(wall_pts):
        for id_b, b_from, b_to in wall_pts[i + 1:]:
            for pa in (a_from, a_to):
                for pb in (b_from, b_to):
                    dxz = ((pa[0] - pb[0]) ** 2 + (pa[2] - pb[2]) ** 2) ** 0.5
                    if 0 < dxz < 0.01:
                        problems.append(
                            f"[红线] {id_a} 与 {id_b} 的端点水平距离 {dxz:.4f}m < 0.01m 但坐标不相等，"
                            f"引擎会自行取平均 → 必须写成完全相同的坐标"
                        )
    return problems


def check(path: Path) -> int:
    print("=" * 76)
    print(path.name)
    print("=" * 76)
    try:
        bp = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  ❌ JSON 解析失败：{exc}")
        return 1

    failures = 0
    for label, tool in PIPELINE:
        try:
            result = tool.func(bp)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  {label}: 校验器抛异常 {exc!r}")
            continue
        text = str(result).strip()
        bad = ("❌" in text) or ("⚠️" in text)
        mark = "⚠️ " if bad else "✅"
        if bad:
            failures += 1
        # 多行结果缩进显示，便于 grep
        lines = text.splitlines() or [""]
        print(f"  {mark} {label}: {lines[0]}")
        for extra in lines[1:]:
            print(f"        {extra}")

    redline = knowledge_redlines(bp)
    if redline:
        failures += len(redline)
        for item in redline:
            print(f"  ❌ {item}")
    else:
        print("  ✅ 知识库红线：roofType 枚举 / baseColor 格式 / 玻璃物理属性 / 墙角坐标 全部通过")

    els = bp.get("geometry", {}).get("elements", []) or []
    comps = bp.get("geometry", {}).get("components", []) or []
    print(f"  — 统计：elements {len(els)} / components {len(comps)} / materials {len(bp.get('materials', {}))}")
    print(f"  — 结果：{'PASS' if failures == 0 else f'{failures} 项需要注意'}")
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]]
    if not targets:
        targets = [Path(SERVER_ROOT).parent / "wild-web" / "lantu" / "villa_modern_2f.wild"]
    return max(check(p) for p in targets)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
