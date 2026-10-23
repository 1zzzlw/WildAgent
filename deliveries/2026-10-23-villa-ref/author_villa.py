# -*- coding: utf-8 -*-
"""
参考图复原：两层奶油白别墅（深色四坡顶 / 方柱门廊 / 二层露台黑铁栏杆）
确定性展开脚本：所有构件由顶部参数表派生，重跑字节一致。
"""
import json
import math
import hashlib
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "villa-ref.wild")

# ── 参数表（唯一事实源） ────────────────────────────────
X0, X1 = 0.0, 13.5          # 主体墙轴线 X
Z0, Z1 = 0.0, 15.0          # 主体墙轴线 Z（front 在 Z0 一侧）
T_EXT = 0.24
T_INT = 0.12

SITE_TOP = 0.00
F1 = 0.45                    # 一层完成面
H1 = 3.30                    # 一层层高
T2 = 0.20                    # 二层板厚
SLAB2_BOT = F1 + H1 - T2     # 3.55 一层墙顶 = 二层板底
F2 = F1 + H1                 # 3.75 二层完成面
H2 = 3.15
WALL_TOP2 = F2 + H2          # 6.90 二层墙顶 = 屋面檐口

ROOF_H = 2.35
ROOF_T = 0.20
EAVE_OV = 0.75               # 常规出檐
EAVE_OV_FRONT = 1.05         # 正面加深，形成露台上方檐影

# 门廊 / 露台
P_X0, P_X1 = 3.05, 10.45
P_Z0, P_Z1 = -3.00, 0.00
PIER = 0.55                  # 方柱截面
PIER_CX_L, PIER_CX_R = P_X0 + PIER / 2 + 0.05, P_X1 - PIER / 2 - 0.05
PIER_CZ = P_Z0 + PIER / 2 + 0.03

# 露台栏杆
RAIL_H = 1.05
TP_X0, TP_X1 = PIER_CX_L, PIER_CX_R
TP_Z = P_Z0 + 0.06

# 楼梯（右侧，X 10.55~13.35，Z 9.9~14.2）
ST_X0, ST_X1 = 10.55, 13.35
ST_Z0, ST_Z1 = 9.90, 14.20
ST_LANES = ((11.15, "a"), (12.55, "b"))
STEP_N = 10
STEP_H = (F2 - F1) / 2 / STEP_N      # 0.165
STEP_D = 2.80 / STEP_N               # 0.28
LAND_TOP = F1 + STEP_N * STEP_H      # 2.10

MATS = {
    "stucco":     dict(baseColor=[0.870, 0.850, 0.792], roughness=0.86, metallic=0.0, albedo=1),
    "trim":       dict(baseColor=[0.938, 0.930, 0.898], roughness=0.78, metallic=0.0, albedo=1),
    "roof_dark":  dict(baseColor=[0.108, 0.118, 0.128], roughness=0.58, metallic=0.18, albedo=1),
    "frame_dark": dict(baseColor=[0.075, 0.083, 0.090], roughness=0.36, metallic=0.55, albedo=1),
    "metal":      dict(baseColor=[0.055, 0.058, 0.062], roughness=0.42, metallic=0.78, albedo=1),
    "paving":     dict(baseColor=[0.640, 0.638, 0.615], roughness=0.92, metallic=0.0, albedo=1),
    "stone":      dict(baseColor=[0.720, 0.712, 0.680], roughness=0.88, metallic=0.0, albedo=1),
    "stone_step": dict(baseColor=[0.690, 0.680, 0.652], roughness=0.85, metallic=0.0, albedo=1),
    "wood":       dict(baseColor=[0.330, 0.220, 0.132], roughness=0.60, metallic=0.0, albedo=1),
    "wood_pale":  dict(baseColor=[0.470, 0.360, 0.240], roughness=0.62, metallic=0.0, albedo=1),
    "linen":      dict(baseColor=[0.870, 0.858, 0.828], roughness=0.95, metallic=0.0, albedo=1),
    "fabric":     dict(baseColor=[0.360, 0.375, 0.372], roughness=0.96, metallic=0.0, albedo=1),
    "soil":       dict(baseColor=[0.225, 0.180, 0.132], roughness=0.98, metallic=0.0, albedo=1),
    "leaf":       dict(baseColor=[0.145, 0.275, 0.128], roughness=0.90, metallic=0.0, albedo=1),
    "leaf_lite":  dict(baseColor=[0.235, 0.360, 0.170], roughness=0.88, metallic=0.0, albedo=1),
    "glow":       dict(baseColor=[1.000, 0.900, 0.680], roughness=0.45, metallic=0.0, albedo=1,
                       emissive=[1.0, 0.72, 0.34], emissiveIntensity=1.6),
    "glass":      dict(baseColor=[0.880, 0.925, 0.940], roughness=0.06, metallic=0.0, albedo=1,
                       materialClass="glass", transmission=0.90, ior=1.5, thickness=0.012),
}

E = []
C = []
IDS = set()


def add(el):
    if el["id"] in IDS:
        raise AssertionError("重复 id: " + el["id"])
    IDS.add(el["id"])
    E.append(el)
    return el


def comp(el):
    if el["id"] in IDS:
        raise AssertionError("重复 id: " + el["id"])
    IDS.add(el["id"])
    C.append(el)
    return el


def r(v, n=4):
    return round(float(v) + 0.0, n)


# ── 基础几何助手 ────────────────────────────────────────
def box(id_, cx, cy, cz, w, h, d, mat="trim", rot=None, label=None, light=None):
    el = {"type": "primitive", "id": id_, "shape": "box",
          "position": [r(cx), r(cy), r(cz)],
          "dimensions": [r(w), r(h), r(d)], "material": mat}
    if rot:
        el["rotation"] = [r(rot[0]), r(rot[1]), r(rot[2])]
    if label:
        el["label"] = label
    if light:
        el["lightSource"] = light
    return add(el)


def cyl(id_, cx, cy, cz, radius, height, mat="trim", seg=16, rot=None, rtop=None):
    el = {"type": "primitive", "id": id_, "shape": "cylinder",
          "position": [r(cx), r(cy), r(cz)], "radius": r(radius),
          "height": r(height), "segments": seg, "material": mat}
    if rtop is not None:
        el["radiusTop"] = r(rtop)
    if rot:
        el["rotation"] = [r(rot[0]), r(rot[1]), r(rot[2])]
    return add(el)


