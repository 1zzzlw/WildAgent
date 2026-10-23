#!/usr/bin/env python3
"""砚溪别院 · 新中式别墅的确定性作者脚本。

设计事实见 ../01-需求与设计/设计输入.json 与 设计说明.md。
只依赖 Python 标准库；输出自足 WILD 1.1，不依赖模板、实例、外部贴图或模型资产。
院墙用实体 box 表达（避免项目校验流水线把 30x24 院墙误判为低层退台承托），
三块屋顶分别由主宅二层墙、茶室墙、门屋墙承托。
"""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "砚溪别院.wild"
STATS = ROOT / "03-过程记录" / "生成统计.json"
PI = math.pi

SITE_X0, SITE_X1 = -12.0, 18.0
SITE_Z0, SITE_Z1 = -10.0, 14.0
F1, F2 = 0.30, 3.70
SLAB_T = 0.24
MAIN_X0, MAIN_X1 = 2.5, 14.5
MAIN_Z0, MAIN_Z1 = -2.0, 10.0
MAIN_TOP1, MAIN_TOP2 = 3.46, 6.90
TEA_X0, TEA_X1 = -7.5, -1.5
TEA_Z0, TEA_Z1 = 2.0, 9.5
TEA_TOP = 3.60
GATE_X0, GATE_X1 = 5.0, 9.0
GATE_Z0, GATE_Z1 = -10.0, -8.6
GATE_TOP = 3.20
POOL_X0, POOL_X1 = -0.6, 1.9
POOL_Z0, POOL_Z1 = 0.2, 8.4
POOL_BOTTOM = -0.55
WATER_Y = -0.08


def clean(value):
    if isinstance(value, float):
        value = round(value, 5)
        if value == 0:
            return 0.0
        return int(value) if value.is_integer() else value
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if v is not None}
    return value


def mat(color, rough, metal=0.0, **extra):
    row = {
        "baseColor": color,
        "roughness": rough,
        "metallic": metal,
        "albedo": 1,
        "lightingCondition": "D65_noon",
    }
    row.update(extra)
    return row


MATERIALS = {
    "plaster": mat([0.88, 0.86, 0.80], 0.85),
    "plaster_cool": mat([0.83, 0.845, 0.81], 0.86),
    "stone": mat([0.46, 0.47, 0.44], 0.82),
    "stone_light": mat([0.66, 0.65, 0.59], 0.84),
    "stone_dark": mat([0.29, 0.31, 0.29], 0.78),
    "paving": mat([0.70, 0.69, 0.63], 0.86),
    "gravel": mat([0.55, 0.54, 0.49], 0.95),
    "soil": mat([0.16, 0.12, 0.08], 0.98),
    "roof_tile": mat([0.135, 0.155, 0.16], 0.72),
    "roof_tile_alt": mat([0.19, 0.215, 0.22], 0.74),
    "roof_edge": mat([0.09, 0.105, 0.11], 0.62),
    "roof_ridge": mat([0.21, 0.23, 0.23], 0.66),
    "wood": mat([0.27, 0.15, 0.08], 0.58, surfaceFamily="wood"),
    "wood_dark": mat([0.17, 0.095, 0.05], 0.56, surfaceFamily="wood"),
    "oak": mat([0.55, 0.40, 0.24], 0.52, surfaceFamily="wood", surfacePattern="planks"),
    "bronze": mat([0.24, 0.17, 0.09], 0.32, 0.72),
    "metal_dark": mat([0.075, 0.085, 0.088], 0.38, 0.66),
    "glass": mat([0.86, 0.93, 0.94], 0.07, materialClass="glass", surfaceFamily="glass",
                 transmission=0.92, ior=1.5, thickness=0.012),
    "water": mat([0.10, 0.20, 0.19], 0.08, materialClass="glass", surfaceFamily="glass",
                 transmission=0.94, ior=1.333, thickness=0.02,
                 attenuationColor=[0.55, 0.75, 0.70], attenuationDistance=2.8),
    "pool_bottom": mat([0.22, 0.24, 0.21], 0.92),
    "grass": mat([0.20, 0.30, 0.10], 0.95),
    "leaf_dark": mat([0.09, 0.20, 0.07], 0.86),
    "leaf_light": mat([0.24, 0.36, 0.12], 0.88),
    "maple": mat([0.52, 0.17, 0.09], 0.86),
    "bamboo": mat([0.16, 0.30, 0.10], 0.88),
    "bark": mat([0.19, 0.13, 0.08], 0.90),
    "linen": mat([0.70, 0.66, 0.56], 0.93, materialClass="fabric",
                 sheen=0.35, sheenColor=[0.90, 0.86, 0.76]),
    "rug": mat([0.38, 0.33, 0.27], 0.96, materialClass="fabric", sheen=0.20),
    "quartz": mat([0.87, 0.86, 0.81], 0.26, surfaceFamily="mineral",
                  surfacePattern="quartz", materialClass="clearcoat",
                  clearcoat=0.20, clearcoatRoughness=0.18),
    "porcelain": mat([0.92, 0.93, 0.90], 0.22, materialClass="clearcoat", clearcoat=0.25),
    "glow": mat([1.0, 0.80, 0.48], 0.40, emissive=[1.0, 0.58, 0.20], emissiveIntensity=1.6),
    "glow_soft": mat([1.0, 0.88, 0.65], 0.50, emissive=[1.0, 0.72, 0.38], emissiveIntensity=1.1),
    "paper": mat([0.92, 0.86, 0.70], 0.90, emissive=[0.55, 0.42, 0.22], emissiveIntensity=0.35),
    "moss": mat([0.18, 0.26, 0.10], 0.97),
    "orange": mat([0.75, 0.28, 0.08], 0.65),
}


