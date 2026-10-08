"""Orthographic review projections of compiled entities; no independent design rules."""
from html import escape
from math import cos, sin


def render_compiled_svg(document, resolved):
    elements = resolved.projection_elements
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="820" viewBox="0 0 1200 820">',
             '<rect width="1200" height="820" fill="#171a20"/>',
             f'<text x="30" y="30" fill="white" font-size="18">{escape(document.decisions.concept or document.requirements.building_type)}</text>',
             f'<text x="30" y="55" fill="#aab8c8">DesignDocument r{document.revision} · {escape(resolved.resolver_version)} · 屋顶虚线表示编译参数范围，曲面由引擎重建</text>']
    for facing, axis, x0, base in (("front", 0, 45, 380), ("left", 2, 645, 380)):
        span = resolved.bounds["width" if axis == 0 else "depth"]
        roof_top = max([float(e.get("position", [0,0,0])[1])+float(e.get("height",0))+float(e.get("thickness",0)) for e in elements if e.get("type")=="roof"] or [resolved.bounds["height"]])
        scale = min(490/max(span+2,1), 280/max(roof_top,1))
        parts.append(f'<text x="{x0}" y="90" fill="white">{facing} · 确定性编译投影</text>')
        for e in elements:
            kind = e.get("type")
            if kind == "wall":
                start, end = e["from"], e["to"]
                left, width = min(start[axis],end[axis]), abs(end[axis]-start[axis])
                if width < 0.001:
                    continue
                bottom, height = min(start[1], end[1]), abs(end[1]-start[1])
                path, dashed = "/decisions/massing", ""
            elif kind == "roof":
                pos = e.get("position",[0,0,0])
                rotation = e.get("rotation", [0,0,0])
                angle = rotation[1] if isinstance(rotation,list) else 0
                width = abs(cos(angle))*float(e.get("span",0))+abs(sin(angle))*float(e.get("depth",0)) if axis==0 else abs(sin(angle))*float(e.get("span",0))+abs(cos(angle))*float(e.get("depth",0))
                left, bottom = pos[axis]-width/2, pos[1]
                height = max(float(e.get("height",0))+float(e.get("thickness",0)),0.02)
                path, dashed = "/decisions/roof", ' stroke-dasharray="5 3"'
            else:
                continue
            parts.append(f'<rect x="{x0+left*scale:.2f}" y="{base-(bottom+height)*scale:.2f}" width="{width*scale:.2f}" height="{height*scale:.2f}" fill="#34485b" fill-opacity="0.3" stroke="#829ab0"{dashed} data-design-path="{path}" data-entity-id="{escape(e["id"])}"/>')
        for slot in resolved.facade_slots:
            if slot.facing != facing:
                continue
            projected_width = abs(slot.world_to[axis] - slot.world_from[axis])
            parts.append(f'<rect x="{x0+slot.offset*scale:.2f}" y="{base-(slot.bottom+slot.height)*scale:.2f}" width="{projected_width*scale:.2f}" height="{slot.height*scale:.2f}" fill="{("#5aa7d7" if slot.type!="door" else "#b78350")}" data-design-path="/decisions/facades/{facing}" data-slot-id="{escape(slot.id)}"><title>{escape(slot.id)}: {slot.width} × {slot.height} m</title></rect>')
        parts.append(f'<text x="{x0}" y="410" fill="#aab8c8">主体宽深参考 {span:.1f} m · 实际墙顶 {resolved.bounds["height"]:.1f} m</text>')
    # Ground-plan anchors project actual compiled walls, not a second volume silhouette.
    parts.append('<text x="650" y="460" fill="white">底层墙体平面</text>')
    walls = [e for e in elements if e.get("type") == "wall"]
    lowest = min([e["from"][1] for e in walls] or [0])
    scale = min(430/max(resolved.bounds["width"],1), 250/max(resolved.bounds["depth"],1))
    for wall in walls:
        a,b = wall["from"], wall["to"]
        if abs(a[1]-lowest)>0.001:
            continue
        mx,mz = (a[0]+b[0])/2,(a[2]+b[2])/2
        index = next((i for i,v in enumerate(resolved.volumes)
                      if v.x-0.001<=mx<=v.x+v.width+0.001 and v.z-0.001<=mz<=v.z+v.depth+0.001), None)
        path = "/decisions/volumes" + (f"/{index}" if index is not None else "")
        parts.append(f'<line x1="{650+a[0]*scale:.2f}" y1="{490+a[2]*scale:.2f}" x2="{650+b[0]*scale:.2f}" y2="{490+b[2]*scale:.2f}" stroke="#9bc3e0" stroke-width="3" data-design-path="{path}" data-entity-id="{escape(wall["id"])}"/>')
    parts.append('<text x="30" y="460" fill="white">设计检查与剩余问题</text>')
    warnings = resolved.warnings
    for i, message in enumerate(warnings[:13]):
        parts.append(f'<text x="30" y="{485+i*23}" fill="#efbc78" font-size="12">{escape(message[:58])}</text>')
    if len(warnings)>13:
        parts.append(f'<text x="30" y="800" fill="#efbc78">另有 {len(warnings)-13} 项，完整结果见审核问题列表。</text>')
    parts.append('</svg>')
    return "".join(parts)