def sph(id_, cx, cy, cz, radius, mat="leaf", scale=None):
    el = {"type": "primitive", "id": id_, "shape": "sphere",
          "position": [r(cx), r(cy), r(cz)], "radius": r(radius),
          "segments": 14, "heightSegments": 9, "material": mat}
    if scale:
        el["scale"] = [r(s) for s in scale]
    return add(el)


def slab(id_, x0, x1, z0, z1, y, t, mat="stone"):
    assert x1 > x0 and z1 > z0 and t > 0, id_
    return add({"type": "floor", "id": id_,
                "from": [r(x0), r(y), r(z0)], "to": [r(x1), r(y), r(z1)],
                "thickness": r(t), "material": mat})


def wall(id_, x0, z0, x1, z1, ybot, ytop, t=T_EXT, mat="stucco"):
    assert ytop > ybot, id_
    assert abs(x1 - x0) > 1e-6 or abs(z1 - z0) > 1e-6, id_
    return add({"type": "wall", "id": id_,
                "from": [r(x0), r(ybot), r(z0)], "to": [r(x1), r(ytop), r(z1)],
                "thickness": r(t), "material": mat})


def stair(id_, x, z_from, z_to, ybot, ytop, width, n, mat="stone_step"):
    rise = ytop - ybot
    depth = abs(z_to - z_from)
    assert rise > 0 and depth > 0 and n > 0, id_
    return add({"type": "stair", "id": id_,
                "from": [r(x), r(ybot), r(z_from)], "to": [r(x), r(ytop), r(z_to)],
                "width": r(width), "stepCount": int(n),
                "stepHeight": r(rise / n, 6), "stepDepth": r(depth / n, 6),
                "material": mat})


def arch_band(prefix, cx, cy, cz, r_in, thick, depth, a0, a1, n, mat="trim"):
    """在半圆/圆弧上生成一圈楔形块（近似拱券环），θ 为 XY 平面角。"""
    span = a1 - a0
    dth = span / n
    rmid = r_in + thick / 2.0
    chord = 2.0 * rmid * math.sin(abs(dth) / 2.0) + 0.004
    for i in range(n):
        th = a0 + (i + 0.5) * dth
        cxx = cx + rmid * math.cos(th)
        cyy = cy + rmid * math.sin(th)
        box("%s_%02d" % (prefix, i), cxx, cyy, cz,
            chord, thick, depth, mat, rot=[0, 0, th + math.pi / 2.0])


# ── 墙面参数助手 ────────────────────────────────────────
def axis(w):
    ax, _, az = w["from"]
    bx, _, bz = w["to"]
    L = math.hypot(bx - ax, bz - az)
    return ax, az, (bx - ax) / L, (bz - az) / L, L


def s_along(w, at):
    """at = 沿墙变化的那个坐标（X 向墙传 X，Z 向墙传 Z），返回自墙起点算起的距离。"""
    ax, az, ux, uz, L = axis(w)
    return (at - ax) * ux + (at - az) * uz


def win_on(w, id_, at, w_width, yb, h, wall_t=T_EXT, mullions=2, glass="glass"):
    s = s_along(w, at)
    L = axis(w)[4]
    s0 = s - w_width / 2.0
    assert s0 > -1e-6 and s0 + w_width <= L + 1e-6, (id_, s0, w_width, L)
    comp({"type": "window", "id": id_, "parentWall": w["id"],
          "from": [r(s0), r(yb), 0], "width": r(w_width), "height": r(h),
          "frameWidth": 0.055, "frameDepth": r(wall_t),
          "glassDepth": 0.012, "verticalMullions": int(mullions),
          "mullionWidth": 0.030,
          "frameMaterial": "frame_dark", "glassMaterial": glass})


def door_on(w, id_, at, w_width, yb, h, wall_t=T_EXT, style="rectangular",
            dstyle="single", leaf="wood", hinge="left"):
    s = s_along(w, at)
    L = axis(w)[4]
    s0 = s - w_width / 2.0
    assert s0 > -1e-6 and s0 + w_width <= L + 1e-6, (id_, s0, w_width, L)
    comp({"type": "door", "id": id_, "parentWall": w["id"],
          "from": [r(s0), r(yb), 0], "width": r(w_width), "height": r(h),
          "frameWidth": 0.065, "frameDepth": r(wall_t), "leafDepth": 0.045,
          "frameMaterial": "frame_dark", "leafMaterial": leaf,
          "openingStyle": style, "doorStyle": dstyle,
          "interaction": {"mode": "swing", "hingeSide": hinge,
                          "openAngle": 90, "initiallyOpen": False}})


# ── 1. 场地 ─────────────────────────────────────────────
slab("site", -6.0, 19.5, -12.0, 21.0, SITE_TOP - 0.12, 0.12, "paving")

# ── 2. 楼板 ─────────────────────────────────────────────
slab("floor_f1", X0 - 0.12, X1 + 0.12, Z0 - 0.12, Z1 + 0.12, SITE_TOP - 0.05, F1 - SITE_TOP + 0.05, "stone")
slab("porch_slab", P_X0, P_X1, P_Z0, Z0 - T_EXT / 2, SITE_TOP - 0.05, F1 - SITE_TOP + 0.05, "stone")
# 二层板：绕楼梯井 (X 10.55~13.35, Z 9.9~14.2) 拆四片
slab("floor_f2_a", X0 - 0.12, ST_X0, Z0 - 0.12, Z1 + 0.12, SLAB2_BOT, T2, "stone")
slab("floor_f2_b", ST_X0, X1 + 0.12, Z0 - 0.12, ST_Z0, SLAB2_BOT, T2, "stone")
slab("floor_f2_c", ST_X0, X1 + 0.12, ST_Z1, Z1 + 0.12, SLAB2_BOT, T2, "stone")
slab("floor_f2_d", ST_X1, X1 + 0.12, ST_Z0, ST_Z1, SLAB2_BOT, T2, "stone")
# 露台板（门廊顶）
slab("terrace_slab", P_X0 - 0.05, P_X1 + 0.05, P_Z0 - 0.05, Z0 - T_EXT / 2, SLAB2_BOT, T2, "stone")
# 楼梯平台
slab("stair_land", ST_X0, ST_X1, 12.70, ST_Z1, LAND_TOP - 0.20, 0.20, "stone")

