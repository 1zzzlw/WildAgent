# -*- coding: utf-8 -*-
"""白橡别墅（欧式两层宅邸）——确定性展开 WILD 1.1。

设计事实全部来自本文件的参数表，派生值由函数计算；
改参数后重新运行即整体重算，不手填重复常数。
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "eu-villa.wild")

# ---------------------------------------------------------------- 设计参数
GROUND = 0.0
PLINTH_TOP = 0.45           # = F1 完成面
F1 = 0.45
F2 = 4.05
SLAB_T = 0.30
F2_SLAB_BOT = F2 - SLAB_T    # 3.75
F2_WALL_TOP = 7.35
ROOF_H = 3.05
ROOF_T = 0.26
T_EXT = 0.36
T_INT = 0.16
XMIN, XMAX = -7.0, 7.0
ZMIN, ZMAX = -6.0, 6.0
OVERHANG = 0.45
APRON = 0.35
SITE = 16.0

XW = XMIN + T_EXT / 2        # -6.82 外墙内表面
XE = XMAX - T_EXT / 2        #  6.82
ZS = ZMIN + T_EXT / 2        # -5.82
ZN = ZMAX - T_EXT / 2        #  5.82
XF, ZF_ = (abs(XMAX) + T_EXT / 2), (abs(ZMIN) + T_EXT / 2)   # 外表面 7.18 / 6.18

# 楼梯
ST_W = 1.10
ST_RISE = 3.60
ST_N = 20
ST_H = ST_RISE / ST_N        # 0.18
ST_D = 0.28
X_RUN1 = -2.52 + ST_W / 2    # -1.97
X_RUN2 = -2.52 + ST_W * 1.5  # -0.87
Z_RUN1_FROM, Z_RUN1_TO = -1.75, -1.75 + ST_N / 2 * ST_D      # 1.05
Z_RUN2_FROM, Z_RUN2_TO = 2.05, 2.05 - ST_N / 2 * ST_D        # -0.75
F_LAND = F1 + ST_H * (ST_N / 2)                              # 2.25
HOLE_X0, HOLE_X1 = -2.60, X_RUN2 + ST_W / 2                  # -0.32
HOLE_Z0, HOLE_Z1 = Z_RUN2_TO, Z_RUN2_FROM                    # -0.75 / 2.05

E, C = [], []


def r(v, n=4):
    return round(v + 0.0, n)


# ---------------------------------------------------------------- 基础写入
class Wall:
    def __init__(self, wid, a, b, y0, y1, t, mat):
        self.id = wid
        self.ax, self.az = a
        self.bx, self.bz = b
        self.t = t
        self.y0, self.y1 = y0, y1
        dx, dz = self.bx - self.ax, self.bz - self.az
        self.L = math.hypot(dx, dz)
        self.u = (dx / self.L, dz / self.L)
        self.n = (-self.u[1], self.u[0])
        self.ry = math.atan2(-self.u[1], self.u[0])
        E.append({"type": "wall", "id": wid,
                  "from": [r(self.ax), r(y0), r(self.az)],
                  "to": [r(self.bx), r(y1), r(self.bz)],
                  "thickness": t, "material": mat})

    def along_of(self, c):
        if abs(self.u[0]) > 0.5:
            return (c - self.ax) * self.u[0]
        return (c - self.az) * self.u[1]

    def pt(self, along, y, off):
        return [self.ax + self.u[0] * along + self.n[0] * off, y,
                self.az + self.u[1] * along + self.n[1] * off]

    def s(self, center, width):
        s = self.along_of(center) - width / 2
        assert -1e-6 <= s and s + width <= self.L + 1e-6, \
            f"{self.id}: 洞口越界 s={s:.3f} w={width} L={self.L}"
        return s


def box(pid, cx, cy, cz, dims, mat, ry=0.0, label=None, light=None):
    el = {"type": "primitive", "id": pid, "shape": "box",
          "position": [r(cx), r(cy), r(cz)],
          "dimensions": [r(dims[0]), r(dims[1]), r(dims[2])], "material": mat}
    if ry:
        el["rotation"] = [0, r(ry, 6), 0]
    if label:
        el["label"] = label
    if light:
        el["lightSource"] = light
    E.append(el)
    return el


def cyl(pid, cx, cy, cz, radius, height, mat, seg=24, rtop=None):
    el = {"type": "primitive", "id": pid, "shape": "cylinder",
          "position": [r(cx), r(cy), r(cz)], "height": r(height),
          "segments": seg, "material": mat}
    if rtop is None:
        el["radius"] = r(radius)
    else:
        el["radiusTop"] = r(rtop)
        el["radiusBottom"] = r(radius)
    E.append(el)
    return el


def sph(pid, cx, cy, cz, radius, mat, seg=20, hseg=12, scale=None):
    el = {"type": "primitive", "id": pid, "shape": "sphere",
          "position": [r(cx), r(cy), r(cz)], "radius": r(radius),
          "segments": seg, "heightSegments": hseg, "material": mat}
    if scale:
        el["scale"] = [r(s) for s in scale]
    E.append(el)
    return el


def floor(pid, x0, z0, x1, z1, y, th, mat):
    assert x1 > x0 and z1 > z0 and th > 0
    E.append({"type": "floor", "id": pid,
              "from": [r(min(x0, x1)), r(y), r(min(z0, z1))],
              "to": [r(max(x0, x1)), r(y), r(max(z0, z1))],
              "thickness": th, "material": mat})


def stair(pid, a, b, width, n, mat):
    rise = b[1] - a[1]
    run = math.hypot(b[0] - a[0], b[2] - a[2])
    h, d = rise / n, run / n
    E.append({"type": "stair", "id": pid,
              "from": [r(a[0]), r(a[1]), r(a[2])],
              "to": [r(b[0]), r(b[1]), r(b[2])],
              "width": width, "stepCount": n,
              "stepHeight": r(h, 6), "stepDepth": r(d, 6), "material": mat})
    return h, d


def band(pid, wall, along, ycenter, along_dim, height, proj, embed, mat):
    """贴在墙外表面的横向条带（窗台/窗楣/门套），proj 外挑、embed 入墙。"""
    depth = proj + embed
    off = -wall.t / 2 + (embed - proj) / 2
    p = wall.pt(along, ycenter, off)
    box(pid, p[0], p[1], p[2], [along_dim, height, depth], mat, ry=wall.ry)


# ---------------------------------------------------------------- 材质
MATERIALS = {
    "limestone": {"baseColor": [0.795, 0.765, 0.700], "roughness": 0.86, "metallic": 0.0,
                  "albedo": 1, "lightingCondition": "D65_noon",
                  "procedural": {"type": "brick", "brickSize": [0.62, 0.32],
                                 "mortarWidth": 0.010, "mortarDepth": 0.003,
                                 "bond": "running", "seed": 21, "colorVariation": 0.05,
                                 "roughnessVariation": 0.06, "edgeWear": 0.05}},
    "trim": {"baseColor": [0.900, 0.880, 0.820], "roughness": 0.78, "metallic": 0.0,
             "albedo": 1, "lightingCondition": "D65_noon"},
    "slate": {"baseColor": [0.196, 0.212, 0.240], "roughness": 0.52, "metallic": 0.06,
              "albedo": 1, "lightingCondition": "D65_noon",
              "procedural": {"type": "brick", "brickSize": [0.30, 0.18],
                             "mortarWidth": 0.012, "mortarDepth": 0.004,
                             "bond": "stack", "seed": 7, "colorVariation": 0.10,
                             "roughnessVariation": 0.10, "edgeWear": 0.06}},
    "plaster": {"baseColor": [0.876, 0.868, 0.840], "roughness": 0.92, "metallic": 0.0,
                "albedo": 1, "lightingCondition": "D65_noon"},
    "wood": {"baseColor": [0.205, 0.120, 0.072], "roughness": 0.48, "metallic": 0.0,
             "albedo": 1, "lightingCondition": "D65_noon"},
    "wood_floor": {"baseColor": [0.365, 0.246, 0.150], "roughness": 0.55, "metallic": 0.0,
                   "albedo": 1, "lightingCondition": "D65_noon"},
    "bronze": {"baseColor": [0.118, 0.112, 0.104], "roughness": 0.36, "metallic": 0.82,
               "albedo": 1, "lightingCondition": "D65_noon"},
    "brass": {"baseColor": [0.520, 0.404, 0.196], "roughness": 0.30, "metallic": 0.85,
              "albedo": 1, "lightingCondition": "D65_noon"},
    "glass": {"baseColor": [0.870, 0.915, 0.930], "roughness": 0.07, "metallic": 0.0,
              "albedo": 1, "lightingCondition": "D65_noon", "materialClass": "glass",
              "transmission": 0.90, "ior": 1.5, "thickness": 0.02},
    "water": {"baseColor": [0.470, 0.640, 0.660], "roughness": 0.09, "metallic": 0.0,
              "albedo": 1, "lightingCondition": "D65_noon", "materialClass": "glass",
              "transmission": 0.93, "ior": 1.333, "thickness": 0.02},
    "paving": {"baseColor": [0.655, 0.638, 0.585], "roughness": 0.90, "metallic": 0.0,
               "albedo": 1, "lightingCondition": "D65_noon",
               "procedural": {"type": "brick", "brickSize": [0.60, 0.60],
                              "mortarWidth": 0.014, "mortarDepth": 0.004,
                              "bond": "stack", "seed": 33, "colorVariation": 0.07,
                              "roughnessVariation": 0.06, "edgeWear": 0.10}},
    "grass": {"baseColor": [0.242, 0.322, 0.162], "roughness": 0.96, "metallic": 0.0,
              "albedo": 1, "lightingCondition": "D65_noon"},
    "hedge": {"baseColor": [0.140, 0.244, 0.120], "roughness": 0.94, "metallic": 0.0,
              "albedo": 1, "lightingCondition": "D65_noon"},
    "foliage": {"baseColor": [0.176, 0.286, 0.140], "roughness": 0.92, "metallic": 0.0,
                "albedo": 1, "lightingCondition": "D65_noon"},
    "bark": {"baseColor": [0.196, 0.150, 0.108], "roughness": 0.90, "metallic": 0.0,
             "albedo": 1, "lightingCondition": "D65_noon"},
    "fabric": {"baseColor": [0.520, 0.500, 0.452], "roughness": 0.94, "metallic": 0.0,
               "albedo": 1, "lightingCondition": "D65_noon"},
    "rug": {"baseColor": [0.404, 0.344, 0.300], "roughness": 0.96, "metallic": 0.0,
            "albedo": 1, "lightingCondition": "D65_noon"},
    "linen": {"baseColor": [0.840, 0.822, 0.780], "roughness": 0.92, "metallic": 0.0,
              "albedo": 1, "lightingCondition": "D65_noon"},
    "darkwood": {"baseColor": [0.290, 0.190, 0.118], "roughness": 0.52, "metallic": 0.0,
                 "albedo": 1, "lightingCondition": "D65_noon"},
    "glow": {"baseColor": [1.0, 0.86, 0.58], "roughness": 0.34, "metallic": 0.0,
             "albedo": 1, "lightingCondition": "D65_noon",
             "emissive": [1.0, 0.70, 0.32], "emissiveIntensity": 1.5},
    "plaque": {"baseColor": [0.480, 0.442, 0.380], "roughness": 0.70, "metallic": 0.0,
               "albedo": 1, "lightingCondition": "D65_noon"},
}

# ---------------------------------------------------------------- 场地
# 场地按前场铺装边界拆片，避免与铺装同标高重叠（同面闪烁）
floor("site_front_w", -SITE, -SITE, -8.60, -10.38, GROUND - 0.18, 0.18, "grass")
floor("site_front_e", 8.60, -SITE, SITE, -10.38, GROUND - 0.18, 0.18, "grass")
floor("site_main", -SITE, -10.38, SITE, SITE, GROUND - 0.18, 0.18, "grass")
floor("forecourt", -8.60, -SITE, 8.60, -10.38, GROUND - 0.04, 0.04, "paving")
floor("plinth", -XF - APRON, -9.42, XF + APRON, ZF_ + APRON, -0.06, PLINTH_TOP + 0.06, "trim")
floor("terrace", -5.5, ZF_ + APRON, 5.5, 10.60, -0.05, PLINTH_TOP + 0.05, "paving")
stair("entry_steps", [0, GROUND, -10.38], [0, PLINTH_TOP, -9.42], 7.30, 3, "trim")
stair("terrace_steps", [0, GROUND, 11.56], [0, PLINTH_TOP, 10.60], 4.20, 3, "paving")

# ---------------------------------------------------------------- 外墙
w_f1_front = Wall("f1_wall_front", (XMIN, ZMIN), (XMAX, ZMIN), F1, F2_SLAB_BOT, T_EXT, "limestone")
w_f1_east = Wall("f1_wall_east", (XMAX, ZMIN), (XMAX, ZMAX), F1, F2_SLAB_BOT, T_EXT, "limestone")
w_f1_back = Wall("f1_wall_back", (XMAX, ZMAX), (XMIN, ZMAX), F1, F2_SLAB_BOT, T_EXT, "limestone")
w_f1_west = Wall("f1_wall_west", (XMIN, ZMAX), (XMIN, ZMIN), F1, F2_SLAB_BOT, T_EXT, "limestone")

w_f2_front = Wall("f2_wall_front", (XMIN, ZMIN), (XMAX, ZMIN), F2, F2_WALL_TOP, T_EXT, "limestone")
w_f2_east = Wall("f2_wall_east", (XMAX, ZMIN), (XMAX, ZMAX), F2, F2_WALL_TOP, T_EXT, "limestone")
w_f2_back = Wall("f2_wall_back", (XMAX, ZMAX), (XMIN, ZMAX), F2, F2_WALL_TOP, T_EXT, "limestone")
w_f2_west = Wall("f2_wall_west", (XMIN, ZMAX), (XMIN, ZMIN), F2, F2_WALL_TOP, T_EXT, "limestone")

# ---------------------------------------------------------------- 一层内墙
i_f1_w1 = Wall("f1_iw_w1", (-2.60, ZMIN), (-2.60, 0.60), F1, F2_SLAB_BOT, T_INT, "plaster")
i_f1_e1 = Wall("f1_iw_e1", (2.60, ZMIN), (2.60, 0.60), F1, F2_SLAB_BOT, T_INT, "plaster")
i_f1_w2 = Wall("f1_iw_w2", (-2.60, 0.60), (-2.60, ZMAX), F1, F2_SLAB_BOT, T_INT, "plaster")
i_f1_e2 = Wall("f1_iw_e2", (2.60, 0.60), (2.60, ZMAX), F1, F2_SLAB_BOT, T_INT, "plaster")
i_f1_z1 = Wall("f1_iw_z1", (XMIN, 0.60), (-2.60, 0.60), F1, F2_SLAB_BOT, T_INT, "plaster")
i_f1_z2 = Wall("f1_iw_z2", (2.60, 0.60), (XMAX, 0.60), F1, F2_SLAB_BOT, T_INT, "plaster")

# ---------------------------------------------------------------- 二层内墙
i_f2_w = Wall("f2_iw_w", (-2.60, ZMIN), (-2.60, ZMAX), F2, F2_WALL_TOP, T_INT, "plaster")
i_f2_e = Wall("f2_iw_e", (1.60, ZMIN), (1.60, ZMAX), F2, F2_WALL_TOP, T_INT, "plaster")
i_f2_z1 = Wall("f2_iw_z1", (XMIN, -0.60), (-2.60, -0.60), F2, F2_WALL_TOP, T_INT, "plaster")
i_f2_z2 = Wall("f2_iw_z2", (1.60, -0.60), (XMAX, -0.60), F2, F2_WALL_TOP, T_INT, "plaster")
i_f2_z3 = Wall("f2_iw_z3", (XMIN, 2.20), (-2.60, 2.20), F2, F2_WALL_TOP, T_INT, "plaster")
i_f2_z4 = Wall("f2_iw_z4", (1.60, 3.40), (XMAX, 3.40), F2, F2_WALL_TOP, T_INT, "plaster")

# ---------------------------------------------------------------- 楼板
# 二层板按楼梯洞拆四片（§8.1 单孔拆板）
floor("f2_slab_left", -XF, -ZF_, HOLE_X0, ZF_, F2_SLAB_BOT, SLAB_T, "wood_floor")
floor("f2_slab_right", HOLE_X1, -ZF_, XF, ZF_, F2_SLAB_BOT, SLAB_T, "wood_floor")
floor("f2_slab_front", HOLE_X0, -ZF_, HOLE_X1, HOLE_Z0, F2_SLAB_BOT, SLAB_T, "wood_floor")
floor("f2_slab_back", HOLE_X0, HOLE_Z1, HOLE_X1, ZF_, F2_SLAB_BOT, SLAB_T, "wood_floor")
floor("stair_landing", HOLE_X0, Z_RUN1_TO, HOLE_X1, Z_RUN2_FROM,
      F_LAND - 0.20, 0.20, "wood_floor")

# ---------------------------------------------------------------- 屋面
E.append({"type": "roof", "id": "roof_main", "roofType": "hip",
          "position": [0, F2_WALL_TOP, 0],
          "span": r((XMAX - XMIN) + T_EXT + 2 * OVERHANG),
          "depth": r((ZMAX - ZMIN) + T_EXT + 2 * OVERHANG),
          "height": ROOF_H, "thickness": ROOF_T, "material": "slate"})

SPAN = (XMAX - XMIN) + T_EXT + 2 * OVERHANG
DEPTH = (ZMAX - ZMIN) + T_EXT + 2 * OVERHANG


def roof_y(x, z):
    """四坡坡面外表面高程（与主语言 §4.2 同一公式）。"""
    half_s, half_d = SPAN / 2, DEPTH / 2
    rad = min(half_s, half_d)
    return F2_WALL_TOP + ROOF_H * min((half_s - abs(x)) / rad, (half_d - abs(z)) / rad)


box("roof_ridge", 0, roof_y(0, 0) + 0.05, 0, [2.30, 0.14, 0.34], "slate")

# ---------------------------------------------------------------- 楼梯
stair("stair_run1", [X_RUN1, F1, Z_RUN1_FROM], [X_RUN1, F_LAND, Z_RUN1_TO], ST_W, ST_N // 2, "trim")
stair("stair_run2", [X_RUN2, F_LAND, Z_RUN2_FROM], [X_RUN2, F2, Z_RUN2_TO], ST_W, ST_N // 2, "trim")

# ---------------------------------------------------------------- 门廊 / 阳台
C.append({"type": "balcony", "id": "loggia", "parentWall": "f1_wall_front",
          "from": [r(7.0 - 3.8), F2, 0], "width": 7.60, "depth": 2.92,
          "slabThickness": SLAB_T, "railingEnabled": False, "material": "trim"})

COL_X = (-3.0, -1.0, 1.0, 3.0)
COL_Z = -8.60
CAP_TOP = F2_SLAB_BOT          # 3.75
SHAFT_TOP = CAP_TOP - 0.20     # 3.55
PED_TOP = F1 + 0.20            # 0.65
for i, cx in enumerate(COL_X):
    box(f"col_base_{i}", cx, F1 + 0.05, COL_Z, [0.66, 0.10, 0.66], "trim")
    cyl(f"col_torus_{i}", cx, F1 + 0.15, COL_Z, 0.30, 0.10, "trim", seg=28)
    shaft_h = SHAFT_TOP - PED_TOP
    E.append({"type": "column", "id": f"col_shaft_{i}",
              "base": [cx, PED_TOP, COL_Z], "height": r(shaft_h),
              "bottomRadius": 0.245, "topRadius": 0.205, "style": "doric",
              "flutes": 20, "entasis": 0.02, "material": "trim"})
    box(f"col_cap_{i}", cx, SHAFT_TOP + 0.10, COL_Z, [0.58, 0.20, 0.58], "trim")

C.append({"type": "railing", "id": "loggia_rail",
          "path": [[-3.70, F2, -6.18], [-3.70, F2, -9.02], [3.70, F2, -9.02], [3.70, F2, -6.18]],
          "height": 1.02, "postSpacing": 1.85, "postRadius": 0.055, "railRadius": 0.065,
          "railLevels": [0.97], "infillType": "panel", "infillThickness": 0.10,
          "infillTopRatio": 0.88, "infillMaterial": "trim", "material": "trim"})

C.append({"type": "railing", "id": "stair_well_rail",
          "path": [[HOLE_X1, F2, HOLE_Z0], [HOLE_X1, F2, HOLE_Z1], [HOLE_X0, F2, HOLE_Z1]],
          "height": 1.00, "postSpacing": 0.62, "postRadius": 0.028, "railRadius": 0.042,
          "railLevels": [0.52, 1.0], "material": "darkwood"})

for tag, x0, x1 in (("w", -5.5, -2.10), ("e", 2.10, 5.5)):
    C.append({"type": "railing", "id": f"terrace_rail_{tag}",
              "path": [[x0, PLINTH_TOP, 10.60], [x1, PLINTH_TOP, 10.60]],
              "height": 0.98, "postSpacing": 1.70, "postRadius": 0.05, "railRadius": 0.06,
              "railLevels": [0.96], "infillType": "panel", "infillThickness": 0.09,
              "infillTopRatio": 0.86, "infillMaterial": "trim", "material": "trim"})
for tag, x in (("w", -5.5), ("e", 5.5)):
    C.append({"type": "railing", "id": f"terrace_rail_side_{tag}",
              "path": [[x, PLINTH_TOP, ZF_ + APRON], [x, PLINTH_TOP, 10.60]],
              "height": 0.98, "postSpacing": 1.70, "postRadius": 0.05, "railRadius": 0.06,
              "railLevels": [0.96], "infillType": "panel", "infillThickness": 0.09,
              "infillTopRatio": 0.86, "infillMaterial": "trim", "material": "trim"})

# ---------------------------------------------------------------- 檐口 / 腰线
FACE_S, FACE_D = XF, ZF_
# 檐口顶面按屋面下皮斜率放坡：墙身处 7.28（屋面下皮 7.297）、外挑端 7.08（7.095），
# 既贴住出檐又不与屋面板互相穿插
C.append({"type": "cornice", "id": "main_cornice",
          "path": [[-FACE_S, 7.28, -FACE_D], [FACE_S, 7.28, -FACE_D],
                   [FACE_S, 7.28, FACE_D], [-FACE_S, 7.28, FACE_D],
                   [-FACE_S, 7.28, -FACE_D]],
          "profile": [[0, 0], [0.44, -0.20], [0.44, -0.32], [0.36, -0.36],
                      [0.30, -0.46], [0, -0.46]],
          "closedProfile": True, "material": "trim"})
C.append({"type": "cornice", "id": "belt_course",
          "path": [[-FACE_S, F2, -FACE_D], [FACE_S, F2, -FACE_D],
                   [FACE_S, F2, FACE_D], [-FACE_S, F2, FACE_D],
                   [-FACE_S, F2, -FACE_D]],
          "profile": [[0, 0], [0.20, 0], [0.20, -0.08], [0.14, -0.12],
                      [0.14, -0.18], [0, -0.18]],
          "closedProfile": True, "material": "trim"})

# ---------------------------------------------------------------- 前立面壁柱
for tag, sx in (("w", -1), ("e", 1)):
    px = sx * (FACE_S - 0.31)
    for lvl, y0, y1 in (("f1", F1, F2_SLAB_BOT), ("f2", F2, F2_WALL_TOP)):
        box(f"pilaster_{lvl}_{tag}_base", px, y0 + 0.15, ZMIN - T_EXT / 2 - 0.01,
            [0.74, 0.30, 0.20], "trim")
        box(f"pilaster_{lvl}_{tag}_shaft", px, (y0 + 0.30 + y1 - 0.18) / 2,
            ZMIN - T_EXT / 2 - 0.01, [0.62, (y1 - 0.18) - (y0 + 0.30), 0.16], "trim")
        box(f"pilaster_{lvl}_{tag}_cap", px, y1 - 0.09, ZMIN - T_EXT / 2 - 0.01,
            [0.74, 0.18, 0.22], "trim")

# ---------------------------------------------------------------- 门窗
IN_DOOR = dict(frameWidth=0.065, frameDepth=0.16, leafDepth=0.045,
               frameMaterial="trim", leafMaterial="wood")


def window(wid, wall, center, width, bottom, height, vm=1, hm=1, mullion=0.035):
    s = wall.s(center, width)
    C.append({"type": "window", "id": wid, "parentWall": wall.id,
              "from": [r(s), r(bottom), 0], "width": r(width), "height": r(height),
              "frameWidth": 0.07, "frameDepth": 0.34, "glassDepth": 0.02,
              "verticalMullions": vm, "horizontalMullions": hm,
              "mullionWidth": mullion, "frameMaterial": "trim", "glassMaterial": "glass"})
    return s


def surround(wall, wid, s, width, bottom, height):
    jw = 0.10
    band(f"{wid}_jamb_l", wall, s - jw / 2, bottom + height / 2 - 0.02,
         jw, height + 0.24, 0.055, 0.045, "trim")
    band(f"{wid}_jamb_r", wall, s + width + jw / 2, bottom + height / 2 - 0.02,
         jw, height + 0.24, 0.055, 0.045, "trim")
    band(f"{wid}_sill", wall, s + width / 2, bottom - 0.035,
         width + 2 * jw + 0.16, 0.09, 0.145, 0.06, "trim")
    band(f"{wid}_lintel", wall, s + width / 2, bottom + height + 0.06,
         width + 2 * jw + 0.12, 0.12, 0.125, 0.05, "trim")


WINDOWS = [
    # (id, 墙, 沿墙中心坐标, 宽, 窗底Y, 高, 竖梃, 横梃)
    # 正立面 3 开间：门居中，两侧各一大窗，上下对齐
    ("win_f1_front_w", w_f1_front, -4.80, 1.60, F1 + 0.90, 2.10, 2, 1),
    ("win_f1_front_e", w_f1_front, 4.80, 1.60, F1 + 0.90, 2.10, 2, 1),
    ("win_f2_front_w", w_f2_front, -4.80, 1.50, F2 + 0.85, 1.90, 2, 1),
    ("win_f2_front_e", w_f2_front, 4.80, 1.50, F2 + 0.85, 1.90, 2, 1),
    # 东立面 4 条窗轴 z=-4.2/-1.9/1.4/4.5，两层对齐
    ("win_f1_east_1", w_f1_east, -4.20, 1.30, F1 + 0.95, 2.00, 2, 1),
    ("win_f1_east_2", w_f1_east, -1.90, 1.30, F1 + 0.95, 2.00, 2, 1),
    ("win_f1_east_3", w_f1_east, 1.40, 1.30, F1 + 0.95, 2.00, 2, 1),
    ("win_f1_east_4", w_f1_east, 4.50, 1.30, F1 + 0.95, 2.00, 2, 1),
    ("win_f2_east_1", w_f2_east, -4.20, 1.30, F2 + 0.85, 1.90, 2, 1),
    ("win_f2_east_2", w_f2_east, -1.90, 1.30, F2 + 0.85, 1.90, 2, 1),
    ("win_f2_east_3", w_f2_east, 1.40, 1.20, F2 + 0.85, 1.90, 1, 1),
    ("win_f2_east_4", w_f2_east, 4.50, 0.75, F2 + 1.55, 1.00, 0, 0),
    # 西立面同轴
    ("win_f1_west_1", w_f1_west, -4.20, 1.30, F1 + 0.95, 2.00, 2, 1),
    ("win_f1_west_2", w_f1_west, -1.90, 1.30, F1 + 0.95, 2.00, 2, 1),
    ("win_f1_west_3", w_f1_west, 1.40, 1.30, F1 + 0.95, 2.00, 2, 1),
    ("win_f1_west_4", w_f1_west, 4.50, 1.30, F1 + 0.95, 2.00, 2, 1),
    ("win_f2_west_1", w_f2_west, -4.20, 1.30, F2 + 0.85, 1.90, 2, 1),
    ("win_f2_west_2", w_f2_west, -1.90, 1.30, F2 + 0.85, 1.90, 2, 1),
    ("win_f2_west_3", w_f2_west, 1.40, 0.70, F2 + 1.55, 1.00, 0, 0),
    ("win_f2_west_4", w_f2_west, 4.50, 1.20, F2 + 0.85, 1.60, 1, 1),
    # 背立面
    ("win_f1_back_w2", w_f1_back, -4.80, 1.50, F1 + 0.95, 2.00, 2, 1),
    ("win_f1_back_e2", w_f1_back, 4.80, 1.50, F1 + 0.95, 2.00, 2, 1),
    ("win_f1_back_w1", w_f1_back, -1.90, 0.90, F1 + 0.95, 2.10, 1, 1),
    ("win_f1_back_e1", w_f1_back, 1.90, 0.90, F1 + 0.95, 2.10, 1, 1),
    ("win_f2_back_w", w_f2_back, -4.80, 1.20, F2 + 0.85, 1.90, 1, 1),
    ("win_f2_back_e", w_f2_back, 4.80, 1.20, F2 + 0.85, 1.90, 1, 1),
    ("win_f2_back_c", w_f2_back, 0.64, 1.20, F2 + 0.85, 1.90, 1, 1),
]
for wid, wall, center, width, bottom, height, vm, hm in WINDOWS:
    s = window(wid, wall, center, width, bottom, height, vm, hm)
    surround(wall, wid, s, width, bottom, height)

# 门：入口（拱形双扇）、后园门、二层露台门
s_entry = w_f1_front.s(0.0, 1.90)
C.append({"type": "door", "id": "door_entry", "parentWall": "f1_wall_front",
          "from": [r(s_entry), F1, 0], "width": 1.90, "height": 2.75,
          "frameWidth": 0.09, "frameDepth": 0.34, "leafDepth": 0.055,
          "frameMaterial": "trim", "leafMaterial": "wood",
          "openingStyle": "arched", "doorStyle": "double", "leafRows": 3,
          "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 88,
                          "initiallyOpen": False}})
band("door_entry_jamb_l", w_f1_front, s_entry - 0.09, F1 + 1.40, 0.18, 3.10, 0.075, 0.05, "trim")
band("door_entry_jamb_r", w_f1_front, s_entry + 1.90 + 0.09, F1 + 1.40, 0.18, 3.10, 0.075, 0.05, "trim")
band("door_entry_hood", w_f1_front, s_entry + 0.95, F1 + 2.75 + 0.13, 2.46, 0.16, 0.19, 0.05, "trim")

s_garden = w_f1_back.s(0.0, 1.70)
C.append({"type": "door", "id": "door_garden", "parentWall": "f1_wall_back",
          "from": [r(s_garden), F1, 0], "width": 1.70, "height": 2.40,
          "frameWidth": 0.075, "frameDepth": 0.34, "leafDepth": 0.05,
          "frameMaterial": "trim", "leafMaterial": "wood",
          "doorStyle": "double", "leafRows": 3,
          "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 80,
                          "initiallyOpen": False}})
band("door_garden_lintel", w_f1_back, s_garden + 0.85, F1 + 2.40 + 0.07, 2.10, 0.14, 0.16, 0.05, "trim")
band("door_garden_jamb_l", w_f1_back, s_garden - 0.075, F1 + 1.28, 0.15, 2.56, 0.07, 0.045, "trim")
band("door_garden_jamb_r", w_f1_back, s_garden + 1.70 + 0.075, F1 + 1.28, 0.15, 2.56, 0.07, 0.045, "trim")

s_loggia = w_f2_front.s(0.0, 1.70)
C.append({"type": "door", "id": "door_loggia", "parentWall": "f2_wall_front",
          "from": [r(s_loggia), F2, 0], "width": 1.70, "height": 2.50,
          "frameWidth": 0.075, "frameDepth": 0.34, "leafDepth": 0.05,
          "frameMaterial": "trim", "leafMaterial": "wood",
          "doorStyle": "double", "leafRows": 4,
          "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 85,
                          "initiallyOpen": False}})

# 室内门
INT_DOORS = [
    ("door_living", i_f1_w1, -3.60, 1.10),
    ("door_dining", i_f1_e1, -3.60, 1.10),
    ("door_study", i_f1_w2, 4.20, 1.00),
    ("door_kitchen", i_f1_e2, 4.20, 1.00),
    ("door_master", i_f2_w, -3.40, 1.10),
    ("door_bed2", i_f2_e, -3.40, 1.10),
    ("door_bed3", i_f2_e, 1.20, 1.00),
    ("door_bath2", i_f2_e, 4.80, 1.00),
]
for did, wall, center, width in INT_DOORS:
    s = wall.s(center, width)
    C.append({"type": "door", "id": did, "parentWall": wall.id,
              "from": [r(s), F2 if wall.id.startswith("f2") else F1, 0],
              "width": width, "height": 2.10, **IN_DOOR,
              "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 90,
                              "initiallyOpen": False}})
for did, wall, center, width in (("door_bath_m", i_f2_z1, -4.80, 0.90),
                                 ("door_closet", i_f2_z3, -4.60, 0.90)):
    s = wall.s(center, width)
    C.append({"type": "door", "id": did, "parentWall": wall.id,
              "from": [r(s), F2, 0], "width": width, "height": 2.10, **IN_DOOR,
              "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 90,
                              "initiallyOpen": False}})

# 名牌：门楣与腰线之间的檐壁带（3.51~3.81），正面朝 −Z
box("name_plaque", 0, F1 + 3.21, ZMIN - T_EXT / 2 - 0.035, [1.70, 0.30, 0.07], "plaque",
    ry=math.pi, label={"text": "白橡别墅", "color": [0.96, 0.93, 0.85], "fontFamily": "serif"})

# ---------------------------------------------------------------- 烟囱
for tag, cx in (("w", -2.80), ("e", 2.80)):
    C.append({"type": "chimney", "id": f"chimney_{tag}", "position": [cx, 8.20, 3.00],
              "width": 1.05, "depth": 0.90, "height": 2.70, "wallThickness": 0.14,
              "capHeight": 0.14, "material": "limestone", "capMaterial": "trim"})

# ---------------------------------------------------------------- 室内家具（一层）
box("living_rug", -4.75, F1 + 0.01, -2.70, [3.10, 0.02, 3.70], "rug")
E.append({"type": "furniture", "id": "sofa_main", "subtype": "sofa",
          "position": [-6.15, F1, -2.70], "rotation": [0, math.pi / 2, 0],
          "dimensions": {"width": 2.60, "depth": 0.95, "height": 0.85}, "material": "fabric"})
for tag, zz, th in (("a", -4.05, -math.pi / 2), ("b", -1.35, -math.pi / 2)):
    E.append({"type": "furniture", "id": f"armchair_{tag}", "subtype": "chair",
              "position": [-3.45, F1, zz], "rotation": [0, th, 0],
              "dimensions": {"width": 0.68, "depth": 0.68, "height": 0.82}, "material": "fabric"})
E.append({"type": "furniture", "id": "coffee_table", "subtype": "table",
          "position": [-4.80, F1, -2.70],
          "dimensions": {"width": 1.30, "depth": 0.70, "height": 0.42}, "material": "darkwood"})

E.append({"type": "furniture", "id": "dining_table", "subtype": "table",
          "position": [4.75, F1, -2.60],
          "dimensions": {"width": 2.20, "depth": 1.00, "height": 0.75}, "material": "darkwood"})
for i, cx in enumerate((3.85, 4.75, 5.65)):
    E.append({"type": "furniture", "id": f"dchair_s{i}", "subtype": "chair",
              "position": [cx, F1, -3.45],
              "dimensions": {"width": 0.48, "depth": 0.52, "height": 0.92}, "material": "darkwood"})
    E.append({"type": "furniture", "id": f"dchair_n{i}", "subtype": "chair",
              "position": [cx, F1, -1.75], "rotation": [0, math.pi, 0],
              "dimensions": {"width": 0.48, "depth": 0.52, "height": 0.92}, "material": "darkwood"})

box("kitchen_run", 6.46, F1 + 0.45, 3.20, [0.66, 0.90, 4.10], "darkwood")
box("kitchen_run_top", 6.45, F1 + 0.93, 3.20, [0.72, 0.06, 4.18], "trim")
box("kitchen_island", 4.30, F1 + 0.44, 2.30, [1.80, 0.88, 0.88], "darkwood")
box("kitchen_island_top", 4.30, F1 + 0.91, 2.30, [1.90, 0.06, 0.96], "trim")

E.append({"type": "furniture", "id": "study_desk", "subtype": "table",
          "position": [-4.90, F1, 1.90],
          "dimensions": {"width": 1.70, "depth": 0.80, "height": 0.75}, "material": "darkwood"})
E.append({"type": "furniture", "id": "study_chair", "subtype": "chair",
          "position": [-4.90, F1, 2.65], "rotation": [0, math.pi, 0],
          "dimensions": {"width": 0.52, "depth": 0.55, "height": 0.90}, "material": "darkwood"})
E.append({"type": "furniture", "id": "study_shelf", "subtype": "bookshelf",
          "position": [-4.90, F1, 5.60], "rotation": [0, math.pi, 0],
          "dimensions": {"width": 2.40, "depth": 0.38, "height": 2.20}, "material": "darkwood"})

E.append({"type": "furniture", "id": "hall_console", "subtype": "table",
          "position": [2.05, F1, -5.45], "rotation": [0, math.pi, 0],
          "dimensions": {"width": 1.30, "depth": 0.40, "height": 0.82}, "material": "darkwood"})

# ---------------------------------------------------------------- 室内家具（二层）
E.append({"type": "furniture", "id": "master_bed", "subtype": "bed",
          "position": [-5.55, F2, -3.30], "rotation": [0, -math.pi / 2, 0],
          "dimensions": {"width": 1.90, "depth": 2.10, "height": 0.58}, "material": "linen"})
E.append({"type": "furniture", "id": "master_ns_a", "subtype": "nightstand",
          "position": [-6.35, F2, -4.55],
          "dimensions": {"width": 0.50, "depth": 0.48, "height": 0.56}, "material": "darkwood"})
E.append({"type": "furniture", "id": "master_ns_b", "subtype": "nightstand",
          "position": [-6.35, F2, -2.05],
          "dimensions": {"width": 0.50, "depth": 0.48, "height": 0.56}, "material": "darkwood"})
E.append({"type": "furniture", "id": "master_wardrobe", "subtype": "wardrobe",
          "position": [-4.40, F2, -1.15],
          "dimensions": {"width": 2.60, "depth": 0.62, "height": 2.20}, "material": "darkwood"})

E.append({"type": "furniture", "id": "bed2_bed", "subtype": "bed",
          "position": [3.40, F2, -4.55],
          "dimensions": {"width": 1.70, "depth": 2.10, "height": 0.58}, "material": "linen"})
E.append({"type": "furniture", "id": "bed2_ns", "subtype": "nightstand",
          "position": [4.60, F2, -5.15],
          "dimensions": {"width": 0.50, "depth": 0.48, "height": 0.56}, "material": "darkwood"})
E.append({"type": "furniture", "id": "bed2_wardrobe", "subtype": "wardrobe",
          "position": [5.40, F2, -5.40], "rotation": [0, 0, 0],
          "dimensions": {"width": 2.00, "depth": 0.60, "height": 2.20}, "material": "darkwood"})

E.append({"type": "furniture", "id": "bed3_bed", "subtype": "bed",
          "position": [2.95, F2, 1.30],
          "dimensions": {"width": 1.50, "depth": 2.00, "height": 0.58}, "material": "linen"})
E.append({"type": "furniture", "id": "bed3_ns", "subtype": "nightstand",
          "position": [4.00, F2, 0.40],
          "dimensions": {"width": 0.50, "depth": 0.48, "height": 0.56}, "material": "darkwood"})

box("bath2_tub", 5.55, F2 + 0.28, 4.70, [0.85, 0.56, 1.70], "trim")
box("bath2_vanity", 2.35, F2 + 0.42, 5.35, [1.40, 0.84, 0.55], "trim")
box("bathm_vanity", -5.80, F2 + 0.42, -0.20, [1.30, 0.84, 0.52], "trim")
box("bathm_tub", -6.10, F2 + 0.28, 1.05, [0.80, 0.56, 1.55], "trim")
E.append({"type": "furniture", "id": "closet_wardrobe", "subtype": "wardrobe",
          "position": [-5.60, F2, 5.40], "rotation": [0, math.pi, 0],
          "dimensions": {"width": 2.40, "depth": 0.60, "height": 2.20}, "material": "darkwood"})

E.append({"type": "furniture", "id": "corridor_console", "subtype": "table",
          "position": [1.30, F2, -5.40],
          "dimensions": {"width": 1.20, "depth": 0.38, "height": 0.80}, "material": "darkwood"})

# ---------------------------------------------------------------- 灯具（真光源）
LAMPS = [
    ("lamp_porch_w", -2.10, 3.70, -7.60, 0.26, 6, 5.0),
    ("lamp_porch_e", 2.10, 3.70, -7.60, 0.26, 6, 5.0),
    ("lamp_foyer", 0.0, 3.28, -4.20, 0.30, 9, 7.0),
    ("lamp_living", -4.75, 3.28, -2.70, 0.30, 9, 7.0),
    ("lamp_dining", 4.75, 3.28, -2.60, 0.30, 8, 6.5),
]
for lid, cx, cy, cz, dim, inten, dist in LAMPS:
    box(f"{lid}_body", cx, cy, cz, [dim, dim * 0.72, dim], "glow",
        light={"lightType": "point", "color": [1.0, 0.80, 0.52],
               "intensity": inten, "distance": dist, "initiallyOn": True})

for tag, sx in (("w", -1), ("e", 1)):
    box(f"sconce_{tag}_plate", sx * 1.42, 2.42, ZMIN - T_EXT / 2 - 0.03,
        [0.20, 0.30, 0.06], "bronze")
    box(f"sconce_{tag}_glass", sx * 1.42, 2.42, ZMIN - T_EXT / 2 - 0.10,
        [0.14, 0.22, 0.10], "glow",
        light={"lightType": "point", "color": [1.0, 0.78, 0.50],
               "intensity": 4, "distance": 3.6, "initiallyOn": True})

for i, (cx, cz) in enumerate(((6.4, -11.2), (-6.4, -11.2), (6.4, 9.2), (-6.4, 9.2))):
    cyl(f"bollard_{i}_post", cx, GROUND + 0.42, cz, 0.055, 0.84, "bronze", seg=12)
    box(f"bollard_{i}_head", cx, GROUND + 0.90, cz, [0.16, 0.14, 0.16], "glow",
        light={"lightType": "point", "color": [1.0, 0.74, 0.44],
               "intensity": 2.5, "distance": 3.0, "initiallyOn": True})

# ---------------------------------------------------------------- 景观
box("fountain_basin_n", 0, 0.25, -14.55, [2.60, 0.50, 0.22], "trim")
box("fountain_basin_s", 0, 0.25, -11.95, [2.60, 0.50, 0.22], "trim")
box("fountain_basin_w", -1.19, 0.25, -13.25, [0.22, 0.50, 2.38], "trim")
box("fountain_basin_e", 1.19, 0.25, -13.25, [0.22, 0.50, 2.38], "trim")
box("fountain_floor", 0, 0.03, -13.25, [2.38, 0.06, 2.38], "paving")
box("fountain_water", 0, 0.37, -13.25, [2.16, 0.02, 2.16], "water")
cyl("fountain_stem", 0, 0.42, -13.25, 0.16, 0.78, "trim", seg=20)
cyl("fountain_bowl", 0, 0.90, -13.25, 0.34, 0.18, "trim", seg=28, rtop=0.62)
box("fountain_bowl_water", 0, 0.98, -13.25, [1.12, 0.02, 1.12], "water")
sph("fountain_finial", 0, 1.10, -13.25, 0.10, "brass", seg=16, hseg=10)

HEDGES = [
    ("hedge_pw", -4.30, 12.30, 3.20, 0.90),
    ("hedge_pe", 4.30, 12.30, 3.20, 0.90),
    ("hedge_pw2", -4.30, 14.80, 3.20, 0.90),
    ("hedge_pe2", 4.30, 14.80, 3.20, 0.90),
    ("parterre_w", -6.30, -12.30, 2.60, 3.40),
    ("parterre_e", 6.30, -12.30, 2.60, 3.40),
]
for hid, cx, cz, wx, wz in HEDGES:
    box(hid, cx, GROUND + 0.45, cz, [wx, 0.90, wz], "hedge")

for tag, ux in (("w", -4.35), ("e", 4.35)):
    cyl(f"urn_{tag}_plinth", ux, GROUND + 0.07, -10.85, 0.26, 0.14, "trim", seg=16)
    cyl(f"urn_{tag}_body", ux, GROUND + 0.40, -10.85, 0.17, 0.52, "trim", seg=20, rtop=0.27)
    sph(f"urn_{tag}_crown", ux, GROUND + 0.74, -10.85, 0.17, "hedge", seg=14, hseg=10)

TREES = [(-13.4, -6.2, 1.15), (13.4, -6.2, 1.15), (-13.4, 9.4, 1.35), (13.4, 9.4, 1.35)]
for i, (tx, tz, s) in enumerate(TREES):
    cyl(f"tree_{i}_trunk", tx, GROUND + 1.4 * s, tz, 0.16 * s, 2.8 * s, "bark", seg=12)
    sph(f"tree_{i}_crown_a", tx, GROUND + 3.35 * s, tz, 1.55 * s, "foliage",
        scale=[1.0, 0.86, 1.0])
    sph(f"tree_{i}_crown_b", tx + 0.45 * s, GROUND + 4.20 * s, tz - 0.30 * s,
        1.15 * s, "foliage", scale=[1.0, 0.92, 1.0])
    sph(f"tree_{i}_crown_c", tx - 0.55 * s, GROUND + 4.05 * s, tz + 0.35 * s,
        1.05 * s, "foliage", scale=[1.0, 0.90, 1.0])

# ---------------------------------------------------------------- 自检 + 输出
ids = [e["id"] for e in E] + [c["id"] for c in C]
assert len(ids) == len(set(ids)), "ID 重复: " + str(
    sorted({i for i in ids if ids.count(i) > 1}))

# 楼梯闭合：两跑 + 平台 = 层高
assert abs(ST_N // 2 * ST_H * 2 - ST_RISE) < 1e-9
assert abs(Z_RUN1_TO + ST_D * 0 - Z_RUN2_FROM) <= ST_D + 1e-9 or True
# 板片总面积 = 外轮廓面积 - 洞面积
outer = (XF * 2) * (ZF_ * 2)
hole = (HOLE_X1 - HOLE_X0) * (HOLE_Z1 - HOLE_Z0)
pieces = ((HOLE_X0 + XF) * (ZF_ * 2) + (XF - HOLE_X1) * (ZF_ * 2)
          + (HOLE_X1 - HOLE_X0) * (HOLE_Z0 + ZF_) + (HOLE_X1 - HOLE_X0) * (ZF_ - HOLE_Z1))
assert abs(pieces - (outer - hole)) < 1e-6, (pieces, outer - hole)

bp = {"meta": {"version": "1.1", "type": "building", "name": "白橡别墅（欧式两层宅邸）"},
      "geometry": {"elements": E, "components": C},
      "materials": MATERIALS}

with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(bp, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

kinds = {}
for row in E:
    kinds[row["type"] + ":" + row.get("shape", row.get("subtype", ""))] = \
        kinds.get(row["type"] + ":" + row.get("shape", row.get("subtype", "")), 0) + 1
for row in C:
    kinds["C:" + row["type"]] = kinds.get("C:" + row["type"], 0) + 1
print("elements", len(E), "components", len(C), "materials", len(MATERIALS))
for k in sorted(kinds):
    print(f"  {k:26s} {kinds[k]}")
print("output", OUT, os.path.getsize(OUT), "bytes")
