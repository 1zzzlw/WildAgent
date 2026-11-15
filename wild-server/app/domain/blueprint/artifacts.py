"""从图状态和分片中选择可保留的蓝图产物。"""
from copy import deepcopy

def _has_entities(blueprint: dict) -> bool:
    geometry = blueprint.get("geometry")
    return isinstance(geometry, dict) and any(
        isinstance(geometry.get(bucket), list) and geometry[bucket]
        for bucket in ("elements", "components")
    )

def retain_generation_blueprint(state: dict, fallback: dict | None = None) -> dict | None:
    """从已有产物或分片恢复可编辑草稿，不因校验结果丢弃数据。"""
    candidates = [state.get("final_blueprint"), state.get("merged_blueprint")]
    fragments = state.get("component_fragments") or {}
    diagnostics = state.get("component_diagnostics") or {}
    failed_rows = [row for diag in diagnostics.values()
                   for key in ("partial_implementations", "failed_implementations")
                   for row in (diag.get(key) or {}).values()
                   if isinstance(row, dict) and isinstance(row.get("geometry"), dict)]
    if failed_rows or (isinstance(fragments, dict) and any(isinstance(parts, list) and parts for parts in fragments.values())):
        draft = deepcopy(state.get("skeleton_blueprint") or {"meta": {}, "geometry": {}})
        geometry = draft.setdefault("geometry", {})
        for bucket in ("elements", "components"):
            geometry[bucket] = list(geometry.get(bucket) or [])
        for task_id, parts in fragments.items():
            diag = diagnostics.get(task_id) or {}
            component_ids = set(diag.get("components") or [])
            for entity in parts if isinstance(parts, list) else []:
                bucket = "components" if isinstance(entity, dict) and entity.get("id") in component_ids else "elements"
                geometry[bucket].append(deepcopy(entity))
            for resource in ("materials", "assets"):
                for name, definition in (diag.get(resource) or {}).items():
                    draft.setdefault(resource, {}).setdefault(name, deepcopy(definition))
        for row in failed_rows:
            seen = {e.get("id") for bucket in ("elements", "components") for e in geometry[bucket]
                    if isinstance(e, dict) and isinstance(e.get("id"), str)}
            for bucket in ("elements", "components"):
                parts = row["geometry"].get(bucket)
                if isinstance(parts, list):
                    for entity in parts:
                        entity_id = entity.get("id") if isinstance(entity, dict) else None
                        if isinstance(entity_id, str) and entity_id in seen:
                            continue
                        geometry[bucket].append(deepcopy(entity))
                        if isinstance(entity_id, str):
                            seen.add(entity_id)
            for resource in ("materials", "assets"):
                definitions = row.get(resource)
                if isinstance(definitions, dict):
                    for name, definition in definitions.items():
                        draft.setdefault(resource, {}).setdefault(name, deepcopy(definition))
        candidates.append(draft)
    candidates.extend([fallback, state.get("skeleton_blueprint"), state.get("current_blueprint")])
    available = [value for value in candidates if isinstance(value, dict) and value]
    for blueprint in available:
        if _has_entities(blueprint):
            return deepcopy(blueprint)
    return None