_area_f2 = (X1 + 0.12 - (X0 - 0.12)) * (Z1 + 0.12 - (Z0 - 0.12))
_area_hole = (ST_X1 - ST_X0) * (ST_Z1 - ST_Z0)
_pieces = [(ST_X0 - (X0 - 0.12)) * (Z1 + 0.12 - (Z0 - 0.12)),
           (X1 + 0.12 - ST_X0) * (ST_Z0 - (Z0 - 0.12)),
           (X1 + 0.12 - ST_X0) * (Z1 + 0.12 - ST_Z1),
           (X1 + 0.12 - ST_X1) * (ST_Z1 - ST_Z0)]
assert abs(sum(_pieces) - (_area_f2 - _area_hole)) < 1e-6, "二层板拆片面积不等"

# ── 3. 外墙（每层四面，逆时针环） ───────────────────────
w_f1_front = wall("wall_f1_front", X0, Z0, X1, Z0, F1, SLAB2_BOT)
w_f1_east = wall("wall_f1_east", X1, Z0, X1, Z1, F1, SLAB2_BOT)
w_f1_back = wall("wall_f1_back", X1, Z1, X0, Z1, F1, SLAB2_BOT)
w_f1_west = wall("wall_f1_west", X0, Z1, X0, Z0, F1, SLAB2_BOT)

w_f2_front = wall("wall_f2_front", X0, Z0, X1, Z0, F2, WALL_TOP2)
w_f2_east = wall("wall_f2_east", X1, Z0, X1, Z1, F2, WALL_TOP2)
w_f2_back = wall("wall_f2_back", X1, Z1, X0, Z1, F2, WALL_TOP2)
w_f2_west = wall("wall_f2_west", X0, Z1, X0, Z0, F2, WALL_TOP2)

# ── 4. 一层内墙（带门洞缺口） ───────────────────────────
# 厨房 | 餐厅 分隔 X=4.20，Z 9.60~15.00，留 1.0m 无门洞口
wall("wall_f1_kit_e_a", 4.20, 9.60, 4.20, 11.40, F1, SLAB2_BOT, T_INT)
wall("wall_f1_kit_e_b", 4.20, 12.40, 4.20, 15.00, F1, SLAB2_BOT, T_INT)
# 餐厅 | 服务区 X=9.00
wall("wall_f1_din_e_a", 9.00, 9.60, 9.00, 11.20, F1, SLAB2_BOT, T_INT)
wall("wall_f1_din_e_b", 9.00, 12.10, 9.00, 15.00, F1, SLAB2_BOT, T_INT)
# 厨房/餐厅 与 前部 的横墙 Z=9.60，X 0~9.00，留餐厅入口
wall("wall_f1_mid_a", X0, 9.60, 2.90, 9.60, F1, SLAB2_BOT, T_INT)
wall("wall_f1_mid_b", 4.40, 9.60, 7.10, 9.60, F1, SLAB2_BOT, T_INT)
wall("wall_f1_mid_c", 8.60, 9.60, 9.00, 9.60, F1, SLAB2_BOT, T_INT)
# 卧室东墙 X=4.20，Z 2.60~9.60，留门
wall("wall_f1_bed_e_a", 4.20, 2.60, 4.20, 5.10, F1, SLAB2_BOT, T_INT)
wall("wall_f1_bed_e_b", 4.20, 6.10, 4.20, 9.60, F1, SLAB2_BOT, T_INT)
# 卧室南墙 Z=2.60，X 0~4.20
wall("wall_f1_bed_s", X0, 2.60, 4.20, 2.60, F1, SLAB2_BOT, T_INT)
# 次卫 X 0~2.20，Z 0~2.60
wall("wall_f1_bath_e", 2.20, Z0 + 0.12, 2.20, 2.60, F1, SLAB2_BOT, T_INT)
wall("wall_f1_bath_n", 2.20, 2.60, 4.20, 2.60, F1, SLAB2_BOT, T_INT)
# 公卫 / 洗衣 X 9.00~11.40
wall("wall_f1_svc_s", 9.00, 9.60, 11.40, 9.60, F1, SLAB2_BOT, T_INT)
wall("wall_f1_svc_e", 11.40, 9.60, 11.40, 15.00, F1, SLAB2_BOT, T_INT)
wall("wall_f1_wc_s", 9.00, 12.40, 11.40, 12.40, F1, SLAB2_BOT, T_INT)
# 门厅 | 楼梯厅 X=10.55（下部）
wall("wall_f1_hall_e", 10.55, Z0 + 0.12, 10.55, 6.20, F1, SLAB2_BOT, T_INT)
# 楼梯井西墙（一层）
wall("wall_f1_st_w", 10.55, 9.60, 10.55, 12.90, F1, SLAB2_BOT, T_INT)

# ── 5. 二层内墙 ─────────────────────────────────────────
wall("wall_f2_m1", 5.40, 8.40, 5.40, 15.00, F2, WALL_TOP2, T_INT)
wall("wall_f2_m2", X0, 8.40, 5.40, 8.40, F2, WALL_TOP2, T_INT)
wall("wall_f2_m3", X0, 6.00, 2.60, 6.00, F2, WALL_TOP2, T_INT)
wall("wall_f2_m4", 2.60, 6.00, 2.60, 8.40, F2, WALL_TOP2, T_INT)
wall("wall_f2_m5", 5.40, 6.00, 9.60, 6.00, F2, WALL_TOP2, T_INT)
wall("wall_f2_m6", 9.60, 0.12, 9.60, 6.00, F2, WALL_TOP2, T_INT)
wall("wall_f2_m7", 5.40, 0.12, 5.40, 6.00, F2, WALL_TOP2, T_INT)
wall("wall_f2_m8", 5.40, 9.90, 9.60, 9.90, F2, WALL_TOP2, T_INT)
wall("wall_f2_m9", 9.60, 9.90, 9.60, 15.00, F2, WALL_TOP2, T_INT)
wall("wall_f2_m10", ST_X0, 9.90, ST_X0, 14.20, F2, WALL_TOP2, T_INT)

