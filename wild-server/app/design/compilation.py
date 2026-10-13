"""设计示意投影；保留离线视觉修订使用的旧编译适配器。"""
from __future__ import annotations

from collections import Counter

from .contracts import DesignDocument, ResolvedDesign, ResolvedLevel

RESOLVER_VERSION = "drawing-projection/1"


def compile_document(document: DesignDocument):
    # Lazy boundary: the compiler consumes plan data and never imports this adapter.
    from app.agent.compiler import compile_design
    from .resolver import architecture_plan_from_document

    materials = document.decisions.materials.resolved_plan
    return compile_design(
        architecture_plan_from_document(document),
        user_message=document.requirements.source_request,
        material_plan=materials.model_dump(mode="json") if materials else None,
        normalized_input=True,
    )


def project_drawing(document: DesignDocument) -> ResolvedDesign:
    """从设计尺寸绘制示意，不运行 WILD 编译器。"""
    from .resolver import _stable_hash
    from .markers import component_markers
    from .coordinates import representative_floor_indices, floor_elevations
    from .relations import opening_target
    from .openings import is_open_side
    from app.agent.knowledge.component_names import resolve_component_name

    d = document.decisions
    indices = representative_floor_indices(d.massing)
    elevations = floor_elevations(d.model_dump(mode="json"))
    levels = [ResolvedLevel(index=i, base_y=elevations[i], top_y=elevations[i+1]) for i in indices]
    walls, frames = [], {}
    for volume_index, v in enumerate(d.volumes):
        corners = {"front": ([v.x, v.z], [v.x+v.width, v.z]),
                   "right": ([v.x+v.width, v.z], [v.x+v.width, v.z+v.depth]),
                   "back": ([v.x+v.width, v.z+v.depth], [v.x, v.z+v.depth]),
                   "left": ([v.x, v.z+v.depth], [v.x, v.z])}
        for floor in range(v.start_floor, v.end_floor+1):
            for face, (a, b) in corners.items():
                facade = v.facades.get(face) or d.facades[face]
                frame = {"id": f"wall_{v.id}_{face}_L{floor}", "type": "wall",
                         "from": [a[0], elevations[indices[floor-1]], a[1]],
                         "to": [b[0], elevations[indices[floor-1]+1], b[1]], "facing": face,
                         "design_path": f"/decisions/volumes/{volume_index}"}
                if is_open_side(facade.ground_pattern if floor == 1 else facade.upper_pattern):
                    frame["open"] = True
                else:
                    walls.append(frame)
                frames[frame["id"]] = frame
    # 平面内墙也是主体的设计宿主；与外墙共用世界坐标和门窗定位协议。
    from math import isfinite
    for index, layout in enumerate(d.model_dump(mode="json").get("floor_layouts") or []):
        floor = layout.get("floor")
        if floor not in elevations or floor > d.massing.floors:
            continue
        for j, wall in enumerate(layout.get("walls") or []):
            path = f"/decisions/floor_layouts/{index}/walls/{j}"
            if (not isinstance(wall.get("id"), str) or not wall["id"] or wall["id"] in frames
                    or any(not isinstance(wall.get(key), list) or len(wall[key]) != 2
                           or any(type(n) not in (int, float) or not isfinite(n) for n in wall[key])
                           for key in ("from", "to"))
                    or wall["from"] == wall["to"]
                    or type(wall.get("thickness")) not in (int, float) or not isfinite(wall["thickness"])
                    or wall["thickness"] <= 0):
                raise ValueError(f"{path}：内墙需唯一 id、不同的世界 X/Z 端点 from/to 和正数 thickness")
            frame = {"id": wall["id"], "type": "wall", "thickness": wall["thickness"],
                     "from": [wall["from"][0], elevations[floor], wall["from"][1]],
                     "to": [wall["to"][0], elevations[floor+1], wall["to"][1]], "design_path": path}
            frames[frame["id"]] = frame
            walls.append(frame)
    markers = component_markers(document)
    for marker in markers:
        if marker["host"] in frames:
            marker["diagram_host"] = frames[marker["host"]]
            size = marker["design"].get("size") or {}
            if (resolve_component_name(marker["type"])["entity_type"] in {"door", "window"}
                    and marker["entity"].get("position") and size.get("width") and size.get("height")):
                marker["entity"]["from"] = opening_target(marker, marker["diagram_host"], size["width"], size["height"])
    return ResolvedDesign(
        design_id=document.design_id, design_revision=document.revision,
        design_hash=_stable_hash(document), resolver_version=RESOLVER_VERSION,
        bounds={"width": max(v.x+v.width for v in d.volumes)-min(v.x for v in d.volumes),
                "depth": max(v.z+v.depth for v in d.volumes)-min(v.z for v in d.volumes),
                "height": elevations[d.massing.floors+1]-elevations[1]},
        levels=levels, volumes=d.volumes, facade_slots=[], projection_elements=walls,
        component_markers=markers, component_quantities=dict(Counter(m["type"] for m in markers)),
        warnings=["图纸为设计示意；构件形态由 plan 尝试实现，未定位标记列于图纸清单。"],
    )
