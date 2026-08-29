"""平面方案人工审核节点：确认前暂停，修改后回到独立平面设计节点。"""

from __future__ import annotations

from langgraph.types import interrupt

from app.agent.graph_state import GenerationState
from app.agent.spatial_plan import is_confirmable_spatial_plan


MAX_AUTOMATIC_RULE_REVISIONS = 2


def floor_plan_review(state: GenerationState) -> dict:
    """等待用户确认或提交修改意见，绝不在未确认时进入三维生成。"""

    floor_plan = state.get("floor_plan") or {}
    revision = int(state.get("floor_plan_revision") or 0)
    can_confirm = is_confirmable_spatial_plan(
        floor_plan,
        state.get("floor_plan_validation"),
    )
    validation = [
        item for item in (state.get("floor_plan_validation") or [])
        if isinstance(item, dict)
    ]
    rule_failures = [
        item for item in validation
        if str(item.get("code") or "").startswith("rule_")
    ]
    geometry_failures = [item for item in validation if item not in rule_failures]
    automatic_count = int(state.get("floor_plan_auto_repair_count") or 0)
    history = list(state.get("floor_plan_review_history") or [])

    # 预审结果已经包含具体实测原因，先让平面节点自行修改，不要求用户点击重试。
    # 最多两轮，防止模型对不可兼容约束反复生成并触发 LangGraph 递归上限。
    if (
        not can_confirm
        and rule_failures
        and not geometry_failures
        and automatic_count < MAX_AUTOMATIC_RULE_REVISIONS
    ):
        feedback = "工程预审未通过，系统正在自动修改：" + "；".join(
            str(item.get("message") or item.get("code")) for item in rule_failures[:6]
        ) + "。请自动调整平面，并保持已经通过的几何关系不变。"
        history.append({
            "revision": revision,
            "action": "auto_revise",
            "feedback": feedback,
        })
        return {
            "floor_plan_review_status": "revise",
            "floor_plan_feedback": feedback,
            "floor_plan_revision": revision + 1,
            "floor_plan_auto_repair_count": automatic_count + 1,
            "floor_plan_auto_repairing": True,
            "floor_plan_review_history": history,
        }

    decision = interrupt({
        "type": "floor_plan_review",
        "revision": revision,
        "can_confirm": can_confirm,
        "fallback_reason": floor_plan.get("fallback_reason", ""),
    })
    action = str(decision.get("action") if isinstance(decision, dict) else "").lower()
    feedback = str(
        decision.get("feedback") if isinstance(decision, dict) else ""
    ).strip()

    if action == "confirm" and can_confirm:
        history.append({"revision": revision, "action": "confirm"})
        return {
            "floor_plan_review_status": "approved",
            "floor_plan_feedback": "",
            "floor_plan_auto_repairing": False,
            "floor_plan_review_history": history,
        }

    if action != "revise" or not feedback:
        if not can_confirm and rule_failures:
            feedback = "当前几何方案可预览，但工程预审未通过：" + "；".join(
                str(item.get("message") or item.get("code")) for item in rule_failures[:6]
            ) + "。请针对这些实测问题调整平面。"
        elif not can_confirm:
            feedback = (
                "当前方案仍是安全降级轮廓，缺少可确认的完整空间与门窗；"
                "请重新生成可通过平面校验的完整方案。"
            )
        else:
            feedback = "请根据现有方案重新检查并完善空间、墙体和门窗关系。"
    history.append({"revision": revision, "action": "revise", "feedback": feedback})
    return {
        "floor_plan_review_status": "revise",
        "floor_plan_feedback": feedback,
        "floor_plan_revision": revision + 1,
        "floor_plan_auto_repair_count": 0,
        "floor_plan_auto_repairing": False,
        "floor_plan_review_history": history,
    }


def route_floor_plan_review(state: GenerationState) -> str:
    """确认进入后续三维链路；修改则重新规划平面。"""

    return "material_plan" if state.get("floor_plan_review_status") == "approved" else "floor_plan_design"