class Author:
    def __init__(self):
        self.elements = []
        self.components = []
        self.walls = {}
        self.serial = 0

    def uid(self, prefix):
        self.serial += 1
        return f"{prefix}_{self.serial:04d}"

    def add(self, row):
        self.elements.append(row)
        return row

    def box(self, x, y, z, w, h, d, material, rotation=None, label=None,
            light_source=None, ident=None):
        row = {
            "type": "primitive", "id": ident or self.uid("box"), "shape": "box",
            "position": [x, y, z], "dimensions": [w, h, d], "material": material,
        }
        if rotation:
            row["rotation"] = rotation
        if label:
            row["label"] = label
        if light_source:
            row["lightSource"] = light_source
        return self.add(row)

    def cyl(self, x, y, z, radius, height, material, top=None, segments=16,
            rotation=None, ident=None):
        row = {
            "type": "primitive", "id": ident or self.uid("cyl"), "shape": "cylinder",
            "position": [x, y, z], "height": height, "segments": segments,
            "material": material,
        }
        if top is None:
            row["radius"] = radius
        else:
            row["radiusBottom"] = radius
            row["radiusTop"] = top
        if rotation:
            row["rotation"] = rotation
        return self.add(row)

    def sphere(self, x, y, z, radius, material, scale=None, segments=14,
               height_segments=10, ident=None):
        row = {
            "type": "primitive", "id": ident or self.uid("sph"), "shape": "sphere",
            "position": [x, y, z], "radius": radius, "segments": segments,
            "heightSegments": height_segments, "material": material,
        }
        if scale:
            row["scale"] = scale
        return self.add(row)

    def rod(self, a, b, width, depth, material, ident=None, round_profile=False):
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-6:
            return None
        if round_profile:
            return self.add({
                "type": "primitive", "id": ident or self.uid("sweep"),
                "shape": "profile_sweep", "position": [0, 0, 0],
                "path": [a, b], "radius": width / 2, "segments": 6,
                "material": material,
            })
        rotation = [math.atan2(dz, dy), 0.0, -math.asin(max(-1.0, min(1.0, dx / length)))]
        return self.box((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2,
                        width, length, depth, material, rotation=rotation, ident=ident)

    def wall(self, ident, x1, z1, x2, z2, y0, y1, thickness=0.24, material="plaster"):
        row = {
            "type": "wall", "id": ident,
            "from": [x1, y0, z1], "to": [x2, y1, z2],
            "thickness": thickness, "material": material,
        }
        self.elements.append(row)
        self.walls[ident] = row
        return ident

    def floor(self, ident, x1, z1, x2, z2, top, thickness, material):
        x1, x2 = sorted((x1, x2))
        z1, z2 = sorted((z1, z2))
        return self.add({
            "type": "floor", "id": ident,
            "from": [x1, top - thickness, z1], "to": [x2, top - thickness, z2],
            "thickness": thickness, "material": material,
        })

    def along(self, wall_id, cx, cz, width):
        wall = self.walls[wall_id]
        ax, az = wall["from"][0], wall["from"][2]
        bx, bz = wall["to"][0], wall["to"][2]
        dx, dz = bx - ax, bz - az
        length = math.hypot(dx, dz)
        ux, uz = dx / length, dz / length
        return (cx - ax) * ux + (cz - az) * uz - width / 2, length

    def window(self, wall_id, cx, cz, bottom, width, height, out=(0, 0),
               vm=1, hm=1, mullion=0.026, slats=0, sill=True, ident=None):
        along, _ = self.along(wall_id, cx, cz, width)
        host = self.walls[wall_id]
        ident = ident or self.uid("win")
        self.components.append({
            "type": "window", "id": ident, "parentWall": wall_id,
            "from": [along, bottom, 0], "width": width, "height": height,
            "frameWidth": 0.06, "frameDepth": host["thickness"] + 0.02,
            "glassDepth": 0.012, "verticalMullions": vm, "horizontalMullions": hm,
            "mullionWidth": mullion, "frameMaterial": "wood_dark",
            "glassMaterial": "glass",
        })
        if sill:
            self.window_trim(cx, cz, bottom, width, height, out, slats)
        return ident

    def window_trim(self, cx, cz, bottom, width, height, out, slats):
        ox, oz = out
        if abs(ox) > abs(oz):
            self.box(cx + ox * 0.08, bottom - 0.06, cz, 0.34, 0.10, width + 0.28, "stone_light")
            self.box(cx + ox * 0.08, bottom + height + 0.07, cz, 0.30, 0.12, width + 0.30, "stone")
            for i in range(slats):
                z = cz - width / 2 + width * (i + 1) / (slats + 1)
                self.box(cx + ox * 0.17, bottom + height / 2, z, 0.05, height - 0.08, 0.045, "wood_dark")
        else:
            self.box(cx, bottom - 0.06, cz + oz * 0.08, width + 0.28, 0.10, 0.34, "stone_light")
            self.box(cx, bottom + height + 0.07, cz + oz * 0.08, width + 0.30, 0.12, 0.30, "stone")
            for i in range(slats):
                x = cx - width / 2 + width * (i + 1) / (slats + 1)
                self.box(x, bottom + height / 2, cz + oz * 0.17, 0.045, height - 0.08, 0.05, "wood_dark")

    def door(self, wall_id, cx, cz, bottom, width, height, out=(0, 0), leaf="glass",
             double=None, ident=None, open_=False):
        along, _ = self.along(wall_id, cx, cz, width)
        host = self.walls[wall_id]
        ident = ident or self.uid("door")
        if double is None:
            double = width >= 1.4
        self.components.append({
            "type": "door", "id": ident, "parentWall": wall_id,
            "from": [along, bottom, 0], "width": width, "height": height,
            "frameWidth": 0.07, "frameDepth": host["thickness"] + 0.02,
            "leafDepth": 0.04, "frameMaterial": "wood_dark", "leafMaterial": leaf,
            "doorStyle": "double" if double else "single", "leafRows": 3,
            "interaction": {"mode": "swing", "hingeSide": "left",
                            "openAngle": 85, "initiallyOpen": open_},
        })
        ox, oz = out
        if abs(ox) > abs(oz):
            self.box(cx + ox * 0.10, bottom - 0.03, cz, 0.38, 0.08, width + 0.22, "stone_light")
        else:
            self.box(cx, bottom - 0.03, cz + oz * 0.10, width + 0.22, 0.08, 0.38, "stone_light")
        return ident

    def native_opening(self, wall_id, cx, cz, bottom, width, height, ident=None):
        along, _ = self.along(wall_id, cx, cz, width)
        ident = ident or self.uid("opening")
        self.add({
            "type": "opening", "id": ident, "parentWall": wall_id,
            "from": [along, bottom, 0], "width": width, "height": height,
            "style": "rectangular", "material": "stone",
        })
        return ident

    def rail(self, path, height=1.02, wood=True, glass=False, post_spacing=0.9, ident=None):
        row = {
            "type": "railing", "id": ident or self.uid("rail"), "path": path,
            "height": height, "postSpacing": post_spacing,
            "postRadius": 0.028 if wood else 0.018,
            "railRadius": 0.030 if wood else 0.022,
            "railLevels": [0.15, 0.88, 1.0],
            "material": "wood_dark" if wood else "metal_dark",
        }
        if glass:
            row.update(infillType="glass", infillMaterial="glass",
                       infillThickness=0.015, infillTopRatio=0.9)
        self.components.append(row)
        return row

    def column(self, x, z, base_y, top_y, radius=0.13, material="wood_dark"):
        self.cyl(x, base_y + 0.06, z, radius * 1.45, 0.12, "stone",
                 top=radius * 1.15, segments=16)
        self.add({
            "type": "column", "id": self.uid("col"), "base": [x, base_y + 0.12, z],
            "height": top_y - (base_y + 0.12), "bottomRadius": radius,
            "topRadius": radius * 0.78, "style": "chinese_wooden",
            "material": material,
        })

    def plaque(self, x, y, z, text, width=2.0, height=0.40, rotation=(0, PI, 0)):
        self.box(x, y, z, width, height, 0.08, "wood_dark", rotation=list(rotation),
                 label={"text": text, "color": [0.95, 0.82, 0.50], "fontFamily": "serif"})

    def roof(self, ident, cx, cz, eave, span, depth, height, thickness, axis):
        self.add({
            "type": "roof", "id": ident, "roofType": "gable", "ridgeAxis": axis,
            "span": span, "depth": depth, "height": height, "thickness": thickness,
            "position": [cx, eave, cz], "material": "roof_tile",
        })
        self.roof_details(cx, cz, eave, span, depth, height, thickness, axis)

    def roof_details(self, cx, cz, eave, span, depth, height, thickness, axis):
        ridge_y = eave + height
        if axis == "x":
            half = depth / 2.0

            def surf(value):
                return eave + height * max(0.0, 1.0 - abs(value - cz) / half)

            for sign in (-1, 1):
                z0 = cz + sign * (half - 0.04)
                z1 = cz + sign * 0.04
                self.box(cx, eave - 0.07, cz + sign * (half + 0.02),
                         span, 0.16, 0.10, "roof_edge")
                self.box(cx, eave - 0.16, cz + sign * (half + 0.02),
                         span, 0.04, 0.06, "roof_edge")
                for frac in (0.20, 0.40, 0.60, 0.80):
                    z = cz + sign * half * (1.0 - frac)
                    self.box(cx, surf(z) + 0.03, z, span - 0.30, 0.018, 0.03, "roof_tile_alt")
                inset = min(1.35, half * 0.45)
                count = max(6, int(span / 0.70))
                for i in range(count):
                    x = cx - span / 2 + span * (i + 0.5) / count
                    z_in = cz + sign * max(0.18, half - inset)
                    self.rod([x, surf(z0) - thickness - 0.10, z0],
                             [x, surf(z_in) - thickness - 0.10, z_in],
                             0.06, 0.10, "wood_dark")
                self.box(cx, eave - 0.30, cz + sign * (half - 0.45),
                         span - 0.40, 0.12, 0.16, "wood_dark")
                for barge in (cx - span / 2 + 0.02, cx + span / 2 - 0.02):
                    self.rod([barge, eave + 0.02, cz + sign * half],
                             [barge, ridge_y + 0.02, cz + sign * 0.04],
                             0.08, 0.14, "roof_edge")
            self.box(cx, ridge_y + 0.06, cz, span, 0.14, 0.20, "roof_ridge")
            self.box(cx, ridge_y + 0.12, cz, span, 0.06, 0.10, "roof_ridge")
            for x in (cx - span / 2, cx + span / 2):
                self.box(x, ridge_y + 0.16, cz, 0.18, 0.28, 0.18, "roof_ridge")
            rows = max(6, int((span - 0.32) / 0.28))
            for i in range(rows + 1):
                x = cx - span / 2 + 0.16 + i * (span - 0.32) / rows
                for sign in (-1, 1):
                    z0 = cz + sign * (half - 0.04)
                    z1 = cz + sign * 0.04
                    material = "roof_tile_alt" if i % 4 == 0 else "roof_tile"
                    self.rod([x, surf(z0) + 0.024, z0],
                             [x, surf(z1) + 0.024, z1],
                             0.044, 0.044, material, round_profile=True)
        else:
            half = span / 2.0

            def surf(value):
                return eave + height * max(0.0, 1.0 - abs(value - cx) / half)

            for sign in (-1, 1):
                x0 = cx + sign * (half - 0.04)
                x1 = cx + sign * 0.04
                self.box(cx + sign * (half + 0.02), eave - 0.07, cz,
                         0.10, 0.16, depth, "roof_edge")
                self.box(cx + sign * (half + 0.02), eave - 0.16, cz,
                         0.06, 0.04, depth, "roof_edge")
                for frac in (0.20, 0.40, 0.60, 0.80):
                    x = cx + sign * half * (1.0 - frac)
                    self.box(x, surf(x) + 0.03, cz, 0.03, 0.018, depth - 0.30, "roof_tile_alt")
                inset = min(1.35, half * 0.45)
                count = max(6, int(depth / 0.70))
                for i in range(count):
                    z = cz - depth / 2 + depth * (i + 0.5) / count
                    x_in = cx + sign * max(0.18, half - inset)
                    self.rod([x0, surf(x0) - thickness - 0.10, z],
                             [x_in, surf(x_in) - thickness - 0.10, z],
                             0.06, 0.10, "wood_dark")
                self.box(cx + sign * (half - 0.45), eave - 0.30, cz,
                         0.16, 0.12, depth - 0.40, "wood_dark")
                for barge in (cz - depth / 2 + 0.02, cz + depth / 2 - 0.02):
                    self.rod([cx + sign * half, eave + 0.02, barge],
                             [cx + sign * 0.04, ridge_y + 0.02, barge],
                             0.08, 0.14, "roof_edge")
            self.box(cx, ridge_y + 0.06, cz, 0.20, 0.14, depth, "roof_ridge")
            self.box(cx, ridge_y + 0.12, cz, 0.10, 0.06, depth, "roof_ridge")
            for z in (cz - depth / 2, cz + depth / 2):
                self.box(cx, ridge_y + 0.16, z, 0.18, 0.28, 0.18, "roof_ridge")
            rows = max(6, int((depth - 0.32) / 0.28))
            for i in range(rows + 1):
                z = cz - depth / 2 + 0.16 + i * (depth - 0.32) / rows
                for sign in (-1, 1):
                    x0 = cx + sign * (half - 0.04)
                    x1 = cx + sign * 0.04
                    material = "roof_tile_alt" if i % 4 == 0 else "roof_tile"
                    self.rod([x0, surf(x0) + 0.024, z],
                             [x1, surf(x1) + 0.024, z],
                             0.044, 0.044, material, round_profile=True)

    def pendant(self, x, z, ceiling_y, drop=0.55, intensity=10, distance=6):
        y = ceiling_y - drop
        self.cyl(x, ceiling_y - drop / 2, z, 0.012, drop, "metal_dark")
        self.cyl(x, y, z, 0.22, 0.12, "metal_dark", top=0.20)
        self.sphere(x, y - 0.10, z, 0.10, "glow", segments=16, height_segments=10)
        bulb = self.elements[-1]
        bulb["lightSource"] = {"lightType": "point", "color": [1.0, 0.78, 0.46],
                               "intensity": intensity, "distance": distance,
                               "initiallyOn": True, "offset": [0, -0.02, 0]}

    def bollard(self, x, z, y=0.0, height=0.75, intensity=4, distance=4):
        self.cyl(x, y + height / 2, z, 0.055, height, "metal_dark")
        self.box(x, y + height + 0.05, z, 0.16, 0.10, 0.16, "glow",
                 light_source={"lightType": "point", "color": [1.0, 0.72, 0.40],
                               "intensity": intensity, "distance": distance,
                               "initiallyOn": True})

    def lantern(self, x, y, z, intensity=5, distance=4):
        self.box(x, y, z, 0.30, 0.42, 0.30, "paper")
        for dx, dz in ((-0.17, 0), (0.17, 0), (0, -0.17), (0, 0.17)):
            self.box(x + dx, y, z + dz, 0.03, 0.46, 0.03, "wood_dark")
        self.box(x, y - 0.24, z, 0.20, 0.04, 0.20, "wood_dark")
        self.box(x, y + 0.24, z, 0.20, 0.04, 0.20, "wood_dark")
        self.box(x, y, z - 0.16, 0.12, 0.18, 0.03, "glow",
                 light_source={"lightType": "point", "color": [1.0, 0.70, 0.38],
                               "intensity": intensity, "distance": distance,
                               "initiallyOn": True})

    def bed(self, x, z, width=1.8, length=2.1, head="north", material="linen", base=F1):
        hdir = 1 if head == "north" else -1
        self.box(x, base + 0.20, z, width + 0.12, 0.34, length + 0.12, "wood_dark")
        self.box(x, base + 0.46, z, width, 0.22, length, material)
        self.box(x, base + 0.62, z + hdir * (length / 2 - 0.22), width * 0.92, 0.12, 0.34, "porcelain")
        self.box(x, base + 0.64, z + hdir * (length / 2 + 0.06), width + 0.20, 1.05, 0.12, "wood")
        for side in (-1, 1):
            self.box(x + side * (width / 2 + 0.28), base + 0.28,
                     z + hdir * (length / 2 - 0.20), 0.42, 0.40, 0.42, "wood")

    def wardrobe(self, x, z, w=1.8, d=0.60, h=2.20, material="wood", base=F1):
        self.box(x, base + h / 2, z, w, h, d, material)
        for i in range(3):
            self.box(x - w / 2 + w * (i + 0.5) / 3, base + h / 2, z + d / 2 + 0.01,
                     w / 3 - 0.04, h - 0.10, 0.03, "wood_dark")

    def shelf(self, x, z, w=1.8, h=2.0, d=0.36, base=F1):
        self.box(x, base + h / 2, z, w, h, d, "wood")
        for level in range(4):
            self.box(x, base + 0.18 + level * (h - 0.3) / 3, z, w - 0.10, 0.04, d - 0.04, "wood_dark")
            for b in range(5):
                self.box(x - w / 2 + 0.22 + b * (w - 0.44) / 4,
                         base + 0.44 + level * (h - 0.3) / 3,
                         z + 0.02, 0.07, 0.28, 0.22,
                         "plaster_cool" if b % 2 else "paper")

    def table(self, x, z, w=1.8, d=0.9, h=0.76, material="oak", base=F1):
        self.box(x, base + h, z, w, 0.08, d, material)
        for sx in (-1, 1):
            for sz in (-1, 1):
                self.box(x + sx * (w / 2 - 0.12), base + h / 2,
                         z + sz * (d / 2 - 0.10), 0.08, h, 0.08, "wood_dark")

    def chair(self, x, z, facing="south", material="linen", base=F1):
        dx, dz = {"south": (0, 1), "north": (0, -1), "east": (-1, 0), "west": (1, 0)}[facing]
        self.box(x, base + 0.45, z, 0.46, 0.10, 0.46, material)
        self.box(x - dx * 0.22, base + 0.78, z - dz * 0.22, 0.48, 0.55, 0.10, "wood_dark")
        for sx in (-1, 1):
            for sz in (-1, 1):
                self.box(x + sx * 0.18, base + 0.22, z + sz * 0.18,
                         0.045, 0.44, 0.045, "wood_dark")

    def vanity(self, x, z, w=1.5, base=F1):
        self.box(x, base + 0.42, z, w, 0.84, 0.52, "wood")
        self.box(x, base + 0.87, z, w + 0.04, 0.06, 0.56, "quartz")
        self.cyl(x, base + 0.92, z, 0.20, 0.08, "porcelain", top=0.22)
        self.box(x, base + 1.15, z - 0.20, 0.04, 0.18, 0.04, "bronze")

    def toilet(self, x, z, base=F1):
        self.box(x, base + 0.20, z, 0.40, 0.40, 0.62, "porcelain")
        self.box(x, base + 0.46, z + 0.06, 0.44, 0.10, 0.48, "porcelain")

    def bathtub(self, x, z, w=1.6, d=0.75, base=F1):
        self.box(x, base + 0.28, z, w, 0.56, d, "porcelain")
        self.box(x, base + 0.50, z, w - 0.18, 0.06, d - 0.16, "stone_light")

    def build(self):
        return clean({
            "meta": {
                "version": "1.1", "type": "building", "name": "砚溪别院",
                "author": "Claude Code · 原创设计", "style": "新中式 · 东宅西亭 · 水院廊桥",
                "seed": 20261023,
            },
            "geometry": {"elements": self.elements, "components": self.components},
            "materials": MATERIALS,
        })


def build_site(a):
    a.floor("site_w", SITE_X0, SITE_Z0, POOL_X0, SITE_Z1, 0.0, 0.15, "paving")
    a.floor("site_e", POOL_X1, SITE_Z0, SITE_X1, SITE_Z1, 0.0, 0.15, "paving")
    a.floor("site_s", POOL_X0, SITE_Z0, POOL_X1, POOL_Z0, 0.0, 0.15, "paving")
    a.floor("site_n", POOL_X0, POOL_Z1, POOL_X1, SITE_Z1, 0.0, 0.15, "paving")

    a.floor("pool_bottom", POOL_X0 + 0.10, POOL_Z0 + 0.10, POOL_X1 - 0.10,
            POOL_Z1 - 0.10, POOL_BOTTOM, 0.05, "pool_bottom")
    a.box((POOL_X0 + POOL_X1) / 2, (POOL_BOTTOM + 0.08) / 2, POOL_Z0 + 0.06,
          POOL_X1 - POOL_X0, 0.08 - POOL_BOTTOM, 0.12, "stone_dark")
    a.box((POOL_X0 + POOL_X1) / 2, (POOL_BOTTOM + 0.08) / 2, POOL_Z1 - 0.06,
          POOL_X1 - POOL_X0, 0.08 - POOL_BOTTOM, 0.12, "stone_dark")
    a.box(POOL_X0 + 0.06, (POOL_BOTTOM + 0.08) / 2, (POOL_Z0 + POOL_Z1) / 2,
          0.12, 0.08 - POOL_BOTTOM, POOL_Z1 - POOL_Z0, "stone_dark")
    a.box(POOL_X1 - 0.06, (POOL_BOTTOM + 0.08) / 2, (POOL_Z0 + POOL_Z1) / 2,
          0.12, 0.08 - POOL_BOTTOM, POOL_Z1 - POOL_Z0, "stone_dark")
    a.floor("water", POOL_X0 + 0.10, POOL_Z0 + 0.10, POOL_X1 - 0.10,
            POOL_Z1 - 0.10, WATER_Y, 0.02, "water")
    for x0, x1, z0, z1 in (
        (POOL_X0, POOL_X1, POOL_Z0 - 0.22, POOL_Z0),
        (POOL_X0, POOL_X1, POOL_Z1, POOL_Z1 + 0.22),
        (POOL_X0 - 0.22, POOL_X0, POOL_Z0 - 0.22, POOL_Z1 + 0.22),
        (POOL_X1, POOL_X1 + 0.22, POOL_Z0 - 0.22, POOL_Z1 + 0.22),
    ):
        a.box((x0 + x1) / 2, 0.05, (z0 + z1) / 2, x1 - x0, 0.10, z1 - z0, "stone_light")

    a.floor("pave_w", 4.80, -8.60, 6.30, -2.30, 0.03, 0.03, "paving")
    a.floor("pave_e", 8.10, -8.60, 12.00, -2.30, 0.03, 0.03, "paving")
    a.floor("entry_path", 6.30, -8.60, 8.10, -2.30, 0.06, 0.03, "stone_light")
    a.floor("apron", 6.30, -12.00, 8.10, -10.00, 0.03, 0.03, "paving")
    a.floor("lawn_w", -11.50, -8.50, -8.00, 12.00, 0.04, 0.04, "grass")
    a.floor("lawn_e", 15.00, -8.50, 17.50, 12.00, 0.04, 0.04, "grass")
    a.floor("lawn_n", -2.00, 10.50, 14.00, 13.50, 0.04, 0.04, "grass")
    a.floor("gravel", -4.00, -8.40, -2.40, -4.00, 0.03, 0.03, "gravel")
    for z in (-7.6, -6.4, -5.2, -4.0, -2.8):
        a.box(7.2, 0.062, z, 1.70, 0.006, 0.018, "stone_dark")

    for i, top in enumerate((0.05, 0.10, 0.15)):
        a.box(7.2, top / 2, -10.32 + i * 0.12, 2.10, top, 0.14, "stone_light")
    a.floor("gate_floor", GATE_X0, GATE_Z0 - 0.20, GATE_X1, GATE_Z1,
            0.15, 0.15, "stone_light")

    a.floor("main_plinth", MAIN_X0 - 0.14, MAIN_Z0 - 0.14,
            MAIN_X1 + 0.14, MAIN_Z1 + 0.14, 0.28, 0.28, "stone")
    a.floor("main_floor1", MAIN_X0, MAIN_Z0, MAIN_X1, MAIN_Z1, F1, 0.02, "oak")
    a.floor("tea_plinth", TEA_X0 - 0.14, TEA_Z0 - 0.14,
            TEA_X1 + 0.14, TEA_Z1 + 0.14, 0.28, 0.28, "stone")
    a.floor("tea_floor1", TEA_X0, TEA_Z0, TEA_X1, TEA_Z1, F1, 0.02, "oak")

    a.box(-1.03, 0.23, (TEA_Z0 + TEA_Z1) / 2 + 0.1, 0.66, 0.14,
          TEA_Z1 - TEA_Z0 - 0.3, "oak")
    a.box(0.875, 0.28, 4.20, 3.45, 0.12, 1.55, "oak")
    a.box(0.875, 0.345, 4.20, 3.45, 0.02, 1.55, "wood_dark")
    a.rail([[2.62, 0.35, 3.44], [-0.86, 0.35, 3.44]], height=0.98, wood=True)
    a.rail([[2.62, 0.35, 4.96], [-0.86, 0.35, 4.96]], height=0.98, wood=True)
    for x in (-0.80, 0.10, 1.00, 1.90, 2.55):
        a.cyl(x, 0.65, 3.44, 0.03, 0.62, "wood_dark")
        a.cyl(x, 0.65, 4.96, 0.03, 0.62, "wood_dark")

    a.box(7.20, 0.15, -3.05, 2.80, 0.30, 1.90, "stone_light")
    for i, top in enumerate((0.10, 0.20, 0.30)):
        a.box(7.20, top / 2, -4.10 + i * 0.18, 1.90, top, 0.16, "stone_light")
    a.column(6.20, -3.35, 0.30, 3.40, radius=0.12)
    a.column(8.20, -3.35, 0.30, 3.40, radius=0.12)
    a.box(7.20, 3.43, -3.20, 3.00, 0.06, 1.10, "wood_dark")
    a.box(7.20, 3.53, -3.05, 3.40, 0.16, 2.10, "roof_tile")
    a.box(7.20, 3.64, -3.05, 3.50, 0.04, 2.20, "roof_edge")
    for i in range(7):
        x = 5.90 + i * 0.44
        a.box(x, 3.40, -3.05, 0.06, 0.10, 1.90, "wood_dark")


def build_tea(a):
    a.wall("tea_s", TEA_X0, TEA_Z0, TEA_X1, TEA_Z0, F1, TEA_TOP, 0.22)
    a.wall("tea_e", TEA_X1, TEA_Z0, TEA_X1, TEA_Z1, F1, TEA_TOP, 0.22)
    a.wall("tea_n", TEA_X1, TEA_Z1, TEA_X0, TEA_Z1, F1, TEA_TOP, 0.22)
    a.wall("tea_w", TEA_X0, TEA_Z1, TEA_X0, TEA_Z0, F1, TEA_TOP, 0.22)
    a.wall("tea_store_w", -5.80, TEA_Z1, -5.80, 7.30, F1, TEA_TOP, 0.12)
    a.wall("tea_store_s", -5.80, 7.30, TEA_X0, 7.30, F1, TEA_TOP, 0.12)
    a.door("tea_store_w", -5.80, 8.45, F1, 0.80, 2.05, out=(0, 0), leaf="wood")
    a.door("tea_e", TEA_X1, 4.20, F1, 1.00, 2.30, out=(1, 0), leaf="glass", double=False)
    a.window("tea_e", TEA_X1, 6.35, 0.90, 1.60, 1.80, out=(1, 0), vm=2, hm=1, slats=4)
    a.window("tea_e", TEA_X1, 8.35, 0.90, 1.10, 1.80, out=(1, 0), vm=1, hm=1, slats=3)
    a.window("tea_s", -4.50, TEA_Z0, 0.90, 3.00, 1.80, out=(0, -1), vm=4, hm=1, slats=8)
    a.window("tea_w", TEA_X0, 5.40, 1.00, 3.00, 1.60, out=(-1, 0), vm=4, hm=1, slats=8)
    a.window("tea_n", -5.00, TEA_Z1, 1.80, 1.40, 1.00, out=(0, 1), vm=2, hm=0, slats=3)

    for z in (3.00, 5.50, 8.00):
        a.column(-1.00, z, 0.30, 3.55, radius=0.13)
    a.box(-1.00, 3.58, (TEA_Z0 + TEA_Z1) / 2, 0.18, 0.18, TEA_Z1 - TEA_Z0, "wood_dark")
    for i in range(11):
        z = TEA_Z0 + 0.2 + i * (TEA_Z1 - TEA_Z0 - 0.4) / 10
        a.box(-1.25, 3.45, z, 1.00, 0.10, 0.08, "wood")
    for z in (4.25, 6.75):
        a.box(-1.00, 3.30, z, 0.10, 0.34, 1.80, "wood_dark")
        for i in range(5):
            a.box(-1.00, 3.18, z - 0.80 + i * 0.40, 0.05, 0.10, 0.05, "wood_dark")

    a.roof("tea_roof", (TEA_X0 + TEA_X1) / 2, (TEA_Z0 + TEA_Z1) / 2,
           TEA_TOP, 7.2, 8.7, 1.05, 0.16, "z")

    a.table(-4.50, 5.50, w=1.90, d=0.85, h=0.42, material="wood")
    for x, z in ((-5.15, 5.05), (-5.15, 5.95), (-3.85, 5.05), (-3.85, 5.95)):
        a.box(x, F1 + 0.14, z, 0.42, 0.28, 0.42, "linen")
    a.cyl(-4.50, F1 + 0.50, 5.50, 0.16, 0.08, "porcelain", top=0.18)
    a.cyl(-4.18, F1 + 0.48, 5.62, 0.06, 0.06, "porcelain")
    a.cyl(-4.80, F1 + 0.48, 5.38, 0.05, 0.06, "porcelain")
    a.shelf(-6.55, 5.20, w=1.70, h=2.10, d=0.36)
    a.box(-6.55, F1 + 0.48, 3.00, 1.80, 0.90, 0.50, "wood")
    a.box(-6.55, F1 + 0.95, 3.00, 1.86, 0.06, 0.54, "quartz")
    a.box(-6.55, F1 + 2.35, 3.00, 1.90, 0.08, 0.10, "wood_dark")
    a.plaque(-1.35, 2.85, 4.20, "听松", width=1.10, height=0.32,
             rotation=(0, PI / 2, 0))
    a.pendant(-4.50, 5.50, TEA_TOP - 0.10, drop=0.65, intensity=9, distance=5)


def build_main(a):
    a.wall("main_s1", MAIN_X0, MAIN_Z0, MAIN_X1, MAIN_Z0, F1, MAIN_TOP1)
    a.wall("main_e1", MAIN_X1, MAIN_Z0, MAIN_X1, MAIN_Z1, F1, MAIN_TOP1)
    a.wall("main_n1", MAIN_X1, MAIN_Z1, MAIN_X0, MAIN_Z1, F1, MAIN_TOP1)
    a.wall("main_w1", MAIN_X0, MAIN_Z1, MAIN_X0, MAIN_Z0, F1, MAIN_TOP1)
    a.wall("main_s2", MAIN_X0, MAIN_Z0, MAIN_X1, MAIN_Z0, F2, MAIN_TOP2)
    a.wall("main_e2", MAIN_X1, MAIN_Z0, MAIN_X1, MAIN_Z1, F2, MAIN_TOP2)
    a.wall("main_n2", MAIN_X1, MAIN_Z1, MAIN_X0, MAIN_Z1, F2, MAIN_TOP2)
    a.wall("main_w2", MAIN_X0, MAIN_Z1, MAIN_X0, MAIN_Z0, F2, MAIN_TOP2)

    a.wall("guest_e", 6.20, MAIN_Z0, 6.20, 3.00, F1, MAIN_TOP1, 0.12)
    a.wall("guest_n", 6.20, 3.00, MAIN_X0, 3.00, F1, MAIN_TOP1, 0.12)
    a.wall("guest_bath_n", MAIN_X0, 1.20, 4.20, 1.20, F1, MAIN_TOP1, 0.12)
    a.wall("guest_bath_e", 4.20, 1.20, 4.20, 3.00, F1, MAIN_TOP1, 0.12)
    a.door("guest_e", 6.20, 2.20, F1, 0.90, 2.10, out=(0, 0), leaf="wood")
    a.door("guest_bath_e", 4.20, 2.20, F1, 0.80, 2.05, out=(0, 0), leaf="wood")
    a.wall("kitchen_e", 8.60, 6.00, 8.60, MAIN_Z1, F1, MAIN_TOP1, 0.12)
    a.wall("kitchen_s", 8.60, 6.00, MAIN_X1, 6.00, F1, MAIN_TOP1, 0.12)
    a.door("kitchen_s", 10.60, 6.00, F1, 1.10, 2.20, out=(0, 0), leaf="glass")
    a.door("kitchen_e", 8.60, 8.20, F1, 0.90, 2.10, out=(0, 0), leaf="wood")

    a.wall("l2_west_spine", 5.40, MAIN_Z0, 5.40, MAIN_Z1, F2, MAIN_TOP2, 0.12)
    a.wall("l2_west_split", MAIN_X0, 3.50, 5.40, 3.50, F2, MAIN_TOP2, 0.12)
    a.wall("l2_bed2_s", 5.40, 3.00, 8.00, 3.00, F2, MAIN_TOP2, 0.12)
    a.wall("l2_bath2_s", 5.40, 7.20, 8.00, 7.20, F2, MAIN_TOP2, 0.12)
    a.wall("l2_east_spine", 8.00, 2.00, 8.00, MAIN_Z1, F2, MAIN_TOP2, 0.12)
    a.wall("l2_master_s", 8.00, 2.00, MAIN_X1, 2.00, F2, MAIN_TOP2, 0.12)
    a.wall("l2_mbath_w", 12.60, 7.20, 12.60, MAIN_Z1, F2, MAIN_TOP2, 0.12)
    a.wall("l2_mbath_s", 12.60, 7.20, MAIN_X1, 7.20, F2, MAIN_TOP2, 0.12)
    a.door("l2_west_split", 4.00, 3.50, F2, 0.90, 2.10, out=(0, 0), leaf="wood")
    a.door("l2_bed2_s", 6.50, 3.00, F2, 0.90, 2.10, out=(0, 0), leaf="wood")
    a.door("l2_bath2_s", 6.60, 7.20, F2, 0.80, 2.05, out=(0, 0), leaf="wood")
    a.door("l2_west_spine", 5.40, 5.00, F2, 0.90, 2.10, out=(0, 0), leaf="wood")
    a.door("l2_west_spine", 5.40, 6.45, F2, 0.70, 2.05, out=(0, 0), leaf="wood")
    a.door("l2_east_spine", 8.00, 4.00, F2, 0.90, 2.10, out=(0, 0), leaf="wood")
    a.door("l2_mbath_w", 12.60, 8.50, F2, 0.80, 2.05, out=(0, 0), leaf="wood")

    a.door("main_s1", 7.20, MAIN_Z0, F1, 1.60, 2.60, out=(0, -1), leaf="glass", double=True)
    a.window("main_s1", 4.30, MAIN_Z0, 1.00, 2.00, 1.80, out=(0, -1), vm=3, hm=1, slats=5)
    a.window("main_s1", 12.00, MAIN_Z0, 0.55, 3.00, 2.70, out=(0, -1), vm=4, hm=2, slats=8)
    a.window("main_e1", MAIN_X1, 0.20, 0.55, 3.00, 2.70, out=(1, 0), vm=4, hm=2, slats=8)
    a.window("main_e1", MAIN_X1, 8.00, 1.00, 2.40, 1.80, out=(1, 0), vm=3, hm=1, slats=5)
    a.window("main_n1", 11.00, MAIN_Z1, 1.20, 3.00, 1.60, out=(0, 1), vm=4, hm=1, slats=7)
    a.door("main_w1", MAIN_X0, 4.20, F1, 1.10, 2.20, out=(-1, 0), leaf="glass", double=False)
    a.window("main_w1", MAIN_X0, 1.00, 1.00, 1.40, 1.60, out=(-1, 0), vm=2, hm=1, slats=3)

    a.window("main_s2", 3.90, MAIN_Z0, 4.60, 1.60, 1.60, out=(0, -1), vm=2, hm=1, slats=3)
    a.window("main_s2", 7.50, MAIN_Z0, 4.40, 2.00, 1.80, out=(0, -1), vm=3, hm=1, slats=5)
    a.window("main_s2", 12.35, MAIN_Z0, 3.70, 3.80, 3.00, out=(0, -1), vm=5, hm=2, slats=0)
    a.window("main_e2", MAIN_X1, 5.00, 4.60, 2.20, 1.80, out=(1, 0), vm=3, hm=1, slats=6)
    a.window("main_e2", MAIN_X1, 8.60, 5.20, 1.20, 1.20, out=(1, 0), vm=2, hm=0, slats=0)
    a.window("main_n2", 13.60, MAIN_Z1, 4.60, 1.20, 1.60, out=(0, 1), vm=2, hm=0, slats=0)
    a.window("main_n2", 7.00, MAIN_Z1, 4.60, 2.00, 1.60, out=(0, 1), vm=3, hm=1, slats=4)
    a.window("main_n2", 4.00, MAIN_Z1, 5.30, 1.00, 1.10, out=(0, 1), vm=2, hm=0, slats=0)
    a.window("main_w2", MAIN_X0, 0.50, 4.60, 1.60, 1.60, out=(-1, 0), vm=2, hm=1, slats=3)

    a.floor("slab_west", MAIN_X0, MAIN_Z0, 5.40, 6.40, F2, SLAB_T, "oak")
    a.floor("slab_center", 5.40, MAIN_Z0, 8.00, MAIN_Z1, F2, SLAB_T, "oak")
    a.floor("slab_east", 8.00, MAIN_Z0, 10.20, MAIN_Z1, F2, SLAB_T, "oak")
    a.floor("slab_master", 10.20, 2.00, MAIN_X1, MAIN_Z1, F2, SLAB_T, "oak")
    a.box(3.95, 3.60, 6.65, 2.90, 0.20, 0.50, "oak")
    a.box(3.95, 1.91, 9.45, 2.90, 0.18, 1.10, "oak")
    a.add({"type": "stair", "id": "stair_a", "from": [3.30, F1, 6.60],
           "to": [3.30, 2.00, 9.00], "width": 1.00,
           "stepCount": 10, "stepHeight": 0.17, "stepDepth": 0.24,
           "material": "oak"})
    a.add({"type": "stair", "id": "stair_b", "from": [4.50, 2.00, 9.00],
           "to": [4.50, F2, 6.60], "width": 1.00,
           "stepCount": 10, "stepHeight": 0.17, "stepDepth": 0.24,
           "material": "oak"})
    a.rail([[2.78, F1, 6.60], [2.78, 2.00, 9.00]], height=0.95, wood=True, post_spacing=0.80)
    a.rail([[5.02, 2.00, 9.00], [5.02, F2, 6.60]], height=0.95, wood=True, post_spacing=0.80)
    a.rail([[10.20, F2, -1.90], [10.20, F2, 2.00]], height=1.02, wood=True, post_spacing=0.90)
    a.rod([2.78, F1, 6.60], [2.78, 2.00, 9.00], 0.08, 0.30, "wood")
    a.rod([5.02, 2.00, 9.00], [5.02, F2, 6.60], 0.08, 0.30, "wood")

    a.roof("main_roof", (MAIN_X0 + MAIN_X1) / 2, (MAIN_Z0 + MAIN_Z1) / 2,
           MAIN_TOP2, 13.4, 13.4, 1.90, 0.18, "x")

    for x1, z1, x2, z2 in ((MAIN_X0, MAIN_Z0, MAIN_X1, MAIN_Z0),
                           (MAIN_X1, MAIN_Z0, MAIN_X1, MAIN_Z1),
                           (MAIN_X1, MAIN_Z1, MAIN_X0, MAIN_Z1),
                           (MAIN_X0, MAIN_Z1, MAIN_X0, MAIN_Z0)):
        length = math.hypot(x2 - x1, z2 - z1)
        cx, cz = (x1 + x2) / 2, (z1 + z2) / 2
        if abs(x2 - x1) > abs(z2 - z1):
            a.box(cx, 0.30, cz, length + 0.06, 0.60, 0.32, "stone")
            a.box(cx, 0.66, cz, length + 0.04, 0.12, 0.30, "stone_light")
            a.box(cx, 3.58, cz, length + 0.04, 0.24, 0.30, "stone_light")
        else:
            a.box(cx, 0.30, cz, 0.32, 0.60, length + 0.06, "stone")
            a.box(cx, 0.66, cz, 0.30, 0.12, length + 0.04, "stone_light")
            a.box(cx, 3.58, cz, 0.30, 0.24, length + 0.04, "stone_light")
    for x in (MAIN_X0, MAIN_X1):
        for z in (MAIN_Z0, MAIN_Z1):
            a.box(x, F1 + 1.60, z, 0.18, 3.16, 0.18, "wood_dark")
            a.box(x, F2 + 1.60, z, 0.18, 3.20, 0.18, "wood_dark")

    a.box(10.80, F1 + 0.30, 3.60, 2.60, 0.14, 2.10, "rug")
    a.box(10.80, F1 + 0.22, 4.30, 2.70, 0.34, 1.00, "linen")
    a.box(10.80, F1 + 0.47, 4.30, 2.40, 0.16, 0.80, "linen")
    a.box(10.80, F1 + 0.70, 4.72, 2.70, 0.80, 0.18, "wood_dark")
    for sx in (-1, 1):
        a.box(10.80 + sx * 1.30, F1 + 0.50, 4.30, 0.18, 0.55, 1.00, "wood_dark")
    a.table(10.80, 2.50, w=1.80, d=0.90, h=0.40, material="wood")
    a.chair(9.50, 1.60, facing="north")
    a.chair(12.10, 1.60, facing="north")
    a.box(7.10, F1 + 0.35, 0.20, 0.90, 0.70, 0.40, "wood")
    a.box(7.10, F1 + 0.72, 0.20, 0.96, 0.05, 0.46, "quartz")

    a.table(10.60, 8.00, w=2.20, d=1.00, h=0.76, material="oak")
    for x, z in ((9.60, 7.30), (10.60, 7.30), (11.60, 7.30),
                 (9.60, 8.70), (10.60, 8.70), (11.60, 8.70)):
        a.chair(x, z, facing="south" if z < 8.0 else "north")
    a.box(13.25, F1 + 0.45, 8.00, 2.20, 0.90, 0.90, "wood")
    a.box(13.25, F1 + 0.93, 8.00, 2.26, 0.06, 0.96, "quartz")
    a.box(13.25, F1 + 0.99, 8.00, 0.70, 0.03, 0.52, "stone_dark")
    a.cyl(13.25, F1 + 1.10, 7.80, 0.030, 0.28, "bronze")
    for z in (7.55, 8.00, 8.45):
        a.box(12.55, F1 + 0.32, z, 0.34, 0.64, 0.34, "linen")
    a.box(11.40, F1 + 0.45, 9.55, 5.40, 0.90, 0.68, "wood")
    a.box(11.40, F1 + 0.93, 9.55, 5.46, 0.06, 0.74, "quartz")
    a.box(11.40, F1 + 1.95, 9.78, 5.40, 0.70, 0.38, "wood")
    a.box(10.50, F1 + 2.40, 9.40, 1.20, 0.16, 0.50, "metal_dark")

    a.bed(4.30, -0.40, width=1.60, length=2.00, head="north")
    a.wardrobe(5.65, 0.35, w=0.60, d=1.60, h=2.20, material="wood")
    a.bathtub(3.30, 1.55, w=1.20, d=0.55)
    a.vanity(3.55, 2.55, w=1.00)
    a.toilet(2.85, 2.60)

    a.pendant(10.80, 2.50, MAIN_TOP1 - 0.10, drop=0.75, intensity=14, distance=7)
    a.pendant(10.60, 8.00, MAIN_TOP1 - 0.10, drop=0.70, intensity=12, distance=6)
    a.pendant(13.25, 8.00, MAIN_TOP1 - 0.10, drop=0.60, intensity=8, distance=5)

    a.bed(3.90, 0.00, width=1.40, length=2.00, head="north", base=F2)
    a.wardrobe(4.85, 2.70, w=0.55, d=1.20, h=2.10, material="wood", base=F2)
    a.box(3.00, F2 + 0.35, 5.00, 0.90, 0.70, 0.40, "wood")
    a.bed(6.70, 0.00, width=1.40, length=1.95, head="north", base=F2)
    a.wardrobe(7.60, 2.20, w=0.55, d=1.20, h=2.05, material="wood", base=F2)
    a.bathtub(6.20, 8.90, w=1.30, d=0.60, base=F2)
    a.vanity(7.20, 9.30, w=0.90, base=F2)
    a.toilet(5.90, 9.30, base=F2)
    a.shelf(9.10, 4.20, w=1.60, h=2.00, d=0.36, base=F2)
    a.box(7.00, F2 + 0.40, 6.20, 1.80, 0.80, 0.42, "linen")
    a.box(7.00, F2 + 0.44, 4.90, 1.20, 0.36, 0.70, "wood")
    a.bed(12.30, 4.80, width=1.90, length=2.10, head="north", base=F2)
    a.wardrobe(9.10, 5.20, w=0.60, d=2.20, h=2.20, material="wood", base=F2)
    a.bathtub(13.55, 9.30, w=1.55, d=0.65, base=F2)
    a.vanity(13.05, 7.90, w=0.80, base=F2)
    a.toilet(13.85, 7.75, base=F2)
    a.box(9.00, F2 + 0.42, 0.80, 1.20, 0.84, 0.40, "wood")
    a.pendant(12.30, 4.80, MAIN_TOP2 - 0.12, drop=0.70, intensity=10, distance=6)
    a.pendant(7.20, 5.20, F2 + 2.95, drop=0.60, intensity=8, distance=5)


def build_gate(a):
    a.wall("gate_front", GATE_X0, GATE_Z0, GATE_X1, GATE_Z0, 0.15, GATE_TOP)
    a.wall("gate_back", GATE_X1, GATE_Z1, GATE_X0, GATE_Z1, 0.15, GATE_TOP)
    a.wall("gate_w", GATE_X0, GATE_Z0, GATE_X0, GATE_Z1, 0.15, GATE_TOP)
    a.wall("gate_e", GATE_X1, GATE_Z0, GATE_X1, GATE_Z1, 0.15, GATE_TOP)
    a.native_opening("gate_front", 7.00, GATE_Z0, 0.15, 2.20, 2.40)
    a.native_opening("gate_back", 7.00, GATE_Z1, 0.15, 2.20, 2.40)
    for x in (5.85, 8.15):
        a.box(x, 1.35, GATE_Z0 - 0.05, 0.18, 2.40, 0.30, "stone")
        a.box(x, 1.35, GATE_Z1 + 0.05, 0.18, 2.40, 0.30, "stone")
    for z in (GATE_Z0 - 0.05, GATE_Z1 + 0.05):
        a.box(7.00, 2.55, z, 2.50, 0.18, 0.30, "stone")
    for z in (GATE_Z0 - 0.03, GATE_Z1 + 0.03):
        a.box(7.00, 0.15, z, 2.50, 0.12, 0.34, "stone_light")
    a.plaque(7.00, 2.96, GATE_Z0 - 0.17, "砚溪别院", width=2.10, height=0.42)
    a.box(6.036, 1.30, -9.493, 1.05, 2.30, 0.06, "wood_dark", rotation=[0, -1.309, 0])
    a.box(7.964, 1.30, -9.493, 1.05, 2.30, 0.06, "wood_dark", rotation=[0, -1.833, 0])
    for x in (6.00, 6.10, 7.90, 8.00):
        for y in (0.85, 1.35, 1.85):
            a.sphere(x, y, -9.50, 0.035, "bronze", segments=10, height_segments=6)
    a.roof("gate_roof", 7.00, -9.30, GATE_TOP, 4.80, 2.60, 0.85, 0.14, "x")
    a.lantern(5.35, 2.35, GATE_Z0 + 0.60, intensity=4, distance=4)
    a.lantern(8.65, 2.35, GATE_Z0 + 0.60, intensity=4, distance=4)
    for x0, x1, z0, z1 in ((GATE_X0, GATE_X1, GATE_Z0 - 0.02, GATE_Z0 + 0.10),
                           (GATE_X0, GATE_X1, GATE_Z1 - 0.10, GATE_Z1 + 0.02)):
        a.box((x0 + x1) / 2, 0.40, (z0 + z1) / 2, x1 - x0 + 0.06, 0.50, 0.30, "stone")
    for x in (GATE_X0, GATE_X1):
        a.box(x, 0.40, (GATE_Z0 + GATE_Z1) / 2, 0.30, 0.50, GATE_Z1 - GATE_Z0, "stone")
    a.plaque(7.00, 3.10, MAIN_Z0 - 0.15, "砚溪", width=1.60, height=0.30,
             rotation=(0, PI, 0))


def build_landscape(a):
    walls = [
        (SITE_X0, SITE_Z0, GATE_X0, SITE_Z0),
        (GATE_X1, SITE_Z0, SITE_X1, SITE_Z0),
        (SITE_X1, SITE_Z0, SITE_X1, SITE_Z1),
        (SITE_X1, SITE_Z1, SITE_X0, SITE_Z1),
        (SITE_X0, SITE_Z1, SITE_X0, SITE_Z0),
    ]
    for index, (x1, z1, x2, z2) in enumerate(walls):
        length = math.hypot(x2 - x1, z2 - z1)
        cx, cz = (x1 + x2) / 2, (z1 + z2) / 2
        if abs(x2 - x1) > abs(z2 - z1):
            a.box(cx, 1.175, cz, length, 2.05, 0.24, "plaster")
            a.box(cx, 0.325, cz, length + 0.04, 0.65, 0.32, "stone")
            a.box(cx, 2.26, cz, length + 0.10, 0.12, 0.34, "roof_tile_alt")
            a.box(cx, 2.34, cz, length + 0.16, 0.05, 0.38, "roof_ridge")
        else:
            a.box(cx, 1.175, cz, 0.24, 2.05, length, "plaster")
            a.box(cx, 0.325, cz, 0.32, 0.65, length + 0.04, "stone")
            a.box(cx, 2.26, cz, 0.34, 0.12, length + 0.10, "roof_tile_alt")
            a.box(cx, 2.34, cz, 0.38, 0.05, length + 0.16, "roof_ridge")
        steps = max(2, int(length / 4.0))
        for i in range(1, steps):
            t = i / steps
            x = x1 + (x2 - x1) * t
            z = z1 + (z2 - z1) * t
            if abs(x2 - x1) > abs(z2 - z1):
                a.box(x, 1.18, z, 0.36, 2.10, 0.36, "stone")
            else:
                a.box(x, 1.18, z, 0.36, 2.10, 0.36, "stone")

    a.box(-0.10, 0.30, -6.22, 5.00, 0.60, 0.40, "stone")
    a.box(-0.10, 1.45, -6.22, 4.90, 1.70, 0.34, "plaster")
    a.box(-0.10, 2.34, -6.22, 5.10, 0.12, 0.42, "roof_tile_alt")
    a.box(-0.10, 2.42, -6.22, 5.18, 0.05, 0.46, "roof_ridge")
    a.box(-0.10, 1.50, -6.42, 1.90, 1.10, 0.06, "stone_dark")
    a.cyl(-0.10, 1.50, -6.46, 0.42, 0.04, "bronze", segments=24,
          rotation=[PI / 2, 0, 0])
    a.plaque(-0.10, 2.02, -6.42, "澄怀", width=1.20, height=0.28)

    def tree(x, z, h, leaf, trunk_r=0.14):
        a.cyl(x, h * 0.28, z, trunk_r, h * 0.56, "bark", top=trunk_r * 0.7, segments=12)
        for dx, dz, dy, r in (
            (0.0, 0.0, 0.72, 0.95), (-0.55, 0.30, 0.58, 0.70),
            (0.55, -0.20, 0.62, 0.66), (0.20, 0.55, 0.48, 0.55),
            (-0.30, -0.50, 0.82, 0.58), (0.10, 0.10, 0.95, 0.52),
        ):
            a.sphere(x + dx, h * dy + 0.45, z + dz, r, leaf, scale=[1.0, 0.62, 1.0])
    tree(-3.20, -4.20, 3.20, "leaf_dark")
    tree(12.30, -5.30, 2.60, "maple")
    tree(4.20, 12.40, 3.00, "leaf_dark")
    tree(11.00, 12.20, 2.50, "maple")

    for x, z, r, sy in ((-2.20, -7.20, 0.55, 0.75), (-1.30, -7.00, 0.42, 0.65),
                        (-2.70, -6.60, 0.35, 0.60), (-0.50, -7.30, 0.30, 0.55)):
        a.sphere(x, 0.30 + r * sy * 0.5, z, r, "stone_dark",
                 scale=[1.0, sy, 0.85], segments=10, height_segments=8)
    for x, z in ((-3.10, -7.90), (-2.55, -7.55), (-1.85, -7.85), (-1.35, -7.50)):
        a.box(x, 0.035, z, 0.55, 0.05, 0.38, "stone_light")

    for i in range(9):
        x = -11.10 + (i % 3) * 0.32
        z = -2.00 + i * 1.25
        h = 2.60 + (i % 4) * 0.35
        a.cyl(x, h / 2, z, 0.035, h, "bamboo", segments=8)
        for j in range(3):
            a.sphere(x + 0.18 * ((j % 2) * 2 - 1), h * (0.55 + j * 0.15), z + 0.12,
                     0.38, "leaf_light", scale=[1.0, 0.55, 0.8], segments=8, height_segments=6)

    for x, z, r in ((-0.20, 2.30, 0.34), (0.65, 3.60, 0.28), (0.20, 6.30, 0.30),
                    (1.20, 7.20, 0.25), (-0.10, 4.80, 0.22)):
        a.cyl(x, WATER_Y + 0.03, z, r, 0.02, "leaf_light", segments=20)
    for x, z in ((0.55, 2.80), (0.95, 5.20), (0.35, 6.90)):
        a.sphere(x, WATER_Y - 0.10, z, 0.10, "orange",
                 scale=[1.7, 0.55, 0.75], segments=10, height_segments=6)
        a.sphere(x + 0.14, WATER_Y - 0.10, z, 0.035, "orange", segments=8, height_segments=5)

    for i in range(14):
        x = -9.50 + (i % 7) * 0.55
        z = 11.20 + (i // 7) * 1.10
        a.sphere(x, 0.16, z, 0.32, "moss", scale=[1.0, 0.28, 1.0], segments=8, height_segments=6)
    a.cyl(2.20, 0.19, 12.20, 0.28, 0.30, "stone", segments=8)
    a.cyl(2.20, 0.59, 12.20, 0.10, 0.50, "stone_dark", segments=8)
    a.box(2.20, 0.94, 12.20, 0.55, 0.40, 0.55, "stone_light")
    a.box(2.20, 1.19, 12.20, 0.30, 0.10, 0.30, "glow_soft",
          light_source={"lightType": "point", "color": [1.0, 0.72, 0.42],
                        "intensity": 3, "distance": 4, "initiallyOn": True})
    a.box(6.20, 0.48, 12.30, 1.70, 0.10, 0.42, "wood")
    for x in (5.50, 6.90):
        a.box(x, 0.24, 12.30, 0.10, 0.48, 0.36, "stone")

    for x, z in ((5.60, -7.80), (8.80, -7.80), (5.60, -4.90), (8.80, -4.90),
                 (0.40, -0.70), (-0.30, 9.10), (4.60, 11.20)):
        a.bollard(x, z, y=0.03 if z < 10 else 0.05, intensity=4, distance=4)
    a.bollard(2.10, 3.70, y=0.35, height=0.55, intensity=3, distance=3)
    for x, z in ((6.20, -2.20), (8.20, -2.20)):
        a.box(x, 3.12, z, 0.18, 0.08, 0.10, "glow_soft",
              light_source={"lightType": "point", "color": [1.0, 0.76, 0.46],
                            "intensity": 4, "distance": 4, "initiallyOn": True})


def main():
    a = Author()
    build_site(a)
    build_main(a)
    build_tea(a)
    build_gate(a)
    build_landscape(a)
    bp = a.build()
    text = json.dumps(bp, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(text, encoding="utf-8")
    stats = {
        "name": bp["meta"]["name"],
        "wild": str(OUT.name),
        "bytes": len(text.encode("utf-8")),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "elements": len(bp["geometry"]["elements"]),
        "components": len(bp["geometry"]["components"]),
        "materials": len(bp["materials"]),
        "method": "手工设计事实 → Python 标准库确定性几何展开 → 自足 WILD；未调用模型 API/RAG/外部资产",
        "validation": "本统计仅为写出结果；编译、项目校验与真实出图另记",
    }
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
