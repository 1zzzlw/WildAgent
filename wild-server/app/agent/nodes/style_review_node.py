"""主体完成后的第二次人工确认：选择风格，再允许装饰装配。"""

from __future__ import annotations

from langgraph.types import interrupt

from app.agent.graph_state import GenerationState
from app.agent.plan2build.style_registry import style_registry


def style_review(state: GenerationState) -> dict:
    selected = str(state.get("style_package_id") or "")
    feedback = str(state.get("style_feedback") or "")
    if not selected:
        selected = style_registry.infer(f"{state.get('user_message', '')}\n{feedback}")
    packages = style_registry.recommend(
        f"{state.get('user_message', '')}\n{feedback}",
        state.get("architecture_plan"),
        include_id=selected,
    )
    decision = interrupt({
        "type": "style_review",
        "revision": int(state.get("style_revision") or 0),
        "selected_style_id": selected,
        "options": style_registry.public_options(packages),
    })
    action = str(decision.get("action") if isinstance(decision, dict) else "").lower()
    requested = str(decision.get("style_package_id") if isinstance(decision, dict) else "").lower()
    feedback = str(decision.get("feedback") if isinstance(decision, dict) else "").strip()
    available = {str(item["id"]) for item in style_registry.list()}
    if requested in available:
        selected = requested
    elif feedback:
        selected = style_registry.infer(feedback, default=selected)

    if action == "confirm" and selected in available:
        return {
            "style_review_status": "approved",
            "style_package_id": selected,
            "style_feedback": "",
        }
    return {
        "style_review_status": "revise",
        "style_package_id": selected,
        "style_feedback": feedback,
        "style_revision": int(state.get("style_revision") or 0) + 1,
    }


def route_style_review(state: GenerationState) -> str:
    return "decor_assembly" if state.get("style_review_status") == "approved" else "style_review"