# ── 6. 楼梯 ─────────────────────────────────────────────
stair("stair_run_a", ST_LANES[0][0], ST_Z0, 12.70, F1, LAND_TOP, 1.15, STEP_N)
stair("stair_run_b", ST_LANES[1][0], 12.70, ST_Z0, LAND_TOP, F2, 1.15, STEP_N)
# 扶手（斜梁 + 立杆）
for lane, z0, z1, y0, y1 in ((ST_LANES[0][0], ST_Z0, 12.70, F1, LAND_TOP),
                             (ST_LANES[1][0], 12.70, ST_Z0, LAND_TOP, F2)):
    L = abs(z1 - z0)
    dy = y1 - y0
    ang = math.atan2(dy, L)
    for k in range(5):
        t = (k + 0.5) / 5.0
        box("stair_post_%s_%d" % (lane, k), lane + 0.50, y0 + dy * t + 0.45, z0 + (z1 - z0) * t,
            0.035, 0.90, 0.035, "metal")
    box("stair_rail_%s" % lane, lane + 0.50, y0 + dy / 2 + 0.92, (z0 + z1) / 2,
        0.06, 0.06, math.hypot(L, dy) + 0.10, "metal", rot=[-ang, 0, 0])
box("stair_land_rail", ST_X0 + 1.40, LAND_TOP + 0.50, ST_Z1 - 0.06, 2.80, 0.06, 0.06, "metal")

# ── 7. 门廊结构：方柱 / 柱础 / 柱头 / 檐下梁 / 壁柱 ────
for tag, cx in (("l", PIER_CX_L), ("r", PIER_CX_R)):
    box("pier_%s" % tag, cx, (F1 + SLAB2_BOT) / 2, PIER_CZ, PIER, SLAB2_BOT - F1, PIER, "trim")
    box("pier_base_%s" % tag, cx, F1 + 0.10, PIER_CZ, PIER + 0.16, 0.20, PIER + 0.16, "trim")
    box("pier_cap_%s" % tag, cx, SLAB2_BOT - 0.09, PIER_CZ, PIER + 0.16, 0.18, PIER + 0.16, "trim")
    # 檐下梁头（托梁）
    box("pier_abacus_%s" % tag, cx, SLAB2_BOT - 0.23, PIER_CZ, PIER + 0.26, 0.10, PIER + 0.26, "trim")
    # 贴墙壁柱
    box("pilaster_%s" % tag, cx, (F1 + SLAB2_BOT) / 2, Z0 - 0.06, PIER + 0.06, SLAB2_BOT - F1, 0.12, "trim")
# 门廊正立面檐梁（柱间）
box("porch_beam", (P_X0 + P_X1) / 2, SLAB2_BOT - 0.16, PIER_CZ, P_X1 - P_X0, 0.32, 0.50, "trim")
# 门廊顶板外沿
box("terrace_fascia_f", (P_X0 + P_X1) / 2, SLAB2_BOT + T2 / 2, P_Z0 - 0.09, P_X1 - P_X0 + 0.24, T2 + 0.10, 0.16, "trim")
box("terrace_fascia_l", P_X0 - 0.09, SLAB2_BOT + T2 / 2, (P_Z0 + P_Z1) / 2, 0.16, T2 + 0.10, P_Z1 - P_Z0, "trim")
box("terrace_fascia_r", P_X1 + 0.09, SLAB2_BOT + T2 / 2, (P_Z0 + P_Z1) / 2, 0.16, T2 + 0.10, P_Z1 - P_Z0, "trim")

# ── 8. 露台栏杆 + 角柱 ─────────────────────────────────
box("tp_pier_l", TP_X0, F2 + 0.62, TP_Z, 0.46, 1.24, 0.46, "trim")
box("tp_pier_r", TP_X1, F2 + 0.62, TP_Z, 0.46, 1.24, 0.46, "trim")
box("tp_cap_l", TP_X0, F2 + 1.30, TP_Z, 0.58, 0.12, 0.58, "trim")
box("tp_cap_r", TP_X1, F2 + 1.30, TP_Z, 0.58, 0.12, 0.58, "trim")
for tag, cx, cz, y in (("front", TP_X0, TP_Z, F2), ("back", TP_X1, TP_Z, F2)):
    pass
comp({"type": "railing", "id": "rail_terrace_front",
      "path": [[r(TP_X0 + 0.23), r(F2), r(TP_Z)], [r(TP_X1 - 0.23), r(F2), r(TP_Z)]],
      "height": RAIL_H, "postSpacing": 0.115, "postRadius": 0.011,
      "railRadius": 0.017, "railLevels": [0.08, 0.97], "material": "metal"})
comp({"type": "railing", "id": "rail_terrace_left",
      "path": [[r(TP_X0), r(F2), r(TP_Z - 0.23)], [r(TP_X0), r(F2), r(Z0 - 0.12)]],
      "height": RAIL_H, "postSpacing": 0.115, "postRadius": 0.011,
      "railRadius": 0.017, "railLevels": [0.08, 0.97], "material": "metal"})
comp({"type": "railing", "id": "rail_terrace_right",
      "path": [[r(TP_X1), r(F2), r(TP_Z - 0.23)], [r(TP_X1), r(F2), r(Z0 - 0.12)]],
      "height": RAIL_H, "postSpacing": 0.115, "postRadius": 0.011,
      "railRadius": 0.017, "railLevels": [0.08, 0.97], "material": "metal"})

