"""plan 策略：调模型定"做什么"，失败即降级为确定性策略。

对应《动态节点设计规划》§3.2。本模块是 plan 阶段**唯一**的模型调用点，职责边界很硬：

- 模型给的是**策略**（哪些构件、什么形态、为什么），不是条目、不是坐标；
- 归一化由程序完成（能力清单过滤、否定词、配额下限、阳台-栏杆去重），所以模型
  即使说了清单外的构件或自相矛盾，也不会污染计划；
- 模型调用失败 / 返回不可解析 / 返回空 → 直接走 ``deterministic_strategy``，把
  骨架节点已经给出的 ``suggested_components`` 当策略。**降级不是错误**：它让离线
  测试与模型故障时的行为都可预期。
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from app.agent.generation.components import (
    get_implemented_components,
    resolve_component_suggestions,
)
from app.agent.plan.contracts import PlanKindStrategy, PlanStrategy
from app.agent.generation.slot_utils import slot_batch_summary, slot_counts
from app.agent.prompts import build_plan_strategy_prompt, build_plan_strategy_user_message
from app.llm.client import create_llm
from app.llm.errors import classify_model_error
from app.llm.invocation import invoke_llm, merge_token_usage
from app.utils.json_extractor import extract_json_object

#: 档位名闭集，与 ``plan.expand.DETAIL_BUDGET`` 保持一致（从那里导入会成环，故复制）。
_DETAIL_LEVELS = ("minimal", "simple", "standard", "detailed")


def capability_catalog() -> list[dict]:
    """可派发能力清单：策略提示词里"能做哪些构件"的唯一来源。"""

    return [
        {
            "kind": config.component_type,
            "label": config.label,
            "depends_on": list(config.dependencies),
            "is_element": config.is_element,
            "skip_keywords": list(config.skip_keywords),
        }
        for config in get_implemented_components()
    ]


def _quota(state: dict[str, Any]) -> dict:
    design_brief = state.get("design_brief")
    if isinstance(design_brief, dict) and isinstance(design_brief.get("component_quota"), dict):
        return design_brief["component_quota"]
    return {}


def normalize_kinds(
    raw_kinds: Any,
    state: dict[str, Any],
    *,
    include_quota: bool = True,
) -> list[PlanKindStrategy]:
    """把模型给的构件列表归一化为可派发策略（这是**安全边界**，不是格式美化）。

    ``include_quota=False`` 只做过滤、不补配额构件——解析阶段需要先判断"模型自己"
    有没有给出可用构件，才能决定该不该降级。
    """

    entries: list[PlanKindStrategy] = []
    seen: set[str] = set()
    for raw in raw_kinds if isinstance(raw_kinds, list) else []:
        if isinstance(raw, dict):
            kind = str(raw.get("kind") or raw.get("type") or "").strip()
            subtype = str(raw.get("subtype") or "").strip()
            guidance = str(raw.get("guidance") or "").strip()
            reason = str(raw.get("reason") or "").strip()
            execution_mode = str(raw.get("execution_mode") or "serial").strip()
            parallel_group = str(raw.get("parallel_group") or "").strip()[:64]
            batch_reason = str(raw.get("batch_reason") or "").strip()
        else:
            kind, subtype, guidance, reason = str(raw).strip(), "", "", ""
            execution_mode, parallel_group, batch_reason = "serial", "", ""
        if not kind or kind in seen:
            continue
        seen.add(kind)
        entries.append(
            PlanKindStrategy(
                kind=kind,
                subtype=subtype,
                guidance=guidance,
                reason=reason,
                execution_mode=(
                    "parallel"
                    if execution_mode == "parallel" and parallel_group
                    else "serial"
                ),
                parallel_group=parallel_group if execution_mode == "parallel" else "",
                batch_reason=batch_reason,
            )
        )

    # 既有策略统一在这里生效：未知/未实现构件被丢弃，否定词生效，配额下限强制进入，
    # 阳台已内嵌栏杆时不再单独生成栏杆。
    allowed = resolve_component_suggestions(
        [entry.kind for entry in entries], state.get("user_message", ""), _quota(state)
    )
    allowed_set = set(allowed)
    kept = [entry for entry in entries if entry.kind in allowed_set]

    # 模型漏掉但配额要求 `min > 0` 的构件由程序补上："模型忘了"不能变成
    # "批准的数量没人做"。补进来的条目没有形态提示，理由如实写在 reason 里。
    if not include_quota:
        return kept
    present = {entry.kind for entry in kept}
    kept.extend(
        PlanKindStrategy(kind=kind, reason="设计清单配额下限要求")
        for kind in allowed
        if kind not in present
    )
    return _sanitize_parallel_groups(kept)


def _sanitize_parallel_groups(entries: list[PlanKindStrategy]) -> list[PlanKindStrategy]:
    """只保留至少两个、且不存在显式依赖关系的并发组。"""

    configs = {config.component_type: config for config in get_implemented_components()}
    groups: dict[str, list[PlanKindStrategy]] = {}
    for entry in entries:
        if entry.execution_mode == "parallel" and entry.parallel_group:
            groups.setdefault(entry.parallel_group, []).append(entry)

    safe_groups: set[str] = set()
    for group, members in groups.items():
        kinds = {member.kind for member in members}
        if len(members) < 2:
            continue
        if any(set(configs[member.kind].dependencies) & kinds for member in members):
            continue
        safe_groups.add(group)

    normalized: list[PlanKindStrategy] = []
    for entry in entries:
        copied = entry.model_copy(deep=True)
        if copied.parallel_group not in safe_groups:
            copied.execution_mode = "serial"
            copied.parallel_group = ""
        normalized.append(copied)
    return normalized


def deterministic_strategy(state: dict[str, Any]) -> PlanStrategy:
    """降级策略：用骨架节点已经给出的建议（它本身就是模型的策略输出）。"""

    kinds = resolve_component_suggestions(
        list(state.get("suggested_components") or []),
        state.get("user_message", ""),
        _quota(state),
    )
    if not kinds:
        kinds = resolve_component_suggestions([], state.get("user_message", ""), _quota(state))
    return PlanStrategy(
        kinds=[PlanKindStrategy(kind=kind, reason="骨架建议") for kind in kinds],
        source="deterministic",
    )


def parse_strategy(raw: Any, state: dict[str, Any]) -> PlanStrategy | None:
    """解析模型输出；拿不到任何可用构件时返回 ``None``（交给降级路径）。"""

    if isinstance(raw, list):
        raw = {"kinds": raw}
    if not isinstance(raw, dict):
        return None
    # 先看"模型自己"给出了什么：一条可用构件都没有就交给降级路径，
    # 这样诊断里的 strategy_source 不会把程序补的配额构件算成模型的功劳。
    if not normalize_kinds(raw.get("kinds"), state, include_quota=False):
        return None
    kinds = normalize_kinds(raw.get("kinds"), state)
    level = raw.get("detail_level")
    return PlanStrategy(
        kinds=kinds,
        detail_level=level if isinstance(level, str) and level in _DETAIL_LEVELS else None,
        notes=str(raw.get("notes") or "")[:500],
        source="llm",
    )


async def request_plan_strategy(
    state: dict[str, Any],
    *,
    llm=None,
) -> tuple[PlanStrategy, dict[str, Any]]:
    """调用模型产出策略，返回 ``(策略, 诊断)``。

    两条失败路径必须分清：

    - **模型调不通**（额度/鉴权/超时/限流）：与其他节点一致，诊断带
      ``terminal_model_error``，由 ``plan_node`` 终止整轮——服务坏掉时不该继续烧 3 次
      尝试去生成每个构件。
    - **模型调通了但输出不可用**（无法解析 / 空策略）：降级为确定性策略，如实记录
      ``used_fallback`` 与 ``fallback_reason``。“想不出计划”不该让用户拿不到建筑。
    """

    started = time.perf_counter()
    catalog = capability_catalog()
    if not catalog:
        strategy = PlanStrategy(source="deterministic", notes="无可派发能力")
        return strategy, {"catalog_count": 0, "used_fallback": True,
                          "fallback_reason": "无可派发能力", "total_ms": 0}

    design_brief = state.get("design_brief")
    detail_level = _resolve_level(state)
    prompt = build_plan_strategy_prompt(
        capability_catalog=catalog,
        design_brief=design_brief,
        skeleton_summary=str(state.get("skeleton_summary") or ""),
        detail_level=detail_level,
        slot_counts=slot_counts(design_brief),
        slot_batches=slot_batch_summary(design_brief),
        architecture_plan=(
            state.get("architecture_plan")
            if isinstance(state.get("architecture_plan"), dict)
            else None
        ),
    )
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": build_plan_strategy_user_message(
                str(state.get("user_message") or ""), design_brief
            ),
        },
    ]

    raw = None
    error = None
    token_usage = None
    llm_ms = 0
    try:
        llm_t0 = time.perf_counter()
        # Plan 是受控分类与分组，不是建筑方案创作。仍由大模型决策，但关闭扩展思考，
        # 避免把能力清单和配额逐字复述几十秒；可观察性由 plan_node 的输入/结果摘要承担。
        model = llm or create_llm(enable_thinking=False, streaming=False)
        llm_result = await invoke_llm(model, messages)
        llm_ms = int((time.perf_counter() - llm_t0) * 1000)
        token_usage = llm_result.token_usage
        raw = extract_json_object(llm_result.content)
        if raw is None:
            from app.llm.recovery import recover_single_json

            recovered, recovery_diag = await recover_single_json(
                prompt,
                str(state.get("user_message") or ""),
                llm_result.content,
                object_hint="包含 kinds 数组的策略 JSON 对象",
                extra_instruction=(
                    "- 顶层必须直接包含 kinds 数组；\n"
                    "- kind 只能取能力清单里的值。"
                ),
            )
            token_usage = merge_token_usage(
                token_usage, (recovery_diag or {}).get("token_usage")
            )
            raw = recovered if isinstance(recovered, dict) else None
    except Exception as exc:
        model_error = classify_model_error(exc)
        logger.warning(f"[plan] 策略模型不可用，终止本轮: {exc}")
        return (
            PlanStrategy(source="fallback"),
            {
                "catalog_count": len(catalog),
                "detail_level": detail_level,
                "strategy_source": "fallback",
                "kinds": [],
                "used_fallback": False,
                "fallback_reason": None,
                "prompt_chars": len(prompt),
                "llm_ms": int((time.perf_counter() - started) * 1000),
                "token_usage": None,
                "error": str(exc),
                "model_error": model_error,
                "terminal_model_error": model_error,
                "total_ms": int((time.perf_counter() - started) * 1000),
            },
        )

    strategy = parse_strategy(raw, state) if raw is not None else None
    fallback_reason: str | None = None
    if strategy is None:
        fallback_reason = error or (
            "模型返回不可解析" if raw is None else "模型未给出可用构件"
        )
        strategy = deterministic_strategy(state)
        strategy.source = "fallback"
        logger.info(f"[plan] 使用确定性策略（{fallback_reason}）：{[k.kind for k in strategy.kinds]}")

    diag = {
        "catalog_count": len(catalog),
        "detail_level": detail_level,
        "strategy_source": strategy.source,
        "kinds": [entry.kind for entry in strategy.kinds],
        "notes": strategy.notes,
        "used_fallback": strategy.source != "llm",
        "reasoning_mode": "concise_structured",
        "fallback_reason": fallback_reason,
        "prompt_chars": len(prompt),
        "llm_ms": llm_ms,
        "token_usage": token_usage,
        "error": error,
        "total_ms": int((time.perf_counter() - started) * 1000),
    }
    return strategy, diag


def _resolve_level(state: dict[str, Any]) -> str:
    from app.agent.plan.expand import resolve_detail_level

    return resolve_detail_level(state)


__all__ = [
    "capability_catalog",
    "deterministic_strategy",
    "normalize_kinds",
    "parse_strategy",
    "request_plan_strategy",
    "slot_counts",
    "slot_batch_summary",
]
