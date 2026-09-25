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


def merge_fragment_batch(base: dict, fragments: list[dict]) -> dict:
    """增量合并：按 ``(id, type)`` **先删后插**，其余元素原样保留。

    与 :func:`merge_fragments` 只差一件事：同一条目重跑时**替换**而不是追加（§4.4 幂等）。

    没有这一条，重试会产出重复门窗——而配额检查只查区间、不查重复，重复会悄悄溜过验收。
    保留 ``base`` 里其它元素则是因为：批次合并只能动自己那一组，不能把收尾阶段做的
    去重、配额强制、槽位吸附成果一起抹掉，也不能删掉骨架自带的屋顶等主体元素。
    """

    blueprint = deepcopy(base)
    geometry = blueprint.setdefault("geometry", {})
    elements = geometry.setdefault("elements", [])
    components = geometry.setdefault("components", [])

    incoming: list[dict] = []
    for fragment in fragments:
        if not fragment:
            continue
        if isinstance(fragment, list):
            incoming.extend(item for item in fragment if isinstance(item, dict))
        elif isinstance(fragment, dict):
            incoming.append(fragment)

    # 先把"本次要重插的 (id, type)"从蓝图里摘掉，再插入：这样重跑同一批得到同一份蓝图。
    stale = {
        (item.get("id"), item.get("type"))
        for item in incoming
        if item.get("id")
    }
    if stale:
        geometry["elements"] = [
            item for item in elements if (item.get("id"), item.get("type")) not in stale
        ]
        geometry["components"] = [
            item for item in components if (item.get("id"), item.get("type")) not in stale
        ]
        elements = geometry["elements"]
        components = geometry["components"]

    used_ids = {item.get("id") for item in elements if item.get("id")}
    used_ids |= {item.get("id") for item in components if item.get("id")}
    for item in incoming:
        # 浅拷贝：_insert_item 只改顶层 id，不能改到 state 里的分片本体。
        _insert_item(dict(item), components, elements, used_ids)

    geometry["elements"] = elements
    geometry["components"] = components
    return blueprint


def _is_element_type(item_type: str) -> bool:
    """该构件类型是否写入 `geometry.elements`。

    判定必须取自注册表的 `is_element`，**不能按类型名硬编码**：这里原本写的是
    `item_type == "roof"`，于是家具（同样是 element 类型）被并进了
    `geometry.components`，而 `plan/reconcile` 的对账与组件校验都按 `is_element`
    去 `elements` 里找——条目永远判不到"产物已落地"，会一直重试到放弃，
    用户拿到的家具在错误的分组里。这类"合并在 A 桶、验收看 B 桶"的错位
    不会报错，只会静默地把成果算丢。

    注册表不可用时退回 `roof`，保持与历史行为一致。
    """

    try:
        from app.agent.generation.components import COMPONENT_REGISTRY

        config = COMPONENT_REGISTRY.get(item_type)
        if config is not None:
            return bool(config.is_element)
    except Exception:  # pragma: no cover - 注册表不可用时按历史行为
        pass
    return item_type == "roof"


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

    # 无宿主的主体类构件进 elements，挂墙/挂板的组合构件进 components。
    if _is_element_type(str(item_type)):
        elements.append(item)
    else:
        components.append(item)
