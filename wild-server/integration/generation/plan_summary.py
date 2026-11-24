"""执行计划的交付清单投影。"""
from loguru import logger


def _plan_delivery_summary(plan_payload: object) -> dict:
    """交付清单：四个终态的计数 + 未完成条目（含能力缺失说明）。

    没有这条记录，交付就只能回答"成没成"，回答不了"哪几条没做成、为什么"——而后者
    正是 plan 驱动链存在的理由之一（《动态节点设计规划》§6.4）。
    """

    if not isinstance(plan_payload, dict) or not plan_payload:
        return {}
    try:
        from agent.utils.planning.contracts import PlanDocument
        from agent.utils.planning.store import terminal_stats

        plan = PlanDocument.model_validate(plan_payload)
    except Exception as exc:  # 计划不合法时不影响交付，只是少一份清单
        logger.warning(f"交付清单生成失败: {exc}")
        return {}

    stats = terminal_stats(plan)
    items = [
        {
            "item_id": item.id,
            "label": item.label,
            "op": item.op,
            "kind": item.kind,
            "status": item.status,
            "notice": str(item.params.get("notice") or ""),
            "evidence": item.run.evidence[:300],
        }
        for item in plan.items
        if item.status != "done"
    ]
    return {
        **stats,
        "give_up": plan.give_up,
        "llm_calls": plan.llm_calls,
        "revision": plan.revision,
        "items": items,
    }
