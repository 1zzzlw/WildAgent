"""按《传统建筑-祈年殿蓝图书写规则及蓝图示范.md》生成天坛祈年殿 .wild 蓝图。

所有数值/公式严格取自文档 §2/§4：台基 3 叠级 cylinder、栏板 3×32 box、台阶 3×2 box、
12 段直墙正十二边形殿身 + 12 柱 + 内核、4 door + 8 window、彩画带/殿身/檐盘 cylinder、
dome 攒顶 + 鎏金宝顶。

引擎语义（已核对 src/wild-core/src/primitive/geometry/*.ts）：
  - primitive box   position = 中心，rotation = 弧度(Euler XYZ)
  - primitive cylinder position = 中心（height 上下对称）
  - primitive sphere   position = 球心
  - roof(dome)       position = 底面（承托标高），顶点 = position.y + height
"""
import json
import math
import os

CX, CZ = 30.0, 30.0          # 场地 60×60，圆心在场地中心，原点西南角
R_COL = 10.5                 # 柱圈半径（殿身外接圆）
CHORD = 2 * R_COL * math.sin(math.pi / 12)   # 弦长 5.4352
TERRACE_R = [30.0, 26.0, 22.0]     # 台基半径（每层内收 4.0）
TERRACE_TOP = [-4.2, -2.1, 0.0]    # 台基顶标高（t3 顶 = ±0.000）
TERRACE_BOTTOM = [t - 2.1 for t in TERRACE_TOP]   # 层高 2.1


def deg(x: float) -> float:
    return math.radians(x)


def cyl(eid, r_top, r_bot, height, cy, segments, material):
    return {
        "type": "primitive", "id": eid, "shape": "cylinder",
        "radiusTop": r_top, "radiusBottom": r_bot, "height": height,
        "segments": segments, "position": [CX, cy, CZ], "material": material,
    }


elements = []
components = []

# ── 4.1 三层圆台基（cylinder，segments 64，直壁） ──
for i, (r, top) in enumerate(zip(TERRACE_R, TERRACE_TOP), 1):
    bottom = top - 2.1
    cy = (top + bottom) / 2
    elements.append(cyl(f"terrace_t{i}", r, r, 2.1, cy, 64, "stone_white"))

# ── 4.2 石栏板（每层 32 段 box 弦线围合） ──
for i, (r, top) in enumerate(zip(TERRACE_R, TERRACE_TOP), 1):
    rr = r - 0.4
    n = 32
    for j in range(n):
        a0 = deg(j * 360 / n)
        a1 = deg((j + 1) * 360 / n)
        x0 = CX + rr * math.cos(a0)
        z0 = CZ + rr * math.sin(a0)
        x1 = CX + rr * math.cos(a1)
        z1 = CZ + rr * math.sin(a1)
        mx = (x0 + x1) / 2
        mz = (z0 + z1) / 2
        seg_len = 2 * rr * math.sin(math.pi / n)
        ry = math.atan2(-(z1 - z0), x1 - x0)   # 文档公式，弧度
        elements.append({
            "type": "primitive", "id": f"railing_t{i}_{j:02d}", "shape": "box",
            "dimensions": [seg_len, 0.8, 0.12],
            "position": [mx, top + 0.4, mz],
            "rotation": [0, ry, 0], "material": "stone_white",
        })

# ── 4.3 御路台阶（每层南缘 2 步） ──
for i, (r, bottom, top) in enumerate(zip(TERRACE_R, TERRACE_BOTTOM, TERRACE_TOP), 1):
    south_z = CZ - r
    for j in range(2):
        pos_y = bottom + j * 1.05 + 0.525
        pos_z = south_z - 1.2 - j * 1.2
        elements.append({
            "type": "primitive", "id": f"step_t{i}_{j}", "shape": "box",
            "dimensions": [6.0, 1.05, 1.2],
            "position": [CX, pos_y, pos_z], "material": "stone_white",
        })

# ── 4.4 折面殿身（12 段直墙 + 12 柱 + 内核） ──
for k in range(12):
    a_from = deg(30 * k - 15)
    a_to = deg(30 * k + 15)
    elements.append({
        "type": "wall", "id": f"wall_seg_{k:02d}",
        "from": [CX + R_COL * math.cos(a_from), 0, CZ + R_COL * math.sin(a_from)],
        "to": [CX + R_COL * math.cos(a_to), 6, CZ + R_COL * math.sin(a_to)],
        "thickness": 0.12, "material": "pillar_red",
    })
    a_col = deg(15 + 30 * k)
    elements.append({
        "type": "column", "id": f"col_{k:02d}",
        "base": [CX + R_COL * math.cos(a_col), 0, CZ + R_COL * math.sin(a_col)],
        "height": 6.0, "bottomRadius": 0.25, "topRadius": 0.22,
        "style": "chinese_wooden", "material": "pillar_red",
    })
# 内核 body_core（r 9.0，透过门窗可见的室内体量）
elements.append(cyl("body_core", 9.0, 9.0, 6.0, 3.0, 64, "pillar_red"))

