"""生成分支的材质规划节点：AI 负责审美，解析器负责资产与物理约束。"""

from __future__ import annotations

import time

from loguru import logger

from .plan import (
    ROLE_SPECS,
    compact_asset_catalog,
    material_role_specs,
    named_material_roles,
    needs_material_design,
    resolve_material_plan,
)
from .recipes import compact_procedural_catalog
from app.agent.prompts import build_material_plan_prompt
from app.agent.runtime import get_reasoning_callback
from app.agent.state import GenerationState
from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, merge_token_usage
from app.services.asset_storage import asset_storage
from app.utils.json_extractor import extract_json_object


async def material_planner(state: GenerationState) -> dict:

    started = time.time()
    # 读取当前建筑方案，来自上一节点
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

    # P6-A：**"是否需要设计决策"与"是否有资产可匹配"是两个独立判断。**
    # 旧实现用 ``elif catalog:`` 把两者绑成一个条件—— 无纹理资产时，用户提了
    # 配色/材质要求也会被整段跳过，于是设计意图静默丢失。而合法参数材质
    # （baseColor / roughness / metallic）根本不需要贴图就能承载设计。
    needs_design, design_reason = needs_material_design(
        str(state.get("user_message") or ""),
        role_specs,
        has_catalog=bool(catalog),
        procedural_materials_enabled=procedural_materials_enabled,
    )
    if isinstance(design_document, dict):
        intent = (design_document.get("decisions") or {}).get("materials") or {}
        if intent.get("regions") or intent.get("keywords") or state.get("design_material_refresh") is True:
            needs_design, design_reason = True, "设计文档包含显式材质意图或要求刷新"
    if existing_material_plan is not None and state.get("design_material_refresh") is False:
        raw_plan = existing_material_plan
        skipped_llm = True
        #: 复用上一版 = 本轮**没有**重新做设计决策（没产生新的设计输出）。
        design_decided = False
        logger.info("[material_plan] 修改未涉及材质，复用上一版受控材质方案")
    elif needs_design:
        #: 本轮真的向模型要了材质设计（无论它成功还是失败）。
        design_decided = True
        prompt = build_material_plan_prompt(
            architecture_plan,
            catalog,
            procedural_catalog,
            style_preference=state.get("style_preference"),
            object_scene=object_scene,
        )
        if callback:
            procedural_detail = "与程序化配方" if procedural_materials_enabled else ""
            # 说清这轮**为什么**调模型：不是"有资产"，而是"有材质要设计"。
            await callback(
                "material_plan",
                f"正在根据{'物件' if object_scene else '建筑'}方案设计材质语言"
                f"（{design_reason}）"
                f"{'，并匹配 PBR 素材' if catalog else '（本机无可用贴图，走参数材质）'}"
                f"{procedural_detail}...\n",
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
        design_decided = False
        logger.info(f"[material_plan] 不需要材质设计决策（{design_reason}），用确定性材质方案")
    if design_decided and error:
        logger.warning(f"[material_plan] 需要材质设计但模型失败，本次意图未实现：{error}")

    plan = resolve_material_plan(
        raw_plan,
        manifests,
        architecture_plan,
        str(state.get("user_message") or ""),
        procedural_materials_enabled=procedural_materials_enabled,
        role_specs=role_specs,
    )
    # P6-A 第7 条：模型失败/未调用时，"哪些材质意图没实现"必须**明确**，
    # 不能让"回退到角色表"看起来像"本来就长这样"。判据 = 用户点名了哪些角色，
    # 而最终方案里这些角色的材质**与角色表逐字段相同**（说明设计没起作用）。
    unrealized_roles: list[str] = []
    if not design_decided:
        unrealized_roles = named_material_roles(
            str(state.get("user_message") or ""), role_specs,
        )
    resolved_design = state.get("resolved_design")
    role_repairs: list[str] = []
    if isinstance(design_document, dict):
        from app.design.repository import design_repository
        from app.design.resolver import attach_material_plan

        # 实例角色名归一（材质名 → 角色名 / 无对应则降级）在 attach 这一个收口点做，
        # 并把记录回给诊断账本。没有这一步，模型写 `metal` 会让图纸的引用完整性校验
        # 直接 raise，整轮生成终止在这里 —— 而编译器本来就能容忍这两种写法。
        updated_document = attach_material_plan(design_document, plan, role_repairs=role_repairs)
        updated_document, resolved_design = design_repository.save(updated_document)
        design_document = updated_document.model_dump(mode="json")
    for repair in role_repairs:
        logger.warning(f"[material_plan] 构件实例材质角色已归一：{repair}")
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
        # 材质方案本体
        "material_plan": plan,
        # 材质方案本体
        "design_document": design_document,
        # 更新后的可执行视图
        "resolved_design": resolved_design,
        # 诊断账本
        "material_diag": {
            "catalog_count": len(catalog),
            # P6-A：决策依据要出得来。"跳过了模型调用"原来只有一个 bool，
            # 看不出**为什么**跳过 —— 于是"没有材质要求"与"用户提了要求但被忽略"
            # 在账本里长得一模一样。
            "design_decided": design_decided,
            "design_reason": design_reason,
            "needs_material_design": needs_design,
            # 用户点名了材质/配色，但本轮没做设计决策 ⇒ 这些意图未实现。
            "unrealized_material_intents": unrealized_roles,
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
            # 实例材质角色名的归一记录（材质名换角色名 / 无对应已降级）。
            # 非空说明图纸里有过"看起来对、词表不对"的值，排查时先看这里。
            "instance_role_repairs": role_repairs,
            "token_usage": token_usage,
            "prompt_chars": len(prompt),
            "total_ms": int((time.time() - started) * 1000),
        },
    }
