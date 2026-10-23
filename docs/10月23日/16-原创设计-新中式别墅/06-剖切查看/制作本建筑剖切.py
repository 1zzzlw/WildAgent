#!/usr/bin/env python3
"""砚溪别院专用剖切查看副本：只删除遮挡构件，不改保留构件的坐标。

与公共脚本的差别：
- 本建筑上层家具/构件位于 3.5–4.0 m 之间，一层剖切阈值取 3.5 m；
- 门屋用原生 opening 元素，宿主墙删除后会同步清理开口引用；
- 生成 03-过程记录/构件分层.json，记录每个源 ID 的剖切层。
"""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "砚溪别院.wild"
OUT_DIR = ROOT / "06-剖切查看"
LAYER_FILE = ROOT / "03-过程记录" / "构件分层.json"
F2 = 3.70
UPPER_Y = 3.50
MAIN = (2.36, 14.64, -2.14, 10.14)
TEA = (-7.64, -1.36, 1.86, 9.64)
ROOF_MATS = {"roof_tile", "roof_tile_alt", "roof_edge", "roof_ridge"}
SITE_IDS = {
    "site_w", "site_e", "site_s", "site_n", "water", "pool_bottom",
    "pave_w", "pave_e", "entry_path", "apron", "lawn_w", "lawn_e",
    "lawn_n", "gravel",
}


def inside(box, x, z):
    x0, x1, z0, z1 = box
    return x0 <= x <= x1 and z0 <= z <= z1


def gate_area(x, z):
    return 4.30 <= x <= 9.70 and -10.50 <= z <= -8.20


def overhead(x, z, y):
    if y < 2.8:
        return False
    return (
        (8.40 <= x <= 14.70 and -4.00 <= z <= -1.90) or
        (-7.00 <= x <= -2.70 and 0.30 <= z <= 1.90) or
        (5.50 <= x <= 8.90 and -4.30 <= z <= -1.90)
    )


def ypos(row):
    if row.get("position"):
        return float(row["position"][1])
    if row.get("base"):
        return float(row["base"][1])
    if row.get("from"):
        return float(row["from"][1])
    if row.get("path"):
        return min(float(point[1]) for point in row["path"])
    return 0.0


def layer_for(row, component=False):
    kind = row.get("type")
    ident = str(row.get("id", ""))
    if component:
        if str(row.get("parentWall", "")).startswith("gate"):
            return "gate"
        if row.get("from") and float(row["from"][1]) >= UPPER_Y:
            return "facade_upper"
        if row.get("path") and min(float(point[1]) for point in row["path"]) >= UPPER_Y:
            return "facade_upper"
        return "components"
    if kind == "roof":
        return "roof"
    if kind == "wall":
        if ident.startswith("gate"):
            return "gate"
        if min(float(row["from"][1]), float(row["to"][1])) >= UPPER_Y:
            return "wall_upper"
        return "wall_ground"
    if kind == "floor":
        if ident == "gate_floor":
            return "gate"
        if ident.startswith("slab_"):
            return "floor_upper"
        if ident.startswith("site_") or ident in SITE_IDS:
            return "site"
        return "floor_ground"
    if kind == "stair":
        return "stair"
    if kind == "column":
        return "structure"
    if kind == "opening":
        return "gate" if str(row.get("parentWall", "")).startswith("gate") else "detail"
    if kind == "furniture":
        return "furniture"
    if kind == "primitive":
        position = row.get("position", [0, 0, 0])
        x, y, z = float(position[0]), float(position[1]), float(position[2])
        if gate_area(x, z):
            return "gate"
        material = row.get("material")
        if material in ROOF_MATS:
            return "roof_detail"
        if y >= 6.0:
            return "roof_detail"
        if overhead(x, z, y):
            return "roof_detail"
        if inside(MAIN, x, z) or inside(TEA, x, z):
            return "furniture"
        if y >= UPPER_Y:
            return "facade_upper"
        return "landscape"
    return "detail"


