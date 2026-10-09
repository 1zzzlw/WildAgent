"""审核用正投影：坐标来自编译实体，屋顶包络不冒充引擎曲面。"""
from html import escape
from math import cos, sin
import textwrap


def _roof_box(entity, axis):
    position = entity.get("position", [0, 0, 0])
    rotation = entity.get("rotation", [0, 0, 0])
    angle = rotation[1] if isinstance(rotation, list) else 0
    span, depth = float(entity.get("span", 0)), float(entity.get("depth", 0))
    width = (abs(cos(angle)) * span + abs(sin(angle)) * depth if axis == 0
             else abs(sin(angle)) * span + abs(cos(angle)) * depth)
    height = max(float(entity.get("height", 0)) + float(entity.get("thickness", 0)), 0.02)
    return position[axis] - width / 2, position[1], width, height


def render_compiled_svg(document, resolved):
    elements = resolved.projection_elements
    walls = [e for e in elements if e.get("type") == "wall"]
    roofs = [e for e in elements if e.get("type") == "roof"]
    warning_lines = [line for message in resolved.warnings
                     for line in textwrap.wrap(str(message), width=42) or [""]]
    height = max(850, 505 + len(warning_lines) * 20)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" font-family="sans-serif">',
             f'<rect width="1200" height="{height}" fill="#171a20"/>',
             f'<text x="30" y="30" fill="white" font-size="18">{escape(document.decisions.concept or document.requirements.building_type)}</text>',
             f'<text x="30" y="55" fill="#aab8c8" font-size="13">DesignDocument r{document.revision} · {escape(resolved.resolver_version)} · 正投影审核图；虚线仅为屋顶参数包络</text>']
    # 使用真实世界范围，而非名义体量尺寸；两个立面使用相同米制比例。
    boxes = {}
    for axis in (0, 2):
        horizontal = [p[axis] for wall in walls for p in (wall["from"], wall["to"])]
        vertical = [p[1] for wall in walls for p in (wall["from"], wall["to"])]
        for roof in roofs:
            left, bottom, width, top = _roof_box(roof, axis)
            horizontal.extend([left, left + width])
            vertical.extend([bottom, bottom + top])
        boxes[axis] = (min(horizontal or [0]), max(horizontal or [1]),
                       min(vertical or [0]), max(vertical or [1]))
    scale = min(min(490 / max(b[1] - b[0], 1), 280 / max(b[3] - b[2], 1)) for b in boxes.values())
    slots_by_wall = {}
    for slot in resolved.facade_slots:
        slots_by_wall.setdefault(slot.parent_wall, []).append(slot)
    for facing, axis, panel_x, title in (("front", 0, 30, "正立面"), ("left", 2, 630, "左立面")):
        low, high, bottom, top = boxes[axis]
        origin = panel_x + 270 - (low + high) * scale / 2
        base = 385 + bottom * scale
        parts.append(f'<text x="{panel_x + 15}" y="90" fill="white">{title} · 与相邻视图同比例</text>')
        # 从远到近绘制不透明墙面，并把门窗与宿主放在同一绘制层；后墙不透到前墙。
        depth_axis = 2 if axis == 0 else 0
        ordered = sorted(walls, key=lambda w: (w["from"][depth_axis] + w["to"][depth_axis]) / 2, reverse=True)
        for wall in ordered:
            start, end = wall["from"], wall["to"]
            left, width = min(start[axis], end[axis]), abs(end[axis] - start[axis])
            if width < 0.001:
                continue
            wall_bottom, wall_top = min(start[1], end[1]), max(start[1], end[1])
            entity_id = escape(wall["id"], quote=True)
            parts.append(f'<rect x="{origin + left * scale:.2f}" y="{base - wall_top * scale:.2f}" width="{width * scale:.2f}" height="{(wall_top - wall_bottom) * scale:.2f}" fill="#2c3b49" stroke="#91aabd" data-design-path="/decisions/massing" data-entity-id="{entity_id}"><title>{entity_id}</title></rect>')
            for slot in slots_by_wall.get(wall["id"], []):
                if slot.facing != facing:
                    continue
                left = min(slot.world_from[axis], slot.world_to[axis])
                width = abs(slot.world_to[axis] - slot.world_from[axis])
                color = "#b78350" if slot.type == "door" else "#5aa7d7"
                parts.append(f'<rect x="{origin + left * scale:.2f}" y="{base - (slot.bottom + slot.height) * scale:.2f}" width="{width * scale:.2f}" height="{slot.height * scale:.2f}" fill="{color}" stroke="#bdd9e8" data-design-path="/decisions/facades/{facing}" data-slot-id="{escape(slot.id)}"><title>{escape(slot.id)}: {slot.width} × {slot.height} m</title></rect>')
        for roof in roofs:
            left, roof_bottom, width, roof_height = _roof_box(roof, axis)
            parts.append(f'<rect x="{origin + left * scale:.2f}" y="{base - (roof_bottom + roof_height) * scale:.2f}" width="{width * scale:.2f}" height="{roof_height * scale:.2f}" fill="none" stroke="#b9c8d6" stroke-dasharray="5 3" data-design-path="/decisions/roof"><title>屋顶参数包络，非曲面轮廓</title></rect>')
        parts.append(f'<text x="{panel_x + 15}" y="418" fill="#aab8c8" font-size="13">投影跨度 {high-low:.2f} m · 墙顶标高 {resolved.bounds["height"]:.2f} m</text>')
    parts.append('<text x="650" y="460" fill="white">底层墙体平面 · 按实际范围居中</text>')
    lowest = min([min(e["from"][1], e["to"][1]) for e in walls] or [0])
    ground = [w for w in walls if abs(min(w["from"][1], w["to"][1]) - lowest) < 0.001]
    points = [p for w in ground for p in (w["from"], w["to"])]
    xmin, xmax = min([p[0] for p in points] or [0]), max([p[0] for p in points] or [1])
    zmin, zmax = min([p[2] for p in points] or [0]), max([p[2] for p in points] or [1])
    plan_scale = min(460 / max(xmax-xmin, 1), 270 / max(zmax-zmin, 1))
    ox, oz = 890 - (xmin+xmax)*plan_scale/2, 650 - (zmin+zmax)*plan_scale/2
    for wall in ground:
        a, b = wall["from"], wall["to"]
        parts.append(f'<line x1="{ox+a[0]*plan_scale:.2f}" y1="{oz+a[2]*plan_scale:.2f}" x2="{ox+b[0]*plan_scale:.2f}" y2="{oz+b[2]*plan_scale:.2f}" stroke="#9bc3e0" stroke-width="3" data-design-path="/decisions/volumes" data-entity-id="{escape(wall["id"])}"/>')
    parts.append('<text x="30" y="460" fill="white">设计检查与剩余问题</text>')
    for index, line in enumerate(warning_lines):
        parts.append(f'<text x="30" y="{490+index*20}" fill="#efbc78" font-size="12">{escape(line)}</text>')
    if not warning_lines:
        parts.append('<text x="30" y="490" fill="#aab8c8">当前检查未报告问题；实际外观仍需渲染验收。</text>')
    parts.append('</svg>')
    return "".join(parts)
