"""分片合并工具：将骨架与组件分片合并为完整 Blueprint。"""
from copy import deepcopy


def merge_fragments(skeleton: dict, fragments: list[dict]) -> dict:
    """
    将骨架 Blueprint + 多个组件分片合并为完整 Blueprint

    Args:
        skeleton: Layer 0 生成的骨架 Blueprint
        fragments: Layer 1 各节点生成的组件分片列表

    Returns:
        合并后的完整 Blueprint
    """
    blueprint = deepcopy(skeleton)
    elements = blueprint.setdefault("geometry", {}).setdefault("elements", [])
    components = blueprint["geometry"].setdefault("components", [])

    # 收集已有的 ID，用于冲突检测
    used_ids = {el.get("id") for el in elements if el.get("id")}

    for fragment in fragments:
        if not fragment:
            continue

        # 如果分片是列表，直接追加到 components
        if isinstance(fragment, list):
            for item in fragment:
                _insert_item(item, components, elements, used_ids)

        # 如果分片是单个对象（如 roof）
        elif isinstance(fragment, dict):
            _insert_item(fragment, components, elements, used_ids)

    blueprint["geometry"]["elements"] = elements
    blueprint["geometry"]["components"] = components

    return blueprint


def _insert_item(item: dict, components: list, elements: list, used_ids: set):
    """插入一个元素或组件，处理 ID 冲突"""
    item_type = item.get("type", "")
    item_id = item.get("id")
    if not item_id:
        return

    # ID 冲突检测：自动加后缀
    if item_id in used_ids:
        original_id = item_id
        suffix = 1
        while f"{original_id}_{suffix}" in used_ids:
            suffix += 1
        item_id = f"{original_id}_{suffix}"
        item["id"] = item_id

    used_ids.add(item_id)

    # roof 写入 elements，其他写入 components
    if item_type == "roof":
        elements.append(item)
    else:
        components.append(item)
