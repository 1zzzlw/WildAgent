"""按楼层展示设计坐标；符号不代替尚未设计的几何。"""
from collections import Counter
from html import escape
from math import hypot, isfinite
import textwrap

from app.agent.knowledge.component_names import resolve_component_name
from .coordinates import representative_floor_indices

BACKGROUND = "#0f172a"
COLORS = {"wall": "#facc15", "window": "#60a5fa", "door": "#fb7185",
          "stair": "#a78bfa", "balcony": "#fb923c", "railing": "#4ade80",
          "column": "#cbd5e1", "light": "#94a3b8"}
LABELS = {"wall": "实体墙", "window": "窗", "door": "门", "stair": "楼梯",
          "balcony": "阳台 / 平台", "railing": "栏杆", "column": "柱", "light": "灯具"}


def _room_bounds(room):
    bounds = room.get("bounds") or {}
    if all(k in bounds for k in ("x", "z", "width", "depth")):
        values = [bounds[k] for k in ("x", "z", "width", "depth")]
    elif all(k in bounds for k in ("x_start", "z_start", "x_end", "z_end")):
        values = [bounds["x_start"], bounds["z_start"], bounds["x_end"]-bounds["x_start"], bounds["z_end"]-bounds["z_start"]]
    else:
        return None
    return values if all(type(n) in (int, float) and isfinite(n) for n in values) and min(values[2:]) > 0 else None


def _marker_location(marker, levels):
    entity, design = marker.get("entity") or {}, marker["design"]
    wall = marker.get("diagram_host")
    point = entity.get("position") or entity.get("base")
    if wall:
        a, b = wall["from"], wall["to"]
        length = hypot(b[0]-a[0], b[2]-a[2])
        local = entity.get("from", [entity.get("centerAlong", length/2), 0, 0])
        if not point and length:
            ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
            point = [a[0]+ux*local[0]-uz*local[2], a[1], a[2]+uz*local[0]+ux*local[2]]
        floor = min(levels, key=lambda l: abs(l.base_y-a[1])).index
    elif isinstance(point, list) and len(point) == 3:
        floor = (design.get("placement") or {}).get("floor")
        floor = floor or min(levels, key=lambda l: abs(l.base_y-point[1])).index
    else:
        form = design.get("form") or {}
        path = entity.get("path") or (form.get("path") if isinstance(form, dict) else None)
        if not path:
            return None
        point = path[0]
        floor = (design.get("placement") or {}).get("floor") or min(levels, key=lambda l: abs(l.base_y-point[1])).index
    return (floor, point) if isinstance(point, list) and len(point) == 3 else None