# ── 4.5 隔扇门窗组件（4 door 四正向 + 8 window） ──
DOOR_K = [0, 3, 6, 9]      # 东/北/西/南
WINDOW_K = [k for k in range(12) if k not in DOOR_K]
for k in DOOR_K:
    components.append({
        "type": "door", "id": f"door_{k:02d}", "parentWall": f"wall_seg_{k:02d}",
        "from": [1.518, 0, 0], "width": 2.4, "height": 3.6,
        "frameWidth": 0.09, "frameDepth": 0.09,
        "doorStyle": "double", "frameMaterial": "gold", "leafMaterial": "pillar_red",
        "interaction": {"mode": "swing", "hingeSide": "right", "openAngle": 90},
    })
for k in WINDOW_K:
    components.append({
        "type": "window", "id": f"win_{k:02d}", "parentWall": f"wall_seg_{k:02d}",
        "from": [1.518, 0.9, 0], "width": 2.4, "height": 2.4,
        "frameWidth": 0.09, "frameDepth": 0.09,
        "verticalMullions": 4, "frameMaterial": "gold", "glassMaterial": "glass",
    })

# ── 4.6 彩画带 + 中/上段殿身（cylinder 环带） ──
# 彩画带：r = 段身半径 + 0.06，高 0.6，底 = 段顶 - 0.6
elements.append(cyl("band_l1", 10.56, 10.56, 0.6, 5.7, 64, "paint_teal"))
elements.append(cyl("band_l2", 8.06, 8.06, 0.6, 10.5, 64, "paint_teal"))
elements.append(cyl("band_l3", 5.56, 5.56, 0.6, 15.3, 64, "paint_teal"))
# 中/上段殿身：r 8.0 (6.0–10.8) / r 5.5 (10.8–15.6)
elements.append(cyl("body_l2", 8.0, 8.0, 4.8, 8.4, 64, "pillar_red"))
elements.append(cyl("body_l3", 5.5, 5.5, 4.8, 13.2, 64, "pillar_red"))

# ── 4.7 三重蓝琉璃檐盘（薄盘 cylinder 高 0.4） ──
elements.append(cyl("eave_l1", 13.0, 13.0, 0.4, 6.2, 64, "tile_blue"))
elements.append(cyl("eave_l2", 10.8, 10.8, 0.4, 11.0, 64, "tile_blue"))
elements.append(cyl("eave_l3", 8.4, 8.4, 0.4, 15.8, 64, "tile_blue"))

# ── 4.8 圆攒顶 + 鎏金宝顶 ──
elements.append({
    "type": "roof", "id": "roof_dome", "roofType": "dome",
    "span": 12.0, "depth": 12.0, "height": 5.4, "thickness": 0.2,
    "position": [CX, 16.0, CZ], "material": "tile_blue",
})
elements.append(cyl("finial_base", 0.4, 0.4, 0.9, 21.85, 32, "gold"))
elements.append({
    "type": "primitive", "id": "finial_ball", "shape": "sphere",
    "radius": 1.0, "segments": 32, "heightSegments": 16,
    "position": [CX, 22.85, CZ], "material": "gold",
})

materials = {
    "stone_white": {"baseColor": [0.93, 0.92, 0.90], "roughness": 0.45, "metallic": 0.0,
                    "albedo": 1.0, "lightingCondition": "D65_noon"},
    "pillar_red": {"baseColor": [0.60, 0.15, 0.10], "roughness": 0.65, "metallic": 0.0,
                   "albedo": 1.0, "lightingCondition": "D65_noon"},
    "paint_teal": {"baseColor": [0.13, 0.48, 0.42], "roughness": 0.55, "metallic": 0.0,
                   "albedo": 1.0, "lightingCondition": "D65_noon"},
    "tile_blue": {"baseColor": [0.10, 0.22, 0.52], "roughness": 0.85, "metallic": 0.0,
                  "albedo": 1.0, "lightingCondition": "D65_noon"},
    "gold": {"baseColor": [0.92, 0.72, 0.22], "roughness": 0.2, "metallic": 0.85,
             "albedo": 1.0, "lightingCondition": "D65_noon"},
    "glass": {"baseColor": [0.72, 0.88, 0.96], "roughness": 0.08, "metallic": 0.0,
              "albedo": 1.0, "lightingCondition": "D65_noon", "materialClass": "glass",
              "side": "double", "transmission": 0.92, "ior": 1.5, "thickness": 0.012,
              "attenuationColor": [0.82, 0.94, 1.0], "attenuationDistance": 6.0,
              "clearcoat": 0.08, "clearcoatRoughness": 0.12},
}

blueprint = {
    "meta": {"version": "1.1", "type": "building", "name": "天坛祈年殿"},
    "geometry": {"elements": elements, "components": components},
    "materials": materials,
}

out_path = os.path.join(os.path.dirname(__file__), "..", "..", "wild-web", "lantu", "qiniandian.wild")
out_path = os.path.normpath(out_path)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(blueprint, f, ensure_ascii=False, indent=2)

print(f"elements: {len(elements)}, components: {len(components)}")
print(f"written: {out_path}")
print(f"chord length: {CHORD:.4f}")

# 范围体检
xs = [e["position"][0] for e in elements if "position" in e]
zs = [e["position"][2] for e in elements if "position" in e]
for e in elements:
    if e["type"] == "wall":
        xs += [e["from"][0], e["to"][0]]
        zs += [e["from"][2], e["to"][2]]
print(f"X range: [{min(xs):.2f}, {max(xs):.2f}]  Z range: [{min(zs):.2f}, {max(zs):.2f}]")
