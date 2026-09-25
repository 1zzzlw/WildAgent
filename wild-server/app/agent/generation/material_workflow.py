"""生成分支的材质规划节点：AI 负责审美，解析器负责资产与物理约束。"""

from __future__ import annotations

import time

from loguru import logger

from app.agent.generation.material_plan import (
    ROLE_SPECS,
    compact_asset_catalog,
    material_role_specs,
    resolve_material_plan,
)
from app.agent.generation.materials import compact_procedural_catalog
from app.agent.prompts import build_material_plan_prompt
from app.agent.runtime import get_reasoning_callback
from app.agent.state import GenerationState
from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, merge_token_usage
from app.services.asset_storage import asset_storage
from app.utils.json_extractor import extract_json_object
async def material_planner(state: GenerationState) -> dict:
    started = time.time()
    architecture_plan = state.get("architecture_plan") or {}
    # 角色表一次定住：物件场景是 wood/metal/glass/stone/fabric/accent，
    # 建筑场景是原来的七个立面/结构角色。提示词与解析器用同一份，避免分叉。
    role_specs = material_role_specs(architecture_plan)
    object_scene = role_specs is not ROLE_SPECS
    manifests = asset_storage.list_manifests()
    catalog = compact_asset_catalog(manifests)
    procedural_materials_enabled = state.get("procedural_materials_enabled") is True
    procedural_catalog = compact_procedural_catalog() if procedural_materials_enabled else []
    raw_plan = None
    prompt = ""
    error = None
    token_usage = None
    skipped_llm = False
    recovery_diag = None
    callback = get_reasoning_callback()
    existing_material_plan = None
    design_document = state.get("design_document")
    if isinstance(design_document, dict):
        materials = (design_document.get("decisions") or {}).get("materials") or {}
        if isinstance(materials.get("resolved_plan"), dict):
            existing_material_plan = materials["resolved_plan"]

    # 确定性优先：没有任何可匹配的 PBR 资产时，LLM 的审美输出会被 ROLE_SPECS
    # 兜底与白名单几乎全部覆盖（只剩概念文案与颜色微调），不值得付出一次串行 LLM
    # 往返。此时直接走 resolve_material_plan(None, ...) 的确定性路径。
    if existing_material_plan is not None and state.get("design_material_refresh") is False:
        raw_plan = existing_material_plan
        skipped_llm = True
        logger.info("[material_plan] 修改未涉及材质，复用上一版受控材质方案")
    elif catalog:
        prompt = build_material_plan_prompt(
            architecture_plan,
            catalog,
            procedural_catalog,
            style_preference=state.get("style_preference"),
            object_scene=object_scene,
        )
        if callback:
            procedural_detail = "与程序化配方" if procedural_materials_enabled else ""
            await callback(
                "material_plan",
                f"正在根据{'物件' if object_scene else '建筑'}方案自动丰富材质语言，"
                f"并匹配 PBR 素材{procedural_detail}...\n",
            )
        try:
            llm_result = await invoke_llm(
                create_llm(enable_thinking=False, streaming=False),
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": state.get("user_message", "")},
                ],
            )
            raw_plan = extract_json_object(llm_result.content)
            token_usage = llm_result.token_usage
            if raw_plan is None:
                # 解析失败时做一次非思考定向格式恢复，避免偶发格式抖动丢弃材质意图。
                from app.llm.recovery import recover_single_json

                recovered, recovery_diag = await recover_single_json(
                    prompt,
                    str(state.get("user_message") or ""),
                    llm_result.content,
                    object_hint="包含 roles 数组的材质方案 JSON 对象",
                    extra_instruction=(
                        "- 顶层必须直接包含 roles 数组；\n"
                        "- 每个 role 只能使用白名单 assetId 或 proceduralPresetId。"
                    ),
                )
                if isinstance(recovered, dict):
                    raw_plan = recovered
                token_usage = merge_token_usage(
                    token_usage,
                    (recovery_diag or {}).get("token_usage"),
                )
                if raw_plan is not None:
                    logger.warning("[material_plan] 材质方案定向格式恢复成功")
        except Exception as exc:
            error = str(exc)
            logger.warning(f"[material_plan] 模型调用失败，使用受控回退材质: {exc}")
    else:
        skipped_llm = True
        logger.info(
            "[material_plan] 无可匹配 PBR 资产，跳过审美 LLM 调用，使用确定性材质方案"
        )

    plan = resolve_material_plan(
        raw_plan,
        manifests,
        architecture_plan,
        str(state.get("user_message") or ""),
        procedural_materials_enabled=procedural_materials_enabled,
        role_specs=role_specs,
    )
    resolved_design = state.get("resolved_design")
    if isinstance(design_document, dict):
        from app.design.repository import design_repository
        from app.design.resolver import attach_material_plan

        updated_document = attach_material_plan(design_document, plan)
        updated_document, resolved_design = design_repository.save(updated_document)
        design_document = updated_document.model_dump(mode="json")
    if callback:
        selected = [
            item for item in plan["roles"] if item.get("assetId")
        ]
        procedural_selected = [
            item for item in plan["roles"] if item.get("proceduralPresetId")
        ]
        await callback(
            "material_plan",
            f"材质方案已确定：{plan['concept']}；匹配 {len(selected)} 个 PBR 资产，"
            f"启用 {len(procedural_selected)} 个程序化配方。\n",
        )
    return {
        "material_plan": plan,
        "design_document": design_document,
        "resolved_design": resolved_design,
        "material_diag": {
            "catalog_count": len(catalog),
            "procedural_catalog_count": len(procedural_catalog),
            "selected_asset_count": len(plan["resolvedAssets"]),
            "selected_procedural_count": sum(
                1 for item in plan["roles"] if item.get("proceduralPresetId")
            ),
            "procedural_materials_enabled": procedural_materials_enabled,
            "rejected_asset_ids": plan["rejectedAssetIds"],
            "rejected_procedural_preset_ids": plan["rejectedProceduralPresetIds"],
            "used_fallback": raw_plan is None,
            "reused_previous": existing_material_plan is not None and state.get("design_material_refresh") is False,
            "skipped_llm": skipped_llm,
            "recovery": recovery_diag,
            "error": error,
            "token_usage": token_usage,
            "prompt_chars": len(prompt) if catalog else 0,
            "total_ms": int((time.time() - started) * 1000),
        },
    }
