"""已通过修复复检的候选蓝图到 GenerationState 的同步规则。"""

from copy import deepcopy

from app.agent.generation.components import COMPONENT_REGISTRY
from app.agent.state import GenerationState


def state_updates_from_candidate(
    state: GenerationState,
    candidate: dict,
    changed_ids: set[str],
) -> dict:
    """提交通过复检的候选蓝图，并同步相关骨架/组件源分片。"""
    geometry = candidate.get("geometry", {})
    candidate_entities = {
        entity["id"]: entity
        for entity in [
            *geometry.get("elements", []),
            *geometry.get("components", []),
        ]
        if isinstance(entity, dict) and entity.get("id") in changed_ids
    }
    updates: dict = {"merged_blueprint": deepcopy(candidate)}
    fragment_updates: dict = {}
    generic_fragments = state.get("component_fragments", {})

    skeleton = deepcopy(state.get("skeleton_blueprint", {}))
    skeleton_changed = False
    skeleton_geometry = skeleton.get("geometry", {})
    for bucket in ("elements", "components"):
        items = skeleton_geometry.get(bucket, [])
        new_items = []
        for item in items:
            entity_id = item.get("id") if isinstance(item, dict) else None
            if entity_id in candidate_entities:
                new_items.append(deepcopy(candidate_entities[entity_id]))
                skeleton_changed = True
            elif entity_id in changed_ids:
                # changed_ids 中不存在于 candidate 的实体已被受限 remove_entity 删除。
                skeleton_changed = True
            else:
                new_items.append(item)
        if skeleton_changed:
            skeleton_geometry[bucket] = new_items
    existing_skeleton_ids = {
        item.get("id")
        for bucket in ("elements", "components")
        for item in skeleton_geometry.get(bucket, [])
        if isinstance(item, dict) and item.get("id")
    }
    candidate_element_ids = {
        item.get("id")
        for item in geometry.get("elements", [])
        if isinstance(item, dict) and item.get("id")
    }
    registered_types = {
        config.component_type for config in COMPONENT_REGISTRY.values()
        if config.implemented
    }
    for entity_id in changed_ids & candidate_element_ids:
        entity = candidate_entities[entity_id]
        if entity_id not in existing_skeleton_ids and entity.get("type") not in registered_types:
            skeleton_geometry.setdefault("elements", []).append(
                deepcopy(entity)
            )
            skeleton_changed = True
    if skeleton_changed:
        updates["skeleton_blueprint"] = skeleton

    for config in COMPONENT_REGISTRY.values():
        if not config.implemented:
            continue
        old_value = generic_fragments.get(config.component_type)
        matching_entities = [
            entity for entity in candidate_entities.values()
            if entity.get("type") == config.component_type
        ]
        if config.is_list:
            old_list = old_value if isinstance(old_value, list) else []
            new_value = []
            changed = False
            old_ids = {
                fragment.get("id") for fragment in old_list
                if isinstance(fragment, dict) and fragment.get("id")
            }
            for fragment in old_list:
                entity_id = fragment.get("id") if isinstance(fragment, dict) else None
                if entity_id in candidate_entities:
                    new_value.append(deepcopy(candidate_entities[entity_id]))
                    changed = True
                elif entity_id in changed_ids:
                    changed = True
                else:
                    new_value.append(fragment)
            for entity in matching_entities:
                if entity.get("id") not in old_ids:
                    new_value.append(deepcopy(entity))
                    changed = True
            if changed:
                fragment_updates[config.component_type] = new_value
        elif not config.is_list:
            if isinstance(old_value, dict) and old_value.get("id") in candidate_entities:
                fragment_updates[config.component_type] = deepcopy(candidate_entities[old_value["id"]])
            elif isinstance(old_value, dict) and old_value.get("id") in changed_ids:
                fragment_updates[config.component_type] = None
            elif matching_entities:
                fragment_updates[config.component_type] = deepcopy(matching_entities[0])

    if fragment_updates:
        updates["component_fragments"] = fragment_updates

    return updates
