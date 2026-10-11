"""设计示意投影；保留离线视觉修订使用的旧编译适配器。"""
from __future__ import annotations

from collections import Counter

from .contracts import DesignDocument, ResolvedDesign, ResolvedLevel

RESOLVER_VERSION = "drawing-projection/5"


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
    from .coordinates import representative_floor_indices
    from .relations import opening_target
    from app.agent.knowledge.component_names import resolve_component_name

    d = document.decisions
    height = d.massing.floor_height
    indices = representative_floor_indices(d.massing)
    levels = [ResolvedLevel(index=i, base_y=(i-1)*height, top_y=i*height) for i in indices]
    walls = []
    for v in d.volumes:
        corners = {"front": ([v.x, v.z], [v.x+v.width, v.z]),
                   "right": ([v.x+v.width, v.z], [v.x+v.width, v.z+v.depth]),
                   "back": ([v.x+v.width, v.z+v.depth], [v.x, v.z+v.depth]),
                   "left": ([v.x, v.z+v.depth], [v.x, v.z])}
        for floor in range(v.start_floor, v.end_floor+1):
            for face, (a, b) in corners.items():
                walls.append({"id": f"wall_{v.id}_{face}_L{floor}", "type": "wall",
                              "from": [a[0], (indices[floor-1]-1)*height, a[1]],
                              "to": [b[0], indices[floor-1]*height, b[1]], "facing": face})
    markers = component_markers(document)
    wall_index = {w["id"]: w for w in walls}
    for marker in markers:
        if marker["host"] in wall_index:
            marker["diagram_host"] = wall_index[marker["host"]]
            size = marker["design"].get("size") or {}
            if (resolve_component_name(marker["type"])["entity_type"] in {"door", "window"}
                    and marker["entity"].get("position") and size.get("width") and size.get("height")):
                marker["entity"]["from"] = opening_target(marker, marker["diagram_host"], size["width"], size["height"])
    return ResolvedDesign(
        design_id=document.design_id, design_revision=document.revision,
        design_hash=_stable_hash(document), resolver_version=RESOLVER_VERSION,
        bounds={"width": max(v.x+v.width for v in d.volumes)-min(v.x for v in d.volumes),
                "depth": max(v.z+v.depth for v in d.volumes)-min(v.z for v in d.volumes),
                "height": d.massing.floors*height},
        levels=levels, volumes=d.volumes, facade_slots=[], projection_elements=walls,
        component_markers=markers, component_quantities=dict(Counter(m["type"] for m in markers)),
        warnings=["图纸为设计示意；构件形态由 plan 尝试实现，未定位标记列于图纸清单。"],
    )