# ── 9. 入口台阶 + 侧翼花池 ─────────────────────────────
stair("entry_steps", (P_X0 + P_X1) / 2, -4.05, P_Z0, SITE_TOP, F1, 6.80, 3)
box("step_cheek_l", 3.22, 0.26, (-4.05 + P_Z0) / 2, 0.26, 0.52, 1.05, "trim")
box("step_cheek_r", 10.28, 0.26, (-4.05 + P_Z0) / 2, 0.26, 0.52, 1.05, "trim")
for tag, x0, x1 in (("l", 0.85, 2.75), ("r", 10.75, 12.65)):
    box("planter_%s_w" % tag, x0, 0.21, -3.55, 0.16, 0.42, 1.90, "trim")
    box("planter_%s_e" % tag, x1, 0.21, -3.55, 0.16, 0.42, 1.90, "trim")
    box("planter_%s_n" % tag, (x0 + x1) / 2, 0.21, -4.45, x1 - x0, 0.42, 0.16, "trim")
    box("planter_%s_s" % tag, (x0 + x1) / 2, 0.21, -2.65, x1 - x0, 0.42, 0.16, "trim")
    box("planter_%s_soil" % tag, (x0 + x1) / 2, 0.36, -3.55, x1 - x0 - 0.3, 0.18, 1.64, "soil")

# ── 10. 屋顶 + 檐口 + 腰线 ─────────────────────────────
span = (X1 - X0) + EAVE_OV * 2
cx_roof = (X0 + X1) / 2
# 前后两片四坡屋面搭接：脊线平行于正立面，接缝处形成天沟（参考图的两段屋面）
ROOF_FRONT_D, ROOF_FRONT_H = 10.20, 2.05
ROOF_REAR_D, ROOF_REAR_H = 9.60, 2.28
rf_cz = (Z0 - EAVE_OV_FRONT + (Z0 - EAVE_OV_FRONT) + ROOF_FRONT_D) / 2
rr_cz = (Z1 + EAVE_OV - ROOF_REAR_D) + ROOF_REAR_D / 2
add({"type": "roof", "id": "roof_front", "roofType": "hip",
     "position": [r(cx_roof), r(WALL_TOP2), r(rf_cz)],
     "span": r(span), "depth": r(ROOF_FRONT_D), "height": r(ROOF_FRONT_H),
     "thickness": r(ROOF_T), "material": "roof_dark"})
add({"type": "roof", "id": "roof_rear", "roofType": "hip",
     "position": [r(cx_roof), r(WALL_TOP2), r(rr_cz)],
     "span": r(span), "depth": r(ROOF_REAR_D), "height": r(ROOF_REAR_H),
     "thickness": r(ROOF_T), "material": "roof_dark"})
ROOF_RIDGE_TOP = WALL_TOP2 + max(ROOF_FRONT_H, ROOF_REAR_H)

# 檐口（白）：深挑檐下的平顶檐板，从墙外皮一直挑到接近屋面檐口
CE_Y0, CE_Y1 = WALL_TOP2 - 0.30, WALL_TOP2
CE_OUT = 0.60                      # 檐板挑出深度（自墙轴线起算）
box("cornice_front", cx_roof, (CE_Y0 + CE_Y1) / 2, Z0 - CE_OUT / 2,
    (X1 - X0) + CE_OUT * 2, CE_Y1 - CE_Y0, CE_OUT, "trim")
box("cornice_back", cx_roof, (CE_Y0 + CE_Y1) / 2, Z1 + CE_OUT / 2,
    (X1 - X0) + CE_OUT * 2, CE_Y1 - CE_Y0, CE_OUT, "trim")
box("cornice_west", X0 - CE_OUT / 2, (CE_Y0 + CE_Y1) / 2, (Z0 + Z1) / 2,
    CE_OUT, CE_Y1 - CE_Y0, (Z1 - Z0), "trim")
box("cornice_east", X1 + CE_OUT / 2, (CE_Y0 + CE_Y1) / 2, (Z0 + Z1) / 2,
    CE_OUT, CE_Y1 - CE_Y0, (Z1 - Z0), "trim")
# 二层楼板腰线
BD_Y0, BD_Y1 = SLAB2_BOT + 0.02, F2
box("band_front", cx_roof, (BD_Y0 + BD_Y1) / 2, Z0 - 0.15, (X1 - X0) + 0.28, BD_Y1 - BD_Y0, 0.24, "trim")
box("band_back", cx_roof, (BD_Y0 + BD_Y1) / 2, Z1 + 0.15, (X1 - X0) + 0.28, BD_Y1 - BD_Y0, 0.24, "trim")
box("band_west", X0 - 0.15, (BD_Y0 + BD_Y1) / 2, (Z0 + Z1) / 2, 0.24, BD_Y1 - BD_Y0, (Z1 - Z0) + 0.24, "trim")
box("band_east", X1 + 0.15, (BD_Y0 + BD_Y1) / 2, (Z0 + Z1) / 2, 0.24, BD_Y1 - BD_Y0, (Z1 - Z0) + 0.24, "trim")
# 后门三级台阶（下到场地）
stair("back_steps", 6.45, 16.20, Z1 + T_EXT / 2, SITE_TOP, F1, 1.80, 3)
# 勒脚
box("plinth_front", cx_roof, F1 / 2, Z0 - 0.14, (X1 - X0) + 0.28, F1, 0.22, "stone")
box("plinth_west", X0 - 0.14, F1 / 2, (Z0 + Z1) / 2, 0.22, F1, (Z1 - Z0) + 0.24, "stone")
box("plinth_east", X1 + 0.14, F1 / 2, (Z0 + Z1) / 2, 0.22, F1, (Z1 - Z0) + 0.24, "stone")

# ── 11. 门窗 ───────────────────────────────────────────
# 一层正面：拱形双开玻璃门 + 两侧固定扇 + 两翼窗
door_on(w_f1_front, "door_entry", 6.75, 2.20, F1, 2.80, style="arched",
        dstyle="double", leaf="glass", hinge="left")
win_on(w_f1_front, "win_entry_l", 5.15, 0.85, F1, 2.60, mullions=0)
win_on(w_f1_front, "win_entry_r", 8.35, 0.85, F1, 2.60, mullions=0)
win_on(w_f1_front, "win_f1_l", 1.55, 1.70, F1 + 0.85, 1.75, mullions=2)
win_on(w_f1_front, "win_f1_r", 11.95, 1.70, F1 + 0.85, 1.75, mullions=2)
# 一层东 / 西 / 背：两侧共用四条窗轴，上下层严格对位
SIDE_AXES = (3.20, 5.20, 10.60, 13.40)
for i, wz in enumerate(SIDE_AXES):
    win_on(w_f1_east, "win_f1_e%d" % i, wz, 1.45, F1 + 0.90, 1.70, mullions=1)
    win_on(w_f1_west, "win_f1_w%d" % i, wz, 1.45, F1 + 0.90, 1.70, mullions=1)