def main():
    if not SOURCE.exists():
        raise SystemExit(f"缺少源文件: {SOURCE}")
    raw = SOURCE.read_bytes()
    blueprint = json.loads(raw)
    elements = blueprint["geometry"]["elements"]
    components = blueprint["geometry"].get("components", [])
    layers = {}
    for row in elements:
        layers[row["id"]] = layer_for(row, component=False)
    for row in components:
        layers[row["id"]] = layer_for(row, component=True)
    LAYER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAYER_FILE.write_text(
        json.dumps(dict(sorted(layers.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    counts = Counter(layers.values())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(raw).hexdigest()

    views = [
        ("一层", {"roof", "roof_detail", "wall_upper", "floor_upper", "facade_upper", "gate"}, True),
        ("二层", {"roof", "roof_detail", "gate"}, False),
    ]
    for name, removed_layers, remove_upper_furniture in views:
        copy = deepcopy(blueprint)
        removed = []
        for kind in ("elements", "components"):
            keep = []
            for row in copy["geometry"][kind]:
                ident = row["id"]
                layer = layers[ident]
                reason = None
                if layer in removed_layers:
                    reason = f"layer:{layer}"
                elif kind == "elements" and layer == "furniture" and remove_upper_furniture:
                    if ypos(row) >= UPPER_Y:
                        reason = "上层家具/构件"
                if reason:
                    removed.append({"id": ident, "layer": layer, "reason": reason})
                else:
                    keep.append(row)
            copy["geometry"][kind] = keep

        # 清理因宿主删除而失去引用的开口/组合构件
        kept_elements = {row["id"]: row for row in copy["geometry"]["elements"]}
        kept_components = []
        for row in copy["geometry"]["components"]:
            missing = False
            for field in ("parentWall", "parentFloor", "parentRoof"):
                parent = row.get(field)
                if parent and parent not in kept_elements:
                    removed.append({
                        "id": row["id"], "layer": layers[row["id"]],
                        "reason": f"宿主随剖切移除:{field}",
                    })
                    missing = True
                    break
            if not missing:
                kept_components.append(row)
        copy["geometry"]["components"] = kept_components

        # 原生 opening 也依赖父墙；清理失去宿主的开口
        kept_elements = {}
        for row in copy["geometry"]["elements"]:
            parent = row.get("parentWall")
            if parent and parent not in {item["id"] for item in copy["geometry"]["elements"]}:
                removed.append({
                    "id": row["id"], "layer": layers[row["id"]],
                    "reason": "宿主随剖切移除:parentWall",
                })
                continue
            kept_elements[row["id"]] = row
        copy["geometry"]["elements"] = list(kept_elements.values())

        copy["meta"]["name"] = blueprint["meta"]["name"] + " · " + name + "查看副本"
        data = (json.dumps(copy, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        wild_path = OUT_DIR / f"{name}剖切.wild"
        wild_path.write_bytes(data)
        record = {
            "source": str(SOURCE),
            "source_sha256": source_hash,
            "view": name,
            "wild": wild_path.name,
            "wild_sha256": sha256(data).hexdigest(),
            "removed_layers": sorted(removed_layers),
            "upper_furniture_threshold": UPPER_Y if remove_upper_furniture else None,
            "removed_count": len(removed),
            "removed": removed,
            "kept_elements": len(copy["geometry"]["elements"]),
            "kept_components": len(copy["geometry"]["components"]),
            "kept_geometry_unchanged": True,
            "layer_counts": dict(sorted(Counter(layers.values()).items())),
        }
        (OUT_DIR / f"{name}来源.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "view": name,
            "removed": len(removed),
            "kept_elements": record["kept_elements"],
            "kept_components": record["kept_components"],
            "wild": wild_path.name,
            "sha256": record["wild_sha256"][:16],
        }, ensure_ascii=False))
    print(json.dumps({"layers": dict(sorted(counts.items()))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
