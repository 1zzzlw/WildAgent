"""Canonical document compilation and review projection; no persisted Blueprint cache."""
from __future__ import annotations

from collections import Counter
from math import hypot
from typing import Any

from .contracts import DesignDocument, DesignGap, ResolvedDesign, ResolvedFacadeSlot, ResolvedLevel

RESOLVER_VERSION = "compiler-projection/2"


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


def project_compilation(document: DesignDocument, result: Any) -> ResolvedDesign:
    from .resolver import _stable_hash
    from .completeness import evaluate_design

    geometry = (result.blueprint or {}).get("geometry") or {}
    elements = geometry.get("elements") or []
    components = geometry.get("components") or []
    walls = {e["id"]: e for e in elements if e.get("type") == "wall"}
    brief = result.design_brief or {}
    facades = brief.get("facade_plan") or {}
    massing = document.decisions.massing
    slots = []
    warnings = [f"{d.code}: {d.evidence}" for d in result.defects]
    for item in components:
        if item.get("type") not in {"door", "window", "bay_window"}:
            continue
        wall = walls.get(item.get("parentWall"))
        if wall is None:
            warnings.append(f"{item.get('id')}: 开口缺少有效墙宿主，无法投影")
            continue
        start, end = wall["from"], wall["to"]
        local = item["from"]
        length = hypot(end[0] - start[0], end[2] - start[2])
        if length <= 0:
            continue
        ux, uz = (end[0]-start[0])/length, (end[2]-start[2])/length
        # WILD opening Y is absolute elevation; X is distance along parent wall.
        world = [start[0]+ux*local[0]-uz*local[2], local[1], start[2]+uz*local[0]+ux*local[2]]
        world_end = [world[0]+ux*item["width"], world[1], world[2]+uz*item["width"]]
        facing = (facades.get(wall["id"]) or {}).get("facing")
        if facing not in {"front", "back", "left", "right"}:
            facing = ("front" if uz == 0 and ux >= 0 else "back") if abs(ux) >= abs(uz) else ("right" if uz >= 0 else "left")
        axis = 0 if facing in {"front", "back"} else 2
        direction = ux if axis == 0 else uz
        offset = min(world[axis], world[axis]+direction*item["width"])
        slots.append(ResolvedFacadeSlot(
            id=item["id"], facing=facing, floor=max(1, round(start[1]/massing.floor_height)+1),
            bay=len(slots)+1, type=item["type"], parent_wall=wall["id"],
            local_from=list(local), world_from=world, world_to=world_end, offset=round(offset, 6),
            width=item["width"], bottom=local[1], height=item["height"],
        ))
    heights = sorted({float(w["from"][1]) for w in walls.values()})
    levels = [ResolvedLevel(index=max(1, round(y/massing.floor_height)+1), base_y=y,
               top_y=max(max(float(w["from"][1]), float(w["to"][1]))
                         for w in walls.values() if float(w["from"][1]) == y)) for y in heights]
    projection = [e for e in elements if e.get("type") in {"wall", "floor", "roof", "column"}]
    resolved = ResolvedDesign(
        design_id=document.design_id, design_revision=document.revision,
        design_hash=_stable_hash(document), resolver_version=RESOLVER_VERSION,
        bounds={"width": massing.width, "depth": massing.depth,
                "height": max([l.top_y for l in levels] or [massing.modeled_floors*massing.floor_height])},
        levels=levels, volumes=document.decisions.volumes, facade_slots=slots,
        component_quantities=dict(Counter(e.get("type", "unknown") for e in [*elements, *components])),
        projection_elements=projection, warnings=warnings,
    )
    resolved.design_gaps = evaluate_design(document, resolved.design_hash)
    for index, change in enumerate((result.stats.get("instance_overrides") or {}).get("size_changes") or []):
        constraint = next((c.id for c in document.constraints if
            c.target == change["path"] or change["path"].startswith(c.target+"/")), "request.source")
        resolved.design_gaps.append(DesignGap(
            id=f"gap.compiler.instance_size.{index}", constraint_id=constraint,
            layer="implementation", status="unsupported", design_hash=resolved.design_hash,
            target=change["path"], expected=change["before"], actual=change["after"],
            evidence=f"{change['target']} {change['path']}：{change['reason']}（{change['before']} → {change['after']}）",
        ))
    resolved.warnings.extend(g.evidence for g in resolved.design_gaps if g.status != "satisfied")
    return resolved


def opening_drift(resolved: ResolvedDesign, blueprint: dict) -> list[str]:
    """Recheck after merge/repair, independently of the geometry validation cache."""
    actual = {e.get("id"): e for e in (blueprint.get("geometry") or {}).get("components", [])}
    errors = []
    walls = {e.get("id"): e for e in (blueprint.get("geometry") or {}).get("elements", []) if e.get("type") == "wall"}
    for slot in resolved.facade_slots:
        item = actual.get(slot.id)
        if item is None:
            errors.append(f"{slot.id}: 审核开口在成品中缺失")
            continue
        if item.get("parentWall") != slot.parent_wall or item.get("type") != slot.type:
            errors.append(f"{slot.id}: 审核开口的类型或宿主改变")
        for field, expected in (("width", slot.width), ("height", slot.height)):
            value = item.get(field)
            if not isinstance(value, (int, float)) or abs(value-expected) > 0.001:
                errors.append(f"{slot.id}.{field}: 审核 {expected}，成品 {value}")
        local = item.get("from")
        if not isinstance(local, list) or len(local) != 3 or any(
            not isinstance(v, (int, float)) or abs(v-e)>0.001 for v,e in zip(local, slot.local_from)
        ):
            errors.append(f"{slot.id}: 审核开口局部位置改变")
        try:
            wall = walls[item["parentWall"]]
            if wall.get("curve"):
                raise ValueError("straight host changed to curve")
            a,b = wall["from"], wall["to"]
            length = hypot(b[0]-a[0], b[2]-a[2])
            ux,uz = (b[0]-a[0])/length, (b[2]-a[2])/length
            world = [a[0]+ux*local[0]-uz*local[2], local[1], a[2]+uz*local[0]+ux*local[2]]
            end = [world[0]+ux*item["width"], world[1], world[2]+uz*item["width"]]
            if any(abs(a-b)>0.001 for a,b in zip(world+end,slot.world_from+slot.world_to)):
                errors.append(f"{slot.id}: 宿主变化导致审核开口世界位置或朝向改变")
        except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
            errors.append(f"{slot.id}: 无法验证审核开口的当前宿主坐标")
    return errors