win_on(w_f1_back, "win_f1_b1", 3.10, 1.60, F1 + 0.90, 1.70, mullions=2)
win_on(w_f1_back, "win_f1_b2", 9.80, 1.60, F1 + 0.90, 1.70, mullions=2)
door_on(w_f1_back, "door_back", 6.45, 1.00, F1, 2.10, leaf="wood")
# 二层正面：露台后侧玻璃幕三扇（深色框）
for i, wx in enumerate((4.45, 6.75, 9.05)):
    win_on(w_f2_front, "win_f2_glz_%d" % i, wx, 2.05, F2 + 0.12, 2.55, mullions=2)
win_on(w_f2_front, "win_f2_l", 1.55, 1.40, F2 + 0.85, 1.85, mullions=1)
win_on(w_f2_front, "win_f2_r", 11.95, 1.40, F2 + 0.85, 1.85, mullions=1)
# 二层侧 / 背
for i, wz in enumerate(SIDE_AXES):
    win_on(w_f2_east, "win_f2_e%d" % i, wz, 1.45, F2 + 0.85, 1.85, mullions=1)
    win_on(w_f2_west, "win_f2_w%d" % i, wz, 1.45, F2 + 0.85, 1.85, mullions=1)
for i, wx in enumerate((3.10, 6.75, 9.80)):
    win_on(w_f2_back, "win_f2_b%d" % i, wx, 1.55, F2 + 0.85, 1.85, mullions=1)

# 室内门
door_on(add({"type": "wall", "id": "wall_f1_bed_door_jamb", "from": [4.20, F1, 5.10],
             "to": [4.20, SLAB2_BOT, 6.10], "thickness": T_INT, "material": "stucco"}),
        "door_bed1", 5.60, 1.00, F1, 2.05, wall_t=T_INT, leaf="wood")
door_on(add({"type": "wall", "id": "wall_f1_bath_jamb", "from": [2.20, F1, 1.40],
             "to": [4.20, SLAB2_BOT, 1.40], "thickness": T_INT, "material": "stucco"}),
        "door_bath1", 3.10, 0.80, F1, 2.05, wall_t=T_INT, leaf="wood")
door_on(add({"type": "wall", "id": "wall_f1_wc_jamb", "from": [9.00, F1, 13.70],
             "to": [11.40, SLAB2_BOT, 13.70], "thickness": T_INT, "material": "stucco"}),
        "door_wc1", 9.90, 0.80, F1, 2.05, wall_t=T_INT, leaf="wood")
door_on(add({"type": "wall", "id": "wall_f1_lau_jamb", "from": [9.00, F1, 11.00],
             "to": [11.40, SLAB2_BOT, 11.00], "thickness": T_INT, "material": "stucco"}),
        "door_lau1", 9.80, 0.80, F1, 2.05, wall_t=T_INT, leaf="wood")
door_on(add({"type": "wall", "id": "wall_f2_m1_jamb", "from": [5.40, F2, 9.10],
             "to": [5.40, WALL_TOP2, 10.20], "thickness": T_INT, "material": "stucco"}),
        "door_master", 9.65, 1.00, F2, 2.10, wall_t=T_INT, leaf="wood")
door_on(add({"type": "wall", "id": "wall_f2_m8_jamb", "from": [7.30, F2, 9.90],
             "to": [8.50, WALL_TOP2, 9.90], "thickness": T_INT, "material": "stucco"}),
        "door_guest", 7.90, 0.90, F2, 2.10, wall_t=T_INT, leaf="wood")
door_on(add({"type": "wall", "id": "wall_f2_m6_jamb", "from": [9.60, F2, 3.20],
             "to": [9.60, WALL_TOP2, 4.20], "thickness": T_INT, "material": "stucco"}),
        "door_bath2", 3.70, 0.80, F2, 2.05, wall_t=T_INT, leaf="wood")

# ── 12. 灯具（壁灯，带真实光源） ───────────────────────
def sconce(id_, cx, cy, cz, face="x"):
    box(id_ + "_body", cx, cy, cz, 0.11, 0.30, 0.11, "frame_dark")
    box(id_ + "_glow_u", cx, cy + 0.19, cz, 0.09, 0.03, 0.09, "glow",
        light={"lightType": "point", "color": [1.0, 0.80, 0.52],
               "intensity": 5.0, "distance": 4.0, "initiallyOn": True})
    box(id_ + "_glow_d", cx, cy - 0.19, cz, 0.09, 0.03, 0.09, "glow",
        light={"lightType": "point", "color": [1.0, 0.80, 0.52],
               "intensity": 4.0, "distance": 3.5, "initiallyOn": True})


sconce("sconce_pier_l", PIER_CX_L + 0.32, 2.28, PIER_CZ)
sconce("sconce_pier_r", PIER_CX_R - 0.32, 2.28, PIER_CZ)
sconce("sconce_door_l", 4.55, 2.40, Z0 - 0.16)
sconce("sconce_door_r", 8.95, 2.40, Z0 - 0.16)
sconce("sconce_east", X1 + 0.17, 2.30, 7.10)
sconce("sconce_west", X0 - 0.17, 2.30, 7.10)

# ── 13. 左侧拱券花园墙 ─────────────────────────────────
GW_Z = -6.20
box("gwall_l", -4.55, 1.30, GW_Z, 0.46, 2.60, 0.46, "trim")
box("gwall_r", -2.35, 1.30, GW_Z, 0.46, 2.60, 0.46, "trim")
box("gwall_cap_l", -4.55, 2.68, GW_Z, 0.58, 0.14, 0.58, "trim")
box("gwall_cap_r", -2.35, 2.68, GW_Z, 0.58, 0.14, 0.58, "trim")
arch_band("gwall_arch", -3.45, 1.30, GW_Z, 0.87, 0.38, 0.44, 0.0, math.pi, 11, "trim")
box("gwall_key", -3.45, 2.30, GW_Z, 0.20, 0.26, 0.36, "trim")