def render_drawing_svg(document, resolved, floor=None):
    d = document.decisions
    selected = [l for l in resolved.levels if floor is None or l.index == floor]
    if not selected:
        raise ValueError(f"设计没有第 {floor} 层")
    layouts = d.model_dump(mode="json").get("floor_layouts") or []
    walls, located, pending, roof_markers = resolved.projection_elements, {}, [], []
    for marker in resolved.component_markers:
        if marker["type"] == "building_body":
            continue
        family = resolve_component_name(marker["type"])["entity_type"] or marker["type"]
        if family == "roof":
            roof_markers.append(marker)
            continue
        location = _marker_location(marker, resolved.levels)
        if location:
            located[marker["id"]] = (marker, family, *location)
        else:
            pending.append(marker)
    bounds = [(v.x, v.z, v.width, v.depth) for v in d.volumes]
    bounds.extend(b for layout in layouts for room in layout.get("rooms") or [] if (b := _room_bounds(room)))
    for marker, family, _, p in located.values():
        size = marker["design"].get("size") or {}
        w, depth = size.get("width", 0), size.get("depth", 0)
        bounds.append((p[0]-w/2, p[2]-depth/2, w, depth))
    xmin, zmin = min(b[0] for b in bounds), min(b[1] for b in bounds)
    xmax, zmax = max(b[0]+b[2] for b in bounds), max(b[1]+b[3] for b in bounds)
    scale = min(660/max(xmax-xmin, 1), 570/max(zmax-zmin, 1))
    warning_lines = [s for w in resolved.warnings for s in textwrap.wrap(w, 27)]
    sheet_height = max(880, 790+len(warning_lines)*21, 860+len(pending)*20)
    height = sheet_height*len(selected)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" font-family="Microsoft YaHei, Noto Sans SC, sans-serif">',
             f'<rect width="1200" height="{height}" fill="{BACKGROUND}"/>']

    def text(x, y, value, color="#cbd5e1", size=16, extra=""):
        parts.append(f'<text x="{x:.2f}" y="{y:.2f}" fill="{color}" font-size="{size}" {extra}>{escape(str(value))}</text>')

    def line(a, b, color, width=2, extra=""):
        parts.append(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" stroke="{color}" stroke-width="{width:.2f}" {extra}/>')

    for row, level in enumerate(selected):
        top = row*sheet_height
        parts.append(f'<g data-floor="{level.index}" data-base-y="{level.base_y:g}" data-marker-id="building_body">')
        text(32, top+42, f"平面设计图纸 · 第 {level.index} 层（F{level.index} · base {level.base_y:.3f}）", "#e2e8f0", 26, 'font-weight="700"')
        for i, s in enumerate(textwrap.wrap(str(d.concept or ""), 62)[:2]):
            text(32, top+72+i*22, s, "#93b4d5", 15)
        text(32, top+120, f"世界坐标 X/Z · 各层同比例 · DesignDocument r{document.revision} · 建筑全高 {resolved.bounds['height']:.1f} m", "#94a3b8", 13)
        ox, oz = 390-(xmin+xmax)*scale/2, top+450-(zmin+zmax)*scale/2

        def xy(p):
            return (ox+p[0]*scale, oz+p[-1]*scale)

        layer = [w for w in walls if abs(w["from"][1]-level.base_y) < 0.001]
        rooms = [(room, _room_bounds(room)) for layout in layouts if layout.get("floor") == level.index
                 for room in layout.get("rooms") or []]
        semantic = representative_floor_indices(d.massing)
        for i, v in enumerate(d.volumes):
            if not v.start_floor <= semantic.index(level.index)+1 <= v.end_floor:
                continue
            x, y = xy([v.x, v.z])
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{v.width*scale:.2f}" height="{v.depth*scale:.2f}" fill="none" stroke="#334155" stroke-dasharray="5 5" data-design-path="/decisions/volumes/{i}"><title>{escape(v.id)} · 空间包络，非实体墙</title></rect>')
            if not rooms:
                text(x+v.width*scale/2, y+v.depth*scale/2, v.model_dump().get("name") or v.id, "#94a3b8", 16, 'text-anchor="middle"')
        for room, b in rooms:
            if not b:
                continue
            x, y = xy(b[:2])
            if room.get("void"):
                parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{b[2]*scale:.2f}" height="{b[3]*scale:.2f}" fill="#1e293b" fill-opacity=".4" stroke="#94a3b8" stroke-dasharray="7 6" data-room-id="{escape(str(room.get("id", room.get("name", ""))), quote=True)}"/>')
        for wall in layer:
            parts.append(f'<g data-entity-id="{escape(wall["id"], quote=True)}" data-design-path="{escape(wall.get("design_path", "/decisions"), quote=True)}"><title>{escape(wall["id"])}</title>')
            line(xy(wall["from"]), xy(wall["to"]), COLORS["wall"], max(5, wall.get("thickness", 0)*scale))
            parts.append('</g>')
        counts, symbols_only = Counter(), 0
        for marker, family, floor_index, p in located.values():
            if floor_index != level.index:
                continue
            counts[family] += 1
            design, entity = marker["design"], marker.get("entity") or {}
            size, form = design.get("size") or {}, design.get("form") or {}
            form = form if isinstance(form, dict) else {}
            x, y = xy(p)
            color = COLORS.get(family, "#94a3b8")
            parts.append(f'<g data-marker-id="{escape(marker["id"], quote=True)}" data-design-path="{escape(marker.get("design_path", "/decisions/components"), quote=True)}"><title>{escape(design.get("name") or LABELS.get(family, marker["type"]))} · {escape(marker["id"])} · {escape(str(size))}</title>')
            wall = marker.get("diagram_host")
            if family in {"door", "window"} and wall and size.get("width"):
                a, b = wall["from"], wall["to"]
                length = hypot(b[0]-a[0], b[2]-a[2])
                ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
                start = entity.get("from", [entity.get("centerAlong", length/2)-size["width"]/2, 0, 0])[0]
                p0 = xy([a[0]+ux*start, a[2]+uz*start])
                p1 = xy([a[0]+ux*(start+size["width"]), a[2]+uz*(start+size["width"])])
                line(p0, p1, BACKGROUND, max(8, wall.get("thickness", 0)*scale)+2)
                line(p0, p1, color, 2)
                if family == "window":
                    for sign in (-1, 1):
                        line((p0[0]-uz*3*sign, p0[1]+ux*3*sign), (p1[0]-uz*3*sign, p1[1]+ux*3*sign), color, 1.5)
                elif form.get("hinge") in {"start", "end"} and form.get("swing_side") in {"left", "right"}:
                    hinge, end = (p0, p1) if form["hinge"] == "start" else (p1, p0)
                    radius = size["width"]*scale
                    sign = 1 if form["swing_side"] == "left" else -1
                    leaf = (hinge[0]-uz*radius*sign, hinge[1]+ux*radius*sign)
                    sweep = int((form["hinge"] == "start") == (sign > 0))
                    line(hinge, leaf, color, 2)
                    parts.append(f'<path d="M {end[0]:.2f} {end[1]:.2f} A {radius:.2f} {radius:.2f} 0 0 {sweep} {leaf[0]:.2f} {leaf[1]:.2f}" fill="none" stroke="{color}" stroke-dasharray="5 4"/>')
            elif family == "railing" and (path := entity.get("path") or form.get("path")):
                for a, b in zip(path, path[1:]):
                    line(xy(a), xy(b), color, 2.5)
            elif family == "light":
                symbols_only += 1
                parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="7" fill="none" stroke="{color}" stroke-width="2"/>')
            elif size.get("width") and size.get("depth"):
                w, depth = size["width"]*scale, size["depth"]*scale
                rotation = form.get("rotation_y", 0)
                parts.append(f'<g transform="translate({x:.2f} {y:.2f}) rotate({rotation:g})"><rect x="{-w/2:.2f}" y="{-depth/2:.2f}" width="{w:.2f}" height="{depth:.2f}" fill="none" stroke="{color}" stroke-width="2"'+(' stroke-dasharray="7 5"' if family == "balcony" else '')+'/>')
                if family == "stair":
                    for i in range(1, 11):
                        line((-w/2, -depth/2+i*depth/11), (w/2, -depth/2+i*depth/11), color, 1)
                    text(0, 5, "楼梯示意", color, 12, 'text-anchor="middle"')
                parts.append('</g>')
            else:
                symbols_only += 1
                if family == "column":
                    parts.append(f'<rect x="{x-5:.2f}" y="{y-5:.2f}" width="10" height="10" fill="{color}"/>')
                else:
                    parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}"/>')
            parts.append('</g>')
        for room, b in rooms:
            if not b:
                continue
            x, y = xy([b[0]+b[2]/2, b[1]+b[3]/2])
            name = room.get("name") or room.get("id") or ""
            lines = textwrap.wrap(str(name), max(3, int(b[2]*scale/18)))
            parts.append(f'<g data-room-id="{escape(str(room.get("id", name)), quote=True)}"><title>{escape(str(name))}</title>')
            for i, s in enumerate(lines):
                text(x, y+(i-(len(lines)-1)/2)*23, s, "#dbeafe", 18, 'text-anchor="middle" paint-order="stroke" stroke="#0f172a" stroke-width="3"')
            if room.get("void"):
                text(x, y+len(lines)*15+12, "挑空上空", "#93c5fd", 13, 'text-anchor="middle"')
            parts.append('</g>')
        vx0, vz0 = min(v.x for v in d.volumes), min(v.z for v in d.volumes)
        vx1, vz1 = max(v.x+v.width for v in d.volumes), max(v.z+v.depth for v in d.volumes)
        a, b = xy([vx0, vz0]), xy([vx1, vz1])
        line((a[0], b[1]+32), (b[0], b[1]+32), "#64748b", 1, 'data-design-path="/decisions/massing"')
        for x in (a[0], b[0]):
            line((x, b[1]+24), (x, b[1]+40), "#64748b", 1)
        text((a[0]+b[0])/2, b[1]+53, f"{vx1-vx0:.1f} m", "#94a3b8", 14, 'text-anchor="middle"')
        text(a[0]-14, (a[1]+b[1])/2, f"{vz1-vz0:.1f} m", "#94a3b8", 14, f'text-anchor="middle" transform="rotate(-90 {a[0]-14:.2f} {(a[1]+b[1])/2:.2f})"')
        text(40, top+810, "X →    Z ↓  · 所有楼层共享世界坐标", "#94a3b8", 13)
        line((785, top+145), (785, top+770), "#253349", 1)
        text(820, top+170, "本层图例", "#e2e8f0", 21, 'font-weight="700"')
        for i, family in enumerate(LABELS):
            ly = top+207+i*35
            parts.append(f'<g data-legend-family="{family}">')
            if family == "column":
                parts.append(f'<rect x="832" y="{ly-16:.2f}" width="14" height="14" fill="{COLORS[family]}"/>')
            elif family == "light":
                parts.append(f'<circle cx="839" cy="{ly-9:.2f}" r="6" fill="none" stroke="{COLORS[family]}" stroke-width="2"/>')
                line((839, ly-20), (839, ly-17), COLORS[family], 2)
                line((839, ly-1), (839, ly+2), COLORS[family], 2)
            else:
                line((820, ly-5), (858, ly-5), COLORS[family], 4 if family == "wall" else 2,
                     'stroke-dasharray="6 4"' if family == "balcony" else '')
            text(878, ly, LABELS[family]+(f" × {counts[family]}" if counts[family] else ""), "#cbd5e1", 16)
            parts.append('</g>')
        text(820, top+515, "虚线框：空间包络 / 挑空", "#94a3b8", 14)
        text(820, top+542, "点标记：位置已知，形态或尺寸待实现", "#94a3b8", 14)
        text(820, top+569, "门弧：已声明铰接端与开启侧", "#94a3b8", 14)
        text(820, top+609, f"本层 {sum(counts.values())} 个构件标记 · {symbols_only} 个点标记", "#93c5fd", 15)
        for i, s in enumerate(textwrap.wrap("屋型："+d.roof.type, 26)[:2]):
            text(820, top+637+i*21, s, "#94a3b8", 13, 'data-design-path="/decisions/roof"')
        for marker in roof_markers:
            parts.append(f'<g data-marker-id="{escape(marker["id"], quote=True)}"><title>{escape(marker["id"])} · 屋面不覆盖平面剖切图</title></g>')
        notices = []
        if not rooms:
            notices.append("本层尚未提供房间分区；图中显示体量名称。")
        elif any(not b for _, b in rooms):
            notices.append("部分房间缺少可绘制的 bounds，位置待设计。")
        notices += warning_lines
        for i, s in enumerate(s for n in notices for s in textwrap.wrap(n, 27)):
            text(820, top+705+i*21, s, "#d6ad72", 13)
        for i, marker in enumerate(pending):
            text(40, top+839+i*20, f"未定位：{marker['type']} · {marker['id']}", "#d6ad72", 12,
                 f'data-marker-id="{escape(marker["id"], quote=True)}"')
        parts.append('</g>')
    parts.append('</svg>')
    return "".join(parts)
