"""直接展示设计体量与构件标记；不依赖 WILD 模板或编译结果。"""
from html import escape
import textwrap


def render_drawing_svg(document, resolved):
    volume_indices = {v.id: i for i, v in enumerate(document.decisions.volumes)}
    elements = resolved.projection_elements
    walls = [e for e in elements if e.get("type") == "wall"]
    warning_lines = [line for message in resolved.warnings
                     for line in textwrap.wrap(str(message), width=42) or [""]]
    height = max(850, 505 + len(warning_lines) * 20, 460 + 340 * len(resolved.levels))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" font-family="sans-serif">',
             f'<rect width="1200" height="{height}" fill="#171a20"/>',
             f'<text x="30" y="30" fill="white" font-size="18">{escape(document.decisions.concept or document.requirements.building_type)}</text>',
             f'<text x="30" y="55" fill="#aab8c8" font-size="13">DesignDocument r{document.revision} · {escape(resolved.resolver_version)} · 设计示意图；具体形态由 plan 实现</text>']
    # 使用真实世界范围，而非名义体量尺寸；两个立面使用相同米制比例。
    boxes = {}
    for axis in (0, 2):
        horizontal = [p[axis] for wall in walls for p in (wall["from"], wall["to"])]
        vertical = [p[1] for wall in walls for p in (wall["from"], wall["to"])]
        boxes[axis] = (min(horizontal or [0]), max(horizontal or [1]),
                       min(vertical or [0]), max(vertical or [1]))
    scale = min(min(490 / max(b[1] - b[0], 1), 280 / max(b[3] - b[2], 1)) for b in boxes.values())
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
            volume_id = wall["id"].removeprefix("wall_").rsplit("_", 2)[0]
            design_path = f"/decisions/volumes/{volume_indices[volume_id]}"
            parts.append(f'<rect x="{origin + left * scale:.2f}" y="{base - wall_top * scale:.2f}" width="{width * scale:.2f}" height="{(wall_top - wall_bottom) * scale:.2f}" fill="#2c3b49" stroke="#91aabd" data-design-path="{design_path}" data-entity-id="{entity_id}"><title>{entity_id}</title></rect>')
        parts.append(f'<text x="{panel_x + 15}" y="418" fill="#aab8c8" font-size="13">投影跨度 {high-low:.2f} m · 墙顶标高 {resolved.bounds["height"]:.2f} m</text>')
    all_points = [p for w in walls for p in (w["from"], w["to"])]
    xmin, xmax = min([p[0] for p in all_points] or [0]), max([p[0] for p in all_points] or [1])
    zmin, zmax = min([p[2] for p in all_points] or [0]), max([p[2] for p in all_points] or [1])
    plan_scale = min(460 / max(xmax-xmin, 1), 240 / max(zmax-zmin, 1))
    wall_map = {w["id"]: w for w in walls}
    displayed = set()
    for row, level in enumerate(resolved.levels):
        top = 460 + row * 340
        parts.append(f'<text x="650" y="{top}" fill="white">第 {level.index} 层平面 · 标高 {level.base_y:g}m</text>')
        ox, oz = 890 - (xmin+xmax)*plan_scale/2, top + 145 - (zmin+zmax)*plan_scale/2
        layer = [w for w in walls if abs(min(w["from"][1], w["to"][1])-level.base_y) < 0.001]
        for wall in layer:
            a, b = wall["from"], wall["to"]
            parts.append(f'<line x1="{ox+a[0]*plan_scale:.2f}" y1="{oz+a[2]*plan_scale:.2f}" x2="{ox+b[0]*plan_scale:.2f}" y2="{oz+b[2]*plan_scale:.2f}" stroke="#9bc3e0" stroke-width="3" data-entity-id="{escape(wall["id"])}"/>')
        for marker in resolved.component_markers:
            entity = marker.get("entity") or {}
            wall = wall_map.get(entity.get("parentWall"))
            point = entity.get("position") or entity.get("base")
            if wall and not point and (isinstance(entity.get("from"), list) or "centerAlong" in entity):
                a, b = wall["from"], wall["to"]
                length = ((b[0]-a[0])**2+(b[2]-a[2])**2)**0.5
                local = entity.get("from", [entity.get("centerAlong", 0), entity.get("bottomY", 0), 0])
                if length > 0 and len(local) == 3:
                    ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
                    point = [a[0]+ux*local[0]-uz*local[2], local[1],
                             a[2]+uz*local[0]+ux*local[2]]
            if wall:
                floor = min(resolved.levels, key=lambda l: abs(l.base_y-wall["from"][1])).index
                a, b = wall["from"], wall["to"]
                point = point or [(a[0]+b[0])/2, level.base_y, (a[2]+b[2])/2]
            elif isinstance(point, list) and len(point) >= 3:
                floor = min(resolved.levels, key=lambda l: abs(l.base_y-point[1])).index
            elif entity.get("path"):
                point = entity["path"][0]
                floor = min(resolved.levels, key=lambda l: abs(l.base_y-point[1])).index
            else:
                continue
            if floor != level.index or not isinstance(point, list) or len(point) < 3:
                continue
            x, y = ox + point[0]*plan_scale, oz + point[2]*plan_scale
            label = escape(marker["id"])
            displayed.add(marker["id"])
            parts.append(f'<g data-marker-id="{label}" data-design-path="{escape(marker.get("design_path", "/decisions"))}"><circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#f3c475"/><text x="{x+5:.2f}" y="{y-6:.2f}" fill="#f3c475" font-size="9">{escape(marker["type"])} · {label}</text><title>{label} · {escape(marker["type"])} · 宿主 {escape(marker.get("host") or "")}</title></g>')

    parts.append('<text x="30" y="460" fill="white">设计检查与剩余问题</text>')
    for index, line in enumerate(warning_lines):
        parts.append(f'<text x="30" y="{490+index*20}" fill="#efbc78" font-size="12">{escape(line)}</text>')
    if not warning_lines:
        parts.append('<text x="30" y="490" fill="#aab8c8">当前检查未报告问题；实际外观仍需渲染验收。</text>')
    unlocated = [m for m in resolved.component_markers if m["id"] not in displayed]
    legend_y = 540 + len(warning_lines) * 20
    for index, marker in enumerate(unlocated):
        parts.append(f'<text x="30" y="{legend_y+index*20}" fill="#efbc78" font-size="12" data-marker-id="{escape(marker["id"])}">{escape(marker["type"])} · {escape(marker["id"])} · 未在示意图中定位，详见构件设计</text>')
    if unlocated:
        required_height = max(height, legend_y + len(unlocated)*20 + 30)
        parts[0] = parts[0].replace(f'height="{height}"', f'height="{required_height}"').replace(f'0 0 1200 {height}', f'0 0 1200 {required_height}')
        parts[1] = parts[1].replace(f'height="{height}"', f'height="{required_height}"')
    parts.append('</svg>')
    return "".join(parts)