# ── 14. 景观：绿篱 + 球状灌木 + 观赏草 ─────────────────
sph("shrub_f1", 2.30, 0.62, -5.10, 0.62, "leaf")
sph("shrub_f2", 1.70, 0.50, -6.10, 0.50, "leaf_lite")
sph("shrub_f3", 11.30, 0.55, -5.00, 0.55, "leaf")
sph("shrub_f4", 12.10, 0.44, -6.00, 0.44, "leaf_lite")
sph("shrub_f5", 3.90, 0.56, -6.10, 0.56, "leaf")
sph("shrub_f6", 9.60, 0.58, -6.20, 0.58, "leaf_lite")
sph("shrub_f7", -2.10, 0.52, -4.60, 0.52, "leaf")
sph("shrub_f8", 15.40, 0.58, -4.40, 0.58, "leaf_lite")
sph("shrub_f9", 15.90, 0.46, -2.60, 0.46, "leaf")
sph("shrub_w1", -2.60, 0.55, 2.40, 0.55, "leaf")
sph("shrub_w2", -2.20, 0.42, 4.20, 0.42, "leaf_lite")
sph("shrub_e1", 15.60, 0.52, 3.40, 0.52, "leaf")
sph("shrub_e2", 15.20, 0.40, 5.20, 0.40, "leaf_lite")
for i in range(7):
    sph("shrub_row_%d" % i, -1.60 + i * 1.05, 0.34, -8.40, 0.34, "leaf_lite")
# 观赏草（细叶丛）
for i, (gx, gz, gh) in enumerate(((2.95, -4.90, 1.10), (2.55, -3.95, 0.95),
                                  (10.95, -4.85, 1.05), (11.35, -3.90, 0.90),
                                  (-2.75, 6.10, 0.85), (15.30, 8.20, 0.80))):
    cyl("grass_%d" % i, gx, gh / 2, gz, 0.10, gh, "leaf", seg=6, rtop=0.03)
# 门廊两侧盆栽
for tag, px in (("l", P_X0 + 0.75), ("r", P_X1 - 0.75)):
    cyl("pot_%s" % tag, px, F1 + 0.22, -2.35, 0.24, 0.44, "stone", seg=12, rtop=0.28)
    sph("pot_plant_%s" % tag, px, F1 + 0.78, -2.35, 0.40, "leaf")
# 露台花箱
for tag, px in (("l", TP_X0 + 0.60), ("r", TP_X1 - 0.60)):
    box("tp_planter_%s" % tag, px, F2 + 0.24, TP_Z + 0.52, 0.78, 0.42, 0.42, "stone")
    sph("tp_plant_%s" % tag, px, F2 + 0.62, TP_Z + 0.52, 0.30, "leaf")

# ── 15. 家具与固定设施 ─────────────────────────────────
def furn(id_, sub, cx, cz, w, d, h, y=F1, rot=0.0, mat="wood"):
    el = {"type": "furniture", "id": id_, "subtype": sub,
          "position": [r(cx), r(y), r(cz)],
          "dimensions": {"width": r(w), "depth": r(d), "height": r(h)},
          "material": mat}
    if rot:
        el["rotation"] = [0.0, r(rot, 6), 0.0]
    return add(el)


# 厨房（X 0~4.2，Z 9.6~15.0）：L 形台面
box("kit_counter_s", 2.10, F1 + 0.45, 14.62, 4.00, 0.90, 0.60, "wood_pale")
box("kit_top_s", 2.10, F1 + 0.93, 14.62, 4.10, 0.06, 0.66, "stone")
box("kit_counter_w", 0.42, F1 + 0.45, 12.10, 0.60, 0.90, 4.60, "wood_pale")
box("kit_top_w", 0.42, F1 + 0.93, 12.10, 0.66, 0.06, 4.70, "stone")
box("kit_up_s", 2.10, F1 + 2.05, 14.72, 4.00, 0.70, 0.34, "wood_pale")
box("kit_up_w", 0.30, F1 + 2.05, 12.10, 0.34, 0.70, 4.60, "wood_pale")
box("kit_island", 2.60, F1 + 0.44, 11.30, 1.80, 0.88, 0.95, "wood_pale")
box("kit_island_top", 2.60, F1 + 0.92, 11.30, 1.92, 0.06, 1.05, "stone")
# 餐厅：圆桌 + 8 椅
cyl("din_table_top", 6.70, F1 + 0.74, 12.10, 0.85, 0.06, "wood", seg=28)
cyl("din_table_col", 6.70, F1 + 0.37, 12.10, 0.13, 0.74, "wood", seg=14)
cyl("din_table_base", 6.70, F1 + 0.03, 12.10, 0.42, 0.06, "wood", seg=20)
for i in range(8):
    a = i * math.pi / 4.0
    furn("din_chair_%d" % i, "chair", 6.70 + 1.22 * math.cos(a), 12.10 + 1.22 * math.sin(a),
         0.48, 0.50, 0.88, rot=-a + math.pi / 2, mat="fabric")
