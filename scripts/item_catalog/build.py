"""生成物品库：每个配方产出一份 `.wild` asset 文件 + 一份目录索引。

产物布局（`wild-server/storage/item_catalog/`）：

    items/<id>.wild      每个物品一份完整蓝图，可被引擎/编辑器原样打开
    manifest.json        目录索引（分类、tags、footprint、零件数）

manifest 里不写生成时间戳 —— 它会让每次构建都产生 diff 噪声，
而这批文件是要进版本库的。

用法：
    python scripts/item_catalog/build.py            # 全量生成
    python scripts/item_catalog/build.py sofa_three # 只生成指定物品
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.item_catalog.blueprint import ITEMS_DIR, MANIFEST_PATH, asset_blueprint
from scripts.item_catalog.dsl import bbox_of
from scripts.item_catalog.recipes.registry import load_all

#: 归一化时的位移超过这个值就打印告警 —— 说明配方自己画歪了，
#: 靠自动平移掩盖问题只会让下一件物品继续歪。
SHIFT_WARN = 0.35


def normalize_to_floor(parts: list[dict]) -> tuple[list[dict], list[float]]:
    """把物品整体平移到"底面中心 = 原点"。

    目录里每件物品的锚点必须同一套语义，否则前端放置时一半悬空、一半埋地。
    挂墙件（画框、镜子、配电箱）同样按底面锚点，贴墙由放置逻辑处理，
    这样引擎和目录都不需要知道"这件是挂墙的"。
    """

    low, high = bbox_of(parts)
    delta = [
        round(-(low[0] + high[0]) / 2, 4),
        round(-low[1], 4),
        round(-(low[2] + high[2]) / 2, 4),
    ]
    if all(abs(value) < 0.0005 for value in delta):
        return parts, [0.0, 0.0, 0.0]
    shifted: list[dict] = []
    for part in parts:
        copy = dict(part)
        position = copy.get("position") or [0, 0, 0]
        copy["position"] = [round(position[axis] + delta[axis], 4) for axis in range(3)]
        shifted.append(copy)
    return shifted, delta


def build_all(only: list[str] | None = None) -> list[dict]:
    registry = load_all()
    if only:
        missing = [key for key in only if key not in registry]
        if missing:
            raise SystemExit(f"未知物品 id: {', '.join(missing)}")
        selected = {key: registry[key] for key in only}
    else:
        selected = dict(registry)

    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []

    for item_id in sorted(selected):
        recipe = selected[item_id]
        parts, shift = normalize_to_floor(recipe.build())
        # 只看 X/Z：Y 方向位移是正常的 —— 吊灯、挂画这类配方天然画在离地处，
        # 归一化把它们拉到地面是有意为之。X/Z 偏大才说明配方横向画歪了。
        if max(abs(shift[0]), abs(shift[2])) > SHIFT_WARN:
            print(f"  ! {item_id} 归一化横向位移 {shift} 偏大，检查配方原点")
        blueprint = asset_blueprint(recipe.name, parts, recipe.extra_materials)
        target = ITEMS_DIR / f"{item_id}.wild"
        target.write_text(
            json.dumps(blueprint, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

        low, high = bbox_of(parts)
        measured = [
            round(high[0] - low[0], 3),
            round(high[1] - low[1], 3),
            round(high[2] - low[2], 3),
        ]
        entries.append(
            {
                "id": recipe.id,
                "name": recipe.name,
                "category": recipe.category,
                "tags": list(recipe.tags),
                # footprint 一律是**几何实测**，不是配方声明的参考值 ——
                # 两个数值并存时前端一定会读到错的那个。
                "footprint": measured,
                **({"referenceSize": list(recipe.footprint)} if recipe.footprint else {}),
                "parts": len(parts),
                "file": f"items/{item_id}.wild",
                **({"sourceItem": recipe.source_item} if recipe.source_item else {}),
            }
        )

    # 只写本次构建的物品时，保留 manifest 里其余条目
    if only and MANIFEST_PATH.exists():
        previous = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        kept = {entry["id"]: entry for entry in previous.get("items", [])}
        kept.update({entry["id"]: entry for entry in entries})
        entries = [kept[key] for key in sorted(kept)]

    manifest = {
        "version": "1.0",
        "generator": "scripts/item_catalog/build.py",
        "count": len(entries),
        "items": entries,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    # 全量构建时清掉改名/删除配方留下的孤儿文件 —— 只写不删会让
    # `items/` 里堆积 manifest 之外的 .wild，目录与文件从此对不上。
    if not only:
        keep = {entry["id"] for entry in entries}
        removed = []
        for path in ITEMS_DIR.glob("*.wild"):
            if path.stem not in keep:
                path.unlink()
                removed.append(path.stem)
        if removed:
            print(f"  清理孤儿文件: {', '.join(sorted(removed))}")
    return entries


def main() -> None:
    only = sys.argv[1:] or None
    entries = build_all(only)
    by_category: dict[str, int] = {}
    for entry in entries:
        by_category[entry["category"]] = by_category.get(entry["category"], 0) + 1
    print(f"生成 {len(entries)} 个物品 -> {ITEMS_DIR}")
    for category, count in sorted(by_category.items()):
        print(f"  {category:10s} {count}")
    total_parts = sum(entry["parts"] for entry in entries)
    print(f"零件总数 {total_parts}，平均 {total_parts / max(len(entries), 1):.1f}")


if __name__ == "__main__":
    main()
