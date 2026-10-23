# -*- coding: utf-8 -*-
"""离线几何投影：把 Core 编译出的真实三角形用 z-buffer 光栅化成图片。

这不是 WebGL 渲染（本机 Chrome 无法启动），只用于检查体量、轮廓、遮挡与比例；
材质只取 baseColor + 太阳方向漫反射，不含贴图/环境反射/阴影贴图。
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "meshes.json"), encoding="utf-8"))
tri = np.array(data["tri"], dtype=np.float64).reshape(-1, 3, 3)
col = np.array(data["color"], dtype=np.float64).reshape(-1, 3)
flag = np.array(data["origin"], dtype=np.float64).reshape(-1, 2)
IS_GLOW, IS_GLASS = flag[:, 0] > 0.5, flag[:, 1] > 0.5
N = len(tri)
print("triangles", N)

W, H, SS = 1040, 780, 2
SUN = np.array([0.42, 0.80, 0.42]) / np.linalg.norm([0.42, 0.80, 0.42])

VIEWS = {
    "front":   dict(eye=[6.75, 4.2, -34], target=[6.75, 4.4, 2.0], up=[0, 1, 0], fov=30),
    "side":    dict(eye=[38, 4.2, 7.5], target=[6.75, 4.4, 7.5], up=[0, 1, 0], fov=28),
    "rear":    dict(eye=[6.75, 4.6, 38], target=[6.75, 4.2, 8.0], up=[0, 1, 0], fov=28),
    "persp":   dict(eye=[26, 9.0, -22], target=[6.75, 4.2, 3.0], up=[0, 1, 0], fov=32),
    "porch":   dict(eye=[6.75, 1.75, -13.5], target=[6.75, 2.35, -1.0], up=[0, 1, 0], fov=42),
    "stair":   dict(eye=[11.9, 9.5, 9.0], target=[11.95, 1.6, 12.2], up=[0, 1, 0], fov=55),
    "top":     dict(eye=[6.755, 40, 7.5], target=[6.75, 0, 7.5], up=[0, 0, 1], fov=35),
    # 剖切检查用（只在投影时隐藏高处三角形，不改动 .wild）
    "plan_f1": dict(eye=[6.755, 34, 7.5], target=[6.75, 0, 7.5], up=[0, 0, 1], fov=35, cut=3.50),
    "plan_f2": dict(eye=[6.755, 34, 7.5], target=[6.75, 0, 7.5], up=[0, 0, 1], fov=35, cut=6.60),
}


def normalize(v):
    return v / np.linalg.norm(v)


def render(spec, path):
    eye = np.array(spec["eye"], float)
    tgt = np.array(spec["target"], float)
    up = np.array(spec["up"], float)
    fwd = normalize(tgt - eye)
    right = normalize(np.cross(fwd, up))
    upv = np.cross(right, fwd)
    f = 1.0 / math.tan(math.radians(spec["fov"]) / 2)
    w, h = W * SS, H * SS
    aspect = w / h

    rel = tri - eye
    cx = rel @ right
    cy = rel @ upv
    cz = rel @ fwd
    near = 0.25
    keep = (cz > near).all(axis=1)
    if spec.get("cut") is not None:
        keep &= tri.mean(axis=1)[:, 1] < spec["cut"]
    cx, cy, cz = cx[keep], cy[keep], cz[keep]
    c = col[keep]
    glow = IS_GLOW[keep]
    glass = IS_GLASS[keep]

    sx = (cx / cz) * f / aspect
    sy = (cy / cz) * f
    px = (sx * 0.5 + 0.5) * w
    py = (0.5 - sy * 0.5) * h

    # 面法线（双面：朝向相机）
    e1 = tri[keep][:, 1] - tri[keep][:, 0]
    e2 = tri[keep][:, 2] - tri[keep][:, 0]
    nrm = np.cross(e1, e2)
    ln = np.linalg.norm(nrm, axis=1)
    ln[ln < 1e-12] = 1e-12
    nrm = nrm / ln[:, None]
    facing = (nrm @ (-fwd))
    nrm = np.where(facing[:, None] < 0, -nrm, nrm)

    lam = np.clip(nrm @ SUN, 0, 1)
    sky = np.clip(nrm[:, 1], 0, 1)
    shade = 0.42 + 0.62 * lam + 0.10 * sky
    rgb = np.clip(c * shade[:, None], 0, 1)
    rgb = np.where(glow[:, None], np.clip(c * 1.25, 0, 1), rgb)
    rgb = np.where(glass[:, None], np.clip(rgb * 0.55 + np.array([0.35, 0.45, 0.52]) * 0.45, 0, 1), rgb)
    rgb = (rgb * 255).astype(np.uint8)

    # 天空渐变背景
    yy = np.linspace(0, 1, h)[:, None]
    top = np.array([104, 140, 176], float)
    bot = np.array([214, 219, 212], float)
    bg = (top[None, None, :] * (1 - yy[:, :, None]) + bot[None, None, :] * yy[:, :, None])
    img = np.repeat(bg, w, axis=1)

    zbuf = np.full((h, w), np.inf)
    # 由远及近无所谓（有 z-buffer），按三角形逐个填充 bbox
    for i in range(len(px)):
        x0 = px[i]
        y0 = py[i]
        minx = max(int(np.floor(x0.min())), 0)
        maxx = min(int(np.ceil(x0.max())), w - 1)
        miny = max(int(np.floor(y0.min())), 0)
        maxy = min(int(np.ceil(y0.max())), h - 1)
        if minx > maxx or miny > maxy:
            continue
        ax, bx, cx_ = x0[0], x0[1], x0[2]
        ay, by, cy_ = y0[0], y0[1], y0[2]
        area = (bx - ax) * (cy_ - ay) - (by - ay) * (cx_ - ax)
        if abs(area) < 1e-9:
            continue
        xs = np.arange(minx, maxx + 1) + 0.5
        ys = np.arange(miny, maxy + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        w0 = ((bx - ax) * (gy - ay) - (by - ay) * (gx - ax)) / area
        w1 = ((gx - ax) * (cy_ - ay) - (gy - ay) * (cx_ - ax)) / area
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w0 + w1 <= 1 + 1e-9)
        if not inside.any():
            continue
        inv = 1.0 / cz[i]
        # w0 对应顶点 C、w1 对应顶点 B，顶点 A 权重为 1-w0-w1
        zval = 1.0 / ((1 - w0 - w1) * inv[0] + w1 * inv[1] + w0 * inv[2] + 1e-12)
        sub = zbuf[miny:maxy + 1, minx:maxx + 1]
        hit = inside & (zval < sub)
        if not hit.any():
            continue
        sub[hit] = zval[hit]
        img[miny:maxy + 1, minx:maxx + 1][hit] = rgb[i]

    out = Image.fromarray(img.astype(np.uint8), "RGB").resize((W, H), Image.LANCZOS)
    out.save(path)
    return path


for name, spec in VIEWS.items():
    p = render(spec, os.path.join(HERE, f"proj_{name}.png"))
    print("wrote", p)
