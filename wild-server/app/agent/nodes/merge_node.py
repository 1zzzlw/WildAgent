"""
Layer 2: 分片合并节点

收集所有 Layer 1 产出的组件分片，合并为完整 Blueprint。
由 COMPONENT_REGISTRY 驱动，新增组件无需修改此文件。
"""
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.component_registry import COMPONENT_REGISTRY
from app.utils.fragment_merger import merge_fragments


async def merge_fragments_node(state: GenerationState) -> dict:
    """合并所有组件分片 —— 注册表驱动，无需手动枚举"""

    logger.info("[merge_fragments] 开始合并分片")

    skeleton = state.get("skeleton_blueprint")
    if not skeleton:
        logger.error("[merge_fragments] 骨架缺失，无法合并")
        return {"error": "骨架缺失，无法合并组件", "status": "failed"}

    # 从注册表遍历所有已实现的组件，收集分片
    fragments = []

    for comp_type, cfg in COMPONENT_REGISTRY.items():
        if not cfg.implemented:
            continue

        data = state.get(cfg.output_key)
        if not data:
            continue

        if cfg.is_list and isinstance(data, list):
            if data:
                fragments.extend(data)
                logger.info(f"[merge_fragments] 收集到 {len(data)} 个 {cfg.label}")
        elif not cfg.is_list and isinstance(data, dict):
            fragments.append(data)
            logger.info(f"[merge_fragments] 收集到 {cfg.label}")

    # 合并
    try:
        merged_blueprint = merge_fragments(skeleton, fragments)

        elements = merged_blueprint.get("geometry", {}).get("elements", [])
        components = merged_blueprint.get("geometry", {}).get("components", [])
        logger.info(
            f"[merge_fragments] 合并完成: "
            f"{len(elements)} elements, {len(components)} components"
        )

        return {"merged_blueprint": merged_blueprint}

    except Exception as e:
        logger.error(f"[merge_fragments] 合并失败: {e}")
        return {"error": f"分片合并失败: {str(e)}", "status": "failed"}