# 客厅：沙发组 + 茶几 + 电视柜
furn("liv_sofa_main", "sofa", 6.70, 3.10, 2.60, 0.92, 0.82, rot=0.0, mat="fabric")
furn("liv_sofa_l", "sofa", 5.20, 4.55, 0.92, 1.90, 0.82, rot=math.pi / 2, mat="fabric")
furn("liv_sofa_r", "sofa", 8.45, 4.55, 0.92, 1.90, 0.82, rot=-math.pi / 2, mat="fabric")
furn("liv_ctable", "table", 6.70, 4.70, 1.30, 0.72, 0.44, mat="wood")
furn("liv_tv", "tv_cabinet", 6.70, 8.90, 2.20, 0.44, 0.50, mat="wood")
box("liv_tv_panel", 6.70, F1 + 1.16, 8.92, 1.60, 0.92, 0.06, "frame_dark")
box("liv_rug", 6.70, F1 + 0.01, 4.20, 3.20, 0.02, 2.40, "linen")
# 卧室（一层西侧）
furn("bed_f1", "bed", 2.10, 8.50, 1.80, 2.05, 0.55, mat="linen")
box("bed_f1_head", 2.10, F1 + 0.62, 9.54, 1.90, 1.24, 0.10, "wood")
furn("ns_f1_l", "nightstand", 0.92, 9.40, 0.48, 0.40, 0.52, mat="wood")
furn("ns_f1_r", "nightstand", 3.28, 9.40, 0.48, 0.40, 0.52, mat="wood")
furn("ward_f1", "wardrobe", 3.82, 6.20, 0.62, 1.80, 2.20, mat="wood")
# 卫生间（一层）
box("fc_bath1_pan", 0.85, F1 + 0.20, 1.05, 1.10, 0.40, 0.90, "linen")
box("fc_bath1_v", 1.80, F1 + 0.42, 2.20, 0.90, 0.84, 0.48, "stone")
cyl("fc_bath1_wc", 1.85, F1 + 0.20, 0.72, 0.20, 0.40, "linen", seg=14)
# 公卫 / 洗衣
cyl("fc_wc1", 10.90, F1 + 0.20, 14.30, 0.20, 0.40, "linen", seg=14)
box("fc_wc1_v", 9.60, F1 + 0.42, 14.30, 0.90, 0.84, 0.48, "stone")
box("fc_lau_washer", 9.55, F1 + 0.44, 10.20, 0.62, 0.88, 0.62, "linen")
box("fc_lau_dryer", 9.55, F1 + 0.44, 11.00, 0.62, 0.88, 0.62, "linen")
box("fc_lau_bench", 10.70, F1 + 0.45, 9.90, 1.30, 0.90, 0.55, "stone")
# 二层主卧
furn("bed_m", "bed", 2.60, 13.60, 1.90, 2.10, 0.58, y=F2, mat="linen")
box("bed_m_head", 2.60, F2 + 0.66, 14.66, 2.00, 1.32, 0.10, "wood")
furn("ns_m_l", "nightstand", 1.30, 14.50, 0.50, 0.42, 0.54, y=F2, mat="wood")
furn("ns_m_r", "nightstand", 3.90, 14.50, 0.50, 0.42, 0.54, y=F2, mat="wood")
furn("ward_m", "wardrobe", 4.92, 10.60, 0.62, 2.20, 2.20, y=F2, mat="wood")
furn("bench_m", "table", 2.60, 9.55, 1.30, 0.45, 0.46, y=F2, mat="fabric")
# 二层次卧
furn("bed_g1", "bed", 7.50, 13.80, 1.60, 2.00, 0.56, y=F2, mat="linen")
box("bed_g1_head", 7.50, F2 + 0.62, 14.86, 1.70, 1.24, 0.10, "wood")
furn("ns_g1", "nightstand", 6.40, 14.70, 0.46, 0.40, 0.52, y=F2, mat="wood")
furn("ward_g1", "wardrobe", 8.95, 11.20, 0.60, 1.60, 2.10, y=F2, mat="wood")
# 二层前部房间（书房/客房）
furn("bed_g2", "bed", 2.55, 1.20, 1.50, 1.95, 0.54, y=F2, mat="linen")
box("bed_g2_head", 2.55, F2 + 0.60, 0.18, 1.60, 1.20, 0.10, "wood")
furn("desk_g2", "table", 4.55, 4.20, 1.10, 0.60, 0.76, y=F2, mat="wood")
furn("chair_g2", "chair", 4.55, 4.95, 0.48, 0.50, 0.88, y=F2, rot=math.pi, mat="fabric")
furn("shelf_g2", "bookshelf", 0.42, 3.20, 0.36, 2.00, 2.00, y=F2, mat="wood")
# 二层卫生间
box("fc_bath2_v", 10.10, F2 + 0.42, 1.10, 1.10, 0.84, 0.50, "stone")
cyl("fc_bath2_wc", 13.10, F2 + 0.20, 1.10, 0.20, 0.40, "linen", seg=14)
box("fc_bath2_tub", 12.10, F2 + 0.28, 4.90, 1.60, 0.56, 0.80, "linen")


# 二层前部房间（家庭起居）
furn("fam_sofa", "sofa", 7.50, 2.30, 2.20, 0.90, 0.80, y=F2, rot=0.0, mat="fabric")
furn("fam_ctable", "table", 7.50, 3.50, 1.10, 0.62, 0.42, y=F2, mat="wood")
furn("fam_shelf", "bookshelf", 9.30, 4.60, 0.40, 1.80, 1.90, y=F2, rot=-math.pi / 2, mat="wood")
furn("fam_lamp", "lamp", 8.90, 2.40, 0.36, 0.36, 1.55, y=F2, mat="linen")
# 一层门厅
furn("hall_console", "table", 9.78, 2.40, 0.42, 1.30, 0.80, y=F1, mat="wood")
furn("hall_bench", "chair", 10.10, 4.60, 0.50, 0.52, 0.86, y=F1, rot=-math.pi / 2, mat="fabric")

# ── 16. 断言 ───────────────────────────────────────────
assert abs((F1 + STEP_N * STEP_H * 2) - F2) < 1e-9, "楼梯总升高不等于层高"
for a, b in ((P_X0, P_X1), (TP_X0, TP_X1)):
    assert b > a
assert ST_X0 < ST_X1 and ST_Z0 < ST_Z1
assert (ST_X1 - ST_X0) <= (X1 - X0)
for w in (w_f1_front, w_f1_back, w_f2_front, w_f2_back):
    assert abs(w["to"][1] - w["from"][1]) > 0

blueprint = {
    "meta": {"version": "1.1", "type": "building",
             "name": "两层奶油白别墅 · 参考图复原",
             "author": "wild-blueprint-authoring", "style": "现代欧式"},
    "geometry": {"elements": E, "components": C},
    "materials": {k: dict(v, lightingCondition="D65_noon") for k, v in MATS.items()},
    "editor": {"revision": 1},
}

text = json.dumps(blueprint, ensure_ascii=False, indent=1)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
    f.write("\n")

kinds = {}
for el in E:
    kinds[el["type"]] = kinds.get(el["type"], 0) + 1
print("elements", len(E), kinds)
print("components", len(C))
print("bytes", len(text.encode("utf-8")))
print("sha256", hashlib.sha256(text.encode("utf-8") + b"\n").hexdigest())
