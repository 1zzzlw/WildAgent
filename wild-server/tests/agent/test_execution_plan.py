"""执行计划协议的纯逻辑回归测试，不依赖 LLM 或数据库。"""

from copy import deepcopy

from app.agent.execution_plan import (
    build_execution_plan,
    next_ready_step,
    plan_is_complete,
    reset_plan_from,
    update_plan_step,
    validate_execution_plan,
)


def _generate_plan() -> dict:
    return build_execution_plan(
        request_id="req_plan_test",
        intent="generate",
        user_message="生成一座高层玻璃幕墙商业综合体",
        architecture_plan={"concept": "商业基座与玻璃塔楼"},
        research_summary="已检索公共建筑与玻璃幕墙知识",
    )


def test_generate_plan_has_review_and_validation_gates() -> None:
    plan = _generate_plan()

    assert validate_execution_plan(plan, "generate") == []
    assert [step["type"] for step in plan["steps"]] == [
        "planning_research",
        "architecture",
        "floor_plan_design",
        "floor_plan_review",
        "material_plan",
        "skeleton",
        "style_review",
        "decor_assembly",
        "merge",
        "final_validate",
    ]
    floor_review = next(
        step for step in plan["steps"] if step["type"] == "floor_plan_review"
    )
    assert floor_review["requires_user_review"] is True
    assert "用户确认平面前不得生成三维" in plan["constraints"]


def test_tampered_node_is_rejected() -> None:
    plan = _generate_plan()
    plan["steps"][2]["node"] = "arbitrary_python_function"

    issues = validate_execution_plan(plan, "generate")

    assert any(issue["code"] == "plan_node_tampered" for issue in issues)


def test_next_ready_step_respects_dependencies() -> None:
    plan = _generate_plan()

    step = next_ready_step(plan)
    assert step is not None
    assert step["type"] == "floor_plan_design"

    plan = update_plan_step(plan, "floor_plan_design", "completed")
    assert next_ready_step(plan)["type"] == "floor_plan_review"


def test_floor_revision_resets_only_floor_and_downstream_steps() -> None:
    plan = _generate_plan()
    for step in plan["steps"]:
        plan = update_plan_step(plan, step["type"], "completed")

    revised = reset_plan_from(plan, "floor_plan_design")

    statuses = {step["type"]: step["status"] for step in revised["steps"]}
    assert statuses["planning_research"] == "completed"
    assert statuses["architecture"] == "completed"
    assert statuses["floor_plan_design"] == "pending"
    assert statuses["final_validate"] == "pending"


def test_edit_plan_is_read_only_until_patch_proposal() -> None:
    plan = build_execution_plan(
        request_id="req_edit_test",
        intent="edit",
        user_message="把入口门加宽",
        research_summary="已读取当前场景",
    )

    assert validate_execution_plan(plan, "edit") == []
    assert [step["type"] for step in plan["steps"]] == [
        "planning_research",
        "patch",
    ]
    assert plan["steps"][1]["requires_user_review"] is True
    assert plan_is_complete(plan) is False


def test_missing_required_step_is_rejected() -> None:
    plan = deepcopy(_generate_plan())
    plan["steps"] = [step for step in plan["steps"] if step["type"] != "final_validate"]

    issues = validate_execution_plan(plan, "generate")

    assert any(issue["code"] == "missing_required_plan_step" for issue in issues)
